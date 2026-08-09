#!/usr/bin/env python3
"""Strictly adjudicate one Phase 3 candidate-ladder localization report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if not sys.path or Path(sys.path[0]).resolve() != REPOSITORY_ROOT:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.build_phase3_comparison_dev_package import TARGET_IDS, TARGET_IDS_SHA256
from scripts.run_phase3_candidate_ladder_localization import (
    DIAGNOSTIC_RUN_ID,
    EXECUTION_BOUNDARY,
    REPORT_SCHEMA_VERSION,
    _classify,
)


ADJUDICATION_SCHEMA_VERSION = "phase3_candidate_ladder_localization_adjudication_v1"
_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_COMMIT = re.compile(r"^[a-f0-9]{40}$")


class ReportRejected(ValueError):
    """The report cannot support a localization decision."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-report-sha256", required=True)
    parser.add_argument("--expected-head-commit", required=True)
    parser.add_argument("--expected-input-manifest-sha256", required=True)
    parser.add_argument("--expected-run-id", default=DIAGNOSTIC_RUN_ID)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _runtime_path(path: Path, *, must_exist: bool = False) -> None:
    if (
        path.is_absolute()
        or not path.parts
        or path.parts[0] != "runtime"
        or ".." in path.parts
    ):
        raise ReportRejected("UNSAFE_RUNTIME_PATH")
    if must_exist and not path.is_file():
        raise ReportRejected("REPORT_MISSING")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ReportRejected(code)
    return value


def _sequence(value: Any, code: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise ReportRejected(code)
    return value


def _number(value: Any, code: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ReportRejected(code)
    return float(value)


def _validate_identity(
    report: Mapping[str, Any],
    *,
    expected_head_commit: str,
    expected_input_manifest_sha256: str,
    expected_run_id: str,
) -> None:
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ReportRejected("REPORT_SCHEMA_INVALID")
    if report.get("execution_boundary") != EXECUTION_BOUNDARY:
        raise ReportRejected("REPORT_EXECUTION_BOUNDARY_INVALID")
    if report.get("head_commit") != expected_head_commit:
        raise ReportRejected("REPORT_HEAD_COMMIT_MISMATCH")
    if report.get("run_id") != expected_run_id:
        raise ReportRejected("REPORT_RUN_ID_MISMATCH")
    if report.get("input_manifest_sha256") != expected_input_manifest_sha256:
        raise ReportRejected("REPORT_INPUT_MANIFEST_IDENTITY_MISMATCH")
    if report.get("cohort_sha256") != TARGET_IDS_SHA256:
        raise ReportRejected("REPORT_COHORT_IDENTITY_MISMATCH")
    identity = _mapping(report.get("identity"), "REPORT_IDENTITY_MISSING")
    if (
        identity.get("run_id") != expected_run_id
        or identity.get("source_commit") != expected_head_commit
        or identity.get("input_manifest_sha256")
        != expected_input_manifest_sha256
        or identity.get("cohort") != list(TARGET_IDS)
        or identity.get("cohort_sha256") != TARGET_IDS_SHA256
        or identity.get("ready_document_count") != 3
        or identity.get("runtime_chunk_count") != 316
    ):
        raise ReportRejected("REPORT_IDENTITY_INVALID")
    embedding = _mapping(identity.get("embedding"), "REPORT_MODEL_IDENTITY_MISSING")
    if (
        embedding.get("provider") != "ollama"
        or not isinstance(embedding.get("model"), str)
        or not embedding["model"]
        or not isinstance(embedding.get("digest"), str)
        or not embedding["digest"]
    ):
        raise ReportRejected("REPORT_MODEL_IDENTITY_INVALID")
    configuration = _mapping(
        identity.get("configuration"), "REPORT_CONFIG_IDENTITY_MISSING"
    )
    if configuration != {
        "candidate_k": 20,
        "rrf_k": 60,
        "final_top_k": 3,
        "query_decomposition_enabled": False,
        "route_coverage_enabled": False,
        "reranker_enabled": False,
    }:
        raise ReportRejected("REPORT_CONFIG_IDENTITY_INVALID")
    routes = _sequence(identity.get("routes"), "REPORT_ROUTE_IDENTITY_MISSING")
    if len(routes) != 3:
        raise ReportRejected("REPORT_ROUTE_IDENTITY_INVALID")
    for route in routes:
        item = _mapping(route, "REPORT_ROUTE_IDENTITY_INVALID")
        for field in (
            "source_document_id",
            "runtime_document_id",
            "document_version_id",
            "elasticsearch_index",
            "milvus_collection",
        ):
            if not isinstance(item.get(field), str) or not item[field]:
                raise ReportRejected("REPORT_ROUTE_IDENTITY_INVALID")


def _validate_isolation_cleanup(report: Mapping[str, Any]) -> None:
    split = _mapping(report.get("split_isolation"), "REPORT_SPLIT_ISOLATION_MISSING")
    if (
        split.get("dev") != "USED_FROZEN_4_ONLY"
        or split.get("test") != "NOT_READ_NOT_RUN"
        or split.get("acceptance") != "NOT_READ_NOT_RUN"
    ):
        raise ReportRejected("REPORT_SPLIT_ISOLATION_INVALID")
    if report.get("performance_boundary") != (
        "NO_300MS_SLO_CONCLUSION_DIAGNOSTIC_METADATA_ONLY"
    ):
        raise ReportRejected("REPORT_PERFORMANCE_BOUNDARY_INVALID")
    if report.get("strategy_handoff") != "NO_NEXT_ALGORITHM_SELECTED":
        raise ReportRejected("REPORT_STRATEGY_BOUNDARY_INVALID")
    behavior = _mapping(report.get("behavior_freeze"), "REPORT_BEHAVIOR_FREEZE_MISSING")
    if behavior != {
        "retrieval_requests_added": 0,
        "backend_candidate_count_changed": False,
        "retrieval_scoring_changed": False,
        "public_answer_api_schema_changed": False,
        "generation_or_judge_calls": 0,
    }:
        raise ReportRejected("REPORT_BEHAVIOR_FREEZE_INVALID")
    cleanup = _mapping(report.get("cleanup"), "REPORT_CLEANUP_MISSING")
    if (
        cleanup.get("status") != "PASS"
        or cleanup.get("scheduled_versions") != 3
        or cleanup.get("jobs_succeeded") != 9
        or cleanup.get("jobs_observed") != 9
        or cleanup.get("jobs_expected") != 9
        or cleanup.get("ready_reconciliation_failed_closed") is not True
        or cleanup.get("deleted_answer_api_status") != 403
    ):
        raise ReportRejected("REPORT_CLEANUP_PROOF_INVALID")


def _candidate_identity(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        candidate.get("runtime_chunk_id"),
        candidate.get("source_chunk_id"),
        candidate.get("runtime_document_id"),
        candidate.get("source_document_id"),
        candidate.get("page_start"),
        candidate.get("page_end"),
        candidate.get("section_path"),
        candidate.get("target_match"),
        candidate.get("target_relevance"),
    )


def _validate_candidate(
    candidate: Mapping[str, Any],
    *,
    expected_rank: int,
    required_chunk_ids: set[str],
) -> None:
    if candidate.get("rank") != expected_rank:
        raise ReportRejected("REPORT_CANDIDATE_RANK_INVALID")
    _number(candidate.get("score"), "REPORT_CANDIDATE_SCORE_INVALID")
    for field in (
        "runtime_chunk_id",
        "source_chunk_id",
        "runtime_document_id",
        "source_document_id",
    ):
        if not isinstance(candidate.get(field), str) or not candidate[field]:
            raise ReportRejected("REPORT_CANDIDATE_IDENTITY_INVALID")
    if (
        not isinstance(candidate.get("page_start"), int)
        or not isinstance(candidate.get("page_end"), int)
        or candidate["page_start"] < 1
        or candidate["page_start"] > candidate["page_end"]
        or not isinstance(candidate.get("section_path"), str)
        or candidate.get("target_match")
        is not (candidate["source_chunk_id"] in required_chunk_ids)
    ):
        raise ReportRejected("REPORT_CANDIDATE_IDENTITY_INVALID")


def _validate_case(case: Mapping[str, Any], *, expected_case_id: str) -> str:
    if case.get("case_id") != expected_case_id:
        raise ReportRejected("REPORT_CASE_IDENTITY_INVALID")
    required_documents = _sequence(
        case.get("required_source_documents"),
        "REPORT_CASE_TARGET_DOCUMENTS_INVALID",
    )
    required_chunks = _sequence(
        case.get("required_source_chunk_ids"),
        "REPORT_CASE_TARGET_CHUNKS_INVALID",
    )
    if (
        len(required_documents) != 2
        or len(set(required_documents)) != 2
        or not required_chunks
        or len(set(required_chunks)) != len(required_chunks)
    ):
        raise ReportRejected("REPORT_CASE_TARGET_IDENTITY_INVALID")
    required_chunk_ids = set(required_chunks)
    ladder = _mapping(case.get("ladder"), "REPORT_CASE_LADDER_MISSING")
    configuration = _mapping(
        ladder.get("configuration"), "REPORT_CASE_CONFIG_MISSING"
    )
    if configuration != {
        "candidate_k": 20,
        "rrf_k": 60,
        "final_top_k": 3,
        "vector_min_score": 0.5,
        "query_decomposition_enabled": False,
        "route_coverage_enabled": False,
        "reranker_enabled": False,
    }:
        raise ReportRejected("REPORT_CASE_CONFIG_INVALID")
    cutoff = _mapping(ladder.get("cutoff_boundary"), "REPORT_CUTOFF_MISSING")
    if cutoff != {
        "backend_request_candidate_k": 20,
        "pre_cutoff_ranking_observed": False,
        "returned_candidates_forwarded_to_fusion": True,
        "below_backend_request_boundary": "UNOBSERVED_NOT_INFERRED",
    }:
        raise ReportRejected("REPORT_CUTOFF_BOUNDARY_INVALID")

    backend_ladders = _sequence(
        ladder.get("backend_ladders"), "REPORT_BACKEND_LADDERS_MISSING"
    )
    if len(backend_ladders) != 4:
        raise ReportRejected("REPORT_BACKEND_LADDER_COUNT_INVALID")
    seen_routes: set[tuple[str, str]] = set()
    identities: dict[str, tuple[Any, ...]] = {}
    source_membership: dict[str, list[dict[str, Any]]] = {}
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for route in backend_ladders:
        item = _mapping(route, "REPORT_BACKEND_LADDER_INVALID")
        backend = item.get("backend")
        source_document_id = item.get("source_document_id")
        if (
            backend not in {"elasticsearch_bm25", "milvus_dense_bge_m3"}
            or source_document_id not in required_documents
            or (backend, source_document_id) in seen_routes
            or item.get("requested_candidate_k") != 20
        ):
            raise ReportRejected("REPORT_BACKEND_LADDER_IDENTITY_INVALID")
        seen_routes.add((backend, source_document_id))
        candidates = _sequence(
            item.get("candidates"), "REPORT_BACKEND_CANDIDATES_INVALID"
        )
        if item.get("returned_candidate_count") != len(candidates) or len(candidates) > 20:
            raise ReportRejected("REPORT_BACKEND_CANDIDATE_COUNT_INVALID")
        local_ids: set[str] = set()
        for rank, candidate_value in enumerate(candidates, 1):
            candidate = _mapping(candidate_value, "REPORT_CANDIDATE_INVALID")
            _validate_candidate(
                candidate,
                expected_rank=rank,
                required_chunk_ids=required_chunk_ids,
            )
            runtime_chunk_id = candidate["runtime_chunk_id"]
            if runtime_chunk_id in local_ids:
                raise ReportRejected("REPORT_BACKEND_CANDIDATE_DUPLICATE")
            local_ids.add(runtime_chunk_id)
            identity = _candidate_identity(candidate)
            if runtime_chunk_id in identities and identities[runtime_chunk_id] != identity:
                raise ReportRejected("REPORT_BACKEND_CANDIDATE_IDENTITY_DRIFT")
            identities[runtime_chunk_id] = identity
            membership = {
                "backend": backend,
                "source_document_id": source_document_id,
                "rank": rank,
            }
            source_membership.setdefault(runtime_chunk_id, []).append(membership)
            scores[runtime_chunk_id] = scores.get(runtime_chunk_id, 0.0) + 1.0 / (
                60 + rank
            )
            best_rank[runtime_chunk_id] = min(
                best_rank.get(runtime_chunk_id, rank), rank
            )
    if seen_routes != {
        (backend, document)
        for backend in ("elasticsearch_bm25", "milvus_dense_bge_m3")
        for document in required_documents
    }:
        raise ReportRejected("REPORT_BACKEND_LADDER_COVERAGE_INVALID")

    expected_order = sorted(
        scores,
        key=lambda chunk_id: (-scores[chunk_id], best_rank[chunk_id], chunk_id),
    )
    fused = _sequence(ladder.get("rrf_ladder"), "REPORT_RRF_LADDER_MISSING")
    if len(fused) != len(expected_order):
        raise ReportRejected("REPORT_RRF_CANDIDATE_COUNT_INVALID")
    for rank, (candidate_value, expected_chunk_id) in enumerate(
        zip(fused, expected_order, strict=True), 1
    ):
        candidate = _mapping(candidate_value, "REPORT_RRF_CANDIDATE_INVALID")
        _validate_candidate(
            candidate,
            expected_rank=rank,
            required_chunk_ids=required_chunk_ids,
        )
        if (
            candidate["runtime_chunk_id"] != expected_chunk_id
            or _candidate_identity(candidate) != identities[expected_chunk_id]
            or not math.isclose(
                float(candidate["score"]),
                scores[expected_chunk_id],
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or candidate.get("source_membership")
            != source_membership[expected_chunk_id]
        ):
            raise ReportRejected("REPORT_RRF_ARITHMETIC_INVALID")

    final = _sequence(ladder.get("final_top3"), "REPORT_FINAL_TOP3_MISSING")
    if len(final) != min(3, len(fused)):
        raise ReportRejected("REPORT_FINAL_TOP3_COUNT_INVALID")
    for rank, candidate_value in enumerate(final, 1):
        candidate = _mapping(candidate_value, "REPORT_FINAL_TOP3_INVALID")
        _validate_candidate(
            candidate,
            expected_rank=rank,
            required_chunk_ids=required_chunk_ids,
        )
        if candidate != fused[rank - 1]:
            raise ReportRejected("REPORT_FINAL_TOP3_NOT_RRF_PREFIX")

    target_boundaries = _sequence(
        ladder.get("target_boundaries"), "REPORT_TARGET_BOUNDARIES_MISSING"
    )
    if len(target_boundaries) != len(required_chunk_ids):
        raise ReportRejected("REPORT_TARGET_BOUNDARY_COUNT_INVALID")
    observed_target_ids: set[str] = set()
    for boundary_value in target_boundaries:
        boundary = _mapping(boundary_value, "REPORT_TARGET_BOUNDARY_INVALID")
        source_chunk_id = boundary.get("source_chunk_id")
        source_document_id = boundary.get("source_document_id")
        if (
            source_chunk_id not in required_chunk_ids
            or source_chunk_id in observed_target_ids
            or source_document_id not in required_documents
        ):
            raise ReportRejected("REPORT_TARGET_BOUNDARY_IDENTITY_INVALID")
        observed_target_ids.add(source_chunk_id)
        backend_observations = _sequence(
            boundary.get("backend_observations"),
            "REPORT_TARGET_BACKEND_OBSERVATIONS_INVALID",
        )
        if len(backend_observations) != 2:
            raise ReportRejected("REPORT_TARGET_BACKEND_OBSERVATIONS_INVALID")
        observed_backends: set[str] = set()
        for observation_value in backend_observations:
            observation = _mapping(
                observation_value,
                "REPORT_TARGET_BACKEND_OBSERVATION_INVALID",
            )
            backend = observation.get("backend")
            if (
                backend not in {"elasticsearch_bm25", "milvus_dense_bge_m3"}
                or backend in observed_backends
                or observation.get("returned_but_below_configured_cutoff") is not False
            ):
                raise ReportRejected("REPORT_TARGET_BACKEND_OBSERVATION_INVALID")
            observed_backends.add(backend)
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
            expected_state = (
                "RETURNED_TO_FUSION"
                if returned is not None
                else "NOT_OBSERVED_WITHIN_BACKEND_REQUEST_BOUNDARY"
            )
            if (
                observation.get("state") != expected_state
                or observation.get("rank")
                != (returned["rank"] if returned is not None else None)
            ):
                raise ReportRejected("REPORT_TARGET_BACKEND_BOUNDARY_INVALID")
        fused_match = next(
            (item for item in fused if item["source_chunk_id"] == source_chunk_id),
            None,
        )
        final_match = next(
            (item for item in final if item["source_chunk_id"] == source_chunk_id),
            None,
        )
        if (
            boundary.get("rrf_rank")
            != (fused_match["rank"] if fused_match is not None else None)
            or boundary.get("final_top3_rank")
            != (final_match["rank"] if final_match is not None else None)
        ):
            raise ReportRejected("REPORT_TARGET_FUSION_BOUNDARY_INVALID")

    target = {
        "required_documents": list(required_documents),
        "relevant": {chunk_id: {} for chunk_id in required_chunk_ids},
    }
    expected_classification = _classify(ladder, target)
    classification = _mapping(
        case.get("classification"), "REPORT_CLASSIFICATION_MISSING"
    )
    if classification != expected_classification:
        raise ReportRejected("REPORT_CLASSIFICATION_INVALID")
    return str(classification["primary_classification"])


def adjudicate(
    report: Mapping[str, Any],
    *,
    expected_head_commit: str,
    expected_input_manifest_sha256: str,
    expected_run_id: str,
    report_sha256: str,
) -> dict[str, Any]:
    if report.get("status") != "PASS" or report.get("primary_stage") != "COMPLETE":
        raise ReportRejected("REPORT_EXECUTION_NOT_COMPLETE")
    _validate_identity(
        report,
        expected_head_commit=expected_head_commit,
        expected_input_manifest_sha256=expected_input_manifest_sha256,
        expected_run_id=expected_run_id,
    )
    _validate_isolation_cleanup(report)
    cases = _sequence(report.get("cases"), "REPORT_CASES_MISSING")
    if len(cases) != len(TARGET_IDS):
        raise ReportRejected("REPORT_CASE_COUNT_INVALID")
    classifications = [
        _validate_case(_mapping(case, "REPORT_CASE_INVALID"), expected_case_id=case_id)
        for case, case_id in zip(cases, TARGET_IDS, strict=True)
    ]
    complete = all(
        value != "INCONCLUSIVE_WITH_CURRENT_EVIDENCE"
        for value in classifications
    )
    decision = "LOCALIZATION_COMPLETE" if complete else "LOCALIZATION_INCONCLUSIVE"
    if report.get("experiment_decision") != decision:
        raise ReportRejected("REPORT_DECISION_INVALID")
    counts = {value: classifications.count(value) for value in sorted(set(classifications))}
    aggregate = _mapping(report.get("aggregate"), "REPORT_AGGREGATE_MISSING")
    if aggregate != {
        "case_count": 4,
        "primary_classification_counts": counts,
        "scope": "FROZEN_4_DEV_ONLY",
    }:
        raise ReportRejected("REPORT_AGGREGATE_INVALID")
    return {
        "schema_version": ADJUDICATION_SCHEMA_VERSION,
        "status": "PASS",
        "experiment_decision": decision,
        "report_sha256": report_sha256,
        "run_id": expected_run_id,
        "head_commit": expected_head_commit,
        "input_manifest_sha256": expected_input_manifest_sha256,
        "cohort_sha256": TARGET_IDS_SHA256,
        "case_count": 4,
        "classification_counts": counts,
        "cleanup": "PASS_9_OF_9_READY_CLOSED_DELETED_403",
        "strategy_handoff": "NO_NEXT_ALGORITHM_SELECTED",
    }


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    _runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        _runtime_path(args.report, must_exist=True)
        _runtime_path(args.output)
        if (
            not _HEX64.fullmatch(args.expected_report_sha256)
            or not _HEX64.fullmatch(args.expected_input_manifest_sha256)
            or not _COMMIT.fullmatch(args.expected_head_commit)
            or args.expected_run_id != DIAGNOSTIC_RUN_ID
            or _sha256(args.report) != args.expected_report_sha256
        ):
            raise ReportRejected("REPORT_EXPECTED_IDENTITY_INVALID")
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ReportRejected("REPORT_ROOT_INVALID")
        result = adjudicate(
            report,
            expected_head_commit=args.expected_head_commit,
            expected_input_manifest_sha256=args.expected_input_manifest_sha256,
            expected_run_id=args.expected_run_id,
            report_sha256=args.expected_report_sha256,
        )
        exit_code = 0
    except (OSError, json.JSONDecodeError, ReportRejected) as exc:
        code = str(exc)
        result = {
            "schema_version": ADJUDICATION_SCHEMA_VERSION,
            "status": "REJECTED",
            "experiment_decision": "BLOCKED",
            "error_code": (
                code
                if re.fullmatch(r"[A-Z][A-Z0-9_]{2,79}", code)
                else "REPORT_ADJUDICATION_FAILED"
            ),
            "strategy_handoff": "NO_NEXT_ALGORITHM_SELECTED",
        }
        exit_code = 1
    _write(args.output, result)
    print(json.dumps(result, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
