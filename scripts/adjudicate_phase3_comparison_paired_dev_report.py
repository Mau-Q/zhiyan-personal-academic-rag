#!/usr/bin/env python3
"""Strictly adjudicate one sanitized Phase 3 paired dev report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if not sys.path or Path(sys.path[0]).resolve() != REPOSITORY_ROOT:
    sys.path.insert(0, str(REPOSITORY_ROOT))


REPORT_SCHEMA_VERSION = "phase3_comparison_paired_dev_report_v1"
ADJUDICATION_SCHEMA_VERSION = "phase3_comparison_dev_adjudication_v1"
CONFIG_SHA256 = "87b969a1b0f006c3406ab01a24837c5ff129d08bedd0b2460a57122f9d0b0f2b"
TARGET_IDS_SHA256 = (
    "3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8"
)
_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_COMMIT = re.compile(r"^[a-f0-9]{40}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")


class ReportRejected(ValueError):
    """The report cannot support a dev decision."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-report-sha256", required=True)
    parser.add_argument("--expected-head-commit", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-input-manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_path(path: Path, *, must_exist: bool = False) -> None:
    if path.is_absolute() or not path.parts or path.parts[0] != "runtime":
        raise ReportRejected("UNSAFE_RUNTIME_PATH")
    if ".." in path.parts:
        raise ReportRejected("UNSAFE_RUNTIME_PATH")
    if must_exist and not path.is_file():
        raise ReportRejected("REPORT_MISSING")


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
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


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=0.000002)


def _validate_identity(
    report: Mapping[str, Any],
    *,
    expected_head_commit: str,
    expected_run_id: str,
    expected_input_manifest_sha256: str,
) -> None:
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ReportRejected("REPORT_SCHEMA_INVALID")
    if report.get("head_commit") != expected_head_commit:
        raise ReportRejected("REPORT_HEAD_COMMIT_MISMATCH")
    if report.get("run_id") != expected_run_id:
        raise ReportRejected("REPORT_RUN_ID_MISMATCH")
    if report.get("config_sha256") != CONFIG_SHA256:
        raise ReportRejected("REPORT_CONFIG_IDENTITY_MISMATCH")
    if report.get("target_ids_sha256") != TARGET_IDS_SHA256:
        raise ReportRejected("REPORT_TARGET_IDENTITY_MISMATCH")
    if report.get("input_manifest_sha256") != expected_input_manifest_sha256:
        raise ReportRejected("REPORT_INPUT_MANIFEST_IDENTITY_MISMATCH")


def _validate_isolation(report: Mapping[str, Any]) -> None:
    split = _mapping(report.get("split_isolation"), "REPORT_SPLIT_ISOLATION_MISSING")
    if (
        split.get("test") != "NOT_READ_NOT_RUN"
        or split.get("acceptance") != "NOT_READ_NOT_RUN"
    ):
        raise ReportRejected("REPORT_HOLDOUT_ISOLATION_VIOLATED")
    performance = str(report.get("performance_boundary", ""))
    if "NO_300MS_SLO_CONCLUSION" not in performance:
        raise ReportRejected("REPORT_PERFORMANCE_BOUNDARY_INVALID")


def _validate_cleanup(report: Mapping[str, Any]) -> None:
    cleanup = _mapping(report.get("cleanup"), "REPORT_CLEANUP_MISSING")
    if (
        cleanup.get("status") != "PASS"
        or cleanup.get("scheduled_versions") != 3
        or cleanup.get("jobs_succeeded") != 9
        or cleanup.get("jobs_expected") != 9
        or cleanup.get("ready_reconciliation_failed_closed") is not True
        or cleanup.get("deleted_answer_api_status") != 403
    ):
        raise ReportRejected("REPORT_CLEANUP_PROOF_INVALID")


def _validate_pass_metrics(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("error_code") is not None:
        raise ReportRejected("PASS_REPORT_ERROR_CODE_INVALID")
    if report.get("execution_boundary") != (
        "ISOLATED_DEV_ONLY_POSTGRES_READY_ES_MILVUS_RRF_CONTROL_TREATMENT"
    ):
        raise ReportRejected("PASS_REPORT_EXECUTION_BOUNDARY_INVALID")

    identity = _mapping(report.get("identity"), "PASS_REPORT_IDENTITY_MISSING")
    if (
        identity.get("ready_document_count") != 3
        or identity.get("runtime_chunk_count") != 316
        or identity.get("owner_acl_version_chunk_identity_violations") != 0
    ):
        raise ReportRejected("PASS_REPORT_IDENTITY_INVALID")

    control = _mapping(report.get("control"), "PASS_REPORT_CONTROL_MISSING")
    treatment = _mapping(report.get("treatment"), "PASS_REPORT_TREATMENT_MISSING")
    gains = _mapping(report.get("gains"), "PASS_REPORT_GAINS_MISSING")
    if (
        control.get("strict_two_sided_passed") != 0
        or control.get("total") != 4
        or treatment.get("total") != 4
        or treatment.get("strict_two_sided_passed") not in {3, 4}
    ):
        raise ReportRejected("PASS_REPORT_PRIMARY_TARGET_INVALID")
    control_recall = _number(
        control.get("macro_recall_at_3"),
        "PASS_REPORT_CONTROL_RECALL_INVALID",
    )
    treatment_recall = _number(
        treatment.get("macro_recall_at_3"),
        "PASS_REPORT_TREATMENT_RECALL_INVALID",
    )
    control_ndcg = _number(
        control.get("macro_ndcg_at_3"),
        "PASS_REPORT_CONTROL_NDCG_INVALID",
    )
    treatment_ndcg = _number(
        treatment.get("macro_ndcg_at_3"),
        "PASS_REPORT_TREATMENT_NDCG_INVALID",
    )
    strict_gain = _number(
        gains.get("strict_two_sided_absolute_gain"),
        "PASS_REPORT_STRICT_GAIN_INVALID",
    )
    recall_gain = _number(
        gains.get("macro_recall_at_3_absolute_gain"),
        "PASS_REPORT_RECALL_GAIN_INVALID",
    )
    ndcg_gain = _number(
        gains.get("macro_ndcg_at_3_absolute_gain"),
        "PASS_REPORT_NDCG_GAIN_INVALID",
    )
    expected_strict_gain = (
        treatment["strict_two_sided_passed"] - control["strict_two_sided_passed"]
    ) / 4
    if (
        not all(
            0.0 <= value <= 1.0
            for value in (
                control_recall,
                treatment_recall,
                control_ndcg,
                treatment_ndcg,
            )
        )
        or not _close(strict_gain, expected_strict_gain)
        or not _close(recall_gain, treatment_recall - control_recall)
        or not _close(ndcg_gain, treatment_ndcg - control_ndcg)
        or strict_gain < 0.5
        or recall_gain < 0.2
        or ndcg_gain < 0.1
    ):
        raise ReportRejected("PASS_REPORT_GAIN_INVALID")

    non_regression = _mapping(
        report.get("critical_non_regression"),
        "PASS_REPORT_NON_REGRESSION_MISSING",
    )
    control_recall_nr = _number(
        non_regression.get("control_recall_at_3"),
        "PASS_REPORT_NON_REGRESSION_RECALL_INVALID",
    )
    treatment_recall_nr = _number(
        non_regression.get("treatment_recall_at_3"),
        "PASS_REPORT_NON_REGRESSION_RECALL_INVALID",
    )
    recall_drop = _number(
        non_regression.get("recall_at_3_drop"),
        "PASS_REPORT_NON_REGRESSION_RECALL_INVALID",
    )
    control_ndcg_nr = _number(
        non_regression.get("control_ndcg_at_10"),
        "PASS_REPORT_NON_REGRESSION_NDCG_INVALID",
    )
    treatment_ndcg_nr = _number(
        non_regression.get("treatment_ndcg_at_10"),
        "PASS_REPORT_NON_REGRESSION_NDCG_INVALID",
    )
    ndcg_drop = _number(
        non_regression.get("ndcg_at_10_drop"),
        "PASS_REPORT_NON_REGRESSION_NDCG_INVALID",
    )
    if (
        non_regression.get("case_count") != 80
        or non_regression.get("recall_at_3_max_drop") != 0.01
        or non_regression.get("ndcg_at_10_max_drop") != 0.01
        or non_regression.get("top10_boundary")
        != "EVALUATION_DIAGNOSTIC_ONLY_PRODUCT_FINAL_TOP3_UNCHANGED"
        or not _close(recall_drop, control_recall_nr - treatment_recall_nr)
        or not _close(ndcg_drop, control_ndcg_nr - treatment_ndcg_nr)
        or not all(
            0.0 <= value <= 1.0
            for value in (
                control_recall_nr,
                treatment_recall_nr,
                control_ndcg_nr,
                treatment_ndcg_nr,
            )
        )
        or recall_drop > 0.01
        or ndcg_drop > 0.01
    ):
        raise ReportRejected("PASS_REPORT_NON_REGRESSION_INVALID")

    no_evidence = _mapping(
        report.get("dev_no_evidence"),
        "PASS_REPORT_NO_EVIDENCE_MISSING",
    )
    if (
        no_evidence.get("case_count") != 9
        or no_evidence.get("no_worse_than_control") is not True
        or not isinstance(
            no_evidence.get("control_no_evidence_zero_candidate_count"),
            int,
        )
        or isinstance(
            no_evidence.get("control_no_evidence_zero_candidate_count"),
            bool,
        )
        or not isinstance(
            no_evidence.get("treatment_no_evidence_zero_candidate_count"),
            int,
        )
        or isinstance(
            no_evidence.get("treatment_no_evidence_zero_candidate_count"),
            bool,
        )
        or not 0
        <= no_evidence["control_no_evidence_zero_candidate_count"]
        <= 9
        or not 0
        <= no_evidence["treatment_no_evidence_zero_candidate_count"]
        <= 9
        or no_evidence["treatment_no_evidence_zero_candidate_count"]
        < no_evidence["control_no_evidence_zero_candidate_count"]
    ):
        raise ReportRejected("PASS_REPORT_NO_EVIDENCE_INVALID")

    canary = _mapping(
        report.get("fixed_15_canary"),
        "PASS_REPORT_CANARY_MISSING",
    )
    if (
        canary.get("passed") != 15
        or canary.get("total") != 15
        or canary.get("category_passed")
        != {"ANSWERABLE": 9, "NO_EVIDENCE": 3, "FORBIDDEN": 3}
        or canary.get("exact_control_treatment_boundary") is not True
    ):
        raise ReportRejected("PASS_REPORT_CANARY_INVALID")

    cost = _mapping(report.get("cost"), "PASS_REPORT_COST_MISSING")
    control_p95 = _number(
        cost.get("control_retrieval_p95_ms"),
        "PASS_REPORT_COST_INVALID",
    )
    treatment_p95 = _number(
        cost.get("treatment_retrieval_p95_ms"),
        "PASS_REPORT_COST_INVALID",
    )
    incremental_p95 = _number(
        cost.get("incremental_retrieval_p95_ms"),
        "PASS_REPORT_COST_INVALID",
    )
    decomposition_p95 = _number(
        cost.get("decomposition_p95_ms"),
        "PASS_REPORT_COST_INVALID",
    )
    sample_count = cost.get("sample_count_per_arm")
    if (
        not isinstance(sample_count, int)
        or not 30 <= sample_count <= 100
        or cost.get("incremental_retrieval_p95_limit_ms") != 50.0
        or cost.get("decomposition_p95_limit_ms") != 5.0
        or cost.get("absolute_300ms_adjudication")
        != "NOT_RUN_SEPARATE_PERFORMANCE_GATE"
        or control_p95 < 0
        or treatment_p95 < 0
        or not _close(incremental_p95, treatment_p95 - control_p95)
        or incremental_p95 > 50.0
        or decomposition_p95 < 0
        or decomposition_p95 > 5.0
    ):
        raise ReportRejected("PASS_REPORT_COST_INVALID")

    tokens = _mapping(report.get("tokens"), "PASS_REPORT_TOKEN_COST_MISSING")
    operations = _mapping(
        report.get("operations"),
        "PASS_REPORT_OPERATION_COST_MISSING",
    )
    if tokens != {"new_llm_calls": 0, "new_generation_tokens": 0}:
        raise ReportRejected("PASS_REPORT_TOKEN_COST_INVALID")
    if (
        operations.get("new_services") != 0
        or operations.get("new_models") != 0
        or operations.get("new_indexes_beyond_three_isolated_version_routes") != 0
        or operations.get("database_migrations") != 0
        or operations.get("reranker_enabled") is not False
    ):
        raise ReportRejected("PASS_REPORT_OPERATION_COST_INVALID")
    return {
        "control_strict_two_sided_passed": 0,
        "treatment_strict_two_sided_passed": treatment[
            "strict_two_sided_passed"
        ],
        "strict_two_sided_absolute_gain": strict_gain,
        "macro_recall_at_3_absolute_gain": recall_gain,
        "macro_ndcg_at_3_absolute_gain": ndcg_gain,
        "non_target_recall_at_3_drop": recall_drop,
        "non_target_ndcg_at_10_drop": ndcg_drop,
        "fixed_15_canary_passed": 15,
        "incremental_retrieval_p95_ms": incremental_p95,
        "decomposition_p95_ms": decomposition_p95,
    }


def adjudicate_report(
    report_path: Path,
    *,
    expected_report_sha256: str,
    expected_head_commit: str,
    expected_run_id: str,
    expected_input_manifest_sha256: str,
) -> dict[str, Any]:
    _runtime_path(report_path, must_exist=True)
    if not _HEX64.fullmatch(expected_report_sha256):
        raise ReportRejected("EXPECTED_REPORT_SHA256_INVALID")
    if _sha256(report_path) != expected_report_sha256:
        raise ReportRejected("REPORT_SHA256_MISMATCH")
    if not _COMMIT.fullmatch(expected_head_commit):
        raise ReportRejected("EXPECTED_HEAD_COMMIT_INVALID")
    if not _RUN_ID.fullmatch(expected_run_id):
        raise ReportRejected("EXPECTED_RUN_ID_INVALID")
    if not _HEX64.fullmatch(expected_input_manifest_sha256):
        raise ReportRejected("EXPECTED_INPUT_MANIFEST_SHA256_INVALID")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ReportRejected("REPORT_ROOT_INVALID")
    _validate_identity(
        report,
        expected_head_commit=expected_head_commit,
        expected_run_id=expected_run_id,
        expected_input_manifest_sha256=expected_input_manifest_sha256,
    )
    _validate_isolation(report)
    _validate_cleanup(report)

    status = report.get("status")
    error_code = report.get("error_code")
    if status == "PASS":
        metrics = _validate_pass_metrics(report)
        return {
            "schema_version": ADJUDICATION_SCHEMA_VERSION,
            "status": "PASS",
            "decision": "DEV_CANDIDATE_PASS_AWAITING_FREEZE_COMMIT",
            "remote_gate_status": "PASS",
            "remote_error_code": None,
            "report_sha256": expected_report_sha256,
            "head_commit": expected_head_commit,
            "run_id": expected_run_id,
            "input_manifest_sha256": report["input_manifest_sha256"],
            "config_sha256": CONFIG_SHA256,
            "target_ids_sha256": TARGET_IDS_SHA256,
            "metrics": metrics,
            "default_enabled": False,
            "test_gate": "SEALED_REQUIRES_SEPARATE_FREEZE_COMMIT_AND_GATE",
            "acceptance": "SEALED_REQUIRES_EXPLICIT_AUTHORIZATION",
            "performance_gate": "PENDING_SEPARATE_300MS_GATE",
        }
    if status != "FAIL" or not isinstance(error_code, str) or not _ERROR_CODE.fullmatch(
        error_code
    ):
        raise ReportRejected("FAIL_REPORT_STATUS_INVALID")
    return {
        "schema_version": ADJUDICATION_SCHEMA_VERSION,
        "status": "FAIL",
        "decision": "KEEP_COMPARISON_DECOMPOSITION_DISABLED",
        "remote_gate_status": "FAIL",
        "remote_error_code": error_code,
        "report_sha256": expected_report_sha256,
        "head_commit": expected_head_commit,
        "run_id": expected_run_id,
        "input_manifest_sha256": report["input_manifest_sha256"],
        "config_sha256": CONFIG_SHA256,
        "target_ids_sha256": TARGET_IDS_SHA256,
        "metrics": None,
        "default_enabled": False,
        "test_gate": "SEALED_DEV_GATE_DID_NOT_PASS",
        "acceptance": "SEALED_REQUIRES_EXPLICIT_AUTHORIZATION",
        "performance_gate": "PENDING_SEPARATE_300MS_GATE",
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
        _runtime_path(args.output)
        adjudication = adjudicate_report(
            args.report,
            expected_report_sha256=args.expected_report_sha256,
            expected_head_commit=args.expected_head_commit,
            expected_run_id=args.expected_run_id,
            expected_input_manifest_sha256=args.expected_input_manifest_sha256,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        error_code = str(exc)
        if not _ERROR_CODE.fullmatch(error_code):
            error_code = "REPORT_ADJUDICATION_REJECTED"
        adjudication = {
            "schema_version": ADJUDICATION_SCHEMA_VERSION,
            "status": "REJECTED",
            "decision": "KEEP_COMPARISON_DECOMPOSITION_DISABLED",
            "error_code": error_code,
            "default_enabled": False,
            "test_gate": "SEALED_REPORT_NOT_TRUSTWORTHY",
            "acceptance": "SEALED_REQUIRES_EXPLICIT_AUTHORIZATION",
            "performance_gate": "PENDING_SEPARATE_300MS_GATE",
        }
    _write(args.output, adjudication)
    print(json.dumps(adjudication, ensure_ascii=False))
    if adjudication["status"] == "PASS":
        return 0
    if adjudication["status"] == "FAIL":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
