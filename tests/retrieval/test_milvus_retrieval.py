import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from backend.retrieval.fixture import load_chunks, load_scope
from backend.retrieval.milvus import (
    HNSW_EF_CONSTRUCTION,
    HNSW_M,
    MilvusIndexNotReadyError,
    MilvusVectorIndex,
    PymilvusTransport,
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
        ranking = self.index.search(
            "How are candidates combined?", self.scope, self.provider,
            expected_chunks=self.chunks,
        )
        results = self.index.retrieve(
            "How are candidates combined?", self.scope, self.provider,
            expected_chunks=self.chunks,
        )
        self.assertEqual((ranking[0].backend, ranking[0].rank, ranking[0].score), (
            "milvus_dense_bge_m3", 1, 0.9,
        ))
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

    def test_online_payload_can_verify_the_staged_source_fingerprint(self):
        staged = [{**chunk, "is_active": False} for chunk in self.chunks]
        online = [{**chunk, "is_active": True} for chunk in self.chunks]
        transport = FakeMilvusTransport()
        index = MilvusVectorIndex("fixture_chunks_v1", transport)
        index.build(staged, self.provider)
        for row, chunk in zip(transport.rows, online, strict=True):
            row["is_active"] = True
            row["payload"] = chunk

        ranking = index.search(
            "How are candidates combined?",
            self.scope,
            self.provider,
            expected_chunks=online,
            source_fingerprint_chunks=staged,
        )

        self.assertEqual(ranking[0].chunk["is_active"], True)

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

    def test_invalid_collection_name_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "collection_name is invalid"):
            MilvusVectorIndex("invalid-name", FakeMilvusTransport())

    def test_transport_forwards_version_lifecycle_operations(self):
        transport = object.__new__(PymilvusTransport)
        transport.client = MagicMock()
        transport.client.upsert.return_value = {"upsert_count": 1}
        transport.client.query.return_value = [{"chunk_id": "chunk_001"}]

        self.assertEqual(
            transport.upsert("version_collection", [{"chunk_id": "chunk_001"}]),
            {"upsert_count": 1},
        )
        self.assertEqual(
            transport.query(
                "version_collection",
                filter_expression="",
                output_fields=["chunk_id"],
                limit=16_000,
            ),
            [{"chunk_id": "chunk_001"}],
        )
        transport.drop_collection("version_collection")

        transport.client.upsert.assert_called_once_with(
            collection_name="version_collection",
            data=[{"chunk_id": "chunk_001"}],
        )
        transport.client.query.assert_called_once_with(
            collection_name="version_collection",
            filter="",
            output_fields=["chunk_id"],
            limit=16_000,
        )
        transport.client.drop_collection.assert_called_once_with(
            collection_name="version_collection"
        )


if __name__ == "__main__":
    unittest.main()
