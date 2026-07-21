from __future__ import annotations

import unittest

from scripts.finalize_assisted_candidates import build_draft_item, normalize_candidate


class FinalizeAssistedCandidatesTests(unittest.TestCase):
    def test_normalizes_model_fields_into_formal_draft_contract(self) -> None:
        request = {
            "slot": {
                "slot_id": "local3.assisted.0001",
                "split": "dev",
                "primary_question_type": "single_document_fact",
                "language": "en",
                "query_form": "short",
                "difficulty": "easy",
                "answerability": "ANSWERABLE",
                "source_document_ids": ["doc.1"],
                "blind_holdout": False,
            },
            "evidence_chunks": [
                {
                    "chunk_id": "chunk.1",
                    "document_id": "doc.1",
                    "page_start": 2,
                    "page_end": 2,
                    "text": "Evidence",
                }
            ],
        }
        result = {
            "candidate": {
                "slot_id": "local3.assisted.0001",
                "question": "What is supported?",
                "conversation_history": [],
                "question_types": ["factoid"],
                "answerability": "ANSWERABLE",
                "expected_route": "free form route explanation",
                "expected_document_ids": ["wrong.doc"],
                "chunk_judgments": [
                    {
                        "chunk_id": "chunk.1",
                        "document_id": "wrong.doc",
                        "page_start": 99,
                        "page_end": 99,
                        "relevance": 3,
                        "supports_claims": ["claim.1"],
                    }
                ],
                "reference_claims": [
                    {"claim_id": "claim.1", "text": "Supported", "required": True}
                ],
                "acceptable_answer_points": ["Supported"],
                "must_not_claim": [],
                "expected_citations": [{"chunk_id": "chunk.1"}],
                "freshness_cutoff": None,
                "generation_notes": "fixture",
            }
        }
        candidate, actions = normalize_candidate(request=request, result=result)
        item = build_draft_item(request=request, candidate=candidate)
        self.assertEqual(candidate["question_types"], ["single_document_fact"])
        self.assertEqual(candidate["expected_route"], "HYBRID_QA")
        self.assertEqual(candidate["expected_citations"], ["chunk.1"])
        self.assertEqual(item.expected_filters.document_ids, ["doc.1"])
        self.assertEqual(item.chunk_judgments[0].page_start, 2)
        self.assertIn("CANONICALIZE_CHUNK_METADATA_FROM_SOURCE", actions)

    def test_negative_item_cannot_keep_supporting_evidence(self) -> None:
        request = {
            "slot": {
                "slot_id": "local3.assisted.0002",
                "split": "test",
                "primary_question_type": "no_answer_evidence_insufficient",
                "language": "zh",
                "query_form": "long",
                "difficulty": "medium",
                "answerability": "NO_EVIDENCE",
                "source_document_ids": ["doc.1"],
                "blind_holdout": False,
            },
            "evidence_chunks": [
                {
                    "chunk_id": "chunk.1",
                    "document_id": "doc.1",
                    "page_start": 1,
                    "page_end": 1,
                    "text": "Irrelevant evidence",
                }
            ],
        }
        result = {
            "candidate": {
                "slot_id": "local3.assisted.0002",
                "question": "What is absent?",
                "conversation_history": [],
                "question_types": ["no_answer_evidence_insufficient"],
                "answerability": "NO_EVIDENCE",
                "expected_route": "HYBRID_QA",
                "expected_document_ids": ["doc.1"],
                "chunk_judgments": [
                    {
                        "chunk_id": "chunk.1",
                        "document_id": "doc.1",
                        "page_start": 1,
                        "page_end": 1,
                        "relevance": 3,
                        "supports_claims": ["claim.1"],
                    }
                ],
                "reference_claims": [
                    {"claim_id": "claim.1", "text": "Wrong", "required": True}
                ],
                "acceptable_answer_points": ["Wrong"],
                "must_not_claim": ["Do not invent evidence"],
                "expected_citations": ["chunk.1"],
                "freshness_cutoff": None,
                "generation_notes": "fixture",
            }
        }
        candidate, actions = normalize_candidate(request=request, result=result)
        item = build_draft_item(request=request, candidate=candidate)
        self.assertEqual(item.expected_citations, [])
        self.assertEqual(item.reference_claims, [])
        self.assertLess(item.chunk_judgments[0].relevance, 2)
        self.assertIn("ENFORCE_NON_SUPPORTING_NEGATIVE_JUDGMENT", actions)


if __name__ == "__main__":
    unittest.main()
