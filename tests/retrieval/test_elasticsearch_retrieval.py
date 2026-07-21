import json
import unittest
from pathlib import Path

from backend.retrieval.elasticsearch import (
    ElasticsearchBm25Index,
    ElasticsearchIndexNotReadyError,
)
from backend.retrieval.fixture import load_chunks, load_scope
from backend.retrieval.sqlite_fts import chunks_fingerprint


ROOT = Path(__file__).resolve().parents[2]


class FakeTransport:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []
        self.search_hits = []
        self.metadata = {
            "schema_version": "elasticsearch_bm25_index_v1",
            "retrieval_backend": "elasticsearch_bm25",
            "text_analyzer": "standard",
            "query_mode": "multi_match_or",
            "section_path_boost": "2.0",
            "source_chunks_sha256": chunks_fingerprint(chunks),
            "chunk_count": str(len(chunks)),
        }

    def request(self, method, path, *, body=None, content_type="application/json"):
        self.calls.append((method, path, body, content_type))
        if path.endswith("/_mapping"):
            return {"fixture-chunks-v1": {"mappings": {"_meta": self.metadata}}}
        if path.endswith("/_count"):
            return {"count": len(self.chunks)}
        if path.endswith("/_search"):
            return {"hits": {"hits": self.search_hits}}
        if path == "/_bulk":
            return {"errors": False}
        return {"acknowledged": True}


class ElasticsearchRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.chunks = load_chunks(ROOT / "fixtures" / "chunks-v1.json")
        self.scope = load_scope(ROOT / "fixtures" / "authorized-scope-v1.json")
        self.transport = FakeTransport(self.chunks)
        self.index = ElasticsearchBm25Index("fixture-chunks-v1", self.transport)

    def test_build_uses_strict_mapping_identity_and_utf8_bulk(self):
        metadata = self.index.build(self.chunks)
        self.assertEqual(metadata["source_chunks_sha256"], chunks_fingerprint(self.chunks))
        create = next(call for call in self.transport.calls if call[:2] == ("PUT", "/fixture-chunks-v1"))
        mapping = json.loads(create[2].decode("utf-8"))
        self.assertEqual(mapping["mappings"]["dynamic"], "strict")
        self.assertEqual(mapping["mappings"]["properties"]["tenant_id"]["type"], "keyword")
        bulk = next(call for call in self.transport.calls if call[1] == "/_bulk")
        self.assertEqual(bulk[3], "application/x-ndjson")
        self.assertIn(self.chunks[0]["text"], bulk[2].decode("utf-8"))

    def test_query_contains_server_side_acl_and_returns_only_authorized_chunks(self):
        self.transport.search_hits = [
            {"_source": self.chunks[0]},
            {"_source": self.chunks[2]},
        ]
        results = self.index.retrieve(
            "hybrid retrieval", self.scope, expected_chunks=self.chunks
        )
        self.assertEqual([chunk["chunk_id"] for chunk in results], ["chunk_fixture_001"])
        search = next(call for call in self.transport.calls if call[1].endswith("/_search"))
        payload = json.loads(search[2].decode("utf-8"))
        encoded = json.dumps(payload, sort_keys=True)
        self.assertIn("tenant_id", encoded)
        self.assertIn("library_scope_ids", encoded)
        self.assertIn("is_active", encoded)

    def test_source_or_configuration_drift_fails_closed(self):
        changed = [dict(chunk) for chunk in self.chunks]
        changed[0]["text"] += " changed"
        with self.assertRaisesRegex(ElasticsearchIndexNotReadyError, "fingerprint"):
            self.index.verify_source(changed)
        self.transport.metadata["query_mode"] = "query_string"
        with self.assertRaisesRegex(ElasticsearchIndexNotReadyError, "query_mode"):
            self.index.inspect()

    def test_invalid_scope_builds_match_none_filter(self):
        self.transport.search_hits = [{"_source": self.chunks[0]}]
        results = self.index.retrieve("hybrid", {"tenant_id": "tenant_fixture"})
        self.assertEqual(results, [])
        search = next(call for call in self.transport.calls if call[1].endswith("/_search"))
        payload = json.loads(search[2].decode("utf-8"))
        self.assertIn(
            {"match_all": {}},
            payload["query"]["bool"]["filter"][0]["bool"]["must_not"],
        )


if __name__ == "__main__":
    unittest.main()

