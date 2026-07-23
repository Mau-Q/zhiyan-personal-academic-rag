#!/usr/bin/env python3
"""Validate the frozen Phase 3 dev query plan without running retrieval."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if not sys.path or Path(sys.path[0]).resolve() != REPOSITORY_ROOT:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.retrieval.comparison_decomposition import (
    BilateralComparisonQueryDecomposer,
    load_bilateral_comparison_config,
)


SCHEMA_VERSION = "phase3_comparison_dev_plan_report_v1"
TARGET_IDS = (
    "local3.assisted.0033",
    "local3.assisted.0304",
    "local3.assisted.0383",
    "local3.assisted.0387",
)
TARGET_IDS_SHA256 = (
    "3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8"
)
DEFAULT_CONFIG = Path(
    "evaluation/phase3/bilateral-comparison-query-decomposition-v1.json"
)
DEFAULT_INPUT = Path(
    "runtime/handoffs/member-b-phase2-4-dev-review-input-v1/"
    "dev-claim-evidence-review-input-v1.jsonl"
)
DEFAULT_OUTPUT = Path(
    "runtime/evaluation/phase3-comparison-dev-v1/query-plan-report-v1.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repetitions", type=int, default=30)
    return parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _validate_output_path(path: Path) -> None:
    if path.is_absolute() or not path.parts or path.parts[0] != "runtime":
        raise ValueError("output must be a relative path under runtime")
    if ".." in path.parts:
        raise ValueError("output path must not escape runtime")


def _load_target_cases(path: Path) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        question_id = value.get("question_id")
        if question_id not in TARGET_IDS:
            continue
        if (
            value.get("schema_version") != "member_b_claim_evidence_review_input_v1"
            or value.get("split") != "dev"
            or value.get("selected_category") != "comparison"
            or not isinstance(value.get("question"), str)
            or not value["question"].strip()
        ):
            raise ValueError(f"target dev case is invalid at line {line_number}")
        final_labels = value.get("final_labels")
        if not isinstance(final_labels, dict):
            raise ValueError(f"target dev labels are invalid at line {line_number}")
        filters = final_labels.get("expected_filters")
        document_ids = (
            filters.get("document_ids") if isinstance(filters, dict) else None
        )
        if (
            final_labels.get("answerability") != "ANSWERABLE"
            or not isinstance(document_ids, list)
            or len(document_ids) != 2
            or len(set(document_ids)) != 2
            or any(not isinstance(item, str) or not item for item in document_ids)
        ):
            raise ValueError(f"target dev labels are invalid at line {line_number}")
        if question_id in cases:
            raise ValueError(f"duplicate target dev case: {question_id}")
        cases[question_id] = {
            "question": value["question"],
            "document_ids": tuple(document_ids),
        }
    if tuple(sorted(cases)) != tuple(sorted(TARGET_IDS)):
        raise ValueError("target dev case coverage is incomplete")
    return cases


def build_report(
    *,
    input_path: Path,
    expected_input_sha256: str,
    config_path: Path,
    repetitions: int,
) -> dict[str, Any]:
    if repetitions < 30 or repetitions > 1000:
        raise ValueError("repetitions must be between 30 and 1000")
    actual_input_sha256 = _sha256(input_path)
    if actual_input_sha256 != expected_input_sha256:
        raise ValueError("dev input identity does not match expected SHA-256")
    cases = _load_target_cases(input_path)
    config = load_bilateral_comparison_config(config_path)
    control = BilateralComparisonQueryDecomposer(config=config, enabled=False)
    treatment_latencies: list[float] = []
    treatment_observations = []
    treatment = BilateralComparisonQueryDecomposer(
        config=config,
        enabled=True,
        observer=treatment_observations.append,
    )
    case_reports: list[dict[str, Any]] = []
    for question_id in TARGET_IDS:
        case = cases[question_id]
        question = case["question"]
        document_ids = case["document_ids"]
        control_plan = control.plan(question, document_ids=document_ids)
        if (
            control_plan.status != "DISABLED"
            or control_plan.queries
            != {document_id: question for document_id in document_ids}
        ):
            raise ValueError("control did not preserve the original query")
        treatment_plan = treatment.plan(question, document_ids=document_ids)
        if treatment_plan.status != "APPLIED":
            raise ValueError(
                f"treatment plan was not applied for {question_id}: "
                f"{treatment_plan.failure_code}"
            )
        for _ in range(repetitions - 1):
            repeated = treatment.plan(question, document_ids=document_ids)
            if repeated.queries != treatment_plan.queries:
                raise ValueError("treatment decomposition is not deterministic")
        recent = treatment_observations[-repetitions:]
        treatment_latencies.extend(
            observation.decomposition_latency_ms for observation in recent
        )
        case_reports.append(
            {
                "question_id": question_id,
                "status": treatment_plan.status,
                "document_ids": list(document_ids),
                "original_query_sha256": _text_sha256(question),
                "route_query_sha256": {
                    document_id: _text_sha256(treatment_plan.queries[document_id])
                    for document_id in document_ids
                },
                "route_query_character_count": {
                    document_id: len(treatment_plan.queries[document_id])
                    for document_id in document_ids
                },
            }
        )
    p95 = _percentile(treatment_latencies, 0.95)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if p95 <= 5.0 else "FAIL",
        "execution_boundary": (
            "DEV_QUERY_PLAN_ONLY_NO_RETRIEVAL_NO_TEST_NO_ACCEPTANCE"
        ),
        "input_sha256": actual_input_sha256,
        "config_sha256": _sha256(config_path),
        "target_ids_sha256": TARGET_IDS_SHA256,
        "target_case_count": len(case_reports),
        "control": {
            "switch_enabled": False,
            "original_query_preserved_count": len(case_reports),
        },
        "treatment": {
            "switch_enabled": True,
            "applied_count": len(case_reports),
            "sample_count": len(treatment_latencies),
            "decomposition_p95_ms": round(p95, 6),
            "decomposition_p95_limit_ms": 5.0,
        },
        "cases": case_reports,
        "retrieval_metrics": None,
        "interpretation_boundary": (
            "This report proves deterministic dev query planning only. It does not "
            "prove ES/Milvus/RRF gain, non-regression, the 300 ms SLO, test, "
            "acceptance, or production readiness."
        ),
    }


def main() -> int:
    args = build_parser().parse_args()
    try:
        _validate_output_path(args.output)
        report = build_report(
            input_path=args.input,
            expected_input_sha256=args.expected_input_sha256,
            config_path=args.config,
            repetitions=args.repetitions,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "status": "REFUSED",
                    "error_code": "PHASE3_DEV_PLAN_INVALID",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
