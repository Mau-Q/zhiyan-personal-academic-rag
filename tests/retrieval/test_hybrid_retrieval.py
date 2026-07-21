import tempfile
import unittest
from pathlib import Path

from backend.retrieval.fixture import load_chunks, load_scope
from backend.retrieval.hybrid import LocalRrfHybridRetriever
from backend.retrieval.sqlite_fts import SQLiteFtsIndex
from backend.retrieval.vector import LocalVectorIndex
from tests.retrieval.fake_embedding import FakeEmbeddingProvider


ROOT = Path(__file__).resolve().parents[2]


class LocalRrfHybridRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        temporary = Path(self.temporary_directory.name)
        self.chunks = load_chunks(ROOT / "fixtures" / "chunks-v1.json")
        self.scope = load_scope(ROOT / "fixtures" / "authorized-scope-v1.json")
        self.provider = FakeEmbeddingProvider()
        self.lexical = SQLiteFtsIndex.build(temporary / "lexical.sqlite", self.chunks)
        self.vector = LocalVectorIndex.build(
            temporary / "vector.sqlite", self.chunks, self.provider
        )
        self.hybrid = LocalRrfHybridRetriever(
            self.lexical,
            self.vector,
            self.provider,
            candidate_k=10,
            rrf_k=60,
            vector_min_score=0.5,
        )

    def test_rrf_returns_authorized_fused_candidates_deterministically(self):
        first = self.hybrid.retrieve(
            "How are semantic candidates combined before reranking?",
            self.scope,
            expected_chunks=self.chunks,
        )
        second = self.hybrid.retrieve(
            "How are semantic candidates combined before reranking?",
            self.scope,
            expected_chunks=self.chunks,
        )
        self.assertEqual(first, second)
        self.assertEqual(first[0]["chunk_id"], "chunk_fixture_001")
        self.assertEqual({chunk["document_id"] for chunk in first}, {"doc_fixture_001"})

    def test_irrelevant_and_unauthorized_queries_remain_empty(self):
        self.assertEqual(
            self.hybrid.retrieve(
                "measured ocean temperature", self.scope, expected_chunks=self.chunks
            ),
            [],
        )
        self.assertEqual(
            self.hybrid.retrieve(
                "quantum entanglement", self.scope, expected_chunks=self.chunks
            ),
            [],
        )

    def test_invalid_rrf_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "candidate_k"):
            LocalRrfHybridRetriever(self.lexical, self.vector, self.provider, candidate_k=0)
        with self.assertRaisesRegex(ValueError, "rrf_k"):
            LocalRrfHybridRetriever(self.lexical, self.vector, self.provider, rrf_k=0)


if __name__ == "__main__":
    unittest.main()
