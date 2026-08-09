from __future__ import annotations

import subprocess
import unittest

from scripts.run_phase3_fixed_reranker_screening import (
    COHORT,
    EXCLUDED_CASE,
    _bilateral_top3,
    _ordered_indices,
    _screening_decision,
    build_identity,
)


class Phase3FixedRerankerScreeningTests(unittest.TestCase):
    def test_current_frozen_inputs_form_exact_three_case_identity(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        identity = build_identity(expected_screening_source_commit=head)
        self.assertEqual(tuple(identity["cohort"]), COHORT)
        self.assertEqual(identity["excluded_cases"], [EXCLUDED_CASE])
        self.assertEqual(len(identity["cases"]), 3)
        self.assertEqual(identity["reranker"]["candidate_top_k"], 20)

    def test_fixed_candidate_limit_makes_two_cases_impossible(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        identity = build_identity(expected_screening_source_commit=head)
        possible = {
            value["case_id"]: value[
                "bilateral_recovery_possible_with_fixed_candidate_top_k"
            ]
            for value in identity["cases"]
        }
        self.assertEqual(
            possible,
            {
                "local3.assisted.0033": False,
                "local3.assisted.0304": False,
                "local3.assisted.0383": True,
            },
        )

    def test_existing_score_order_uses_original_rank_as_tie_break(self) -> None:
        self.assertEqual(_ordered_indices([0.2, 0.7, 0.7, -0.1]), [1, 2, 0, 3])

    def test_bilateral_metric_requires_relevant_top3_from_both_documents(self) -> None:
        targets = {
            "a": {"document_id": "doc-a", "relevance": 3},
            "b": {"document_id": "doc-b", "relevance": 2},
        }
        self.assertTrue(_bilateral_top3(["x", "a", "b"], targets))
        self.assertFalse(_bilateral_top3(["a", "x", "y"], targets))

    def test_frozen_decision_thresholds(self) -> None:
        self.assertEqual(_screening_decision(3), "SCREENING_STRONG_SUPPORT")
        self.assertEqual(_screening_decision(2), "SCREENING_PARTIAL_SUPPORT")
        self.assertEqual(_screening_decision(1), "SCREENING_WEAKENED")
        self.assertEqual(_screening_decision(0), "SCREENING_WEAKENED")


if __name__ == "__main__":
    unittest.main()
