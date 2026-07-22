from __future__ import annotations

import unittest

from backend.rag.answer_builder import build_answer
from backend.rag.generation import (
    GenerationModelIdentity,
    GenerationResult,
    OllamaGenerationProvider,
    apply_real_generation,
)


SCOPE = {
    "user_id": "user_fixture",
    "tenant_id": "tenant_fixture",
    "document_ids": ["doc_fixture_001"],
    "library_ids": [],
    "folder_ids": [],
    "include_public": False,
    "acl_version": "acl_fixture_v1",
}
CHUNKS = [
    {
        "chunk_id": "chunk_fixture_001",
        "document_id": "doc_fixture_001",
        "version_id": "version_fixture_001",
        "text": "Evidence one.",
        "section_path": "Method",
        "page_start": 5,
        "page_end": 5,
    },
    {
        "chunk_id": "chunk_fixture_002",
        "document_id": "doc_fixture_001",
        "version_id": "version_fixture_001",
        "text": "Evidence two.",
        "section_path": "Results",
        "page_start": 6,
        "page_end": 6,
    },
]
DIGEST = "a" * 64


def base_answer(chunks=CHUNKS):
    return build_answer(
        "What does the paper report?",
        SCOPE,
        chunks,
        execution_boundary="TEST_FAKE_LLM",
        completed_warning="TEST_FAKE_LLM",
        no_evidence_warning="TEST_NO_EVIDENCE",
        answer_prefix="fake: ",
    )


class StubGenerationProvider:
    def __init__(self, answer: str = "The paper reports evidence one [1].") -> None:
        self.identity = GenerationModelIdentity(
            provider="test",
            model="real-model-v1",
            digest=DIGEST,
        )
        self.answer = answer
        self.calls = []

    def configured_identity(self):
        return self.identity

    def generate(self, question, evidence):
        self.calls.append((question, evidence))
        return GenerationResult(answer=self.answer, identity=self.identity)


class FakeOllamaGenerationProvider(OllamaGenerationProvider):
    def __init__(self) -> None:
        super().__init__(model="llama3.2:latest", expected_digest=DIGEST)
        self.requests = []

    def _request(self, path, payload=None):
        self.requests.append((path, payload))
        if path == "/api/tags":
            return {
                "models": [
                    {"name": "llama3.2:latest", "digest": DIGEST},
                ]
            }
        return {
            "done": True,
            "model": "llama3.2:latest",
            "message": {
                "content": (
                    '{"claims":[{"text":"Supported result.","citation_ids":[1]}]}'
                )
            },
            "prompt_eval_count": 80,
            "eval_count": 8,
        }


class RealGenerationTests(unittest.TestCase):
    def test_real_generation_replaces_fake_answer_and_filters_citations(self):
        provider = StubGenerationProvider()
        answer = apply_real_generation(
            "What does the paper report?", SCOPE, base_answer(), provider
        )

        self.assertEqual(answer["status"], "COMPLETED")
        self.assertEqual(answer["answer"], "The paper reports evidence one [1].")
        self.assertEqual(len(answer["citations"]), 1)
        self.assertEqual(answer["citations"][0]["evidence_id"], "evidence_001")
        self.assertIn("REAL_GENERATION_TEST_REAL-MODEL-V1", answer["warnings"][0])
        self.assertIn("CITATION_IDS_VALIDATED", answer["warnings"][0])
        self.assertEqual(provider.calls[0][1][0]["version_id"], "version_fixture_001")

    def test_invalid_model_citation_fails_closed_to_evidence_cards(self):
        answer = apply_real_generation(
            "What does the paper report?",
            SCOPE,
            base_answer(),
            StubGenerationProvider("Unsupported citation [3]."),
        )

        self.assertEqual(answer["status"], "DEGRADED")
        self.assertNotIn("Unsupported citation", answer["answer"])
        self.assertEqual(len(answer["evidence"]), 2)
        self.assertIn("FAILED_CLOSED_EVIDENCE_ONLY", answer["warnings"][0])

    def test_no_evidence_does_not_call_generation_model(self):
        provider = StubGenerationProvider()
        answer = apply_real_generation(
            "Unknown question", SCOPE, base_answer([]), provider
        )

        self.assertEqual(answer["status"], "NO_EVIDENCE")
        self.assertEqual(provider.calls, [])
        self.assertIn("NOT_CALLED_NO_EVIDENCE", answer["warnings"][0])

    def test_ollama_payload_pins_prompt_and_decoding_identity(self):
        provider = FakeOllamaGenerationProvider()
        result = provider.generate("Question?", base_answer()["evidence"])

        self.assertEqual(result.answer, "Supported result. [1]")
        self.assertEqual(result.prompt_eval_count, 80)
        path, payload = provider.requests[1]
        self.assertEqual(path, "/api/chat")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["format"]["required"], ["claims"])
        self.assertEqual(
            payload["options"],
            {"temperature": 0.0, "seed": 42, "num_predict": 384, "num_ctx": 8192},
        )
        self.assertIn("<evidence>", payload["messages"][1]["content"])

    def test_ollama_model_digest_drift_is_rejected(self):
        provider = FakeOllamaGenerationProvider()
        provider.expected_digest = "b" * 64
        with self.assertRaisesRegex(RuntimeError, "digest drift"):
            provider.generate("Question?", base_answer()["evidence"])


if __name__ == "__main__":
    unittest.main()
