"""Read-only residue audit for one isolated Phase 3 comparison dev run."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.storage.postgres import connect_postgres


SCHEMA_VERSION = "phase3_comparison_cleanup_audit_v1"
EXPECTED_BACKENDS = frozenset(
    {"elasticsearch_chunks", "milvus_vectors", "runtime_snapshot"}
)
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")


class CleanupAuditError(RuntimeError):
    """Stable, non-secret read-only audit failure."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit one Phase 3 comparison run without mutating any state"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _validate_output(path: Path) -> Path:
    if path.is_absolute():
        raise CleanupAuditError("AUDIT_OUTPUT_PATH_INVALID")
    resolved = (Path.cwd() / path).resolve()
    runtime_root = (Path.cwd() / "runtime").resolve()
    if not resolved.is_relative_to(runtime_root) or resolved.suffix != ".json":
        raise CleanupAuditError("AUDIT_OUTPUT_PATH_INVALID")
    return resolved


def _require_loopback_database(database_url: str) -> None:
    parsed = urlparse(database_url)
    if parsed.scheme != "postgresql" or parsed.hostname not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        raise CleanupAuditError("DATABASE_URL_NOT_LOOPBACK_POSTGRESQL")


def _rows(connection: Any, query: str, owner_id: str) -> tuple[dict[str, Any], ...]:
    with connection.cursor() as cursor:
        cursor.execute(query, (owner_id,))
        return tuple(dict(row) for row in cursor.fetchall())


def _global_rows(connection: Any, query: str) -> tuple[dict[str, Any], ...]:
    with connection.cursor() as cursor:
        cursor.execute(query)
        return tuple(dict(row) for row in cursor.fetchall())


def _count(connection: Any, table: str, owner_id: str) -> int:
    if table not in {"rag_chunks", "rag_pdf_objects"}:
        raise CleanupAuditError("AUDIT_TABLE_NOT_ALLOWED")
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*)::integer AS row_count FROM {table} WHERE owner_id = %s",
            (owner_id,),
        )
        row = cursor.fetchone()
    return int(row["row_count"])


def collect_snapshot(connection: Any, owner_id: str) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )

    versions = _rows(
        connection,
        """
        SELECT lifecycle_status, is_active, COUNT(*)::integer AS row_count
        FROM rag_document_versions
        WHERE owner_id = %s
        GROUP BY lifecycle_status, is_active
        ORDER BY lifecycle_status, is_active
        """,
        owner_id,
    )
    ingestion_jobs = _rows(
        connection,
        """
        SELECT status, failure_code, COUNT(*)::integer AS row_count
        FROM rag_ingestion_jobs
        WHERE owner_id = %s
        GROUP BY status, failure_code
        ORDER BY status, failure_code
        """,
        owner_id,
    )
    cleanup_jobs = _rows(
        connection,
        """
        SELECT backend, status, failure_code, COUNT(*)::integer AS row_count
        FROM rag_index_cleanup_jobs
        WHERE owner_id = %s
        GROUP BY backend, status, failure_code
        ORDER BY backend, status, failure_code
        """,
        owner_id,
    )
    global_nonterminal_cleanup_jobs = _global_rows(
        connection,
        """
        SELECT backend, status, failure_code, COUNT(*)::integer AS row_count
        FROM rag_index_cleanup_jobs
        WHERE status IN ('PENDING', 'RUNNING', 'RETRY')
        GROUP BY backend, status, failure_code
        ORDER BY backend, status, failure_code
        """,
    )
    return {
        "versions": versions,
        "ingestion_jobs": ingestion_jobs,
        "cleanup_jobs": cleanup_jobs,
        "global_nonterminal_cleanup_jobs": global_nonterminal_cleanup_jobs,
        "chunk_rows": _count(connection, "rag_chunks", owner_id),
        "pdf_object_rows": _count(connection, "rag_pdf_objects", owner_id),
    }


def _sum_rows(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(int(row["row_count"]) for row in rows)


def evaluate_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    versions = tuple(snapshot["versions"])
    ingestion_jobs = tuple(snapshot["ingestion_jobs"])
    cleanup_jobs = tuple(snapshot["cleanup_jobs"])
    global_nonterminal_cleanup_jobs = tuple(
        snapshot["global_nonterminal_cleanup_jobs"]
    )
    version_count = _sum_rows(versions)
    ingestion_job_count = _sum_rows(ingestion_jobs)
    cleanup_job_count = _sum_rows(cleanup_jobs)
    active_version_count = sum(
        int(row["row_count"]) for row in versions if bool(row["is_active"])
    )
    noninactive_version_count = sum(
        int(row["row_count"])
        for row in versions
        if row["lifecycle_status"] != "INACTIVE"
    )
    nonterminal_ingestion_job_count = sum(
        int(row["row_count"])
        for row in ingestion_jobs
        if row["status"] not in {"SUCCEEDED", "FAILED"}
    )
    nonterminal_cleanup_job_count = sum(
        int(row["row_count"])
        for row in cleanup_jobs
        if row["status"] != "SUCCEEDED"
    )
    global_nonterminal_cleanup_job_count = _sum_rows(
        global_nonterminal_cleanup_jobs
    )
    observed_backends = {
        str(row["backend"]) for row in cleanup_jobs if int(row["row_count"]) > 0
    }
    chunk_rows = int(snapshot["chunk_rows"])
    pdf_object_rows = int(snapshot["pdf_object_rows"])

    no_rows = (
        version_count == 0
        and ingestion_job_count == 0
        and cleanup_job_count == 0
        and chunk_rows == 0
        and pdf_object_rows == 0
        and global_nonterminal_cleanup_job_count == 0
    )
    completed_cleanup = (
        version_count > 0
        and active_version_count == 0
        and noninactive_version_count == 0
        and ingestion_job_count == version_count
        and nonterminal_ingestion_job_count == 0
        and cleanup_job_count == 3 * version_count
        and nonterminal_cleanup_job_count == 0
        and observed_backends == EXPECTED_BACKENDS
        and chunk_rows == 0
        and pdf_object_rows == 0
        and global_nonterminal_cleanup_job_count == 0
    )
    clean = no_rows or completed_cleanup
    return {
        "status": "PASS" if clean else "FAIL",
        "decision": "CLEAN" if clean else "RESIDUAL_REQUIRES_RECOVERY_GATE",
        "error_code": None if clean else "PHASE3_COMPARISON_RESIDUAL_STATE",
        "summary": {
            "version_count": version_count,
            "active_version_count": active_version_count,
            "noninactive_version_count": noninactive_version_count,
            "ingestion_job_count": ingestion_job_count,
            "nonterminal_ingestion_job_count": nonterminal_ingestion_job_count,
            "cleanup_job_count": cleanup_job_count,
            "nonterminal_cleanup_job_count": nonterminal_cleanup_job_count,
            "global_nonterminal_cleanup_job_count": (
                global_nonterminal_cleanup_job_count
            ),
            "cleanup_backends": sorted(observed_backends),
            "chunk_rows": chunk_rows,
            "pdf_object_rows": pdf_object_rows,
        },
    }


def build_report(run_id: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_snapshot(snapshot)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "owner_scope": f"phase3_comparison_canary_{run_id}",
        "read_only": True,
        **result,
        "groups": {
            "versions": snapshot["versions"],
            "ingestion_jobs": snapshot["ingestion_jobs"],
            "cleanup_jobs": snapshot["cleanup_jobs"],
            "global_nonterminal_cleanup_jobs": (
                snapshot["global_nonterminal_cleanup_jobs"]
            ),
        },
        "proof_boundary": {
            "postgresql_queried": True,
            "elasticsearch_queried": False,
            "milvus_queried": False,
            "services_restarted": False,
            "state_mutated": False,
            "test_read_or_run": False,
            "acceptance_read_or_run": False,
            "quality_rerun_authorized": False,
            "physical_absence_interpretation": (
                "DURABLE_SUCCEEDED_CLEANUP_JOBS_AND_ZERO_RUNTIME_SNAPSHOT_ROWS_ONLY"
            ),
        },
    }


def _error_report(run_id: str, error_code: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "read_only": True,
        "status": "ERROR",
        "decision": "AUDIT_NOT_COMPLETED",
        "error_code": error_code,
        "proof_boundary": {
            "state_mutated": False,
            "test_read_or_run": False,
            "acceptance_read_or_run": False,
            "quality_rerun_authorized": False,
        },
    }


def main() -> int:
    args = build_parser().parse_args()
    run_id = args.run_id
    output: Path | None = None
    connection: Any | None = None
    report: dict[str, Any]
    exit_code = 2
    try:
        if not _RUN_ID.fullmatch(run_id):
            raise CleanupAuditError("RUN_ID_INVALID")
        output = _validate_output(args.output)
        database_url = os.environ.get("DATABASE_URL", "")
        _require_loopback_database(database_url)
        connection = connect_postgres(database_url)
        snapshot = collect_snapshot(
            connection,
            f"phase3_comparison_canary_{run_id}",
        )
        report = build_report(run_id, snapshot)
        exit_code = 0 if report["status"] == "PASS" else 1
    except CleanupAuditError as exc:
        report = _error_report(run_id, str(exc))
    except BaseException:
        report = _error_report(run_id, "CLEANUP_AUDIT_FAILED")
    finally:
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()

    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
