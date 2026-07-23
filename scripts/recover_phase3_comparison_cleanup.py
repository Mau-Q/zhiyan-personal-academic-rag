"""Recover one explicitly frozen Phase 3 pending cleanup queue once."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if not sys.path or Path(sys.path[0]).resolve() != REPOSITORY_ROOT:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.ingestion.cleanup import (
    PersistentIndexCleanupWorker,
    PersistentRuntimeSnapshotCleaner,
)
from backend.ingestion.elasticsearch_writer import ElasticsearchVersionIndexWriter
from backend.ingestion.milvus_writer import MilvusVersionIndexWriter
from backend.retrieval.elasticsearch import UrllibElasticsearchTransport
from backend.retrieval.embedding import OllamaEmbeddingProvider
from backend.retrieval.milvus import PymilvusTransport
from backend.storage.pdf_objects import FilesystemPdfObjectStore
from backend.storage.postgres import PostgresFactRepository, connect_postgres


SCHEMA_VERSION = "phase3_comparison_cleanup_recovery_v1"
CONFIRMATION = "RECOVER_EXACT_PHASE3_COMPARISON_02_CLEANUP"
FROZEN_RUN_ID = "phase3_comparison_dev_20260723_02"
EXPECTED_OWNER = f"phase3_comparison_canary_{FROZEN_RUN_ID}"
FROZEN_RECOVERY_CASES = {
    FROZEN_RUN_ID: {
        "confirmation": CONFIRMATION,
        "audit_sha256": (
            "a3fbddc29acaaab0e72edcd889f14a198f238f523a08588d5d486765999498cf"
        ),
    },
    "phase3_comparison_dev_20260723_03": {
        "confirmation": "RECOVER_EXACT_PHASE3_COMPARISON_03_CLEANUP",
        "audit_sha256": (
            "e9430be17811c60116630f718c182a3ffd0a12ffd83f753ebb5fdfba0420112b"
        ),
    },
}
EXPECTED_BACKENDS = {
    "elasticsearch_chunks",
    "milvus_vectors",
    "runtime_snapshot",
}
EXPECTED_VERSIONS = 3
EXPECTED_JOBS = 9
EXPECTED_CHUNKS = 316
EXPECTED_PDF_OBJECTS = 3
_GIT_COMMIT = re.compile(r"^[a-f0-9]{40}$")


class RecoveryError(RuntimeError):
    """Stable, sanitized recovery failure."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=FROZEN_RUN_ID)
    parser.add_argument("--expected-head-commit", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--pdf-object-root",
        type=Path,
        default=Path("runtime/phase3-comparison-pdf-objects"),
    )
    parser.add_argument(
        "--es-index-prefix",
        default="zhiyan-phase3-comparison-canary",
    )
    parser.add_argument(
        "--milvus-collection-prefix",
        default="zhiyan_phase3_comparison_canary",
    )
    return parser


def _runtime_path(path: Path, *, suffix: str | None = None) -> Path:
    if path.is_absolute():
        raise RecoveryError("RUNTIME_PATH_INVALID")
    resolved = (Path.cwd() / path).resolve()
    runtime_root = (Path.cwd() / "runtime").resolve()
    if not resolved.is_relative_to(runtime_root):
        raise RecoveryError("RUNTIME_PATH_INVALID")
    if suffix is not None and resolved.suffix != suffix:
        raise RecoveryError("RUNTIME_PATH_INVALID")
    return resolved


def _repository_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _loopback(name: str, value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https", "postgresql"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise RecoveryError(f"{name}_MUST_USE_LOOPBACK")
    return value


def _rows(
    connection: Any,
    query: str,
    params: tuple[Any, ...] = (),
) -> tuple[dict[str, Any], ...]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return tuple(dict(row) for row in cursor.fetchall())


def _count(connection: Any, table: str, owner_id: str) -> int:
    if table not in {
        "rag_chunks",
        "rag_pdf_objects",
        "rag_ingestion_jobs",
    }:
        raise RecoveryError("RECOVERY_TABLE_NOT_ALLOWED")
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*)::integer AS row_count FROM {table} WHERE owner_id = %s",
            (owner_id,),
        )
        row = cursor.fetchone()
    return int(row["row_count"])


def _snapshot(
    connection: Any,
    expected_owner: str = EXPECTED_OWNER,
) -> dict[str, Any]:
    versions = _rows(
        connection,
        """
        SELECT document_version_id, lifecycle_status, is_active
        FROM rag_document_versions
        WHERE owner_id = %s
        ORDER BY document_version_id
        """,
        (expected_owner,),
    )
    owner_cleanup = _rows(
        connection,
        """
        SELECT document_version_id, backend, status, attempt_count, failure_code
        FROM rag_index_cleanup_jobs
        WHERE owner_id = %s
        ORDER BY document_version_id, backend
        """,
        (expected_owner,),
    )
    global_nonterminal = _rows(
        connection,
        """
        SELECT owner_id, document_version_id, backend, status, attempt_count,
               failure_code
        FROM rag_index_cleanup_jobs
        WHERE status IN ('PENDING', 'RUNNING', 'RETRY')
        ORDER BY owner_id, document_version_id, backend
        """,
    )
    return {
        "versions": versions,
        "owner_cleanup": owner_cleanup,
        "global_nonterminal": global_nonterminal,
        "ingestion_job_count": _count(
            connection,
            "rag_ingestion_jobs",
            expected_owner,
        ),
        "chunk_rows": _count(connection, "rag_chunks", expected_owner),
        "pdf_object_rows": _count(
            connection,
            "rag_pdf_objects",
            expected_owner,
        ),
    }


def _summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    cleanup_statuses = Counter(row["status"] for row in snapshot["owner_cleanup"])
    cleanup_backends = Counter(row["backend"] for row in snapshot["owner_cleanup"])
    return {
        "version_count": len(snapshot["versions"]),
        "active_version_count": sum(
            1 for row in snapshot["versions"] if row["is_active"]
        ),
        "noninactive_version_count": sum(
            1
            for row in snapshot["versions"]
            if row["lifecycle_status"] != "INACTIVE"
        ),
        "ingestion_job_count": snapshot["ingestion_job_count"],
        "cleanup_job_count": len(snapshot["owner_cleanup"]),
        "cleanup_status_counts": dict(sorted(cleanup_statuses.items())),
        "cleanup_backend_counts": dict(sorted(cleanup_backends.items())),
        "global_nonterminal_cleanup_job_count": len(
            snapshot["global_nonterminal"]
        ),
        "chunk_rows": snapshot["chunk_rows"],
        "pdf_object_rows": snapshot["pdf_object_rows"],
    }


def _require_frozen_precondition(
    snapshot: dict[str, Any],
    expected_owner: str = EXPECTED_OWNER,
) -> None:
    version_ids = {
        row["document_version_id"] for row in snapshot["versions"]
    }
    expected_pairs = {
        (version_id, backend)
        for version_id in version_ids
        for backend in EXPECTED_BACKENDS
    }
    owner_pairs = {
        (row["document_version_id"], row["backend"])
        for row in snapshot["owner_cleanup"]
    }
    if (
        len(version_ids) != EXPECTED_VERSIONS
        or len(snapshot["versions"]) != EXPECTED_VERSIONS
        or any(
            row["lifecycle_status"] != "INACTIVE" or row["is_active"]
            for row in snapshot["versions"]
        )
        or snapshot["ingestion_job_count"] != EXPECTED_VERSIONS
        or len(snapshot["owner_cleanup"]) != EXPECTED_JOBS
        or owner_pairs != expected_pairs
        or any(
            row["status"] != "PENDING"
            or row["attempt_count"] != 0
            or row["failure_code"] is not None
            for row in snapshot["owner_cleanup"]
        )
        or len(snapshot["global_nonterminal"]) != EXPECTED_JOBS
        or any(
            row["owner_id"] != expected_owner
            for row in snapshot["global_nonterminal"]
        )
        or snapshot["chunk_rows"] != EXPECTED_CHUNKS
        or snapshot["pdf_object_rows"] != EXPECTED_PDF_OBJECTS
    ):
        raise RecoveryError("FROZEN_RECOVERY_PRECONDITION_MISMATCH")


def _postcondition_pass(snapshot: dict[str, Any]) -> bool:
    return (
        len(snapshot["versions"]) == EXPECTED_VERSIONS
        and all(
            row["lifecycle_status"] == "INACTIVE" and not row["is_active"]
            for row in snapshot["versions"]
        )
        and len(snapshot["owner_cleanup"]) == EXPECTED_JOBS
        and all(
            row["status"] == "SUCCEEDED"
            and row["failure_code"] is None
            for row in snapshot["owner_cleanup"]
        )
        and not snapshot["global_nonterminal"]
        and snapshot["chunk_rows"] == 0
        and snapshot["pdf_object_rows"] == 0
    )


def _error_report(
    *,
    run_id: str,
    expected_head_commit: str,
    audit_sha256: str | None,
    stage: str,
    error_code: str,
    precondition: dict[str, Any] | None,
    postcondition: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "expected_head_commit": expected_head_commit,
        "status": "FAIL",
        "stage": stage,
        "error_code": error_code,
        "precondition": precondition,
        "postcondition": postcondition,
        "proof_boundary": {
            "recovery_scope": "EXACT_EXISTING_NINE_CLEANUP_JOBS_ONLY",
            "quality_run": False,
            "test_read_or_run": False,
            "acceptance_read_or_run": False,
            "performance_gate_run": False,
            "services_restarted": False,
            "frozen_read_only_audit_sha256": audit_sha256,
        },
    }


def run_recovery(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    precondition: dict[str, Any] | None = None
    postcondition: dict[str, Any] | None = None
    connection: Any | None = None
    stage = "VALIDATE_INPUT"
    recovery_case: dict[str, str] | None = None
    try:
        recovery_case = FROZEN_RECOVERY_CASES.get(args.run_id)
        if recovery_case is None:
            raise RecoveryError("RECOVERY_RUN_ID_NOT_FROZEN")
        if args.confirm != recovery_case["confirmation"]:
            raise RecoveryError("RECOVERY_CONFIRMATION_REQUIRED")
        if (
            not _GIT_COMMIT.fullmatch(args.expected_head_commit)
            or _repository_head() != args.expected_head_commit
        ):
            raise RecoveryError("REPOSITORY_HEAD_MISMATCH")
        pdf_object_root = _runtime_path(args.pdf_object_root)
        database_url = _loopback("DATABASE_URL", os.environ["DATABASE_URL"])
        elasticsearch_url = _loopback(
            "ELASTICSEARCH_URL",
            os.environ.get("ELASTICSEARCH_URL", "http://127.0.0.1:9200"),
        )
        milvus_uri = _loopback(
            "MILVUS_URI",
            os.environ.get("MILVUS_URI", "http://127.0.0.1:19530"),
        )
        ollama_url = _loopback(
            "OLLAMA_URL",
            os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
        )

        connection = connect_postgres(database_url)
        stage = "VERIFY_FROZEN_PRECONDITION"
        expected_owner = f"phase3_comparison_canary_{args.run_id}"
        initial = _snapshot(connection, expected_owner)
        precondition = _summary(initial)
        _require_frozen_precondition(initial, expected_owner)
        connection.rollback()

        stage = "RUN_EXACT_CLEANUP_WORKER"
        repository = PostgresFactRepository(connection)
        worker = PersistentIndexCleanupWorker(
            repository=repository,
            elasticsearch=ElasticsearchVersionIndexWriter(
                index_prefix=args.es_index_prefix,
                transport=UrllibElasticsearchTransport(
                    base_url=elasticsearch_url,
                ),
            ),
            milvus=MilvusVersionIndexWriter(
                collection_prefix=args.milvus_collection_prefix,
                transport=PymilvusTransport(uri=milvus_uri),
                provider=OllamaEmbeddingProvider(
                    model=os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3:latest"),
                    base_url=ollama_url,
                ),
            ),
            runtime_snapshot=PersistentRuntimeSnapshotCleaner(
                repository=repository,
                pdf_objects=FilesystemPdfObjectStore(pdf_object_root),
            ),
        )
        results = worker.run_batch(max_jobs=EXPECTED_JOBS)

        stage = "VERIFY_POSTCONDITION"
        final = _snapshot(connection, expected_owner)
        postcondition = _summary(final)
        passed = (
            len(results) == EXPECTED_JOBS
            and all(result.succeeded for result in results)
            and _postcondition_pass(final)
        )
        report = {
            "schema_version": SCHEMA_VERSION,
            "run_id": args.run_id,
            "expected_head_commit": args.expected_head_commit,
            "status": "PASS" if passed else "FAIL",
            "stage": "COMPLETE" if passed else stage,
            "error_code": None if passed else "RECOVERY_POSTCONDITION_FAILED",
            "jobs_observed": len(results),
            "jobs_succeeded": sum(result.succeeded for result in results),
            "precondition": precondition,
            "postcondition": postcondition,
            "proof_boundary": {
                "recovery_scope": "EXACT_EXISTING_NINE_CLEANUP_JOBS_ONLY",
                "quality_run": False,
                "test_read_or_run": False,
                "acceptance_read_or_run": False,
                "performance_gate_run": False,
                "services_restarted": False,
                "frozen_read_only_audit_sha256": recovery_case["audit_sha256"],
            },
        }
        connection.rollback()
        return report, 0 if passed else 1
    except KeyError:
        error_code = "DATABASE_URL_REQUIRED"
    except RecoveryError as exc:
        error_code = str(exc)
    except BaseException:
        error_code = {
            "RUN_EXACT_CLEANUP_WORKER": "RECOVERY_WORKER_FAILED",
            "VERIFY_POSTCONDITION": "RECOVERY_POSTCONDITION_QUERY_FAILED",
        }.get(stage, "RECOVERY_FAILED")
    finally:
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()
    return (
        _error_report(
            run_id=args.run_id,
            expected_head_commit=args.expected_head_commit,
            audit_sha256=(
                recovery_case["audit_sha256"]
                if recovery_case is not None
                else None
            ),
            stage=stage,
            error_code=error_code,
            precondition=precondition,
            postcondition=postcondition,
        ),
        2,
    )


def main() -> int:
    args = build_parser().parse_args()
    output = _runtime_path(args.output, suffix=".json")
    report, exit_code = run_recovery(args)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
