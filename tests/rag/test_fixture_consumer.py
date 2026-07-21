import json
import subprocess
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.rag.fixture_consumer import answer_fixture_question
from backend.retrieval.fixture import load_chunks, load_scope


ROOT = Path(__file__).resolve().parents[2]


class FixtureConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = load_chunks(ROOT / "fixtures" / "chunks-v1.json")
        cls.scope = load_scope(ROOT / "fixtures" / "authorized-scope-v1.json")
        schema = json.loads(
            (ROOT / "contracts" / "schemas" / "rag-answer-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        cls.answer_validator = Draft202012Validator(schema)

    def test_supported_question_returns_completed_answer_with_valid_citations(self):
        answer = answer_fixture_question(
            "How are candidates combined before reranking?", self.scope, self.chunks
        )
        self.answer_validator.validate(answer)
        self.assertEqual(answer["status"], "COMPLETED")
        self.assertEqual(answer["warnings"], ["FIXTURE_ONLY_FAKE_LLM"])
        self.assertTrue(answer["evidence"])
        evidence_ids = {item["evidence_id"] for item in answer["evidence"]}
        self.assertTrue(
            all(citation["evidence_id"] in evidence_ids for citation in answer["citations"])
        )
        self.assertTrue(all(item["page_start"] >= 1 for item in answer["citations"]))

    def test_unknown_question_returns_explicit_no_evidence(self):
        answer = answer_fixture_question(
            "What is the measured ocean temperature?", self.scope, self.chunks
        )
        self.answer_validator.validate(answer)
        self.assertEqual(answer["status"], "NO_EVIDENCE")
        self.assertEqual(answer["evidence"], [])
        self.assertEqual(answer["citations"], [])
        self.assertTrue(answer["answer"])

    def test_unauthorized_exact_match_cannot_become_evidence(self):
        answer = answer_fixture_question("quantum entanglement", self.scope, self.chunks)
        self.assertEqual(answer["status"], "NO_EVIDENCE")
        self.assertNotIn("confidential", answer["answer"].lower())

    def test_same_input_produces_same_answer(self):
        first = answer_fixture_question("retrieval candidates", self.scope, self.chunks)
        second = answer_fixture_question("retrieval candidates", self.scope, self.chunks)
        self.assertEqual(first, second)

    def test_cli_emits_rag_answer_json(self):
        completed = subprocess.run(
            [
                "python3",
                "-m",
                "backend.rag.fixture_consumer",
                "--question",
                "retrieval candidates reranking",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        answer = json.loads(completed.stdout)
        self.answer_validator.validate(answer)
        self.assertEqual(answer["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
