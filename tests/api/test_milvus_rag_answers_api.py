import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.retrieval.fixture import load_chunks
from backend.retrieval.milvus import MilvusVectorIndex
from tests.retrieval.fake_embedding import FakeEmbeddingProvider
from tests.retrieval.fake_milvus import FakeMilvusTransport


ROOT = Path(__file__).resolve().parents[2]


class MilvusRagAnswersApiTests(unittest.TestCase):
    def test_remote_vector_boundary_is_explicit(self):
        chunks_path = ROOT / "fixtures" / "chunks-v1.json"
        chunks = load_chunks(chunks_path)
        provider = FakeEmbeddingProvider()
        transport = FakeMilvusTransport()
        MilvusVectorIndex("fixture_chunks_v1", transport).build(chunks, provider)
        client = TestClient(create_app(
            chunks_path=chunks_path,
            scope_path=ROOT / "fixtures" / "authorized-scope-v1.json",
            retrieval_backend="milvus_vector",
            milvus_collection="fixture_chunks_v1",
            milvus_transport=transport,
            embedding_provider=provider,
        ))
        response = client.post("/api/v1/rag/answers", json={
            "question": "How are candidates combined?",
            "document_ids": ["doc_fixture_001"],
            "stream": False,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["warnings"], ["REMOTE_MILVUS_BGE_M3_FAKE_LLM"])

    def test_remote_backend_requires_collection_name(self):
        with self.assertRaisesRegex(ValueError, "milvus_collection is required"):
            create_app(retrieval_backend="milvus_vector")


if __name__ == "__main__":
    unittest.main()
