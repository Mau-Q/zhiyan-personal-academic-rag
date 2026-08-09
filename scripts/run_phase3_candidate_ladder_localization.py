#!/usr/bin/env python3
"""Run one identity-matched Phase 3 online candidate-ladder diagnostic."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
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
from backend.retrieval.elasticsearch import UrllibElasticsearchTransport
from backend.retrieval.embedding import OllamaEmbeddingProvider
from backend.retrieval.milvus import PymilvusTransport
from backend.retrieval.online import (
    OnlineCandidateLadderObservation,
    OnlineVersionRrfRetriever,
    PostgresReadyRouteResolver,
)
from backend.storage.pdf_objects import FilesystemPdfObjectStore
from backend.storage.postgres import PostgresFactRepository, connect_postgres
from backend.validation.stage1 import Stage1ReconciliationError, reconcile_ready_scope
from scripts.build_phase3_comparison_dev_package import (
    ASSETS,
    TARGET_IDS,
    TARGET_IDS_SHA256,
)
from scripts.run_phase3_comparison_paired_dev_gate import (
    EXPECTED_CLEANUP_JOBS,
    GateError,
    NoCachedQueryVisibility,
    _api_result,
    _environment,
    _loopback,
    _repository_head,
    _require_empty_cleanup_queue,
    _require_exact_cleanup_scope,
    _retrieval_failure_code,
    _sanitized_code,
    _scope,
    _strict_two_sided,
    _validate_safe_runtime_path,
    _write_report,
    load_input_package,
    remap_runtime_chunks,
)


REPORT_SCHEMA_VERSION = "phase3_candidate_ladder_localization_report_v1"
CONFIRMATION = "RUN_PHASE3_IDENTITY_MATCHED_CANDIDATE_LADDER_LOCALIZATION"
DIAGNOSTIC_RUN_ID = "phase3_candidate_ladder_20260809_01"
EXECUTION_BOUNDARY = "ISOLATED_FROZEN_4_DEV_CONTROL_CANDIDATE_LADDER_ONLY"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
_COMMIT = re.compile(r"^[a-f0-9]{40}$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-head-commit", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--pdf-object-root",
        type=Path,
        default=Path("runtime/phase3-candidate-ladder-pdf-objects"),
    )
    parser.add_argument(
        "--es-index-prefix",
        default="zhiyan-phase3-candidate-ladder-canary",
    )
    parser.add_argument(
        "--milvus-collection-prefix",
        default="zhiyan_phase3_candidate_ladder_canary",
    )
    return parser


def _source_document_ids() -> tuple[str, ...]:
    values = tuple(Path(path).stem for path in ASSETS if path.startswith("papers/"))
    if len(values) != 3 or len(set(values)) != 3:
        raise GateError("FROZEN_DOCUMENT_IDENTITY_INVALID")
    return values


def _target_contract(row: Mapping[str, Any]) -> dict[str, Any]:
    judgments = row["final_labels"]["chunk_judgments"]
    relevant = {
        str(item["chunk_id"]): {
            "document_id": str(item["document_id"]),
            "relevance": int(item["relevance"]),
        }
        for item in judgments
        if int(item["relevance"]) >= 2
    }
    required_documents = sorted(
        {item["document_id"] for item in relevant.values()}
    )
    if not relevant or len(required_documents) != 2:
        raise GateError("FROZEN_TARGET_EVIDENCE_CONTRACT_INVALID")
    return {
        "relevant": relevant,
        "required_documents": required_documents,
    }


def _candidate_record(
    candidate: Any,
    *,
    runtime_to_source: Mapping[str, str],
    runtime_to_source_document: Mapping[str, str],
    target: Mapping[str, Any],
    memberships: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    runtime_chunk_id = str(candidate.chunk.get("chunk_id", ""))
    source_chunk_id = runtime_to_source.get(runtime_chunk_id)
    runtime_document_id = str(candidate.chunk.get("document_id", ""))
    source_document_id = runtime_to_source_document.get(runtime_document_id)
    if source_chunk_id is None or source_document_id is None:
        raise GateError("DIAGNOSTIC_CANDIDATE_IDENTITY_UNMAPPED")
    relevant = target["relevant"].get(source_chunk_id)
    return {
        "rank": candidate.rank,
        "score": candidate.score,
        "runtime_chunk_id": runtime_chunk_id,
        "source_chunk_id": source_chunk_id,
        "runtime_document_id": runtime_document_id,
        "source_document_id": source_document_id,
        "page_start": candidate.chunk.get("page_start"),
        "page_end": candidate.chunk.get("page_end"),
        "section_path": candidate.chunk.get("section_path"),
        "target_match": relevant is not None,
        "target_relevance": relevant["relevance"] if relevant is not None else 0,
        "source_membership": [dict(value) for value in memberships],
    }


def _serialize_observation(
    observation: OnlineCandidateLadderObservation,
    *,
    runtime_to_source: Mapping[str, str],
    document_id_map: Mapping[str, str],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_to_source_document = {
        runtime: source for source, runtime in document_id_map.items()
    }
    membership_by_chunk: dict[str, list[dict[str, Any]]] = {}
    backend_ladders: list[dict[str, Any]] = []
    for ranking in observation.route_rankings:
        source_document_id = runtime_to_source_document.get(ranking.route.document_id)
        if source_document_id is None:
            raise GateError("DIAGNOSTIC_ROUTE_IDENTITY_UNMAPPED")
        candidates = []
        for candidate in ranking.candidates:
            runtime_chunk_id = str(candidate.chunk["chunk_id"])
            membership = {
                "backend": ranking.backend,
                "source_document_id": source_document_id,
                "rank": candidate.rank,
            }
            membership_by_chunk.setdefault(runtime_chunk_id, []).append(membership)
            candidates.append(
                _candidate_record(
                    candidate,
                    runtime_to_source=runtime_to_source,
                    runtime_to_source_document=runtime_to_source_document,
                    target=target,
                )
            )
        backend_ladders.append(
            {
                "backend": ranking.backend,
                "source_document_id": source_document_id,
                "runtime_document_id": ranking.route.document_id,
                "document_version_id": ranking.route.document_version_id,
                "physical_route": (
                    ranking.route.elasticsearch_index
                    if ranking.backend == "elasticsearch_bm25"
                    else ranking.route.milvus_collection
                ),
                "requested_candidate_k": observation.candidate_k,
                "returned_candidate_count": len(candidates),
                "candidates": candidates,
            }
        )

    fused = [
        _candidate_record(
            candidate,
            runtime_to_source=runtime_to_source,
            runtime_to_source_document=runtime_to_source_document,
            target=target,
            memberships=membership_by_chunk.get(str(candidate.chunk["chunk_id"]), ()),
        )
        for candidate in observation.fused_candidates
    ]
    final = [
        _candidate_record(
            candidate,
            runtime_to_source=runtime_to_source,
            runtime_to_source_document=runtime_to_source_document,
            target=target,
            memberships=membership_by_chunk.get(str(candidate.chunk["chunk_id"]), ()),
        )
        for candidate in observation.final_candidates
    ]
    target_boundaries = []
    for source_chunk_id, target_identity in sorted(target["relevant"].items()):
        source_document_id = target_identity["document_id"]
        backend_observations = []
        for backend in ("elasticsearch_bm25", "milvus_dense_bge_m3"):
            route = next(
                item
                for item in backend_ladders
                if item["backend"] == backend
                and item["source_document_id"] == source_document_id
            )
            returned = next(
                (
                    item
                    for item in route["candidates"]
                    if item["source_chunk_id"] == source_chunk_id
                ),
                None,
            )
            backend_observations.append(
                {
                    "backend": backend,
                    "state": (
                        "RETURNED_TO_FUSION"
                        if returned is not None
                        else "NOT_OBSERVED_WITHIN_BACKEND_REQUEST_BOUNDARY"
                    ),
                    "rank": returned["rank"] if returned is not None else None,
                    "returned_but_below_configured_cutoff": False,
                }
            )
        fused_match = next(
            (item for item in fused if item["source_chunk_id"] == source_chunk_id),
            None,
        )
        final_match = next(
            (item for item in final if item["source_chunk_id"] == source_chunk_id),
            None,
        )
        target_boundaries.append(
            {
                "source_chunk_id": source_chunk_id,
                "source_document_id": source_document_id,
                "backend_observations": backend_observations,
                "rrf_rank": fused_match["rank"] if fused_match is not None else None,
                "final_top3_rank": (
                    final_match["rank"] if final_match is not None else None
                ),
            }
        )
    return {
        "configuration": {
            "candidate_k": observation.candidate_k,
            "rrf_k": observation.rrf_k,
            "final_top_k": observation.final_top_k,
            "vector_min_score": observation.vector_min_score,
            "query_decomposition_enabled": False,
            "route_coverage_enabled": False,
            "reranker_enabled": False,
        },
        "cutoff_boundary": {
            "backend_request_candidate_k": observation.candidate_k,
            "pre_cutoff_ranking_observed": observation.pre_cutoff_ranking_observed,
            "returned_candidates_forwarded_to_fusion": True,
            "below_backend_request_boundary": "UNOBSERVED_NOT_INFERRED",
        },
        "backend_ladders": backend_ladders,
        "target_boundaries": target_boundaries,
        "rrf_ladder": fused,
        "final_top3": final,
    }


def _coverage(
    records: Sequence[Mapping[str, Any]],
) -> set[str]:
    return {
        str(record["source_document_id"])
        for record in records
        if record.get("target_match") is True
    }


def _classify(ladder: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
    required = set(target["required_documents"])
    es_records = [
        candidate
        for route in ladder["backend_ladders"]
        if route["backend"] == "elasticsearch_bm25"
        for candidate in route["candidates"]
    ]
    milvus_records = [
        candidate
        for route in ladder["backend_ladders"]
        if route["backend"] == "milvus_dense_bge_m3"
        for candidate in route["candidates"]
    ]
    es = _coverage(es_records)
    milvus = _coverage(milvus_records)
    fused = _coverage(ladder["rrf_ladder"])
    final = _coverage(ladder["final_top3"])
    es_missing = sorted(required - es)
    milvus_missing = sorted(required - milvus)
    fused_missing = sorted(required - fused)
    final_missing = sorted(required - final)
    backend_causes: list[str] = []
    if es_missing:
        backend_causes.append("ES_CANDIDATE_RETRIEVAL")
    if milvus_missing:
        backend_causes.append("MILVUS_CANDIDATE_RETRIEVAL")

    if fused_missing:
        shared_missing = sorted(set(es_missing) & set(milvus_missing))
        if shared_missing:
            primary = "ES_CANDIDATE_RETRIEVAL"
            co_primary = "MILVUS_CANDIDATE_RETRIEVAL"
        else:
            primary = "RRF_FUSION_OR_RANKING"
            co_primary = None
    elif final_missing:
        primary = "RRF_FUSION_OR_RANKING"
        co_primary = None
    else:
        primary = "INCONCLUSIVE_WITH_CURRENT_EVIDENCE"
        co_primary = None

    return {
        "primary_classification": primary,
        "co_primary_classification": co_primary,
        "backend_candidate_causes": backend_causes,
        "required_source_documents": sorted(required),
        "es_target_documents_observed": sorted(es),
        "milvus_target_documents_observed": sorted(milvus),
        "rrf_target_documents_observed": sorted(fused),
        "final_top3_target_documents_observed": sorted(final),
        "es_missing_target_documents": es_missing,
        "milvus_missing_target_documents": milvus_missing,
        "rrf_missing_target_documents": fused_missing,
        "final_top3_missing_target_documents": final_missing,
        "candidate_cutoff_classification": "UNAVAILABLE_PRE_CUTOFF_NOT_OBSERVED",
    }


def run_diagnostic(args: argparse.Namespace) -> dict[str, Any]:
    inputs = load_input_package(
        args.input_root,
        expected_manifest_sha256=args.expected_manifest_sha256,
    )
    source_document_ids = _source_document_ids()
    dev_by_id = {row["question_id"]: row for row in inputs["dev_rows"]}
    if set(TARGET_IDS) - set(dev_by_id):
        raise GateError("FROZEN_TARGET_COHORT_INCOMPLETE")
    targets = [dev_by_id[question_id] for question_id in TARGET_IDS]
    target_contracts = {
        row["question_id"]: _target_contract(row) for row in targets
    }

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
    owner_id = f"phase3_candidate_ladder_{args.run_id}"
    if repository.resolve_online_versions(owner_id=owner_id):
        raise GateError("ISOLATED_OWNER_ALREADY_HAS_READY_VERSION")

    versions = []
    report: dict[str, Any] | None = None
    primary_error: BaseException | None = None
    primary_stage = "INGEST_AND_PUBLISH"
    cleanup_stage = "NOT_STARTED"
    cleanup_results: tuple[Any, ...] = ()
    inactive_403 = False
    reconciliation_failed_closed = False
    control_client: TestClient | None = None
    cleanup_summary: dict[str, Any] | None = None
    try:
        document_id_map: dict[str, str] = {}
        now = datetime.now(timezone.utc)
        for source_document_id in source_document_ids:
            pdf_path = args.input_root / "papers" / f"{source_document_id}.pdf"
            runtime = prepare_and_persist_pdf_ingestion(
                pdf_path.read_bytes(),
                repository=repository,
                object_store=pdf_objects,
                owner_id=owner_id,
                paper_id=f"{source_document_id}_{args.run_id}",
                source_type="uploaded",
                source_created_time=now,
                source_updated_time=now,
                idempotency_key=f"phase3_ladder_{source_document_id}_{args.run_id}",
                strategy="section_parent_child_v1",
                library_scope_ids=[f"phase3_candidate_ladder_{args.run_id}"],
                expected_sha256=ASSETS[f"papers/{source_document_id}.pdf"]["sha256"],
            )
            publication = publish_prepared_indexes(
                runtime.preparation,
                repository=repository,
                elasticsearch=elasticsearch,
                milvus=milvus,
            )
            versions.append(publication.version)
            document_id_map[source_document_id] = publication.version.document_id

        primary_stage = "VERIFY_READY_SCOPE"
        ready = reconcile_ready_scope(
            repository=repository,
            elasticsearch=elasticsearch,
            milvus=milvus,
            owner_id=owner_id,
            document_ids=[version.document_id for version in versions],
        )
        if len(ready.versions) != 3:
            raise GateError("READY_RECONCILIATION_COUNT_INVALID")
        primary_stage = "VERIFY_RUNTIME_CHUNK_IDENTITY"
        runtime_chunks = repository.load_online_chunks(
            owner_id=owner_id,
            document_version_ids=[version.document_version_id for version in versions],
        )
        _, runtime_to_source = remap_runtime_chunks(
            inputs["frozen_chunks"],
            [chunk.model_dump(mode="json") for chunk in runtime_chunks],
            document_id_map,
        )
        model_identity = embedding.identity()
        resolver = PostgresReadyRouteResolver(
            repository=repository,
            elasticsearch=elasticsearch,
            milvus=milvus,
        )
        observations: list[OnlineCandidateLadderObservation] = []
        retriever = OnlineVersionRrfRetriever(
            resolver=resolver,
            elasticsearch_transport=es_transport,
            milvus_transport=milvus_transport,
            embedding_provider=embedding,
            chunk_snapshots=repository,
            candidate_k=20,
            rrf_k=60,
            candidate_ladder_observer=observations.append,
        )
        control_client = TestClient(
            create_app(
                retrieval_backend="online_remote_rrf",
                authenticated_owner_id=owner_id,
                online_rrf_retriever=retriever,
            )
        )

        primary_stage = "RUN_FROZEN_4_CONTROL_DIAGNOSTIC"
        cases = []
        for row in targets:
            before = len(observations)
            document_ids = [
                document_id_map[source_id]
                for source_id in row["final_labels"]["expected_filters"]["document_ids"]
            ]
            ranking = retriever.search(
                row["question"],
                _scope(owner_id, document_ids),
                owner_id=owner_id,
                document_ids=document_ids,
                top_k=3,
            )
            if len(observations) != before + 1:
                raise GateError("DIAGNOSTIC_OBSERVATION_CARDINALITY_INVALID")
            target = target_contracts[row["question_id"]]
            ladder = _serialize_observation(
                observations[-1],
                runtime_to_source=runtime_to_source,
                document_id_map=document_id_map,
                target=target,
            )
            classification = _classify(ladder, target)
            cases.append(
                {
                    "case_id": row["question_id"],
                    "required_source_documents": target["required_documents"],
                    "required_source_chunk_ids": sorted(target["relevant"]),
                    "frozen_bilateral_metric_passed": _strict_two_sided(
                        row,
                        [dict(candidate.chunk) for candidate in ranking],
                        runtime_to_source,
                    ),
                    "ladder": ladder,
                    "classification": classification,
                }
            )

        classifications = [
            case["classification"]["primary_classification"] for case in cases
        ]
        localization_complete = all(
            value != "INCONCLUSIVE_WITH_CURRENT_EVIDENCE"
            for value in classifications
        )
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "PASS",
            "experiment_decision": (
                "LOCALIZATION_COMPLETE"
                if localization_complete
                else "LOCALIZATION_INCONCLUSIVE"
            ),
            "execution_boundary": EXECUTION_BOUNDARY,
            "identity": {
                "run_id": args.run_id,
                "source_commit": args.expected_head_commit,
                "input_manifest_sha256": inputs["manifest_sha256"],
                "cohort": list(TARGET_IDS),
                "cohort_sha256": TARGET_IDS_SHA256,
                "owner_id": owner_id,
                "ready_document_count": 3,
                "runtime_chunk_count": len(runtime_chunks),
                "document_id_map": document_id_map,
                "embedding": {
                    "provider": model_identity.provider,
                    "model": model_identity.model,
                    "digest": model_identity.digest,
                },
                "routes": [
                    {
                        "source_document_id": source_document_id,
                        "runtime_document_id": runtime_document_id,
                        "document_version_id": next(
                            version.document_version_id
                            for version in versions
                            if version.document_id == runtime_document_id
                        ),
                        "elasticsearch_index": elasticsearch.physical_index_name(
                            owner_id=owner_id,
                            document_version_id=next(
                                version.document_version_id
                                for version in versions
                                if version.document_id == runtime_document_id
                            ),
                        ),
                        "milvus_collection": milvus.physical_collection_name(
                            owner_id=owner_id,
                            document_version_id=next(
                                version.document_version_id
                                for version in versions
                                if version.document_id == runtime_document_id
                            ),
                        ),
                    }
                    for source_document_id, runtime_document_id in sorted(
                        document_id_map.items()
                    )
                ],
                "configuration": {
                    "candidate_k": 20,
                    "rrf_k": 60,
                    "final_top_k": 3,
                    "query_decomposition_enabled": False,
                    "route_coverage_enabled": False,
                    "reranker_enabled": False,
                },
            },
            "cases": cases,
            "aggregate": {
                "case_count": len(cases),
                "primary_classification_counts": {
                    value: classifications.count(value)
                    for value in sorted(set(classifications))
                },
                "scope": "FROZEN_4_DEV_ONLY",
            },
            "split_isolation": {
                "dev": "USED_FROZEN_4_ONLY",
                "test": "NOT_READ_NOT_RUN",
                "acceptance": "NOT_READ_NOT_RUN",
            },
            "behavior_freeze": {
                "retrieval_requests_added": 0,
                "backend_candidate_count_changed": False,
                "retrieval_scoring_changed": False,
                "public_answer_api_schema_changed": False,
                "generation_or_judge_calls": 0,
            },
            "performance_boundary": "NO_300MS_SLO_CONCLUSION_DIAGNOSTIC_METADATA_ONLY",
            "strategy_handoff": "NO_NEXT_ALGORITHM_SELECTED",
        }
        primary_stage = "COMPLETE"
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
                    question="Deleted isolated diagnostic content must remain unavailable.",
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
                "status": (
                    "PASS"
                    if cleanup_ok and inactive_403 and reconciliation_failed_closed
                    else "FAIL"
                ),
                "scheduled_versions": len(versions),
                "jobs_succeeded": sum(result.succeeded for result in cleanup_results),
                "jobs_observed": len(cleanup_results),
                "jobs_expected": EXPECTED_CLEANUP_JOBS,
                "ready_reconciliation_failed_closed": reconciliation_failed_closed,
                "deleted_answer_api_status": 403 if inactive_403 else None,
            }
        except BaseException:
            cleanup_summary = {
                "status": "FAIL",
                "stage": cleanup_stage,
                "scheduled_versions": len(versions),
                "jobs_succeeded": sum(result.succeeded for result in cleanup_results),
                "jobs_observed": len(cleanup_results),
                "jobs_expected": EXPECTED_CLEANUP_JOBS,
                "ready_reconciliation_failed_closed": reconciliation_failed_closed,
                "deleted_answer_api_status": 403 if inactive_403 else None,
            }
        connection.close()

    if report is None:
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "FAIL",
            "experiment_decision": "BLOCKED",
            "error_code": _sanitized_code(
                primary_error or GateError("PHASE3_CANDIDATE_LADDER_FAILED")
            ),
            "execution_boundary": EXECUTION_BOUNDARY,
            "split_isolation": {
                "dev": "FROZEN_INPUT_ONLY_OR_VALIDATION_REFUSED",
                "test": "NOT_READ_NOT_RUN",
                "acceptance": "NOT_READ_NOT_RUN",
            },
            "performance_boundary": "NO_300MS_SLO_CONCLUSION",
            "strategy_handoff": "NO_NEXT_ALGORITHM_SELECTED",
        }
    report["run_id"] = args.run_id
    report["head_commit"] = args.expected_head_commit
    report["input_manifest_sha256"] = inputs["manifest_sha256"]
    report["cohort_sha256"] = TARGET_IDS_SHA256
    report["primary_stage"] = primary_stage
    report["cleanup"] = cleanup_summary
    if primary_error is not None:
        report["primary_error_code"] = _sanitized_code(primary_error)
    if cleanup_summary is None or cleanup_summary.get("status") != "PASS":
        report["status"] = "FAIL"
        report["experiment_decision"] = "BLOCKED"
        report["error_code"] = "CLEANUP_PROOF_FAILED"
    return report


def main() -> int:
    args = build_parser().parse_args()
    invalid = (
        args.confirm != CONFIRMATION
        or args.run_id != DIAGNOSTIC_RUN_ID
        or not _RUN_ID.fullmatch(args.run_id)
        or not _COMMIT.fullmatch(args.expected_head_commit)
        or "canary" not in args.es_index_prefix
        or "canary" not in args.milvus_collection_prefix
    )
    if invalid:
        print(
            '{"status":"REFUSED","error_code":"PHASE3_CANDIDATE_LADDER_ARGUMENTS_INVALID"}',
            file=sys.stderr,
        )
        return 2
    try:
        _validate_safe_runtime_path(args.input_root, directory=True)
        _validate_safe_runtime_path(args.output)
        _validate_safe_runtime_path(args.pdf_object_root)
        if _repository_head() != args.expected_head_commit:
            raise GateError("REPOSITORY_HEAD_MISMATCH")
        report = run_diagnostic(args)
        _write_report(args.output, report)
    except Exception as exc:
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "FAIL",
            "experiment_decision": "BLOCKED",
            "error_code": _sanitized_code(exc),
            "run_id": args.run_id,
            "head_commit": args.expected_head_commit,
            "cohort_sha256": TARGET_IDS_SHA256,
            "cleanup": {"status": "NOT_STARTED"},
            "split_isolation": {
                "dev": "VALIDATION_REFUSED",
                "test": "NOT_READ_NOT_RUN",
                "acceptance": "NOT_READ_NOT_RUN",
            },
            "performance_boundary": "NO_300MS_SLO_CONCLUSION",
            "strategy_handoff": "NO_NEXT_ALGORITHM_SELECTED",
        }
        _write_report(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
