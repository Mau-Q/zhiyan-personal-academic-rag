from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.adjudicate_phase3_comparison_paired_dev_report import (
    ReportRejected,
    adjudicate_report,
)


HEAD = "a" * 40
RUN_ID = "phase3_dev_synthetic_001"
INPUT_MANIFEST_SHA256 = "b" * 64
CONFIG_SHA256 = "87b969a1b0f006c3406ab01a24837c5ff129d08bedd0b2460a57122f9d0b0f2b"
TARGET_IDS_SHA256 = (
    "3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8"
)


def _pass_report() -> dict:
    return {
        "schema_version": "phase3_comparison_paired_dev_report_v1",
        "status": "PASS",
        "error_code": None,
        "run_id": RUN_ID,
        "head_commit": HEAD,
        "execution_boundary": (
            "ISOLATED_DEV_ONLY_POSTGRES_READY_ES_MILVUS_RRF_CONTROL_TREATMENT"
        ),
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "config_sha256": CONFIG_SHA256,
        "target_ids_sha256": TARGET_IDS_SHA256,
        "identity": {
            "ready_document_count": 3,
            "runtime_chunk_count": 316,
            "owner_acl_version_chunk_identity_violations": 0,
        },
        "control": {
            "strict_two_sided_passed": 0,
            "total": 4,
            "macro_recall_at_3": 0.1,
            "macro_ndcg_at_3": 0.2,
        },
        "treatment": {
            "strict_two_sided_passed": 3,
            "total": 4,
            "macro_recall_at_3": 0.35,
            "macro_ndcg_at_3": 0.32,
        },
        "gains": {
            "strict_two_sided_absolute_gain": 0.75,
            "macro_recall_at_3_absolute_gain": 0.25,
            "macro_ndcg_at_3_absolute_gain": 0.12,
        },
        "critical_non_regression": {
            "case_count": 80,
            "control_recall_at_3": 0.5,
            "treatment_recall_at_3": 0.5,
            "recall_at_3_drop": 0.0,
            "recall_at_3_max_drop": 0.01,
            "control_ndcg_at_10": 0.6,
            "treatment_ndcg_at_10": 0.595,
            "ndcg_at_10_drop": 0.005,
            "ndcg_at_10_max_drop": 0.01,
            "top10_boundary": (
                "EVALUATION_DIAGNOSTIC_ONLY_PRODUCT_FINAL_TOP3_UNCHANGED"
            ),
        },
        "dev_no_evidence": {
            "case_count": 9,
            "control_no_evidence_zero_candidate_count": 5,
            "treatment_no_evidence_zero_candidate_count": 5,
            "no_worse_than_control": True,
        },
        "fixed_15_canary": {
            "passed": 15,
            "total": 15,
            "category_passed": {
                "ANSWERABLE": 9,
                "NO_EVIDENCE": 3,
                "FORBIDDEN": 3,
            },
            "exact_control_treatment_boundary": True,
        },
        "cost": {
            "sample_count_per_arm": 30,
            "control_retrieval_p95_ms": 100.0,
            "treatment_retrieval_p95_ms": 130.0,
            "incremental_retrieval_p95_ms": 30.0,
            "incremental_retrieval_p95_limit_ms": 50.0,
            "decomposition_p95_ms": 1.0,
            "decomposition_p95_limit_ms": 5.0,
            "absolute_300ms_adjudication": (
                "NOT_RUN_SEPARATE_PERFORMANCE_GATE"
            ),
        },
        "tokens": {"new_llm_calls": 0, "new_generation_tokens": 0},
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
        "cleanup": {
            "scheduled_versions": 3,
            "jobs_succeeded": 9,
            "jobs_expected": 9,
            "ready_reconciliation_failed_closed": True,
            "deleted_answer_api_status": 403,
            "status": "PASS",
        },
    }


class Phase3ComparisonReportAdjudicationTests(unittest.TestCase):
    def _adjudicate(self, report: dict) -> dict:
        with tempfile.TemporaryDirectory(dir="runtime") as temporary:
            path = Path(temporary) / "report.json"
            path.write_text(
                json.dumps(report, ensure_ascii=False),
                encoding="utf-8",
            )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return adjudicate_report(
                path.relative_to(Path.cwd()),
                expected_report_sha256=digest,
                expected_head_commit=HEAD,
                expected_run_id=RUN_ID,
                expected_input_manifest_sha256=INPUT_MANIFEST_SHA256,
            )

    def test_strict_pass_produces_only_a_default_off_dev_candidate(self):
        result = self._adjudicate(_pass_report())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(
            result["decision"],
            "DEV_CANDIDATE_PASS_AWAITING_FREEZE_COMMIT",
        )
        self.assertFalse(result["default_enabled"])
        self.assertEqual(
            result["test_gate"],
            "SEALED_REQUIRES_SEPARATE_FREEZE_COMMIT_AND_GATE",
        )
        self.assertEqual(
            result["performance_gate"],
            "PENDING_SEPARATE_300MS_GATE",
        )

    def test_inconsistent_gain_is_rejected(self):
        report = _pass_report()
        report["gains"]["macro_recall_at_3_absolute_gain"] = 0.3
        with self.assertRaisesRegex(ReportRejected, "PASS_REPORT_GAIN_INVALID"):
            self._adjudicate(report)

    def test_test_or_acceptance_use_is_rejected(self):
        report = _pass_report()
        report["split_isolation"]["test"] = "USED"
        with self.assertRaisesRegex(
            ReportRejected,
            "REPORT_HOLDOUT_ISOLATION_VIOLATED",
        ):
            self._adjudicate(report)

    def test_incomplete_cleanup_is_rejected(self):
        report = _pass_report()
        report["cleanup"]["jobs_succeeded"] = 8
        with self.assertRaisesRegex(
            ReportRejected,
            "REPORT_CLEANUP_PROOF_INVALID",
        ):
            self._adjudicate(report)

    def test_valid_remote_failure_keeps_variable_disabled_and_test_sealed(self):
        report = _pass_report()
        report["status"] = "FAIL"
        report["error_code"] = "QUALITY_OR_COST_THRESHOLD_NOT_MET"
        result = self._adjudicate(report)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(
            result["decision"],
            "KEEP_COMPARISON_DECOMPOSITION_DISABLED",
        )
        self.assertEqual(result["test_gate"], "SEALED_DEV_GATE_DID_NOT_PASS")
        self.assertIsNone(result["metrics"])

    def test_commit_identity_mismatch_is_rejected(self):
        report = _pass_report()
        report["head_commit"] = "c" * 40
        with self.assertRaisesRegex(
            ReportRejected,
            "REPORT_HEAD_COMMIT_MISMATCH",
        ):
            self._adjudicate(report)

    def test_input_manifest_identity_mismatch_is_rejected(self):
        report = _pass_report()
        report["input_manifest_sha256"] = "c" * 64
        with self.assertRaisesRegex(
            ReportRejected,
            "REPORT_INPUT_MANIFEST_IDENTITY_MISMATCH",
        ):
            self._adjudicate(report)


if __name__ == "__main__":
    unittest.main()
