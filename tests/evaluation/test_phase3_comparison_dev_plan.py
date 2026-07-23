from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_phase3_comparison_dev_plan import TARGET_IDS, build_report


ROOT = Path(__file__).resolve().parents[2]
CONFIG = (
    ROOT
    / "evaluation"
    / "phase3"
    / "bilateral-comparison-query-decomposition-v1.json"
)
DOCUMENT_IDS = (
    "doc_arxiv_2601_03260",
    "doc_arxiv_2602_11409",
)


class Phase3ComparisonDevPlanTests(unittest.TestCase):
    def _write_input(self, path: Path) -> list[str]:
        questions = [
            (
                f"SciNet ({DOCUMENT_IDS[0]}) 与 TRACER ({DOCUMENT_IDS[1]}) "
                f"在 synthetic dimension {index} 上有何不同？"
            )
            for index in range(len(TARGET_IDS))
        ]
        rows = [
            {
                "schema_version": "member_b_claim_evidence_review_input_v1",
                "question_id": question_id,
                "split": "dev",
                "selected_category": "comparison",
                "question": question,
                "final_labels": {
                    "answerability": "ANSWERABLE",
                    "expected_filters": {
                        "document_ids": list(DOCUMENT_IDS),
                        "year_gte": None,
                        "year_lte": None,
                    },
                },
            }
            for question_id, question in zip(TARGET_IDS, questions, strict=True)
        ]
        path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False) + "\n" for row in rows
            ),
            encoding="utf-8",
        )
        return questions

    def test_build_report_is_dev_only_sanitized_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dev.jsonl"
            questions = self._write_input(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()

            report = build_report(
                input_path=path,
                expected_input_sha256=digest,
                config_path=CONFIG,
                repetitions=30,
            )

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(
            report["execution_boundary"],
            "DEV_QUERY_PLAN_ONLY_NO_RETRIEVAL_NO_TEST_NO_ACCEPTANCE",
        )
        self.assertEqual(report["control"]["original_query_preserved_count"], 4)
        self.assertEqual(report["treatment"]["applied_count"], 4)
        self.assertEqual(report["treatment"]["sample_count"], 120)
        self.assertIsNone(report["retrieval_metrics"])
        serialized = json.dumps(report, ensure_ascii=False)
        for question in questions:
            self.assertNotIn(question, serialized)

    def test_input_identity_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dev.jsonl"
            self._write_input(path)

            with self.assertRaisesRegex(ValueError, "identity"):
                build_report(
                    input_path=path,
                    expected_input_sha256="0" * 64,
                    config_path=CONFIG,
                    repetitions=30,
                )


if __name__ == "__main__":
    unittest.main()
