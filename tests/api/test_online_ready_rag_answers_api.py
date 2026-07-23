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
from backend.retrieval.online_reranker import (
    OnlineFixedCrossEncoderReranker,
    StaticDocumentTitleProvider,
    load_online_reranker_config,
)


ROOT = Path(__file__).resolve().parents[2]
OWNER_ID = "tenant_fixture"
RERANKER_CONFIG = (
    ROOT
    / "evaluation"
    / "reranker"
    / "online-fixed-cross-encoder-windows-rtx4090-v1.json"
)


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
                "tenant_id": OWNER_ID,
                "is_active": True,
            }
        ]


class FakeRerankerScorer:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls = []

    def score(self, pairs):
        self.calls.append(list(pairs))
        if self.failure is not None:
            raise self.failure
        return [1.0 for _ in pairs]


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
    def client(
        self,
        retriever: FakeOnlineRetriever,
        *,
        reranker: OnlineFixedCrossEncoderReranker | None = None,
        observer=None,
    ) -> TestClient:
        return TestClient(
            create_app(
                chunks_path=ROOT / "fixtures" / "must-not-be-loaded.json",
                scope_path=ROOT / "fixtures" / "must-not-be-loaded-scope.json",
                retrieval_backend="online_remote_rrf",
                authenticated_owner_id=OWNER_ID,
                online_rrf_retriever=retriever,
                online_reranker=reranker,
                online_retrieval_observer=observer,
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

    def test_optional_reranker_runs_after_ready_retrieval_and_is_observed(self):
        retriever = FakeOnlineRetriever()
        scorer = FakeRerankerScorer()
        reranker = OnlineFixedCrossEncoderReranker(
            config=load_online_reranker_config(RERANKER_CONFIG),
            scorer=scorer,
            title_provider=StaticDocumentTitleProvider(
                {"doc_fixture_001": "Fixture Paper"}
            ),
        )
        observations = []

        response = self.client(
            retriever,
            reranker=reranker,
            observer=observations.append,
        ).post(
            "/api/v1/rag/answers",
            json={
                "question": "How are candidates combined?",
                "document_ids": ["doc_fixture_001"],
                "stream": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["warnings"],
            [
                "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_"
                "BGE_RERANKER_V2_M3_FAKE_LLM"
            ],
        )
        self.assertEqual(retriever.calls[0][2]["top_k"], 20)
        self.assertEqual(len(scorer.calls), 1)
        self.assertEqual(observations[0].reranker_status, "APPLIED")
        self.assertEqual(observations[0].candidate_count, 1)
        self.assertGreaterEqual(observations[0].combined_retrieval_latency_ms, 0)

    def test_reranker_model_failure_returns_existing_authorized_rrf_evidence(self):
        retriever = FakeOnlineRetriever()
        reranker = OnlineFixedCrossEncoderReranker(
            config=load_online_reranker_config(RERANKER_CONFIG),
            scorer=FakeRerankerScorer(failure=RuntimeError("private model error")),
            title_provider=StaticDocumentTitleProvider(
                {"doc_fixture_001": "Fixture Paper"}
            ),
        )

        response = self.client(retriever, reranker=reranker).post(
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
            [
                "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_"
                "RERANKER_FALLBACK_FAKE_LLM"
            ],
        )
        self.assertEqual(
            response.json()["evidence"][0]["chunk_id"],
            "chunk_persisted_001",
        )

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
