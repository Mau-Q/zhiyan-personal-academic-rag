import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.retrieval.elasticsearch import ElasticsearchBm25Index
from backend.retrieval.fixture import load_chunks, load_scope
from backend.retrieval.milvus import MilvusVectorIndex
from backend.retrieval.remote_config import load_remote_retrieval_config
from backend.retrieval.remote_hybrid import RETRIEVAL_BACKEND, RemoteRrfHybridRetriever
from backend.retrieval.sqlite_fts import chunks_fingerprint
from tests.retrieval.fake_embedding import FakeEmbeddingProvider
from tests.retrieval.fake_milvus import FakeMilvusTransport


ROOT = Path(__file__).resolve().parents[2]


class FakeElasticsearchTransport:
    def __init__(self, chunks):
        self.chunks = chunks

    def request(self, method, path, *, body=None, content_type="application/json"):
        del method, body, content_type
        if path.endswith("/_mapping"):
            return {
                "fixture-chunks-v1": {
                    "mappings": {
                        "_meta": {
                            "schema_version": "elasticsearch_bm25_index_v1",
                            "retrieval_backend": "elasticsearch_bm25",
                            "text_analyzer": "standard",
                            "query_mode": "multi_match_or",
                            "section_path_boost": "2.0",
                            "source_chunks_sha256": chunks_fingerprint(self.chunks),
                            "chunk_count": str(len(self.chunks)),
                        }
                    }
                }
            }
        if path.endswith("/_count"):
            return {"count": len(self.chunks)}
        if path.endswith("/_search"):
            return {
                "hits": {
                    "hits": [
                        {"_score": 2.0, "_source": self.chunks[1]},
                        {"_score": 1.0, "_source": self.chunks[0]},
                    ]
                }
            }
        raise AssertionError(path)


class RemoteRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.chunks = load_chunks(ROOT / "fixtures" / "chunks-v1.json")
        self.scope = load_scope(ROOT / "fixtures" / "authorized-scope-v1.json")
        self.provider = FakeEmbeddingProvider()
        self.milvus_transport = FakeMilvusTransport()
        self.milvus = MilvusVectorIndex("fixture_chunks_v1", self.milvus_transport)
        self.milvus.build(self.chunks, self.provider)
        self.elasticsearch = ElasticsearchBm25Index(
            "fixture-chunks-v1", FakeElasticsearchTransport(self.chunks)
        )

    def test_versioned_config_example_loads_and_rejects_credentials(self):
        config = load_remote_retrieval_config(
            ROOT / "deploy" / "remote" / "retrieval-config.example.json"
        )
        self.assertEqual(config.schema_version, "remote_retrieval_config_v1")
        self.assertEqual(config.fusion.candidate_k, 20)

        payload = config.model_dump(mode="json")
        payload["elasticsearch"]["url"] = "http://user:secret@127.0.0.1:9200"
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "invalid.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "must not contain credentials"):
                load_remote_retrieval_config(path)

    def test_remote_rrf_fuses_backend_ranks_deterministically(self):
        retriever = RemoteRrfHybridRetriever(
            self.elasticsearch,
            self.milvus,
            self.provider,
            candidate_k=2,
            rrf_k=60,
            vector_min_score=0.5,
        )
        first = retriever.search(
            "How are candidates combined?",
            self.scope,
            top_k=2,
            expected_chunks=self.chunks,
        )
        second = retriever.search(
            "How are candidates combined?",
            self.scope,
            top_k=2,
            expected_chunks=self.chunks,
        )

        self.assertEqual(
            [item.chunk["chunk_id"] for item in first],
            ["chunk_fixture_001", "chunk_fixture_002"],
        )
        self.assertEqual([item.score for item in first], [item.score for item in second])
        self.assertEqual([item.rank for item in first], [1, 2])
        self.assertTrue(all(item.backend == RETRIEVAL_BACKEND for item in first))


if __name__ == "__main__":
    unittest.main()
