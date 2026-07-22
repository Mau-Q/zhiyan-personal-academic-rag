from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts.prepare_mvp_initial_review_package import (
    build_decision,
    classify_item,
    select_items,
)


def _item(index: int, category: str) -> SimpleNamespace:
    mapping = {
        "exact_lookup": ("ANSWERABLE", ["exact_lookup"]),
        "single_document_fact": ("ANSWERABLE", ["single_document_fact"]),
        "semantic_rewrite": ("ANSWERABLE", ["cross_document_semantic"]),
        "comparison": ("ANSWERABLE", ["comparison"]),
        "evidence_boundary": ("NO_EVIDENCE", ["no_answer_evidence_insufficient"]),
        "security": ("FORBIDDEN", ["adversarial_security"]),
    }
    answerability, question_types = mapping[category]
    return SimpleNamespace(
        question_id=f"q.{category}.{index:03d}",
        leakage_group_id=f"g.{category}.{index:03d}",
        question_types=question_types,
        answerability=answerability,
    )


class PrepareMvpInitialReviewPackageTests(unittest.TestCase):
    def test_classifies_six_disjoint_mvp_categories(self) -> None:
        for category in (
            "exact_lookup",
            "single_document_fact",
            "semantic_rewrite",
            "comparison",
            "evidence_boundary",
            "security",
        ):
            self.assertEqual(classify_item(_item(1, category)), category)

    def test_selection_is_deterministic_and_leakage_group_safe(self) -> None:
        categories = (
            "exact_lookup",
            "single_document_fact",
            "semantic_rewrite",
            "comparison",
            "evidence_boundary",
            "security",
        )
        items = [item for category in categories for item in (_item(i, category) for i in range(6))]
        policy = {
            "schema_version": "mvp_initial_review_policy_v1",
            "seed": 7,
            "target_size": 18,
            "category_quotas": {category: 3 for category in categories},
            "split_quotas": {"dev": 6, "test": 6, "acceptance": 6},
            "category_split_quotas": {
                category: {"dev": 1, "test": 1, "acceptance": 1}
                for category in categories
            },
        }
        first = select_items(items, policy)
        second = select_items(reversed(items), policy)
        self.assertEqual(
            [(item.question_id, category, split) for item, category, split in first],
            [(item.question_id, category, split) for item, category, split in second],
        )
        self.assertEqual(len({item.leakage_group_id for item, _, _ in first}), 18)

    def test_decision_is_pending_and_does_not_claim_human_review(self) -> None:
        entry = {
            "review_id": "mvp175.q1",
            "question_id": "q1",
            "required_reviewer_mode": "HUMAN_REVIEWER",
            "review_checks": ["QUESTION_AND_SCOPE_MATCH"],
            "proposal": {
                "labels_sha256": "a" * 64,
                "answerability": "ANSWERABLE",
            },
        }
        decision = build_decision(entry)
        self.assertEqual(decision["review_outcome"], "PENDING")
        self.assertEqual(decision["review_checks"]["QUESTION_AND_SCOPE_MATCH"], "PENDING")
        self.assertEqual(decision["reviewer_id"], "")


if __name__ == "__main__":
    unittest.main()
