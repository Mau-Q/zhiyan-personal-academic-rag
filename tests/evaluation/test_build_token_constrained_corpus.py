from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.evaluation.formal_corpus import EvaluationItemV1
from scripts.build_token_constrained_corpus import derive_items


ROOT = Path(__file__).resolve().parents[2]


class BuildTokenConstrainedCorpusTests(unittest.TestCase):
    def test_applies_edits_excludes_rejects_and_keeps_unreviewed(self) -> None:
        source = [
            EvaluationItemV1.model_validate(json.loads(line))
            for line in (ROOT / "evaluation/formal/fixture-items-v1.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        reviewed = source[0]
        rejected = source[1]
        proposal = {
            "answerability": reviewed.answerability,
            "expected_route": reviewed.expected_route,
            "chunk_judgments": [
                value.model_dump(mode="json") for value in reviewed.chunk_judgments
            ],
            "labels_sha256": "a" * 64,
        }
        queue = [
            {
                "question_id": reviewed.question_id,
                "review_id": f"review.{reviewed.question_id}",
                "review_reasons": ["ACCEPTANCE_CONFIRMATION"],
                "required_reviewer_mode": "HUMAN_REVIEWER",
                "gpt_proposal": proposal,
            },
            {
                "question_id": rejected.question_id,
                "review_id": f"review.{rejected.question_id}",
                "review_reasons": ["NO_EVIDENCE_CONFIRMATION"],
                "required_reviewer_mode": "HUMAN_REVIEWER",
                "gpt_proposal": {
                    "answerability": rejected.answerability,
                    "expected_route": rejected.expected_route,
                    "chunk_judgments": [],
                    "labels_sha256": "b" * 64,
                },
            },
        ]
        decisions = [
            {
                "schema_version": "assisted_risk_review_decision_v1",
                "question_id": reviewed.question_id,
                "review_id": f"review.{reviewed.question_id}",
                "review_reasons": ["ACCEPTANCE_CONFIRMATION"],
                "required_reviewer_mode": "HUMAN_REVIEWER",
                "proposal_labels_sha256": "a" * 64,
                "review_outcome": "EDIT_LABELS",
                "reviewer_id": "ai.fixture",
                "reviewed_at": "2026-07-21T18:00:00+08:00",
                "corrected_labels": {
                    "answerability": "PARTIALLY_ANSWERABLE",
                    "expected_route": reviewed.expected_route,
                    "chunk_judgments": proposal["chunk_judgments"],
                },
                "expert_confirmation": "NOT_REQUIRED",
                "reviewer_notes": "fixture edit",
            },
            {
                "schema_version": "assisted_risk_review_decision_v1",
                "question_id": rejected.question_id,
                "review_id": f"review.{rejected.question_id}",
                "review_reasons": ["NO_EVIDENCE_CONFIRMATION"],
                "required_reviewer_mode": "HUMAN_REVIEWER",
                "proposal_labels_sha256": "b" * 64,
                "review_outcome": "REJECT_ITEM",
                "reviewer_id": "ai.fixture",
                "reviewed_at": "2026-07-21T18:00:00+08:00",
                "corrected_labels": {
                    "answerability": rejected.answerability,
                    "expected_route": rejected.expected_route,
                    "chunk_judgments": [],
                },
                "expert_confirmation": "NOT_REQUIRED",
                "reviewer_notes": "fixture reject",
            },
        ]
        derived, report = derive_items(
            source_items=source,
            queue=queue,
            decisions=decisions,
            dataset_version="fixture-token-constrained-v1",
        )
        self.assertEqual(len(derived), 3)
        self.assertEqual(derived[0].answerability, "PARTIALLY_ANSWERABLE")
        self.assertEqual(derived[0].annotation_status, "DRAFT")
        self.assertNotIn(rejected.question_id, {item.question_id for item in derived})
        self.assertEqual(report["edited_item_count"], 1)
        self.assertEqual(report["excluded_item_count"], 1)


if __name__ == "__main__":
    unittest.main()
