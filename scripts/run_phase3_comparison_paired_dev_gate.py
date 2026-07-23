#!/usr/bin/env python3
"""Run one isolated Phase 3 Control/Treatment dev Gate on user-operated services."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if not sys.path or Path(sys.path[0]).resolve() != REPOSITORY_ROOT:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.ingestion.cleanup import (
    PersistentIndexCleanupScheduler,
    PersistentIndexCleanupWorker,
    PersistentRuntimeSnapshotCleaner,
)
from backend.ingestion.elasticsearch_writer import ElasticsearchVersionIndexWriter
from backend.ingestion.index_lifecycle import (
    InactivationReason,
    inactivate_and_schedule_cleanup,
    publish_prepared_indexes,
)
from backend.ingestion.milvus_writer import MilvusVersionIndexWriter
from backend.ingestion.persistent import prepare_and_persist_pdf_ingestion
from backend.retrieval.comparison_decomposition import (
    BilateralComparisonQueryDecomposer,
    load_bilateral_comparison_config,
    remap_document_identities,
)
from backend.retrieval.elasticsearch import UrllibElasticsearchTransport
from backend.retrieval.embedding import OllamaEmbeddingProvider
from backend.retrieval.milvus import PymilvusTransport
from backend.retrieval.online import (
    OnlineRetrievalLatencyBreakdown,
    OnlineVersionRrfRetriever,
    PostgresReadyRouteResolver,
)
from backend.storage.pdf_objects import FilesystemPdfObjectStore
from backend.storage.postgres import PostgresFactRepository, connect_postgres
from backend.validation.stage1 import Stage1ReconciliationError, reconcile_ready_scope
from scripts.build_phase3_comparison_dev_package import (
    ASSETS,
    SCHEMA_VERSION as INPUT_SCHEMA_VERSION,
    TARGET_IDS,
    TARGET_IDS_SHA256,
)


CONFIRMATION = "RUN_ISOLATED_PHASE3_COMPARISON_DEV_GATE"
REPORT_SCHEMA_VERSION = "phase3_comparison_paired_dev_report_v1"
CONFIG_PATH = Path(
    "evaluation/phase3/bilateral-comparison-query-decomposition-v1.json"
)
CONFIG_SHA256 = "87b969a1b0f006c3406ab01a24837c5ff129d08bedd0b2460a57122f9d0b0f2b"
EXPECTED_CLEANUP_JOBS = 9
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_GIT_COMMIT = re.compile(r"^[a-f0-9]{40}$")
_ANSWERABLE = {"ANSWERABLE", "PARTIALLY_ANSWERABLE"}
_CLEANUP_STAGE_ERROR_CODES = {
    "INACTIVATE_AND_SCHEDULE": "CLEANUP_INACTIVATION_OR_SCHEDULING_FAILED",
    "VERIFY_QUEUE_SCOPE": "CLEANUP_QUEUE_SCOPE_PROOF_FAILED",
    "RUN_WORKER": "CLEANUP_WORKER_EXECUTION_FAILED",
    "VERIFY_DELETED_API": "CLEANUP_DELETED_API_PROOF_FAILED",
    "VERIFY_READY_CLOSED": "CLEANUP_READY_CLOSED_PROOF_FAILED",
}


class GateError(RuntimeError):
    """A stable error code safe for the sanitized report."""


class NoCachedQueryVisibility:
    def invalidate_version(self, **kwargs: object) -> None:
        del kwargs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-head-commit", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--latency-repetitions", type=int, default=30)
    parser.add_argument(
        "--pdf-object-root",
        type=Path,
        default=Path("runtime/phase3-comparison-pdf-objects"),
    )
    parser.add_argument("--es-index-prefix", default="zhiyan-phase3-comparison-canary")
    parser.add_argument(
        "--milvus-collection-prefix",
        default="zhiyan_phase3_comparison_canary",
    )
    return parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lf_canonical_sha256(path: Path) -> str:
    payload = path.read_bytes()
    if b"\r" in payload.replace(b"\r\n", b""):
        raise GateError("CONFIG_LINE_ENDING_INVALID")
    return hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()


def _repository_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    head = completed.stdout.strip()
    if not _GIT_COMMIT.fullmatch(head):
        raise GateError("REPOSITORY_HEAD_INVALID")
    return head


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile values are empty")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean values are empty")
    return sum(values) / len(values)


def _loopback(name: str, value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https", "postgresql"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise GateError(f"{name}_MUST_USE_LOOPBACK")
    return value


def _environment(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise GateError(f"{name}_MISSING")
    return value


def _validate_safe_runtime_path(path: Path, *, directory: bool = False) -> None:
    if path.is_absolute() or not path.parts or path.parts[0] != "runtime" or ".." in path.parts:
        raise GateError("UNSAFE_RUNTIME_PATH")
    if directory and not path.is_dir():
        raise GateError("INPUT_ROOT_MISSING")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    values = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not values or not all(isinstance(value, dict) for value in values):
        raise GateError("INPUT_JSONL_INVALID")
    return values


def load_input_package(
    root: Path,
    *,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    _validate_safe_runtime_path(root, directory=True)
    manifest_path = root / "manifest.json"
    if (
        not _HEX64.fullmatch(expected_manifest_sha256)
        or not manifest_path.is_file()
        or _sha256(manifest_path) != expected_manifest_sha256
    ):
        raise GateError("INPUT_MANIFEST_IDENTITY_MISMATCH")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != INPUT_SCHEMA_VERSION
        or manifest.get("split_boundary") != "DEV_ONLY_TEST_AND_ACCEPTANCE_EXCLUDED"
        or manifest.get("strategy") != "section_parent_child_v1"
        or tuple(manifest.get("target_question_ids", ())) != TARGET_IDS
        or manifest.get("target_ids_sha256") != TARGET_IDS_SHA256
    ):
        raise GateError("INPUT_MANIFEST_CONTRACT_INVALID")
    expected_paths = set(ASSETS)
    artifacts = manifest.get("artifacts")
    if (
        not isinstance(artifacts, list)
        or {item.get("path") for item in artifacts if isinstance(item, dict)}
        != expected_paths
    ):
        raise GateError("INPUT_ARTIFACT_SET_INVALID")
    for artifact in artifacts:
        relative = Path(artifact["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise GateError("INPUT_ARTIFACT_PATH_INVALID")
        path = root / relative
        if (
            not path.is_file()
            or artifact.get("sha256") != ASSETS[artifact["path"]]["sha256"]
            or _sha256(path) != artifact["sha256"]
            or path.stat().st_size != artifact.get("size_bytes")
        ):
            raise GateError("INPUT_ARTIFACT_IDENTITY_MISMATCH")
    dev_rows = _load_jsonl(root / "dev-review.jsonl")
    if len(dev_rows) != 105 or {row.get("split") for row in dev_rows} != {"dev"}:
        raise GateError("DEV_SPLIT_BOUNDARY_INVALID")
    chunks = json.loads((root / "frozen-chunks.json").read_text(encoding="utf-8"))
    canary = _load_jsonl(root / "fixed-15-canary.jsonl")
    if not isinstance(chunks, list) or len(chunks) != 316 or len(canary) != 15:
        raise GateError("INPUT_COUNT_INVALID")
    return {
        "manifest_sha256": expected_manifest_sha256,
        "dev_rows": dev_rows,
        "frozen_chunks": chunks,
        "canary": canary,
    }


def _source_chunk_key(chunk: Mapping[str, Any], *, document_id: str) -> tuple[Any, ...]:
    return (
        document_id,
        chunk.get("page_start"),
        chunk.get("page_end"),
        chunk.get("section_path"),
        chunk.get("text"),
    )


def remap_runtime_chunks(
    frozen_chunks: Sequence[Mapping[str, Any]],
    runtime_chunks: Sequence[Mapping[str, Any]],
    document_id_map: Mapping[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    reverse_documents = {runtime: source for source, runtime in document_id_map.items()}
    runtime_by_key: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for chunk in runtime_chunks:
        runtime_document_id = str(chunk.get("document_id", ""))
        source_document_id = reverse_documents.get(runtime_document_id)
        if source_document_id is None:
            raise GateError("RUNTIME_CHUNK_DOCUMENT_IDENTITY_INVALID")
        runtime_by_key.setdefault(
            _source_chunk_key(chunk, document_id=source_document_id),
            [],
        ).append(chunk)
    source_to_runtime: dict[str, str] = {}
    runtime_to_source: dict[str, str] = {}
    for source in frozen_chunks:
        source_id = source.get("chunk_id")
        source_document_id = source.get("document_id")
        matches = runtime_by_key.get(
            _source_chunk_key(source, document_id=str(source_document_id)),
            [],
        )
        if not isinstance(source_id, str) or len(matches) != 1:
            raise GateError("RUNTIME_CHUNK_IDENTITY_MISMATCH")
        runtime_id = matches[0].get("chunk_id")
        if not isinstance(runtime_id, str) or runtime_id in runtime_to_source:
            raise GateError("RUNTIME_CHUNK_IDENTITY_AMBIGUOUS")
        source_to_runtime[source_id] = runtime_id
        runtime_to_source[runtime_id] = source_id
    if len(source_to_runtime) != len(frozen_chunks) or len(runtime_chunks) != len(frozen_chunks):
        raise GateError("RUNTIME_CHUNK_COVERAGE_MISMATCH")
    return source_to_runtime, runtime_to_source


def _scope(owner_id: str, document_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "tenant_id": owner_id,
        "user_id": owner_id,
        "acl_version": "postgres_ready_v1",
        "include_public": False,
        "document_ids": list(document_ids),
        "library_ids": [],
        "folder_ids": [],
    }


def _relevance(row: Mapping[str, Any]) -> dict[str, int]:
    labels = row["final_labels"]
    return {
        judgment["chunk_id"]: judgment["relevance"]
        for judgment in labels["chunk_judgments"]
    }


def _score(
    row: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    runtime_to_source: Mapping[str, str],
    *,
    k: int,
) -> dict[str, float]:
    relevance = _relevance(row)
    relevant = {chunk_id for chunk_id, grade in relevance.items() if grade >= 2}
    source_ids = [
        runtime_to_source.get(str(candidate.get("chunk_id")), "")
        for candidate in candidates[:k]
    ]
    recall = sum(chunk_id in relevant for chunk_id in source_ids) / len(relevant)
    dcg = sum(
        (2 ** relevance.get(chunk_id, 0) - 1) / math.log2(rank + 1)
        for rank, chunk_id in enumerate(source_ids, 1)
    )
    ideal = sorted(relevance.values(), reverse=True)[:k]
    ideal_dcg = sum(
        (2**grade - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(ideal, 1)
    )
    return {"recall": recall, "ndcg": dcg / ideal_dcg if ideal_dcg else 0.0}


def _strict_two_sided(
    row: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    runtime_to_source: Mapping[str, str],
) -> bool:
    relevance = _relevance(row)
    relevant_documents = {
        judgment["document_id"]
        for judgment in row["final_labels"]["chunk_judgments"]
        if judgment["relevance"] >= 2
    }
    frozen_document_by_chunk = {
        judgment["chunk_id"]: judgment["document_id"]
        for judgment in row["final_labels"]["chunk_judgments"]
    }
    observed = {
        frozen_document_by_chunk[source_id]
        for candidate in candidates[:3]
        for source_id in [runtime_to_source.get(str(candidate.get("chunk_id")), "")]
        if relevance.get(source_id, 0) >= 2
    }
    return observed == relevant_documents and len(relevant_documents) == 2


def _runtime_document_ids(
    row: Mapping[str, Any],
    document_id_map: Mapping[str, str],
) -> list[str]:
    source_ids = row["final_labels"]["expected_filters"]["document_ids"]
    try:
        return [document_id_map[source_id] for source_id in source_ids]
    except KeyError as exc:
        raise GateError("DEV_DOCUMENT_IDENTITY_UNAVAILABLE") from exc


def _search(
    retriever: OnlineVersionRrfRetriever,
    row: Mapping[str, Any],
    *,
    owner_id: str,
    document_id_map: Mapping[str, str],
    top_k: int,
) -> list[dict[str, Any]]:
    document_ids = _runtime_document_ids(row, document_id_map)
    return [
        dict(candidate.chunk)
        for candidate in retriever.search(
            row["question"],
            _scope(owner_id, document_ids),
            owner_id=owner_id,
            document_ids=document_ids,
            top_k=top_k,
        )
    ]


def _target_metrics(
    rows: Sequence[Mapping[str, Any]],
    results: Mapping[str, Sequence[Mapping[str, Any]]],
    runtime_to_source: Mapping[str, str],
) -> dict[str, Any]:
    scores = [
        _score(row, results[row["question_id"]], runtime_to_source, k=3)
        for row in rows
    ]
    strict = sum(
        _strict_two_sided(row, results[row["question_id"]], runtime_to_source)
        for row in rows
    )
    return {
        "strict_two_sided_passed": strict,
        "total": len(rows),
        "macro_recall_at_3": round(_mean([score["recall"] for score in scores]), 6),
        "macro_ndcg_at_3": round(_mean([score["ndcg"] for score in scores]), 6),
    }


def _api_result(
    client: TestClient,
    *,
    question: str,
    document_ids: Sequence[str],
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/rag/answers",
        json={"question": question, "document_ids": list(document_ids), "stream": False},
    )
    payload = response.json()
    return {
        "http_status": response.status_code,
        "status": payload.get("status"),
        "error_code": payload.get("code"),
        "evidence_count": len(payload.get("evidence", [])),
        "evidence": payload.get("evidence", []),
    }


def evaluate_canary(
    cases: Sequence[Mapping[str, Any]],
    *,
    control_client: TestClient,
    treatment_client: TestClient,
    document_id_map: Mapping[str, str],
) -> dict[str, Any]:
    passed = 0
    category_passed = {key: 0 for key in ("ANSWERABLE", "NO_EVIDENCE", "FORBIDDEN")}
    for case in cases:
        category = case["category"]
        source_document_ids = case["document_ids"]
        runtime_ids = [
            document_id_map.get(source_id, source_id)
            for source_id in source_document_ids
        ]
        control = _api_result(
            control_client,
            question=case["question"],
            document_ids=runtime_ids,
        )
        treatment = _api_result(
            treatment_client,
            question=case["question"],
            document_ids=runtime_ids,
        )
        case_passed = control == treatment
        if category == "ANSWERABLE":
            required = case["expected"]["required_evidence"]
            observed = control["evidence"]
            location_ok = all(
                any(
                    evidence.get("document_id") == document_id_map[item["document_id"]]
                    and evidence.get("page_start") <= item["page_end"]
                    and evidence.get("page_end") >= item["page_start"]
                    for evidence in observed
                )
                for item in required
            )
            case_passed = (
                case_passed
                and control["http_status"] == 200
                and control["status"] == "COMPLETED"
                and control["evidence_count"] >= 1
                and location_ok
            )
        elif category == "NO_EVIDENCE":
            case_passed = (
                case_passed
                and control["http_status"] == 200
                and control["status"] == "NO_EVIDENCE"
                and control["evidence_count"] == 0
            )
        else:
            case_passed = (
                case_passed
                and control["http_status"] == 403
                and control["error_code"] == "RAG_FORBIDDEN_SCOPE"
                and control["evidence_count"] == 0
            )
        if case_passed:
            passed += 1
            category_passed[category] += 1
    return {
        "passed": passed,
        "total": len(cases),
        "category_passed": category_passed,
        "exact_control_treatment_boundary": passed == len(cases),
    }


def evaluate_dev_no_evidence(
    rows: Sequence[Mapping[str, Any]],
    *,
    control_client: TestClient,
    treatment_client: TestClient,
    document_id_map: Mapping[str, str],
) -> dict[str, Any]:
    control_passed = 0
    treatment_passed = 0
    for row in rows:
        document_ids = _runtime_document_ids(row, document_id_map)
        control = _api_result(
            control_client,
            question=row["question"],
            document_ids=document_ids,
        )
        treatment = _api_result(
            treatment_client,
            question=row["question"],
            document_ids=document_ids,
        )
        if (
            control["http_status"] == 200
            and control["status"] == "NO_EVIDENCE"
            and control["evidence_count"] == 0
        ):
            control_passed += 1
        if (
            treatment["http_status"] == 200
            and treatment["status"] == "NO_EVIDENCE"
            and treatment["evidence_count"] == 0
        ):
            treatment_passed += 1
    return {
        "case_count": len(rows),
        "control_no_evidence_zero_candidate_count": control_passed,
        "treatment_no_evidence_zero_candidate_count": treatment_passed,
        "no_worse_than_control": treatment_passed >= control_passed,
    }


def _latency_summary(
    control: Sequence[OnlineRetrievalLatencyBreakdown],
    treatment: Sequence[OnlineRetrievalLatencyBreakdown],
    decomposition_latencies: Sequence[float],
) -> dict[str, Any]:
    control_p95 = _percentile([item.total_latency_ms for item in control], 0.95)
    treatment_p95 = _percentile([item.total_latency_ms for item in treatment], 0.95)
    decomposition_p95 = _percentile(decomposition_latencies, 0.95)
    return {
        "sample_count_per_arm": len(control),
        "control_retrieval_p95_ms": round(control_p95, 6),
        "treatment_retrieval_p95_ms": round(treatment_p95, 6),
        "incremental_retrieval_p95_ms": round(treatment_p95 - control_p95, 6),
        "incremental_retrieval_p95_limit_ms": 50.0,
        "decomposition_p95_ms": round(decomposition_p95, 6),
        "decomposition_p95_limit_ms": 5.0,
        "absolute_300ms_adjudication": "NOT_RUN_SEPARATE_PERFORMANCE_GATE",
    }


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    _validate_safe_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sanitized_code(exc: BaseException) -> str:
    value = str(exc)
    return value if re.fullmatch(r"[A-Z][A-Z0-9_]{2,79}", value) else "PHASE3_GATE_FAILED"


def _cleanup_failure_summary(
    *,
    stage: str,
    scheduled_versions: int,
    cleanup_results: Sequence[Any],
    inactive_403: bool,
    reconciliation_failed_closed: bool,
) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "stage": stage,
        "scheduled_versions": scheduled_versions,
        "jobs_succeeded": sum(result.succeeded for result in cleanup_results),
        "jobs_observed": len(cleanup_results),
        "jobs_expected": EXPECTED_CLEANUP_JOBS,
        "ready_reconciliation_failed_closed": reconciliation_failed_closed,
        "deleted_answer_api_status": 403 if inactive_403 else None,
        "error_code": _CLEANUP_STAGE_ERROR_CODES.get(
            stage,
            "CLEANUP_PROOF_FAILED",
        ),
    }


def _active_cleanup_scope(connection: Any) -> set[tuple[str, str, str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT owner_id, document_version_id, backend
            FROM rag_index_cleanup_jobs
            WHERE status IN ('PENDING', 'RETRY', 'RUNNING')
            """
        )
        return {
            (str(owner_id), str(document_version_id), str(backend))
            for owner_id, document_version_id, backend in cursor.fetchall()
        }


def _require_empty_cleanup_queue(connection: Any) -> None:
    if _active_cleanup_scope(connection):
        raise GateError("CLEANUP_QUEUE_NOT_ISOLATED")


def _require_exact_cleanup_scope(
    connection: Any,
    *,
    owner_id: str,
    document_version_ids: Sequence[str],
) -> None:
    expected = {
        (owner_id, version_id, backend)
        for version_id in document_version_ids
        for backend in (
            "elasticsearch_chunks",
            "milvus_vectors",
            "runtime_snapshot",
        )
    }
    if _active_cleanup_scope(connection) != expected:
        raise GateError("CLEANUP_QUEUE_SCOPE_MISMATCH")


def run_gate(args: argparse.Namespace) -> dict[str, Any]:
    inputs = load_input_package(
        args.input_root,
        expected_manifest_sha256=args.expected_manifest_sha256,
    )
    if _lf_canonical_sha256(CONFIG_PATH) != CONFIG_SHA256:
        raise GateError("COMPARISON_CONFIG_IDENTITY_MISMATCH")
    source_document_ids = tuple(
        identity["document_id"]
        for identity in json.loads(CONFIG_PATH.read_text(encoding="utf-8"))[
            "document_identities"
        ]
    )
    dev_by_id = {row["question_id"]: row for row in inputs["dev_rows"]}
    targets = [dev_by_id[question_id] for question_id in TARGET_IDS]
    if any(
        row.get("split") != "dev"
        or row.get("selected_category") != "comparison"
        or row["final_labels"].get("answerability") != "ANSWERABLE"
        for row in targets
    ):
        raise GateError("FROZEN_TARGET_CONTRACT_INVALID")

    connection = connect_postgres(
        _loopback("DATABASE_URL", _environment("DATABASE_URL"))
    )
    repository = PostgresFactRepository(connection)
    _require_empty_cleanup_queue(connection)
    pdf_objects = FilesystemPdfObjectStore(args.pdf_object_root)
    es_transport = UrllibElasticsearchTransport(
        base_url=_loopback(
            "ELASTICSEARCH_URL",
            _environment("ELASTICSEARCH_URL", "http://127.0.0.1:9200"),
        )
    )
    milvus_transport = PymilvusTransport(
        uri=_loopback(
            "MILVUS_URI",
            _environment("MILVUS_URI", "http://127.0.0.1:19530"),
        )
    )
    embedding = OllamaEmbeddingProvider(
        model=_environment("OLLAMA_EMBED_MODEL", "bge-m3:latest"),
        base_url=_loopback(
            "OLLAMA_URL",
            _environment("OLLAMA_URL", "http://127.0.0.1:11434"),
        ),
    )
    elasticsearch = ElasticsearchVersionIndexWriter(
        index_prefix=args.es_index_prefix,
        transport=es_transport,
    )
    milvus = MilvusVersionIndexWriter(
        collection_prefix=args.milvus_collection_prefix,
        transport=milvus_transport,
        provider=embedding,
    )
    owner_id = f"phase3_comparison_canary_{args.run_id}"
    if repository.resolve_online_versions(owner_id=owner_id):
        raise GateError("ISOLATED_OWNER_ALREADY_HAS_READY_VERSION")

    versions = []
    cleanup_summary: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    primary_error: BaseException | None = None
    control_client: TestClient | None = None
    cleanup_stage = "NOT_STARTED"
    cleanup_results: tuple[Any, ...] = ()
    inactive_403 = False
    reconciliation_failed_closed = False
    try:
        document_id_map: dict[str, str] = {}
        now = datetime.now(timezone.utc)
        for source_document_id in source_document_ids:
            pdf_path = args.input_root / "papers" / f"{source_document_id}.pdf"
            expected_sha = ASSETS[f"papers/{source_document_id}.pdf"]["sha256"]
            runtime = prepare_and_persist_pdf_ingestion(
                pdf_path.read_bytes(),
                repository=repository,
                object_store=pdf_objects,
                owner_id=owner_id,
                paper_id=f"{source_document_id}_{args.run_id}",
                source_type="uploaded",
                source_created_time=now,
                source_updated_time=now,
                idempotency_key=f"phase3_{source_document_id}_{args.run_id}",
                strategy="section_parent_child_v1",
                library_scope_ids=[f"phase3_comparison_{args.run_id}"],
                expected_sha256=expected_sha,
            )
            publication = publish_prepared_indexes(
                runtime.preparation,
                repository=repository,
                elasticsearch=elasticsearch,
                milvus=milvus,
            )
            versions.append(publication.version)
            document_id_map[source_document_id] = publication.version.document_id
        ready = reconcile_ready_scope(
            repository=repository,
            elasticsearch=elasticsearch,
            milvus=milvus,
            owner_id=owner_id,
            document_ids=[version.document_id for version in versions],
        )
        if len(ready.versions) != 3:
            raise GateError("READY_RECONCILIATION_COUNT_INVALID")
        runtime_chunks = repository.load_online_chunks(
            owner_id=owner_id,
            document_version_ids=[
                version.document_version_id for version in versions
            ],
        )
        source_to_runtime, runtime_to_source = remap_runtime_chunks(
            inputs["frozen_chunks"],
            [chunk.model_dump(mode="json") for chunk in runtime_chunks],
            document_id_map,
        )
        del source_to_runtime

        resolver = PostgresReadyRouteResolver(
            repository=repository,
            elasticsearch=elasticsearch,
            milvus=milvus,
        )
        control_latency: list[OnlineRetrievalLatencyBreakdown] = []
        treatment_latency: list[OnlineRetrievalLatencyBreakdown] = []
        decomposition_observations = []
        control = OnlineVersionRrfRetriever(
            resolver=resolver,
            elasticsearch_transport=es_transport,
            milvus_transport=milvus_transport,
            embedding_provider=embedding,
            chunk_snapshots=repository,
            candidate_k=20,
            rrf_k=60,
            latency_observer=control_latency.append,
        )
        control_client = TestClient(
            create_app(
                retrieval_backend="online_remote_rrf",
                authenticated_owner_id=owner_id,
                online_rrf_retriever=control,
            )
        )

        control_results = {
            row["question_id"]: _search(
                control,
                row,
                owner_id=owner_id,
                document_id_map=document_id_map,
                top_k=3,
            )
            for row in targets
        }
        control_target = _target_metrics(targets, control_results, runtime_to_source)
        if control_target["strict_two_sided_passed"] != 0:
            report = {
                "schema_version": REPORT_SCHEMA_VERSION,
                "status": "FAIL",
                "error_code": "CONTROL_BASELINE_MISMATCH",
                "execution_boundary": (
                    "ISOLATED_DEV_ONLY_POSTGRES_READY_ES_MILVUS_RRF_CONTROL_ONLY"
                ),
                "input_manifest_sha256": inputs["manifest_sha256"],
                "config_sha256": CONFIG_SHA256,
                "target_ids_sha256": TARGET_IDS_SHA256,
                "control": control_target,
                "treatment": None,
                "split_isolation": {
                    "dev": "USED_FROZEN_CONTROL_ONLY",
                    "test": "NOT_READ_NOT_RUN",
                    "acceptance": "NOT_READ_NOT_RUN",
                },
                "performance_boundary": (
                    "TREATMENT_NOT_RUN_NO_300MS_SLO_CONCLUSION"
                ),
            }
            raise GateError("CONTROL_BASELINE_MISMATCH")

        # Treatment is not constructed until the frozen Control failure is
        # reproduced on the exact READY scope.
        config = remap_document_identities(
            load_bilateral_comparison_config(CONFIG_PATH),
            document_id_map,
        )
        planner = BilateralComparisonQueryDecomposer(
            config=config,
            enabled=True,
            observer=decomposition_observations.append,
        )
        treatment = OnlineVersionRrfRetriever(
            resolver=resolver,
            elasticsearch_transport=es_transport,
            milvus_transport=milvus_transport,
            embedding_provider=embedding,
            chunk_snapshots=repository,
            candidate_k=20,
            rrf_k=60,
            route_query_planner=planner,
            latency_observer=treatment_latency.append,
        )
        treatment_client = TestClient(
            create_app(
                retrieval_backend="online_remote_rrf",
                authenticated_owner_id=owner_id,
                online_rrf_retriever=treatment,
            )
        )
        treatment_results = {
            row["question_id"]: _search(
                treatment,
                row,
                owner_id=owner_id,
                document_id_map=document_id_map,
                top_k=3,
            )
            for row in targets
        }
        treatment_target = _target_metrics(
            targets,
            treatment_results,
            runtime_to_source,
        )

        non_target = [
            row
            for row in inputs["dev_rows"]
            if row["question_id"] not in TARGET_IDS
            and row["final_labels"]["answerability"] in _ANSWERABLE
        ]
        control_non_target_scores3 = []
        treatment_non_target_scores3 = []
        control_non_target_scores10 = []
        treatment_non_target_scores10 = []
        for row in non_target:
            control_candidates = _search(
                control,
                row,
                owner_id=owner_id,
                document_id_map=document_id_map,
                top_k=10,
            )
            treatment_candidates = _search(
                treatment,
                row,
                owner_id=owner_id,
                document_id_map=document_id_map,
                top_k=10,
            )
            control_non_target_scores3.append(
                _score(row, control_candidates, runtime_to_source, k=3)
            )
            treatment_non_target_scores3.append(
                _score(row, treatment_candidates, runtime_to_source, k=3)
            )
            control_non_target_scores10.append(
                _score(row, control_candidates, runtime_to_source, k=10)
            )
            treatment_non_target_scores10.append(
                _score(row, treatment_candidates, runtime_to_source, k=10)
            )
        control_recall3 = _mean(
            [score["recall"] for score in control_non_target_scores3]
        )
        treatment_recall3 = _mean(
            [score["recall"] for score in treatment_non_target_scores3]
        )
        control_ndcg10 = _mean(
            [score["ndcg"] for score in control_non_target_scores10]
        )
        treatment_ndcg10 = _mean(
            [score["ndcg"] for score in treatment_non_target_scores10]
        )
        non_regression = {
            "case_count": len(non_target),
            "control_recall_at_3": round(control_recall3, 6),
            "treatment_recall_at_3": round(treatment_recall3, 6),
            "recall_at_3_drop": round(control_recall3 - treatment_recall3, 6),
            "recall_at_3_max_drop": 0.01,
            "control_ndcg_at_10": round(control_ndcg10, 6),
            "treatment_ndcg_at_10": round(treatment_ndcg10, 6),
            "ndcg_at_10_drop": round(control_ndcg10 - treatment_ndcg10, 6),
            "ndcg_at_10_max_drop": 0.01,
            "top10_boundary": "EVALUATION_DIAGNOSTIC_ONLY_PRODUCT_FINAL_TOP3_UNCHANGED",
        }
        canary = evaluate_canary(
            inputs["canary"],
            control_client=control_client,
            treatment_client=treatment_client,
            document_id_map=document_id_map,
        )
        dev_no_evidence = evaluate_dev_no_evidence(
            [
                row
                for row in inputs["dev_rows"]
                if row["final_labels"]["answerability"] == "NO_EVIDENCE"
            ],
            control_client=control_client,
            treatment_client=treatment_client,
            document_id_map=document_id_map,
        )

        target_cycle = [targets[index % len(targets)] for index in range(args.latency_repetitions)]
        control_latency.clear()
        treatment_latency.clear()
        decomposition_observations.clear()
        for row in target_cycle:
            _search(
                control,
                row,
                owner_id=owner_id,
                document_id_map=document_id_map,
                top_k=3,
            )
            _search(
                treatment,
                row,
                owner_id=owner_id,
                document_id_map=document_id_map,
                top_k=3,
            )
        latency = _latency_summary(
            control_latency,
            treatment_latency,
            [
                observation.decomposition_latency_ms
                for observation in decomposition_observations
            ],
        )
        gains = {
            "strict_two_sided_absolute_gain": round(
                (
                    treatment_target["strict_two_sided_passed"]
                    - control_target["strict_two_sided_passed"]
                )
                / 4,
                6,
            ),
            "macro_recall_at_3_absolute_gain": round(
                treatment_target["macro_recall_at_3"]
                - control_target["macro_recall_at_3"],
                6,
            ),
            "macro_ndcg_at_3_absolute_gain": round(
                treatment_target["macro_ndcg_at_3"]
                - control_target["macro_ndcg_at_3"],
                6,
            ),
        }
        quality_pass = (
            treatment_target["strict_two_sided_passed"] >= 3
            and gains["strict_two_sided_absolute_gain"] >= 0.5
            and gains["macro_recall_at_3_absolute_gain"] >= 0.2
            and gains["macro_ndcg_at_3_absolute_gain"] >= 0.1
            and non_regression["recall_at_3_drop"] <= 0.01
            and non_regression["ndcg_at_10_drop"] <= 0.01
            and dev_no_evidence["no_worse_than_control"]
            and canary["passed"] == 15
            and latency["incremental_retrieval_p95_ms"] <= 50
            and latency["decomposition_p95_ms"] <= 5
        )
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "PASS" if quality_pass else "FAIL",
            "error_code": None if quality_pass else "QUALITY_OR_COST_THRESHOLD_NOT_MET",
            "execution_boundary": (
                "ISOLATED_DEV_ONLY_POSTGRES_READY_ES_MILVUS_RRF_CONTROL_TREATMENT"
            ),
            "input_manifest_sha256": inputs["manifest_sha256"],
            "config_sha256": CONFIG_SHA256,
            "target_ids_sha256": TARGET_IDS_SHA256,
            "identity": {
                "ready_document_count": 3,
                "runtime_chunk_count": len(runtime_chunks),
                "owner_acl_version_chunk_identity_violations": 0,
            },
            "control": control_target,
            "treatment": treatment_target,
            "gains": gains,
            "critical_non_regression": non_regression,
            "dev_no_evidence": dev_no_evidence,
            "fixed_15_canary": canary,
            "cost": latency,
            "tokens": {
                "new_llm_calls": 0,
                "new_generation_tokens": 0,
            },
            "operations": {
                "new_services": 0,
                "new_models": 0,
                "new_indexes_beyond_three_isolated_version_routes": 0,
                "database_migrations": 0,
                "reranker_enabled": False,
            },
            "split_isolation": {
                "dev": "USED_FROZEN_INPUT_ONLY",
                "test": "NOT_READ_NOT_RUN",
                "acceptance": "NOT_READ_NOT_RUN",
            },
            "performance_boundary": (
                "INCREMENTAL_QUALITY_VARIABLE_COST_ONLY_NO_300MS_SLO_CONCLUSION"
            ),
        }
    except BaseException as exc:
        primary_error = exc
    finally:
        try:
            cleanup_stage = "INACTIVATE_AND_SCHEDULE"
            for version in versions:
                inactivate_and_schedule_cleanup(
                    version,
                    reason=InactivationReason.DELETE,
                    repository=repository,
                    visibility=NoCachedQueryVisibility(),
                    cleanup=PersistentIndexCleanupScheduler(repository),
                    elasticsearch=elasticsearch,
                    milvus=milvus,
                )
            cleanup_stage = "VERIFY_QUEUE_SCOPE"
            _require_exact_cleanup_scope(
                connection,
                owner_id=owner_id,
                document_version_ids=[
                    version.document_version_id for version in versions
                ],
            )
            cleanup_stage = "RUN_WORKER"
            cleanup_results = PersistentIndexCleanupWorker(
                repository=repository,
                elasticsearch=elasticsearch,
                milvus=milvus,
                runtime_snapshot=PersistentRuntimeSnapshotCleaner(
                    repository=repository,
                    pdf_objects=pdf_objects,
                ),
            ).run_batch(max_jobs=EXPECTED_CLEANUP_JOBS)
            cleanup_ok = (
                len(versions) == 3
                and len(cleanup_results) == EXPECTED_CLEANUP_JOBS
                and all(result.succeeded for result in cleanup_results)
            )
            cleanup_stage = "VERIFY_DELETED_API"
            if control_client is not None and versions:
                deleted = _api_result(
                    control_client,
                    question="Deleted isolated canary content must remain unavailable.",
                    document_ids=[version.document_id for version in versions],
                )
                inactive_403 = (
                    deleted["http_status"] == 403
                    and deleted["error_code"] == "RAG_FORBIDDEN_SCOPE"
                    and deleted["evidence_count"] == 0
                )
            cleanup_stage = "VERIFY_READY_CLOSED"
            if versions:
                try:
                    reconcile_ready_scope(
                        repository=repository,
                        elasticsearch=elasticsearch,
                        milvus=milvus,
                        owner_id=owner_id,
                        document_ids=[version.document_id for version in versions],
                    )
                except Stage1ReconciliationError:
                    reconciliation_failed_closed = True
            cleanup_stage = "COMPLETE"
            cleanup_summary = {
                "scheduled_versions": len(versions),
                "jobs_succeeded": sum(result.succeeded for result in cleanup_results),
                "jobs_observed": len(cleanup_results),
                "jobs_expected": EXPECTED_CLEANUP_JOBS,
                "ready_reconciliation_failed_closed": reconciliation_failed_closed,
                "deleted_answer_api_status": 403 if inactive_403 else None,
                "status": (
                    "PASS"
                    if cleanup_ok and inactive_403 and reconciliation_failed_closed
                    else "FAIL"
                ),
            }
            if cleanup_summary["status"] != "PASS" and primary_error is None:
                primary_error = GateError("CLEANUP_PROOF_FAILED")
        except BaseException:
            cleanup_summary = _cleanup_failure_summary(
                stage=cleanup_stage,
                scheduled_versions=len(versions),
                cleanup_results=cleanup_results,
                inactive_403=inactive_403,
                reconciliation_failed_closed=reconciliation_failed_closed,
            )
            if primary_error is None:
                primary_error = GateError("CLEANUP_PROOF_FAILED")
        connection.close()

    if report is None:
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "FAIL",
            "error_code": _sanitized_code(
                primary_error or GateError("PHASE3_GATE_FAILED")
            ),
            "execution_boundary": (
                "ISOLATED_DEV_ONLY_POSTGRES_READY_ES_MILVUS_RRF_CONTROL_TREATMENT"
            ),
            "input_manifest_sha256": inputs["manifest_sha256"],
            "config_sha256": CONFIG_SHA256,
            "target_ids_sha256": TARGET_IDS_SHA256,
            "split_isolation": {
                "dev": "USED_FROZEN_INPUT_ONLY",
                "test": "NOT_READ_NOT_RUN",
                "acceptance": "NOT_READ_NOT_RUN",
            },
            "performance_boundary": (
                "NO_300MS_SLO_CONCLUSION_SEPARATE_PERFORMANCE_GATE_PENDING"
            ),
        }
    report["cleanup"] = cleanup_summary
    report["run_id"] = args.run_id
    report["head_commit"] = args.expected_head_commit
    if primary_error is not None:
        report["primary_error_code"] = _sanitized_code(primary_error)
    if cleanup_summary is None or cleanup_summary.get("status") != "PASS":
        report["status"] = "FAIL"
        report["error_code"] = "CLEANUP_PROOF_FAILED"
    return report


def main() -> int:
    args = build_parser().parse_args()
    if (
        args.confirm != CONFIRMATION
        or not _RUN_ID.fullmatch(args.run_id)
        or not _GIT_COMMIT.fullmatch(args.expected_head_commit)
        or args.latency_repetitions < 30
        or args.latency_repetitions > 100
        or "canary" not in args.es_index_prefix
        or "canary" not in args.milvus_collection_prefix
    ):
        print(
            '{"status":"REFUSED","error_code":"PHASE3_GATE_ARGUMENTS_INVALID"}',
            file=sys.stderr,
        )
        return 2
    try:
        _validate_safe_runtime_path(args.output)
        _validate_safe_runtime_path(args.pdf_object_root)
        if _repository_head() != args.expected_head_commit:
            raise GateError("REPOSITORY_HEAD_MISMATCH")
        report = run_gate(args)
        _write_report(args.output, report)
    except Exception as exc:
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "FAIL",
            "error_code": _sanitized_code(exc),
            "run_id": args.run_id,
            "head_commit": args.expected_head_commit,
            "cleanup": {"status": "NOT_STARTED"},
            "split_isolation": {
                "dev": "VALIDATION_REFUSED",
                "test": "NOT_READ_NOT_RUN",
                "acceptance": "NOT_READ_NOT_RUN",
            },
            "performance_boundary": "NO_300MS_SLO_CONCLUSION",
        }
        _write_report(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
