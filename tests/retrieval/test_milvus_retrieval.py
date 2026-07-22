import json
import unittest
from pathlib import Path

from backend.retrieval.fixture import load_chunks, load_scope
from backend.retrieval.milvus import (
    HNSW_EF_CONSTRUCTION,
    HNSW_M,
    MilvusIndexNotReadyError,
    MilvusVectorIndex,
)
from tests.retrieval.fake_embedding import FakeEmbeddingProvider
from tests.retrieval.fake_milvus import FakeMilvusTransport


ROOT = Path(__file__).resolve().parents[2]


class MilvusVectorRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.chunks = load_chunks(ROOT / "fixtures" / "chunks-v1.json")
        self.scope = load_scope(ROOT / "fixtures" / "authorized-scope-v1.json")
        self.provider = FakeEmbeddingProvider()
        self.transport = FakeMilvusTransport()
        self.index = MilvusVectorIndex("fixture_chunks_v1", self.transport)
        self.metadata = self.index.build(self.chunks, self.provider)

    def test_build_pins_model_source_schema_and_hnsw_baseline(self):
        self.assertEqual(self.metadata["embedding_dimension"], "4")
        self.assertEqual(self.metadata["embedding_model_digest"], self.provider.digest)
        self.assertEqual(self.metadata["hnsw_m"], str(HNSW_M))
        self.assertEqual(self.metadata["hnsw_ef_construction"], str(HNSW_EF_CONSTRUCTION))
        self.assertEqual(len(self.transport.rows), len(self.chunks))
        self.assertAlmostEqual(
            sum(value * value for value in self.transport.rows[0]["embedding"]), 1.0
        )

    def test_retrieve_pushes_acl_filter_and_defensively_filters_hits(self):
        results = self.index.retrieve(
            "How are candidates combined?", self.scope, self.provider,
            expected_chunks=self.chunks,
        )
        self.assertEqual(results[0]["chunk_id"], "chunk_fixture_001")
        self.assertIn('tenant_id == "tenant_fixture"', self.transport.last_filter)
        self.assertIn("array_contains_any", self.transport.last_filter)

    def test_folder_only_or_invalid_scope_fails_closed(self):
        folder_scope = dict(self.scope, library_ids=[], document_ids=[], folder_ids=["folder-x"])
        self.index.retrieve("test", folder_scope, self.provider, expected_chunks=self.chunks)
        self.assertEqual(
            self.transport.last_filter, "is_active == true and is_active == false"
        )
        invalid_scope = dict(self.scope)
        invalid_scope.pop("acl_version")
        self.index.retrieve("test", invalid_scope, self.provider, expected_chunks=self.chunks)
        self.assertEqual(
            self.transport.last_filter, "is_active == true and is_active == false"
        )

    def test_source_and_model_drift_are_rejected(self):
        changed = [dict(chunk) for chunk in self.chunks]
        changed[0]["text"] += " changed"
        with self.assertRaisesRegex(MilvusIndexNotReadyError, "source fingerprint"):
            self.index.verify_source(changed)
        with self.assertRaisesRegex(MilvusIndexNotReadyError, "model identity"):
            self.index.verify_provider(FakeEmbeddingProvider(digest="sha256:changed"))

    def test_identity_configuration_drift_is_rejected(self):
        prefix, payload = self.transport.description.split(":", 1)
        metadata = json.loads(payload)
        metadata["metric_type"] = "L2"
        self.transport.description = prefix + ":" + json.dumps(metadata)
        with self.assertRaisesRegex(MilvusIndexNotReadyError, "metric_type"):
            self.index.inspect()

    def test_existing_collection_is_not_overwritten(self):
        with self.assertRaisesRegex(MilvusIndexNotReadyError, "already exists"):
            self.index.build(self.chunks, self.provider)


if __name__ == "__main__":
    unittest.main()
