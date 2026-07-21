import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.retrieval.fixture import load_chunks
from backend.retrieval.sqlite_fts import SQLiteFtsIndex
from backend.retrieval.vector import LocalVectorIndex, VectorIndexNotReadyError
from tests.retrieval.fake_embedding import FakeEmbeddingProvider


ROOT = Path(__file__).resolve().parents[2]


class VectorRagAnswersApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        temporary = Path(self.temporary_directory.name)
        self.chunks_path = ROOT / "fixtures" / "chunks-v1.json"
        chunks = load_chunks(self.chunks_path)
        self.provider = FakeEmbeddingProvider()
        self.vector_path = temporary / "vector.sqlite"
        self.fts_path = temporary / "fts.sqlite"
        LocalVectorIndex.build(self.vector_path, chunks, self.provider)
        SQLiteFtsIndex.build(self.fts_path, chunks)

    def client(self, backend: str) -> TestClient:
        return TestClient(
            create_app(
                chunks_path=self.chunks_path,
                retrieval_backend=backend,
                index_path=self.fts_path if backend == "local_rrf" else None,
                vector_index_path=self.vector_path,
                embedding_provider=self.provider,
                vector_min_score=0.5,
            )
        )

    @staticmethod
    def post(client: TestClient, question: str, document_ids: list[str]):
        return client.post(
            "/api/v1/rag/answers",
            json={"question": question, "document_ids": document_ids, "stream": False},
        )

    def test_vector_and_rrf_backends_expose_truthful_boundaries(self):
        vector = self.post(
            self.client("local_vector"),
            "How are semantic candidates combined?",
            ["doc_fixture_001"],
        ).json()
        rrf = self.post(
            self.client("local_rrf"),
            "How are semantic candidates combined?",
            ["doc_fixture_001"],
        ).json()
        self.assertEqual(vector["status"], "COMPLETED")
        self.assertEqual(vector["warnings"], ["LOCAL_REAL_VECTOR_FAKE_LLM"])
        self.assertEqual(rrf["status"], "COMPLETED")
        self.assertEqual(rrf["warnings"], ["LOCAL_RRF_HYBRID_FAKE_LLM"])

    def test_no_evidence_and_forbidden_scope_remain_distinct(self):
        client = self.client("local_rrf")
        no_evidence = self.post(client, "measured ocean temperature", [])
        forbidden = self.post(client, "quantum", ["doc_fixture_private_other_tenant"])
        self.assertEqual(no_evidence.status_code, 200)
        self.assertEqual(no_evidence.json()["status"], "NO_EVIDENCE")
        self.assertEqual(no_evidence.json()["warnings"], ["LOCAL_RRF_HYBRID_ONLY"])
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json()["code"], "RAG_FORBIDDEN_SCOPE")

    def test_missing_index_and_model_drift_are_rejected_before_serving(self):
        with self.assertRaisesRegex(ValueError, "vector_index_path"):
            create_app(
                retrieval_backend="local_vector",
                embedding_provider=self.provider,
            )
        with self.assertRaises(VectorIndexNotReadyError):
            create_app(
                retrieval_backend="local_vector",
                vector_index_path=self.vector_path,
                embedding_provider=FakeEmbeddingProvider(digest="sha256:changed"),
            )


if __name__ == "__main__":
    unittest.main()
