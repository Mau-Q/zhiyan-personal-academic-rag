from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.rag.generation import GenerationModelIdentity, GenerationResult
from backend.retrieval.online import (
    OnlineScopeForbiddenError,
    OnlineVisibilityUnavailableError,
)


ROOT = Path(__file__).resolve().parents[2]
OWNER_ID = "tenant_fixture"


class FakeOnlineRetriever:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls = []

    def retrieve(self, question, scope, **kwargs):
        self.calls.append((question, scope, kwargs))
        if self.failure is not None:
            raise self.failure
        return [
            {
                "chunk_id": "chunk_persisted_001",
                "document_id": kwargs["document_ids"][0],
                "version_id": "version_persisted_001",
                "text": "Persisted READY evidence",
                "section_path": "Method",
                "page_start": 1,
                "page_end": 1,
            }
        ]


class FakeRealGenerationProvider:
    def __init__(self) -> None:
        self.identity = GenerationModelIdentity(
            provider="test",
            model="real-model-v1",
            digest="a" * 64,
        )
        self.calls = []

    def configured_identity(self):
        return self.identity

    def generate(self, question, evidence):
        self.calls.append((question, evidence))
        return GenerationResult(
            answer="The READY evidence supports this answer [1].",
            identity=self.identity,
        )


class OnlineReadyRagAnswersApiTests(unittest.TestCase):
    def client(self, retriever: FakeOnlineRetriever) -> TestClient:
        return TestClient(
            create_app(
                chunks_path=ROOT / "fixtures" / "must-not-be-loaded.json",
                scope_path=ROOT / "fixtures" / "must-not-be-loaded-scope.json",
                retrieval_backend="online_remote_rrf",
                authenticated_owner_id=OWNER_ID,
                online_rrf_retriever=retriever,
            )
        )

    def test_online_answer_uses_server_owner_and_ready_retriever(self):
        retriever = FakeOnlineRetriever()
        response = self.client(retriever).post(
            "/api/v1/rag/answers",
            json={
                "question": "How are candidates combined?",
                "document_ids": ["doc_fixture_001"],
                "stream": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "COMPLETED")
        self.assertEqual(
            response.json()["warnings"],
            ["ONLINE_POSTGRES_READY_ES_MILVUS_RRF_FAKE_LLM"],
        )
        _, scope, kwargs = retriever.calls[0]
        self.assertEqual(scope["user_id"], OWNER_ID)
        self.assertEqual(scope["tenant_id"], OWNER_ID)
        self.assertEqual(kwargs["owner_id"], OWNER_ID)
        self.assertEqual(kwargs["document_ids"], ["doc_fixture_001"])

    def test_unprovable_scope_or_fact_source_failure_returns_existing_403_contract(self):
        failures = (
            (OnlineScopeForbiddenError("not ready"), False),
            (OnlineVisibilityUnavailableError("postgres unavailable"), True),
        )
        for failure, retryable in failures:
            with self.subTest(failure=type(failure).__name__):
                response = self.client(FakeOnlineRetriever(failure=failure)).post(
                    "/api/v1/rag/answers",
                    json={
                        "question": "hidden evidence",
                        "document_ids": ["doc_missing"],
                        "stream": False,
                    },
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "RAG_FORBIDDEN_SCOPE")
                self.assertEqual(response.json()["retryable"], retryable)

    def test_online_backend_requires_server_identity_and_route_resolver(self):
        with self.assertRaisesRegex(ValueError, "authenticated_owner_id"):
            create_app(retrieval_backend="online_remote_rrf")

    def test_real_generation_consumes_only_ready_revalidated_evidence(self):
        retriever = FakeOnlineRetriever()
        generator = FakeRealGenerationProvider()
        client = TestClient(
            create_app(
                chunks_path=ROOT / "fixtures" / "must-not-be-loaded.json",
                scope_path=ROOT / "fixtures" / "must-not-be-loaded-scope.json",
                retrieval_backend="online_remote_rrf",
                authenticated_owner_id=OWNER_ID,
                online_rrf_retriever=retriever,
                generation_provider=generator,
            )
        )

        response = client.post(
            "/api/v1/rag/answers",
            json={
                "question": "How are candidates combined?",
                "document_ids": ["doc_fixture_001"],
                "stream": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "COMPLETED")
        self.assertEqual(
            response.json()["answer"],
            "The READY evidence supports this answer [1].",
        )
        self.assertIn("CITATION_IDS_VALIDATED", response.json()["warnings"][0])
        self.assertEqual(generator.calls[0][1][0]["chunk_id"], "chunk_persisted_001")


if __name__ == "__main__":
    unittest.main()
