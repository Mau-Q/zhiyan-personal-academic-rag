import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.retrieval.fixture import load_chunks, load_scope
from backend.retrieval.vector import LocalVectorIndex, VectorIndexNotReadyError
from tests.retrieval.fake_embedding import FakeEmbeddingProvider


ROOT = Path(__file__).resolve().parents[2]


class LocalVectorRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.index_path = Path(self.temporary_directory.name) / "chunks.vector.sqlite"
        self.chunks = load_chunks(ROOT / "fixtures" / "chunks-v1.json")
        self.scope = load_scope(ROOT / "fixtures" / "authorized-scope-v1.json")
        self.provider = FakeEmbeddingProvider()
        self.index = LocalVectorIndex.build(self.index_path, self.chunks, self.provider)

    def test_build_records_source_and_model_identity(self):
        metadata = self.index.inspect()
        self.assertEqual(metadata["schema_version"], "local_vector_index_v1")
        self.assertEqual(metadata["retrieval_backend"], "local_dense_exact_cosine")
        self.assertEqual(metadata["embedding_provider"], "test")
        self.assertEqual(metadata["embedding_model"], "semantic-fixture-v1")
        self.assertEqual(metadata["embedding_model_digest"], self.provider.digest)
        self.assertEqual(metadata["embedding_dimension"], "4")
        self.assertEqual(metadata["input_truncation"], "provider_enabled_v1")
        self.assertEqual(metadata["chunk_count"], str(len(self.chunks)))
        self.assertEqual(len(metadata["source_chunks_sha256"]), 64)

    def test_semantic_retrieval_is_deterministic_and_authorized(self):
        first = self.index.retrieve(
            "How are semantic candidates combined?",
            self.scope,
            self.provider,
            min_score=0.5,
            expected_chunks=self.chunks,
        )
        second = self.index.retrieve(
            "How are semantic candidates combined?",
            self.scope,
            self.provider,
            min_score=0.5,
            expected_chunks=self.chunks,
        )
        self.assertEqual(first, second)
        self.assertEqual(first[0]["chunk_id"], "chunk_fixture_001")
        self.assertEqual({chunk["document_id"] for chunk in first}, {"doc_fixture_001"})

    def test_threshold_and_authorization_preserve_no_evidence(self):
        ocean = self.index.retrieve(
            "measured ocean temperature",
            self.scope,
            self.provider,
            min_score=0.5,
            expected_chunks=self.chunks,
        )
        quantum = self.index.retrieve(
            "quantum entanglement",
            self.scope,
            self.provider,
            min_score=0.5,
            expected_chunks=self.chunks,
        )
        self.assertEqual(ocean, [])
        self.assertEqual(quantum, [])

    def test_source_and_model_drift_fail_closed(self):
        changed = [dict(chunk) for chunk in self.chunks]
        changed[0]["text"] += " changed"
        with self.assertRaisesRegex(VectorIndexNotReadyError, "fingerprint"):
            self.index.retrieve(
                "retrieval",
                self.scope,
                self.provider,
                expected_chunks=changed,
            )
        with self.assertRaisesRegex(VectorIndexNotReadyError, "provider identity"):
            self.index.verify_provider(FakeEmbeddingProvider(digest="sha256:changed"))

    def test_metadata_drift_and_invalid_configuration_fail_closed(self):
        connection = sqlite3.connect(self.index_path)
        try:
            connection.execute(
                "UPDATE index_metadata SET value = ? WHERE key = ?",
                ("dot_product", "similarity"),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(VectorIndexNotReadyError, "similarity"):
            self.index.inspect()
        with self.assertRaisesRegex(ValueError, "min_score"):
            self.index.retrieve("retrieval", self.scope, self.provider, min_score=2.0)

    def test_row_count_drift_fails_closed(self):
        connection = sqlite3.connect(self.index_path)
        try:
            connection.execute("DELETE FROM vectors WHERE chunk_id = ?", ("chunk_fixture_001",))
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(VectorIndexNotReadyError, "row count"):
            self.index.inspect()


if __name__ == "__main__":
    unittest.main()
