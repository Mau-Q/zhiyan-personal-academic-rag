from __future__ import annotations

import unittest

from scripts.run_phase4_claim_evidence_candidate_intake import (
    CandidateIntakeError,
    _taxonomy_category,
    _validate_reviews,
    _validate_taxonomy,
    build_report,
)


def private_item(
    question_id: str = "fixture.dev.1",
    *,
    answerability: str = "ANSWERABLE",
) -> dict:
    claims = (
        [{"claim_id": "claim.1", "text": "The study enrolled 240 participants."}]
        if answerability == "ANSWERABLE"
        else []
    )
    judgments = (
        [{"chunk_id": "chunk.1", "supports_claims": ["claim.1"]}]
        if answerability == "ANSWERABLE"
        else []
    )
    return {
        "question_id": question_id,
        "split": "dev",
        "final_labels": {
            "answerability": answerability,
            "reference_claims": claims,
            "chunk_judgments": judgments,
        },
        "frozen_evidence_chunks": [
            {
                "chunk_id": "chunk.1",
                "text": "The study enrolled 240 participants.",
            }
        ],
    }


def taxonomy_row(
    question_id: str = "fixture.dev.1",
    *,
    category: str = "ANSWERABLE",
) -> dict[str, str]:
    return {
        "question_id": question_id,
        "split": "dev",
        "category": category,
        "es_passed": "true",
        "milvus_passed": "true",
        "primary_failure": "NONE",
        "secondary_failure": "",
        "confidence": "HIGH",
        "candidate_detail_available": "false",
        "review_status": "REVIEWED",
    }


def review_row(
    question_id: str = "fixture.dev.1",
    *,
    relation: str = "SUPPORTED",
) -> dict[str, str]:
    not_applicable = relation == "NOT_APPLICABLE"
    return {
        "question_id": question_id,
        "claim_id": "" if not_applicable else "claim.1",
        "chunk_id": "" if not_applicable else "chunk.1",
        "relation": relation,
        "citation_complete": "true",
        "confidence": "HIGH",
        "review_status": "REVIEWED",
    }


def policy() -> dict:
    return {
        "run_id": "fixture",
        "candidate_source": {
            "status": "AI_ASSISTED_CANDIDATE_NOT_HUMAN_ADJUDICATED",
            "expected_taxonomy_questions": 1,
            "expected_claim_evidence_questions": 1,
        },
        "private_input": {
            "test": "NOT_READ_NOT_RUN",
            "acceptance": "NOT_READ_NOT_RUN",
        },
        "decision_policy": {
            "minimum_candidate_supported_retention_for_future_adjudication": 0.85,
            "safe_default": "AUDIT_ONLY",
        },
    }


class Phase4ClaimEvidenceCandidateIntakeTests(unittest.TestCase):
    def test_taxonomy_contract_folds_partial_answerable_into_answerable(self):
        self.assertEqual(_taxonomy_category("PARTIALLY_ANSWERABLE"), "ANSWERABLE")

    def test_supported_candidate_is_validated_without_becoming_human_truth(self):
        item = private_item()
        report = build_report(
            [taxonomy_row()],
            [review_row()],
            {item["question_id"]: item},
            policy(),
        )

        self.assertEqual(report["intake"]["status"], "PASS")
        self.assertEqual(report["diagnostics"]["candidate_supported_retention"], 1.0)
        self.assertFalse(report["decision"]["candidate_labels_promoted_to_truth"])
        self.assertEqual(
            report["diagnostics"]["human_agreement"],
            "NOT_MEASURABLE_AI_ASSISTED_CANDIDATE",
        )

    def test_not_applicable_requires_no_claim_or_chunk_identity(self):
        row = review_row(relation="NOT_APPLICABLE")
        row["claim_id"] = "claim.1"

        with self.assertRaisesRegex(
            CandidateIntakeError, "NOT_APPLICABLE_IDENTITIES_PRESENT"
        ):
            _validate_reviews([row], 1)

    def test_not_applicable_must_match_no_evidence_or_forbidden(self):
        item = private_item()

        with self.assertRaisesRegex(
            CandidateIntakeError, "NOT_APPLICABLE_CATEGORY_INVALID"
        ):
            build_report(
                [taxonomy_row()],
                [review_row(relation="NOT_APPLICABLE")],
                {item["question_id"]: item},
                policy(),
            )

    def test_taxonomy_rejects_holdout_split(self):
        row = taxonomy_row()
        row["split"] = "test"

        with self.assertRaisesRegex(
            CandidateIntakeError, "TAXONOMY_ID_OR_SPLIT_INVALID"
        ):
            _validate_taxonomy([row], 1)

    def test_taxonomy_scope_must_equal_private_dev_scope(self):
        item = private_item()
        other = private_item("fixture.dev.2")

        with self.assertRaisesRegex(
            CandidateIntakeError, "TAXONOMY_PRIVATE_INPUT_SCOPE_MISMATCH"
        ):
            build_report(
                [taxonomy_row()],
                [review_row()],
                {item["question_id"]: item, other["question_id"]: other},
                policy(),
            )


if __name__ == "__main__":
    unittest.main()
