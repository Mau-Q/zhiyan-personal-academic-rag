from __future__ import annotations

import copy
import json
import unittest
from collections.abc import Mapping, Sequence
from typing import Any

from backend.ingestion.index_lifecycle import IndexBackend
from backend.ingestion.milvus_writer import MilvusVersionIndexWriter
from backend.retrieval.milvus import (
    DESCRIPTION_PREFIX,
    EXPECTED_FIELDS,
    MilvusIndexNotReadyError,
    _description,
)
from backend.retrieval.sqlite_fts import chunks_fingerprint
from tests.retrieval.fake_embedding import FakeEmbeddingProvider


OWNER_ID = "owner_001"
DOCUMENT_ID = "document_001"
VERSION_ID = "document_version_001"


def chunks() -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": f"chunk_{position:03d}",
            "document_id": DOCUMENT_ID,
            "version_id": VERSION_ID,
            "text": f"Versioned semantic evidence {position}",
            "section_path": "Method",
            "page_start": position,
            "page_end": position,
            "parent_chunk_id": None,
            "previous_chunk_id": None,
            "next_chunk_id": None,
            "tenant_id": OWNER_ID,
            "visibility": "private",
            "library_scope_ids": ["library_001"],
            "parse_version": "pypdf_text_v1",
            "embedding_version": "bge_m3_v1",
            "is_active": False,
        }
        for position in (1, 2)
    ]


class TrackingEmbeddingProvider(FakeEmbeddingProvider):
    def __init__(self) -> None:
        super().__init__()
        self.embed_calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.embed_calls += 1
        return super().embed(texts)


class FakeMilvusVersionTransport:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, Any]] = {}
        self.upsert_batches: list[list[str]] = []
        self.calls: list[tuple[str, str]] = []

    def has_collection(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(
        self, collection_name: str, *, dimension: int, description: str
    ) -> None:
        self.calls.append(("create", collection_name))
        if collection_name in self.collections:
            raise MilvusIndexNotReadyError("collection already exists")
        self.collections[collection_name] = {
            "description": description,
            "dimension": dimension,
            "fields": set(EXPECTED_FIELDS),
            "rows": {},
        }

    def insert(
        self, collection_name: str, data: list[dict[str, Any]]
    ) -> Mapping[str, Any]:
        raise AssertionError(f"version writer must use upsert: {collection_name} {data}")

    def upsert(
        self, collection_name: str, data: list[dict[str, Any]]
    ) -> Mapping[str, Any]:
        self.calls.append(("upsert", collection_name))
        self.upsert_batches.append([str(row["chunk_id"]) for row in data])
        rows = self.collections[collection_name]["rows"]
        for row in data:
            rows[row["chunk_id"]] = copy.deepcopy(row)
        return {"upsert_count": len(data)}

    def flush(self, collection_name: str) -> None:
        self.calls.append(("flush", collection_name))

    def load_collection(self, collection_name: str) -> None:
        self.calls.append(("load", collection_name))

    def drop_collection(self, collection_name: str) -> None:
        self.calls.append(("drop", collection_name))
        del self.collections[collection_name]

    def describe_collection(self, collection_name: str) -> Mapping[str, Any]:
        collection = self.collections[collection_name]
        return {
            "description": collection["description"],
            "fields": [
                {"name": field_name} for field_name in sorted(collection["fields"])
            ],
        }

    def get_collection_stats(self, collection_name: str) -> Mapping[str, Any]:
        return {"row_count": len(self.collections[collection_name]["rows"])}

    def query(
        self,
        collection_name: str,
        *,
        filter_expression: str,
        output_fields: Sequence[str],
        limit: int,
    ) -> list[Mapping[str, Any]]:
        del filter_expression, output_fields
        rows = self.collections[collection_name]["rows"].values()
        return [copy.deepcopy(row) for row in list(rows)[:limit]]

    def search(
        self,
        collection_name: str,
        *,
        vector: Sequence[float],
        filter_expression: str,
        limit: int,
    ) -> list[list[Mapping[str, Any]]]:
        raise AssertionError(
            f"version writer must not search: {collection_name} {vector} "
            f"{filter_expression} {limit}"
        )


class MilvusVersionIndexWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeMilvusVersionTransport()
        self.provider = TrackingEmbeddingProvider()
        self.writer = MilvusVersionIndexWriter(
            collection_prefix="rag_chunks_v1",
            transport=self.transport,
            provider=self.provider,
        )
        self.chunks = chunks()

    def stage(self):
        return self.writer.ensure_staged(
            owner_id=OWNER_ID,
            document_id=DOCUMENT_ID,
            document_version_id=VERSION_ID,
            chunks=self.chunks,
        )

    def collection_name(self) -> str:
        return self.writer.physical_collection_name(
            owner_id=OWNER_ID,
            document_version_id=VERSION_ID,
        )

    def metadata(self) -> dict[str, Any]:
        raw = self.transport.collections[self.collection_name()]["description"]
        return json.loads(raw.removeprefix(DESCRIPTION_PREFIX))

    def set_metadata(self, metadata: Mapping[str, Any]) -> None:
        self.transport.collections[self.collection_name()]["description"] = _description(
            metadata
        )

    def test_stage_creates_detached_identity_pinned_collection(self):
        receipt = self.stage()
        name = self.collection_name()
        metadata = self.metadata()

        self.assertEqual(receipt.backend, IndexBackend.MILVUS)
        self.assertEqual(receipt.source_chunks_sha256, chunks_fingerprint(self.chunks))
        self.assertNotIn(OWNER_ID, name)
        self.assertNotIn(VERSION_ID, name)
        self.assertEqual(metadata["online_entrypoint"], "DETACHED_VERSION_COLLECTION")
        self.assertEqual(len(metadata["embeddings_sha256"]), 64)
        rows = self.transport.collections[name]["rows"].values()
        self.assertTrue(all(not row["is_active"] for row in rows))
        self.assertEqual(self.provider.embed_calls, 1)

    def test_complete_replay_skips_embedding_and_duplicate_upsert(self):
        first = self.stage()
        embed_calls = self.provider.embed_calls
        upsert_calls = len(self.transport.upsert_batches)

        second = self.stage()

        self.assertEqual(second, first)
        self.assertEqual(self.provider.embed_calls, embed_calls)
        self.assertEqual(len(self.transport.upsert_batches), upsert_calls)

    def test_incomplete_replay_verifies_existing_rows_and_upserts_only_missing(self):
        self.stage()
        rows = self.transport.collections[self.collection_name()]["rows"]
        rows.pop("chunk_002")

        receipt = self.stage()

        self.assertEqual(receipt.chunk_count, 2)
        self.assertEqual(set(rows), {"chunk_001", "chunk_002"})
        self.assertEqual(self.transport.upsert_batches[-1], ["chunk_002"])
        self.assertEqual(self.provider.embed_calls, 2)

    def test_metadata_payload_embedding_and_schema_drift_fail_closed(self):
        self.stage()
        name = self.collection_name()
        metadata = self.metadata()
        upsert_calls = len(self.transport.upsert_batches)

        changed_metadata = dict(metadata, source_chunks_sha256="0" * 64)
        self.set_metadata(changed_metadata)
        with self.assertRaisesRegex(MilvusIndexNotReadyError, "identity drift"):
            self.stage()

        self.set_metadata(metadata)
        rows = self.transport.collections[name]["rows"]
        rows["chunk_001"]["payload"]["text"] = "drifted"
        with self.assertRaisesRegex(MilvusIndexNotReadyError, "payload drift"):
            self.stage()

        rows["chunk_001"]["payload"]["text"] = self.chunks[0]["text"]
        rows["chunk_001"]["embedding"][0] = 0.5
        with self.assertRaisesRegex(MilvusIndexNotReadyError, "embedding identity drift"):
            self.stage()

        rows["chunk_001"]["embedding"][0] = rows["chunk_002"]["embedding"][0]
        self.transport.collections[name]["fields"].remove("payload")
        with self.assertRaisesRegex(MilvusIndexNotReadyError, "schema drift"):
            self.stage()

        self.assertEqual(len(self.transport.upsert_batches), upsert_calls)

    def test_incomplete_collection_embedding_drift_fails_before_repair(self):
        self.stage()
        rows = self.transport.collections[self.collection_name()]["rows"]
        rows.pop("chunk_002")
        rows["chunk_001"]["embedding"][0] = 0.5
        upsert_calls = len(self.transport.upsert_batches)

        with self.assertRaisesRegex(MilvusIndexNotReadyError, "embedding drift"):
            self.stage()

        self.assertEqual(len(self.transport.upsert_batches), upsert_calls)
        self.assertNotIn("chunk_002", rows)

    def test_activate_deactivate_and_delete_are_collection_scoped(self):
        self.stage()
        name = self.collection_name()

        self.writer.activate_version(
            owner_id=OWNER_ID,
            document_version_id=VERSION_ID,
        )
        rows = self.transport.collections[name]["rows"].values()
        self.assertTrue(
            all(row["is_active"] and row["payload"]["is_active"] for row in rows)
        )
        self.writer.deactivate_version(
            owner_id=OWNER_ID,
            document_version_id=VERSION_ID,
        )
        rows = self.transport.collections[name]["rows"].values()
        self.assertTrue(
            all(not row["is_active"] and not row["payload"]["is_active"] for row in rows)
        )
        self.assertTrue(
            self.writer.delete_version(
                owner_id=OWNER_ID,
                document_version_id=VERSION_ID,
            )
        )
        self.assertFalse(
            self.writer.delete_version(
                owner_id=OWNER_ID,
                document_version_id=VERSION_ID,
            )
        )

    def test_invalid_or_active_chunks_fail_before_transport_mutation(self):
        self.chunks[0]["is_active"] = True

        with self.assertRaisesRegex(ValueError, "remain inactive"):
            self.stage()

        self.assertFalse(self.transport.calls)
        self.assertEqual(self.provider.embed_calls, 0)


if __name__ == "__main__":
    unittest.main()
