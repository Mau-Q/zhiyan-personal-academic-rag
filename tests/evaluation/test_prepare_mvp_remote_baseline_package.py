from __future__ import annotations

import unittest

from scripts.prepare_mvp_remote_baseline_package import build_case


def _queue(category: str = "single_document_fact") -> dict:
    return {
        "question_id": "mvp.q1",
        "question": "What is the result?",
        "mvp_split": "dev",
        "selected_category": category,
    }


def _decision(answerability: str) -> dict:
    labels = {
        "answerability": answerability,
        "expected_filters": {"document_ids": ["doc_1"]},
        "chunk_judgments": [],
        "expected_citations": [],
    }
    if answerability == "ANSWERABLE":
        labels["chunk_judgments"] = [
            {
                "chunk_id": "chunk_1",
                "document_id": "doc_1",
                "page_start": 3,
                "page_end": 3,
                "relevance": 3,
                "supports_claims": [],
            }
        ]
        labels["expected_citations"] = ["chunk_1"]
    return {"question_id": "mvp.q1", "corrected_labels": labels}


class PrepareMvpRemoteBaselinePackageTests(unittest.TestCase):
    def test_builds_backend_specific_answerable_case(self) -> None:
        es = build_case(_queue(), _decision("ANSWERABLE"), backend="elasticsearch_bm25")
        milvus = build_case(_queue(), _decision("ANSWERABLE"), backend="milvus_vector")
        self.assertEqual(es["category"], "ANSWERABLE")
        self.assertNotIn("mvp_split", es)
        self.assertNotIn("selected_category", es)
        self.assertEqual(es["expected"]["required_evidence"][0]["page_start"], 3)
        self.assertEqual(
            es["expected"]["required_warnings"],
            ["REMOTE_ELASTICSEARCH_BM25_FAKE_LLM"],
        )
        self.assertEqual(
            milvus["expected"]["required_warnings"],
            ["REMOTE_MILVUS_BGE_M3_FAKE_LLM"],
        )

    def test_preserves_no_evidence_and_security_expectations(self) -> None:
        no_evidence = build_case(
            _queue("evidence_boundary"),
            _decision("NO_EVIDENCE"),
            backend="elasticsearch_bm25",
        )
        forbidden_decision = _decision("FORBIDDEN")
        forbidden_decision["corrected_labels"]["expected_filters"]["document_ids"] = []
        forbidden = build_case(
            _queue("security"),
            forbidden_decision,
            backend="milvus_vector",
        )
        self.assertEqual(no_evidence["expected"]["answer_status"], "NO_EVIDENCE")
        self.assertEqual(no_evidence["expected"]["max_evidence_count"], 0)
        self.assertEqual(forbidden["category"], "FORBIDDEN")
        self.assertEqual(forbidden["document_ids"], [])
        self.assertEqual(forbidden["expected"]["http_status"], 403)


if __name__ == "__main__":
    unittest.main()
