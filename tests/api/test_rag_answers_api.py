import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.api.app import create_app


ROOT = Path(__file__).resolve().parents[2]


class RagAnswersApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())
        cls.answer_validator = Draft202012Validator(
            json.loads(
                (ROOT / "contracts" / "schemas" / "rag-answer-v1.schema.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        openapi_contract = json.loads(
            (ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8")
        )
        cls.error_validator = Draft202012Validator(
            openapi_contract["components"]["schemas"]["ErrorV1"]
        )

    def post_answer(self, payload):
        return self.client.post("/api/v1/rag/answers", json=payload)

    def test_supported_question_returns_contract_valid_completed_answer(self):
        response = self.post_answer(
            {
                "question": "How are candidates combined before reranking?",
                "document_ids": ["doc_fixture_001"],
                "stream": False,
            }
        )
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.answer_validator.validate(answer)
        self.assertEqual(answer["status"], "COMPLETED")
        self.assertEqual(answer["warnings"], ["FIXTURE_ONLY_FAKE_LLM"])
        self.assertTrue(answer["citations"])

    def test_unknown_question_returns_contract_valid_no_evidence(self):
        response = self.post_answer(
            {
                "question": "What is the measured ocean temperature?",
                "document_ids": ["doc_fixture_001"],
                "stream": False,
            }
        )
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.answer_validator.validate(answer)
        self.assertEqual(answer["status"], "NO_EVIDENCE")
        self.assertEqual(answer["evidence"], [])

    def test_client_document_scope_cannot_expand_server_authority(self):
        response = self.post_answer(
            {
                "question": "quantum entanglement",
                "document_ids": ["doc_fixture_private_other_tenant"],
                "stream": False,
            }
        )
        self.assertEqual(response.status_code, 403)
        error = response.json()
        self.error_validator.validate(error)
        self.assertEqual(error["code"], "RAG_FORBIDDEN_SCOPE")
        self.assertFalse(error["retryable"])

    def test_empty_document_selection_uses_server_authorized_scope(self):
        response = self.post_answer(
            {
                "question": "retrieval candidates",
                "document_ids": [],
                "stream": False,
            }
        )
        self.assertEqual(response.status_code, 200)
        document_ids = {item["document_id"] for item in response.json()["evidence"]}
        self.assertEqual(document_ids, {"doc_fixture_001"})

    def test_stream_true_returns_contract_valid_422(self):
        response = self.post_answer(
            {"question": "retrieval", "document_ids": [], "stream": True}
        )
        self.assertEqual(response.status_code, 422)
        error = response.json()
        self.error_validator.validate(error)
        self.assertEqual(error["code"], "RAG_INVALID_REQUEST")

    def test_duplicate_document_ids_return_contract_valid_422(self):
        response = self.post_answer(
            {
                "question": "retrieval",
                "document_ids": ["doc_fixture_001", "doc_fixture_001"],
                "stream": False,
            }
        )
        self.assertEqual(response.status_code, 422)
        self.error_validator.validate(response.json())

    def test_blank_question_and_extra_fields_return_422(self):
        blank = self.post_answer({"question": " ", "document_ids": [], "stream": False})
        extra = self.post_answer(
            {
                "question": "retrieval",
                "document_ids": [],
                "stream": False,
                "tenant_id": "attacker_supplied",
            }
        )
        self.assertEqual(blank.status_code, 422)
        self.assertEqual(extra.status_code, 422)
        self.error_validator.validate(blank.json())
        self.error_validator.validate(extra.json())

    def test_generated_openapi_exposes_frozen_operation(self):
        spec = self.client.get("/openapi.json").json()
        operation = spec["paths"]["/api/v1/rag/answers"]["post"]
        self.assertEqual(operation["operationId"], "createRagAnswer")
        self.assertIn("200", operation["responses"])
        self.assertIn("403", operation["responses"])
        self.assertIn("422", operation["responses"])


if __name__ == "__main__":
    unittest.main()
