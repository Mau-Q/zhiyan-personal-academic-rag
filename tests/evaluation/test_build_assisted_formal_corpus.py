from __future__ import annotations

import unittest
from datetime import datetime

from scripts.build_assisted_formal_corpus import (
    assign_group_splits,
    build_formal_records,
    group_candidates,
)


def _row(index: int, *, split: str, question: str) -> dict:
    slot_id = f"local3.assisted.{index:04d}"
    return {
        "slot": {
            "slot_id": slot_id,
            "split": split,
            "primary_question_type": "single_document_fact",
            "language": "en",
            "query_form": "short",
            "difficulty": "easy",
            "answerability": "ANSWERABLE",
            "source_document_ids": ["doc.1"],
            "source_chunk_ids": ["chunk.1"],
            "blind_holdout": split == "acceptance",
        },
        "candidate": {
            "question": question,
            "conversation_history": [],
            "question_types": ["single_document_fact"],
            "answerability": "ANSWERABLE",
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
                {"claim_id": "claim.1", "text": "answer", "required": True}
            ],
            "acceptable_answer_points": ["answer"],
            "must_not_claim": [],
            "expected_citations": ["chunk.1"],
            "freshness_cutoff": None,
        },
        "execution": {
            "enable_thinking": False,
            "reasoning_present": False,
            "temperature": 0,
            "model": "qwen3.7-plus",
            "prompt_version": "assisted-question-generation-v1",
        },
        "normalization": {
            "actions": ["SET_EXPECTED_ROUTE_HYBRID_QA"],
            "source_response_id": f"response.{index}",
        },
    }


class BuildAssistedFormalCorpusTests(unittest.TestCase):
    def test_groups_cross_split_near_duplicates(self) -> None:
        rows = [
            _row(1, split="dev", question="What is TRACER?"),
            _row(2, split="test", question="TRACER 是什么？"),
            _row(3, split="acceptance", question="What is SciNet?"),
        ]
        question_vectors = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]]
        answer_vectors = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
        groups, pairs, reasons, _ = group_candidates(
            rows, question_vectors, answer_vectors
        )
        self.assertEqual(sorted(map(len, groups)), [1, 2])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(reasons, {"QUESTION_SEMANTIC_0_88": 1})

    def test_assigns_groups_to_exact_split_targets(self) -> None:
        rows = []
        for index in range(1, 501):
            split = "dev" if index <= 300 else "test" if index <= 400 else "acceptance"
            rows.append(_row(index, split=split, question=f"Question {index}"))
        groups = [[0, 300], *[[index] for index in range(1, 300)], *[[index] for index in range(301, 500)]]
        assignments = assign_group_splits(rows, groups)
        counts = {split: list(assignments.values()).count(split) for split in ("dev", "test", "acceptance")}
        self.assertEqual(counts, {"dev": 300, "test": 100, "acceptance": 100})
        self.assertEqual(assignments[0], assignments[300])

    def test_builds_matching_qwen_annotation_lineage(self) -> None:
        rows = [_row(1, split="acceptance", question="What is TRACER?")]
        items, annotations = build_formal_records(
            rows=rows,
            groups=[[0]],
            assignments={0: "acceptance"},
            dataset_version="fixture-assisted-v1",
            submitted_at=datetime.fromisoformat("2026-07-21T20:00:00+08:00"),
        )
        self.assertEqual(items[0].annotation_status, "GPT_ASSISTED")
        self.assertTrue(items[0].blind_holdout)
        self.assertEqual(annotations[0].actor_type, "GPT")
        self.assertEqual(annotations[0].model_identity, "qwen3.7-plus")
        self.assertEqual(annotations[0].chunk_judgments, items[0].chunk_judgments)


if __name__ == "__main__":
    unittest.main()
