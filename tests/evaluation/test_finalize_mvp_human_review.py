from __future__ import annotations

import unittest
from datetime import datetime

from scripts.finalize_mvp_human_review import finalize_decision


class FinalizeMvpHumanReviewTests(unittest.TestCase):
    def test_records_human_and_expert_signoff_without_losing_edit(self) -> None:
        decision = {
            "review_outcome": "EDIT_LABELS",
            "reviewer_id": "ai-reviewer",
            "reviewed_at": "2026-07-21T20:22:42-07:00",
            "expert_confirmation": "APPROVE",
            "corrected_labels": {"answerability": "ANSWERABLE"},
            "reviewer_notes": "修改理由。 AI 独立预审意见，不构成人工签署。",
        }
        queue_entry = {"required_reviewer_mode": "HUMAN_EXPERT"}
        reviewed_at = datetime.fromisoformat("2026-07-22T11:28:05+08:00")
        result = finalize_decision(
            decision,
            queue_entry=queue_entry,
            reviewer_id="A",
            expert_reviewer_id="A",
            reviewed_at=reviewed_at,
        )
        self.assertEqual(result["reviewer_id"], "A")
        self.assertEqual(result["reviewed_at"], reviewed_at.isoformat())
        self.assertEqual(result["expert_confirmation"], "APPROVE")
        self.assertEqual(result["corrected_labels"], decision["corrected_labels"])
        self.assertIn("修改理由", result["reviewer_notes"])
        self.assertIn("人工评审者 A", result["reviewer_notes"])
        self.assertIn("授权专家 A", result["reviewer_notes"])
        self.assertNotIn("不构成人工签署", result["reviewer_notes"])

    def test_non_expert_does_not_gain_expert_confirmation(self) -> None:
        decision = {
            "reviewer_id": "ai-reviewer",
            "expert_confirmation": "NOT_REQUIRED",
            "reviewer_notes": "",
        }
        result = finalize_decision(
            decision,
            queue_entry={"required_reviewer_mode": "HUMAN_REVIEWER"},
            reviewer_id="A",
            expert_reviewer_id="A",
            reviewed_at=datetime.fromisoformat("2026-07-22T11:28:05+08:00"),
        )
        self.assertEqual(result["expert_confirmation"], "NOT_REQUIRED")
        self.assertNotIn("授权专家", result["reviewer_notes"])


if __name__ == "__main__":
    unittest.main()
