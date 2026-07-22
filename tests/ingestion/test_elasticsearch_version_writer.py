from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from typing import Any

from backend.ingestion.elasticsearch_writer import ElasticsearchVersionIndexWriter
from backend.ingestion.index_lifecycle import IndexBackend
from backend.retrieval.elasticsearch import ElasticsearchIndexNotReadyError
from backend.retrieval.sqlite_fts import chunks_fingerprint


OWNER_ID = "owner_001"
DOCUMENT_ID = "document_001"
VERSION_ID = "document_version_001"


def chunks() -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": f"chunk_{position:03d}",
            "document_id": DOCUMENT_ID,
            "version_id": VERSION_ID,
            "text": f"Versioned evidence {position}",
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


class FakeElasticsearchVersionTransport:
    def __init__(self) -> None:
        self.indexes: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, str, bytes | None, str]] = []

    def index_exists(self, index_name: str) -> bool:
        return index_name in self.indexes

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        self.calls.append((method, path, body, content_type))
        if method == "PUT":
            name = path.removeprefix("/")
            if name in self.indexes:
                raise ElasticsearchIndexNotReadyError("index already exists")
            self.indexes[name] = {
                "mapping": json.loads(body.decode("utf-8")),
                "docs": {},
            }
            return {"acknowledged": True}
        if path == "/_bulk":
            lines = body.decode("utf-8").splitlines()
            for position in range(0, len(lines), 2):
                action = json.loads(lines[position])["index"]
                document = json.loads(lines[position + 1])
                self.indexes[action["_index"]]["docs"][action["_id"]] = document
            return {"errors": False}

        name = path.split("/", 2)[1]
        index = self.indexes[name]
        if method == "GET" and path.endswith("/_mapping"):
            return {name: {"mappings": index["mapping"]["mappings"]}}
        if method == "GET" and path.endswith("/_settings/index.hidden"):
            hidden = index["mapping"]["settings"].get("index.hidden")
            return {name: {"settings": {"index": {"hidden": str(hidden).lower()}}}}
        if path.endswith("/_count"):
            query = None if body is None else json.loads(body.decode("utf-8"))["query"]
            return {
                "count": sum(
                    self._matches(document, query)
                    for document in index["docs"].values()
                )
            }
        if path.endswith("/_mget"):
            ids = json.loads(body.decode("utf-8"))["ids"]
            return {
                "docs": [
                    {
                        "_id": chunk_id,
                        "found": chunk_id in index["docs"],
                        "_source": index["docs"].get(chunk_id),
                    }
                    for chunk_id in ids
                ]
            }
        if "_update_by_query" in path:
            payload = json.loads(body.decode("utf-8"))
            active = payload["script"]["params"]["is_active"]
            updated = 0
            for document in index["docs"].values():
                if self._matches(document, payload["query"]):
                    document["is_active"] = active
                    updated += 1
            return {"updated": updated, "failures": []}
        if method == "POST" and path.endswith("/_refresh"):
            return {"_shards": {"successful": 1}}
        if method == "DELETE":
            del self.indexes[name]
            return {"acknowledged": True}
        raise AssertionError(f"unexpected request: {method} {path}")

    def _matches(self, document: Mapping[str, Any], query: Any) -> bool:
        if query is None:
            return True
        if "term" in query:
            field, value = next(iter(query["term"].items()))
            return document.get(field) == value
        if "bool" in query:
            return all(
                self._matches(document, clause)
                for clause in query["bool"].get("filter", [])
            )
        raise AssertionError(f"unsupported query: {query}")


class ElasticsearchVersionIndexWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeElasticsearchVersionTransport()
        self.writer = ElasticsearchVersionIndexWriter(
            index_prefix="rag-chunks-v1",
            transport=self.transport,
        )
        self.chunks = chunks()

    def stage(self):
        return self.writer.ensure_staged(
            owner_id=OWNER_ID,
            document_id=DOCUMENT_ID,
            document_version_id=VERSION_ID,
            chunks=self.chunks,
        )

    def test_stage_creates_hidden_identity_pinned_physical_index(self):
        receipt = self.stage()
        name = self.writer.physical_index_name(
            owner_id=OWNER_ID,
            document_version_id=VERSION_ID,
        )

        self.assertEqual(receipt.backend, IndexBackend.ELASTICSEARCH)
        self.assertEqual(receipt.source_chunks_sha256, chunks_fingerprint(self.chunks))
        self.assertNotIn(OWNER_ID, name)
        self.assertNotIn(VERSION_ID, name)
        metadata = self.transport.indexes[name]["mapping"]["mappings"]["_meta"]
        self.assertEqual(metadata["online_entrypoint"], "HIDDEN_PHYSICAL_INDEX")
        self.assertIs(
            self.transport.indexes[name]["mapping"]["settings"]["index.hidden"],
            True,
        )
        documents = self.transport.indexes[name]["docs"].values()
        self.assertTrue(
            all(not document["is_active"] for document in documents)
        )
        self.assertFalse(any("_aliases" in call[1] for call in self.transport.calls))

    def test_replay_reuses_complete_index_without_duplicate_bulk(self):
        first = self.stage()
        bulk_count = sum(call[1] == "/_bulk" for call in self.transport.calls)

        second = self.stage()

        self.assertEqual(second, first)
        self.assertEqual(
            sum(call[1] == "/_bulk" for call in self.transport.calls),
            bulk_count,
        )

    def test_replay_repairs_an_incomplete_but_identity_matching_index(self):
        self.stage()
        name = self.writer.physical_index_name(
            owner_id=OWNER_ID,
            document_version_id=VERSION_ID,
        )
        self.transport.indexes[name]["docs"].pop("chunk_002")

        receipt = self.stage()

        self.assertEqual(receipt.chunk_count, 2)
        self.assertEqual(len(self.transport.indexes[name]["docs"]), 2)
        self.assertEqual(sum(call[1] == "/_bulk" for call in self.transport.calls), 2)

    def test_incomplete_index_with_existing_payload_drift_fails_before_repair(self):
        self.stage()
        name = self.writer.physical_index_name(
            owner_id=OWNER_ID,
            document_version_id=VERSION_ID,
        )
        documents = self.transport.indexes[name]["docs"]
        documents.pop("chunk_002")
        documents["chunk_001"]["text"] = "drifted"
        bulk_count = sum(call[1] == "/_bulk" for call in self.transport.calls)

        with self.assertRaisesRegex(ElasticsearchIndexNotReadyError, "payload drift"):
            self.stage()

        self.assertEqual(
            sum(call[1] == "/_bulk" for call in self.transport.calls),
            bulk_count,
        )

    def test_source_identity_drift_fails_closed_without_rewrite(self):
        self.stage()
        name = self.writer.physical_index_name(
            owner_id=OWNER_ID,
            document_version_id=VERSION_ID,
        )
        metadata = self.transport.indexes[name]["mapping"]["mappings"]["_meta"]
        metadata["source_chunks_sha256"] = "0" * 64
        bulk_count = sum(call[1] == "/_bulk" for call in self.transport.calls)

        with self.assertRaisesRegex(ElasticsearchIndexNotReadyError, "identity drift"):
            self.stage()

        self.assertEqual(
            sum(call[1] == "/_bulk" for call in self.transport.calls),
            bulk_count,
        )

        metadata["source_chunks_sha256"] = chunks_fingerprint(self.chunks)
        self.transport.indexes[name]["docs"]["chunk_001"]["text"] = "drifted"
        with self.assertRaisesRegex(ElasticsearchIndexNotReadyError, "payload drift"):
            self.stage()

        self.transport.indexes[name]["docs"]["chunk_001"]["text"] = self.chunks[0][
            "text"
        ]
        properties = self.transport.indexes[name]["mapping"]["mappings"]["properties"]
        properties["version_id"]["type"] = "text"
        with self.assertRaisesRegex(ElasticsearchIndexNotReadyError, "mapping drift"):
            self.stage()

    def test_activate_deactivate_and_delete_are_owner_version_scoped(self):
        self.stage()
        name = self.writer.physical_index_name(
            owner_id=OWNER_ID,
            document_version_id=VERSION_ID,
        )

        self.writer.activate_version(
            owner_id=OWNER_ID,
            document_version_id=VERSION_ID,
        )
        self.assertTrue(
            all(document["is_active"] for document in self.transport.indexes[name]["docs"].values())
        )
        self.writer.deactivate_version(
            owner_id=OWNER_ID,
            document_version_id=VERSION_ID,
        )
        documents = self.transport.indexes[name]["docs"].values()
        self.assertTrue(
            all(not document["is_active"] for document in documents)
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


if __name__ == "__main__":
    unittest.main()
