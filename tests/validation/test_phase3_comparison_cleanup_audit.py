from __future__ import annotations

import unittest

from scripts.audit_phase3_comparison_cleanup_state import (
    build_report,
    evaluate_snapshot,
)


def _completed_snapshot(version_count: int = 3) -> dict[str, object]:
    return {
        "versions": (
            {
                "lifecycle_status": "INACTIVE",
                "is_active": False,
                "row_count": version_count,
            },
        ),
        "ingestion_jobs": (
            {
                "status": "SUCCEEDED",
                "failure_code": None,
                "row_count": version_count,
            },
        ),
        "cleanup_jobs": tuple(
            {
                "backend": backend,
                "status": "SUCCEEDED",
                "failure_code": None,
                "row_count": version_count,
            }
            for backend in (
                "elasticsearch_chunks",
                "milvus_vectors",
                "runtime_snapshot",
            )
        ),
        "global_nonterminal_cleanup_jobs": (),
        "chunk_rows": 0,
        "pdf_object_rows": 0,
    }


class Phase3ComparisonCleanupAuditTests(unittest.TestCase):
    def test_completed_three_backend_cleanup_is_clean(self):
        result = evaluate_snapshot(_completed_snapshot())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["decision"], "CLEAN")
        self.assertEqual(result["summary"]["cleanup_job_count"], 9)
        self.assertEqual(result["summary"]["cleanup_backends"], [
            "elasticsearch_chunks",
            "milvus_vectors",
            "runtime_snapshot",
        ])

    def test_pre_service_zero_row_scope_is_clean(self):
        result = evaluate_snapshot(
            {
                "versions": (),
                "ingestion_jobs": (),
                "cleanup_jobs": (),
                "global_nonterminal_cleanup_jobs": (),
                "chunk_rows": 0,
                "pdf_object_rows": 0,
            }
        )
        self.assertEqual(result["decision"], "CLEAN")

    def test_active_version_or_runtime_snapshot_rows_require_recovery(self):
        snapshot = _completed_snapshot()
        snapshot["versions"] = (
            {
                "lifecycle_status": "READY",
                "is_active": True,
                "row_count": 3,
            },
        )
        snapshot["chunk_rows"] = 12
        result = evaluate_snapshot(snapshot)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["decision"], "RESIDUAL_REQUIRES_RECOVERY_GATE")
        self.assertEqual(result["summary"]["active_version_count"], 3)
        self.assertEqual(result["summary"]["chunk_rows"], 12)

    def test_retry_or_failed_cleanup_job_is_not_clean(self):
        snapshot = _completed_snapshot()
        snapshot["cleanup_jobs"] = (
            {
                "backend": "elasticsearch_chunks",
                "status": "RETRY",
                "failure_code": "ELASTICSEARCH_DELETE_FAILED",
                "row_count": 1,
            },
            {
                "backend": "milvus_vectors",
                "status": "SUCCEEDED",
                "failure_code": None,
                "row_count": 3,
            },
            {
                "backend": "runtime_snapshot",
                "status": "SUCCEEDED",
                "failure_code": None,
                "row_count": 3,
            },
        )
        result = evaluate_snapshot(snapshot)
        self.assertEqual(result["decision"], "RESIDUAL_REQUIRES_RECOVERY_GATE")
        self.assertEqual(result["summary"]["nonterminal_cleanup_job_count"], 1)

    def test_unrelated_global_nonterminal_cleanup_blocks_new_quality_run(self):
        snapshot = _completed_snapshot()
        snapshot["global_nonterminal_cleanup_jobs"] = (
            {
                "backend": "milvus_vectors",
                "status": "RETRY",
                "failure_code": "MILVUS_DELETE_FAILED",
                "row_count": 1,
            },
        )
        result = evaluate_snapshot(snapshot)
        self.assertEqual(result["decision"], "RESIDUAL_REQUIRES_RECOVERY_GATE")
        self.assertEqual(
            result["summary"]["global_nonterminal_cleanup_job_count"],
            1,
        )

    def test_report_keeps_quality_and_sealed_split_boundaries(self):
        report = build_report("phase3_comparison_dev_20260723_02", _completed_snapshot())
        self.assertTrue(report["read_only"])
        self.assertFalse(report["proof_boundary"]["elasticsearch_queried"])
        self.assertFalse(report["proof_boundary"]["milvus_queried"])
        self.assertFalse(report["proof_boundary"]["test_read_or_run"])
        self.assertFalse(report["proof_boundary"]["acceptance_read_or_run"])
        self.assertFalse(report["proof_boundary"]["quality_rerun_authorized"])


if __name__ == "__main__":
    unittest.main()
