"""Run one isolated, mutating Stage 1 canary against user-operated services."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.rag.generation import (
    GENERATION_FAILURE_CODES,
    GenerationModelIdentity,
    GenerationProvider,
    GenerationResult,
    GenerationServiceError,
    OllamaGenerationProvider,
)
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
from backend.ingestion.persistent import (
    RuntimeSnapshotPersistenceError,
    prepare_and_persist_pdf_ingestion,
)
from backend.retrieval.elasticsearch import UrllibElasticsearchTransport
from backend.retrieval.embedding import OllamaEmbeddingProvider
from backend.retrieval.milvus import PymilvusTransport
from backend.retrieval.online import (
    OnlineVersionRrfRetriever,
    PostgresReadyRouteResolver,
)
from backend.retrieval.sqlite_fts import chunks_fingerprint
from backend.storage.pdf_objects import FilesystemPdfObjectStore
from backend.storage.postgres import PostgresFactRepository, connect_postgres
from backend.validation.stage1 import Stage1ReconciliationError, reconcile_ready_scope


CONFIRMATION = "RUN_ISOLATED_STAGE1_CANARY"
REPORT_SCHEMA_VERSION = "stage1_remote_canary_report_v2"
EXPECTED_CLEANUP_JOBS = 3
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
_SANITIZED_RUNTIME_CODES = frozenset(
    {
        "PDF_OBJECT_REOPEN_FAILED",
        "READY_REPLAY_AMBIGUOUS",
        "READY_REPLAY_IDENTITY_MISMATCH",
        "READY_REPLAY_PDF_OBJECT_MISSING",
        "PERSISTED_SNAPSHOT_ANSWER_API_FAILED",
        "PERSISTED_SNAPSHOT_ANSWER_HTTP_FAILED",
        "PERSISTED_SNAPSHOT_ANSWER_NOT_COMPLETED",
        "PERSISTED_SNAPSHOT_ANSWER_EVIDENCE_MISSING",
        "REAL_GENERATION_INITIAL_FAILED_CLOSED",
        "REAL_GENERATION_INITIAL_CITATION_MAPPING_FAILED",
        "REAL_GENERATION_INITIAL_CITATION_GATE_FAILED",
        "REAL_GENERATION_REPLAY_HTTP_FAILED",
        "REAL_GENERATION_REPLAY_NOT_COMPLETED",
        "REAL_GENERATION_REPLAY_EVIDENCE_MISSING",
        "REAL_GENERATION_REPLAY_FAILED_CLOSED",
        "REAL_GENERATION_REPLAY_CITATION_MAPPING_FAILED",
        "REAL_GENERATION_REPLAY_CITATION_GATE_FAILED",
        "REAL_GENERATION_REPLAY_CITATION_MISMATCH",
        "CLEANUP_DID_NOT_COMPLETE",
        "RUNTIME_SNAPSHOT_CLEANUP_FAILED",
        "INACTIVE_VERSION_REMAINED_VISIBLE",
        "INACTIVE_ANSWER_API_REMAINED_VISIBLE",
    }
) | frozenset(
    f"REAL_GENERATION_{phase}_{code}"
    for phase in ("INITIAL", "REPLAY")
    for code in GENERATION_FAILURE_CODES
)


class NoCachedQueryVisibility:
    """PG READY is queried directly; there is no separate query cache to clear."""

    def invalidate_version(self, **kwargs: object) -> None:
        del kwargs


class _ObservedGenerationProvider:
    """Capture only an allowlisted failure code for the private Canary report."""

    def __init__(self, delegate: GenerationProvider) -> None:
        self.delegate = delegate
        self.failure_code: str | None = None

    def configured_identity(self) -> GenerationModelIdentity:
        return self.delegate.configured_identity()

    def generate(
        self,
        question: str,
        evidence: Sequence[Mapping[str, Any]],
    ) -> GenerationResult:
        self.failure_code = None
        try:
            return self.delegate.generate(question, evidence)
        except GenerationServiceError as exc:
            self.failure_code = exc.code
            raise
        except Exception:
            self.failure_code = "UNCLASSIFIED_GENERATION_FAILURE"
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strategy", default="fixed_boundary_v1")
    parser.add_argument(
        "--pdf-object-root",
        type=Path,
        default=Path("runtime/stage1-pdf-objects"),
    )
    parser.add_argument("--es-index-prefix", default="zhiyan-stage1-canary")
    parser.add_argument("--milvus-collection-prefix", default="zhiyan_stage1_canary")
    parser.add_argument("--generation-model")
    parser.add_argument("--generation-model-digest")
    return parser


def _environment(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise ValueError(f"required environment variable is empty: {name}")
    return value


def _loopback_endpoint(name: str, value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https", "postgresql"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError(f"{name}_MUST_USE_LOOPBACK")
    return value


def _validate_output_path(path: Path) -> None:
    if path.is_absolute() or not path.parts or path.parts[0] != "runtime" or ".." in path.parts:
        raise ValueError("OUTPUT_MUST_BE_UNDER_RUNTIME")


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sanitized_error_code(exc: Exception) -> str:
    if isinstance(exc, RuntimeSnapshotPersistenceError):
        return exc.code
    if type(exc) is RuntimeError and str(exc) in _SANITIZED_RUNTIME_CODES:
        return str(exc)
    return type(exc).__name__


def _warnings_contain(payload: dict[str, object], suffix: str) -> bool:
    warnings = payload.get("warnings")
    return isinstance(warnings, list) and any(
        isinstance(warning, str) and warning.endswith(suffix) for warning in warnings
    )


def _require_answer_api_gate(
    *,
    status_code: int,
    payload: dict[str, object],
    generation_enabled: bool,
    replay: bool = False,
    generation_failure_code: str | None = None,
) -> None:
    if replay:
        prefix = "REAL_GENERATION_REPLAY"
    else:
        prefix = "PERSISTED_SNAPSHOT_ANSWER"
    if status_code != 200:
        raise RuntimeError(f"{prefix}_HTTP_FAILED")
    if payload.get("status") != "COMPLETED":
        if generation_enabled and _warnings_contain(
            payload, "_FAILED_CLOSED_EVIDENCE_ONLY"
        ):
            generation_phase = "REPLAY" if replay else "INITIAL"
            if generation_failure_code in GENERATION_FAILURE_CODES:
                raise RuntimeError(
                    f"REAL_GENERATION_{generation_phase}_{generation_failure_code}"
                )
            raise RuntimeError(f"REAL_GENERATION_{generation_phase}_FAILED_CLOSED")
        if generation_enabled and _warnings_contain(
            payload, "_CITATION_MAPPING_FAILED_CLOSED"
        ):
            generation_phase = "REPLAY" if replay else "INITIAL"
            raise RuntimeError(
                f"REAL_GENERATION_{generation_phase}_CITATION_MAPPING_FAILED"
            )
        raise RuntimeError(f"{prefix}_NOT_COMPLETED")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise RuntimeError(f"{prefix}_EVIDENCE_MISSING")
    if generation_enabled and not _warnings_contain(
        payload, "_CITATION_IDS_VALIDATED"
    ):
        generation_phase = "REPLAY" if replay else "INITIAL"
        raise RuntimeError(
            f"REAL_GENERATION_{generation_phase}_CITATION_GATE_FAILED"
        )


def _generation_replay_byte_stable(
    initial_payload: dict[str, object],
    replay_payload: dict[str, object],
) -> bool:
    """Require the same validated citations; return answer byte stability."""
    if replay_payload.get("citations") != initial_payload.get("citations"):
        raise RuntimeError("REAL_GENERATION_REPLAY_CITATION_MISMATCH")
    return replay_payload.get("answer") == initial_payload.get("answer")


def main() -> int:
    args = build_parser().parse_args()
    if args.confirm != CONFIRMATION:
        print(
            json.dumps(
                {
                    "status": "REFUSED",
                    "error_code": "EXPLICIT_CONFIRMATION_REQUIRED",
                    "expected_confirmation": CONFIRMATION,
                }
            ),
            file=sys.stderr,
        )
        return 2
    if not _RUN_ID_PATTERN.fullmatch(args.run_id):
        print('{"status":"REFUSED","error_code":"INVALID_RUN_ID"}', file=sys.stderr)
        return 2
    if "canary" not in args.es_index_prefix or "canary" not in args.milvus_collection_prefix:
        print('{"status":"REFUSED","error_code":"CANARY_PREFIX_REQUIRED"}', file=sys.stderr)
        return 2
    if bool(args.generation_model) != bool(args.generation_model_digest):
        print(
            '{"status":"REFUSED","error_code":"GENERATION_IDENTITY_INCOMPLETE"}',
            file=sys.stderr,
        )
        return 2
    try:
        _validate_output_path(args.output)
    except ValueError:
        print('{"status":"REFUSED","error_code":"UNSAFE_OUTPUT_PATH"}', file=sys.stderr)
        return 2

    connection = None
    try:
        pdf_bytes = args.pdf.read_bytes()
        actual_sha256 = sha256(pdf_bytes).hexdigest()
        if actual_sha256 != args.expected_sha256:
            raise ValueError("PDF_IDENTITY_MISMATCH")

        connection = connect_postgres(
            _loopback_endpoint("DATABASE_URL", _environment("DATABASE_URL"))
        )
        repository = PostgresFactRepository(connection)
        pdf_object_store = FilesystemPdfObjectStore(args.pdf_object_root)
        elasticsearch_transport = UrllibElasticsearchTransport(
            base_url=_loopback_endpoint(
                "ELASTICSEARCH_URL",
                _environment("ELASTICSEARCH_URL", "http://127.0.0.1:9200"),
            )
        )
        elasticsearch = ElasticsearchVersionIndexWriter(
            index_prefix=args.es_index_prefix,
            transport=elasticsearch_transport,
        )
        milvus_transport = PymilvusTransport(
            uri=_loopback_endpoint(
                "MILVUS_URI",
                _environment("MILVUS_URI", "http://127.0.0.1:19530"),
            )
        )
        embedding_provider = OllamaEmbeddingProvider(
            model=_environment("OLLAMA_EMBED_MODEL", "bge-m3:latest"),
            base_url=_loopback_endpoint(
                "OLLAMA_URL",
                _environment("OLLAMA_URL", "http://127.0.0.1:11434"),
            ),
        )
        generation_observer = (
            _ObservedGenerationProvider(
                OllamaGenerationProvider(
                    model=args.generation_model,
                    expected_digest=args.generation_model_digest,
                    base_url=_loopback_endpoint(
                        "OLLAMA_URL",
                        _environment("OLLAMA_URL", "http://127.0.0.1:11434"),
                    ),
                )
            )
            if args.generation_model is not None
            else None
        )
        generation_provider = generation_observer
        milvus = MilvusVersionIndexWriter(
            collection_prefix=args.milvus_collection_prefix,
            transport=milvus_transport,
            provider=embedding_provider,
        )
        now = datetime.now(timezone.utc)
        owner_id = f"stage1_canary_{args.run_id}"
        paper_id = f"paper_{args.run_id}"
        ready_versions = repository.resolve_online_versions(owner_id=owner_id)
        resumed_from_ready = bool(ready_versions)
        if resumed_from_ready:
            if len(ready_versions) != 1:
                raise RuntimeError("READY_REPLAY_AMBIGUOUS")
            version = ready_versions[0]
            if (
                version.paper_id != paper_id
                or version.content_sha256 != actual_sha256
                or version.source_snapshot_sha256 != actual_sha256
            ):
                raise RuntimeError("READY_REPLAY_IDENTITY_MISMATCH")
            online_chunks = repository.load_online_chunks(
                owner_id=owner_id,
                document_version_ids=[version.document_version_id],
            )
            source_chunks = tuple(
                chunk.model_copy(update={"is_active": False})
                for chunk in online_chunks
            )
            pdf_object = repository.get_pdf_object(
                owner_id=owner_id,
                document_version_id=version.document_version_id,
            )
            if pdf_object is None:
                raise RuntimeError("READY_REPLAY_PDF_OBJECT_MISSING")
            runtime_snapshot_sha256 = chunks_fingerprint(
                [chunk.model_dump(mode="json") for chunk in source_chunks]
            )
        else:
            runtime_ingestion = prepare_and_persist_pdf_ingestion(
                pdf_bytes,
                repository=repository,
                object_store=pdf_object_store,
                owner_id=owner_id,
                paper_id=paper_id,
                source_type="uploaded",
                source_created_time=now,
                source_updated_time=now,
                idempotency_key=f"ingest_{args.run_id}",
                strategy=args.strategy,
                library_scope_ids=[f"library_{args.run_id}"],
                expected_sha256=args.expected_sha256,
            )
            preparation = runtime_ingestion.preparation
            source_chunks = preparation.ingestion.chunks
            pdf_object = runtime_ingestion.pdf_object
            runtime_snapshot_sha256 = (
                runtime_ingestion.snapshot.chunk_snapshot_sha256
            )
            publication = publish_prepared_indexes(
                preparation,
                repository=repository,
                elasticsearch=elasticsearch,
                milvus=milvus,
            )
            version = publication.version
        reopened_pdf = FilesystemPdfObjectStore(args.pdf_object_root).read_pdf(
            pdf_object
        )
        if reopened_pdf != pdf_bytes:
            raise RuntimeError("PDF_OBJECT_REOPEN_FAILED")
        ready_report = reconcile_ready_scope(
            repository=repository,
            elasticsearch=elasticsearch,
            milvus=milvus,
            owner_id=owner_id,
            document_ids=[version.document_id],
        )
        online_retriever = OnlineVersionRrfRetriever(
            resolver=PostgresReadyRouteResolver(
                repository=repository,
                elasticsearch=elasticsearch,
                milvus=milvus,
            ),
            elasticsearch_transport=elasticsearch_transport,
            milvus_transport=milvus_transport,
            embedding_provider=embedding_provider,
            chunk_snapshots=repository,
        )
        answer_client = TestClient(
            create_app(
                retrieval_backend="online_remote_rrf",
                authenticated_owner_id=owner_id,
                online_rrf_retriever=online_retriever,
                generation_provider=generation_provider,
            )
        )
        answer_response = answer_client.post(
            "/api/v1/rag/answers",
            json={
                "question": source_chunks[0].text[:4000],
                "document_ids": [version.document_id],
                "stream": False,
            },
        )
        answer_payload = answer_response.json()
        _require_answer_api_gate(
            status_code=answer_response.status_code,
            payload=answer_payload,
            generation_enabled=generation_provider is not None,
            generation_failure_code=(
                generation_observer.failure_code
                if generation_observer is not None
                else None
            ),
        )
        generation_stable_replay = False
        generation_byte_stable_replay = False
        if generation_provider is not None:
            replay_response = answer_client.post(
                "/api/v1/rag/answers",
                json={
                    "question": source_chunks[0].text[:4000],
                    "document_ids": [version.document_id],
                    "stream": False,
                },
            )
            replay_payload = replay_response.json()
            _require_answer_api_gate(
                status_code=replay_response.status_code,
                payload=replay_payload,
                generation_enabled=True,
                replay=True,
                generation_failure_code=generation_observer.failure_code,
            )
            generation_byte_stable_replay = _generation_replay_byte_stable(
                answer_payload,
                replay_payload,
            )
            generation_stable_replay = True

        scheduler = PersistentIndexCleanupScheduler(repository)
        inactivation = inactivate_and_schedule_cleanup(
            version,
            reason=InactivationReason.DELETE,
            repository=repository,
            visibility=NoCachedQueryVisibility(),
            cleanup=scheduler,
            elasticsearch=elasticsearch,
            milvus=milvus,
        )
        cleanup_results = PersistentIndexCleanupWorker(
            repository=repository,
            elasticsearch=elasticsearch,
            milvus=milvus,
            runtime_snapshot=PersistentRuntimeSnapshotCleaner(
                repository=repository,
                pdf_objects=pdf_object_store,
            ),
        ).run_batch(max_jobs=EXPECTED_CLEANUP_JOBS)
        if len(cleanup_results) != EXPECTED_CLEANUP_JOBS or not all(
            result.succeeded for result in cleanup_results
        ):
            raise RuntimeError("CLEANUP_DID_NOT_COMPLETE")
        if repository.get_inactive_pdf_object(
            owner_id=owner_id,
            document_version_id=version.document_version_id,
        ) is not None:
            raise RuntimeError("RUNTIME_SNAPSHOT_CLEANUP_FAILED")
        try:
            reconcile_ready_scope(
                repository=repository,
                elasticsearch=elasticsearch,
                milvus=milvus,
                owner_id=owner_id,
                document_ids=[version.document_id],
            )
        except Stage1ReconciliationError:
            inactive_proven = True
        else:
            inactive_proven = False
        if not inactive_proven:
            raise RuntimeError("INACTIVE_VERSION_REMAINED_VISIBLE")
        inactive_answer = answer_client.post(
            "/api/v1/rag/answers",
            json={
                "question": "This deleted document must remain unavailable.",
                "document_ids": [version.document_id],
                "stream": False,
            },
        )
        inactive_answer_payload = inactive_answer.json()
        if (
            inactive_answer.status_code != 403
            or inactive_answer_payload.get("code") != "RAG_FORBIDDEN_SCOPE"
        ):
            raise RuntimeError("INACTIVE_ANSWER_API_REMAINED_VISIBLE")

        payload: dict[str, object] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "PASS",
            "run_id": args.run_id,
            "pdf_sha256": actual_sha256,
            "owner_id": owner_id,
            "paper_id": paper_id,
            "document_id": version.document_id,
            "document_version_id": version.document_version_id,
            "chunk_count": len(source_chunks),
            "runtime_snapshot_sha256": runtime_snapshot_sha256,
            "pdf_object_reopen_proven": True,
            "resumed_from_ready": resumed_from_ready,
            "ready_reconciliation": ready_report.model_dump(),
            "answer_api_status": answer_payload["status"],
            "answer_api_evidence_count": len(answer_payload["evidence"]),
            "answer_generation_boundary": (
                generation_provider.configured_identity().execution_boundary
                if generation_provider is not None
                else "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_FAKE_LLM"
            ),
            "answer_citation_ids_validated": generation_provider is not None,
            "answer_sha256": (
                sha256(answer_payload["answer"].encode("utf-8")).hexdigest()
                if generation_provider is not None
                else None
            ),
            "generation_identity": (
                asdict(generation_provider.configured_identity())
                if generation_provider is not None
                else None
            ),
            "generation_stable_replay": generation_stable_replay,
            "generation_byte_stable_replay": (
                generation_byte_stable_replay
                if generation_provider is not None
                else None
            ),
            "inactivation_reason": inactivation.reason.value,
            "cleanup_jobs_succeeded": len(cleanup_results),
            "runtime_snapshot_cleanup_proven": True,
            "inactive_visibility_proven": inactive_proven,
            "inactive_answer_api_status": inactive_answer.status_code,
        }
        _write_report(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:
        failure = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "FAIL",
            "run_id": args.run_id,
            "error_code": _sanitized_error_code(exc),
        }
        _write_report(args.output, failure)
        print(json.dumps(failure), file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
