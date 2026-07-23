import json
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.retrieval.elasticsearch import (
    ElasticsearchBm25Index,
    ElasticsearchIndexNotReadyError,
    UrllibElasticsearchTransport,
    _build_parser,
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
        create = next(
            call
            for call in self.transport.calls
            if call[:2] == ("PUT", "/fixture-chunks-v1")
        )
        mapping = json.loads(create[2].decode("utf-8"))
        self.assertEqual(mapping["mappings"]["dynamic"], "strict")
        self.assertEqual(mapping["mappings"]["properties"]["tenant_id"]["type"], "keyword")
        bulk = next(call for call in self.transport.calls if call[1] == "/_bulk")
        self.assertEqual(bulk[3], "application/x-ndjson")
        self.assertIn(self.chunks[0]["text"], bulk[2].decode("utf-8"))

    def test_query_contains_server_side_acl_and_returns_only_authorized_chunks(self):
        self.transport.search_hits = [
            {"_score": 1.25, "_source": self.chunks[0]},
            {"_score": 0.75, "_source": self.chunks[2]},
        ]
        ranking = self.index.search(
            "hybrid retrieval", self.scope, expected_chunks=self.chunks
        )
        results = self.index.retrieve(
            "hybrid retrieval", self.scope, expected_chunks=self.chunks
        )
        self.assertEqual((ranking[0].backend, ranking[0].rank, ranking[0].score), (
            "elasticsearch_bm25", 1, 1.25,
        ))
        self.assertEqual([chunk["chunk_id"] for chunk in results], ["chunk_fixture_001"])
        search = next(call for call in self.transport.calls if call[1].endswith("/_search"))
        payload = json.loads(search[2].decode("utf-8"))
        encoded = json.dumps(payload, sort_keys=True)
        self.assertIn("tenant_id", encoded)
        self.assertIn("library_scope_ids", encoded)
        self.assertIn("is_active", encoded)

    def test_search_emits_validation_query_and_total_latency_breakdown(self):
        self.transport.search_hits = [
            {"_score": 1.25, "_source": self.chunks[0]},
        ]
        timings = []

        self.index.search(
            "hybrid retrieval",
            self.scope,
            expected_chunks=self.chunks,
            timing_sink=timings.append,
        )

        self.assertEqual(len(timings), 1)
        self.assertGreaterEqual(timings[0].validation_latency_ms, 0)
        self.assertGreaterEqual(timings[0].query_latency_ms, 0)
        self.assertGreaterEqual(timings[0].total_latency_ms, 0)

    def test_source_or_configuration_drift_fails_closed(self):
        changed = [dict(chunk) for chunk in self.chunks]
        changed[0]["text"] += " changed"
        with self.assertRaisesRegex(ElasticsearchIndexNotReadyError, "fingerprint"):
            self.index.verify_source(changed)
        self.transport.metadata["query_mode"] = "query_string"
        with self.assertRaisesRegex(ElasticsearchIndexNotReadyError, "query_mode"):
            self.index.inspect()

    def test_online_payload_can_verify_the_staged_source_fingerprint(self):
        staged = [{**chunk, "is_active": False} for chunk in self.chunks]
        online = [{**chunk, "is_active": True} for chunk in self.chunks]
        transport = FakeTransport(staged)
        transport.search_hits = [{"_score": 1.0, "_source": online[0]}]
        index = ElasticsearchBm25Index("fixture-chunks-v1", transport)

        ranking = index.search(
            "hybrid retrieval",
            self.scope,
            expected_chunks=online,
            source_fingerprint_chunks=staged,
        )

        self.assertEqual(ranking[0].chunk["is_active"], True)

    def test_invalid_scope_builds_match_none_filter(self):
        self.transport.search_hits = [{"_score": 1.0, "_source": self.chunks[0]}]
        results = self.index.retrieve("hybrid", {"tenant_id": "tenant_fixture"})
        self.assertEqual(results, [])
        search = next(call for call in self.transport.calls if call[1].endswith("/_search"))
        payload = json.loads(search[2].decode("utf-8"))
        self.assertIn(
            {"match_all": {}},
            payload["query"]["bool"]["filter"][0]["bool"]["must_not"],
        )

    def test_malformed_ranked_hit_fails_closed(self):
        self.transport.search_hits = [{"_source": self.chunks[0]}]
        with self.assertRaisesRegex(
            ElasticsearchIndexNotReadyError, "ranked candidate interface"
        ):
            self.index.search("hybrid", self.scope)

    def test_cli_converts_fixture_arguments_to_paths(self):
        with patch(
            "sys.argv",
            [
                "elasticsearch",
                "--index",
                "fixture-chunks-v1",
                "query",
                "--chunks",
                "fixtures/chunks-v1.json",
                "--scope",
                "fixtures/authorized-scope-v1.json",
                "--question",
                "hybrid retrieval",
            ],
        ):
            args = _build_parser().parse_args()
        self.assertIsInstance(args.chunks, Path)
        self.assertIsInstance(args.scope, Path)

    def test_transport_index_existence_distinguishes_404_from_failures(self):
        transport = UrllibElasticsearchTransport()
        response = MagicMock()
        response.__enter__.return_value.status = 200
        with patch("urllib.request.urlopen", return_value=response):
            self.assertTrue(transport.index_exists("rag-version-v1"))

        missing = urllib.error.HTTPError("url", 404, "missing", None, None)
        with patch("urllib.request.urlopen", side_effect=missing):
            self.assertFalse(transport.index_exists("rag-version-v1"))

        failure = urllib.error.HTTPError("url", 500, "failure", None, None)
        with patch("urllib.request.urlopen", side_effect=failure):
            with self.assertRaisesRegex(ElasticsearchIndexNotReadyError, "HTTP 500"):
                transport.index_exists("rag-version-v1")


if __name__ == "__main__":
    unittest.main()
