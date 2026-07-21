from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_assisted_generation_qwen import (
    build_api_payload,
    build_https_opener,
    load_env_file,
    parse_api_response,
)


class QwenAssistedGenerationTests(unittest.TestCase):
    def test_https_opener_uses_verified_tls_context(self) -> None:
        opener = build_https_opener()
        https_handler = next(
            handler
            for handler in opener.handlers
            if handler.__class__.__name__ == "HTTPSHandler"
        )
        context = https_handler._context
        self.assertEqual(context.verify_mode.name, "CERT_REQUIRED")
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)

    def test_builds_non_thinking_structured_request(self) -> None:
        request = {
            "instructions": "generate",
            "slot": {"slot_id": "slot.1"},
            "evidence_chunks": [{"chunk_id": "chunk.1", "text": "evidence"}],
        }
        payload = build_api_payload(request, "qwen3.7-plus")
        self.assertEqual(payload["model"], "qwen3.7-plus")
        self.assertIs(payload["enable_thinking"], False)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["temperature"], 0)

    def test_parses_candidate_and_rejects_reasoning(self) -> None:
        candidate = {
            "slot_id": "slot.1",
            "question": "What is supported?",
            "conversation_history": [],
            "question_types": ["exact_lookup"],
            "answerability": "ANSWERABLE",
            "expected_route": "retrieval",
            "expected_document_ids": ["doc.1"],
            "chunk_judgments": [],
            "reference_claims": [],
            "acceptable_answer_points": [],
            "must_not_claim": [],
            "expected_citations": [],
            "freshness_cutoff": None,
            "generation_notes": "fixture",
        }
        response = {
            "id": "response.1",
            "model": "qwen3.7-plus",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(candidate)},
                }
            ],
            "usage": {"total_tokens": 10},
        }
        parsed, metadata = parse_api_response(response, "slot.1")
        self.assertEqual(parsed, candidate)
        self.assertIs(metadata["reasoning_present"], False)
        response["choices"][0]["message"]["reasoning_content"] = "hidden thought"
        with self.assertRaisesRegex(ValueError, "thinking content"):
            parse_api_response(response, "slot.1")

    def test_loads_dotenv_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text(
                "# comment\nexport API_KEY='secret-value'\nMODEL=qwen3.7-plus\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_env_file(path),
                {"API_KEY": "secret-value", "MODEL": "qwen3.7-plus"},
            )


if __name__ == "__main__":
    unittest.main()
