import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.retrieval.fixture import load_chunks
from backend.retrieval.sqlite_fts import chunks_fingerprint


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
            return {"hits": {"hits": [{"_score": 1.0, "_source": self.chunks[0]}]}}
        raise AssertionError(path)


class ElasticsearchRagAnswersApiTests(unittest.TestCase):
    def setUp(self):
        self.chunks_path = ROOT / "fixtures" / "chunks-v1.json"
        chunks = load_chunks(self.chunks_path)
        self.client = TestClient(
            create_app(
                chunks_path=self.chunks_path,
                scope_path=ROOT / "fixtures" / "authorized-scope-v1.json",
                retrieval_backend="elasticsearch_bm25",
                elasticsearch_index="fixture-chunks-v1",
                elasticsearch_transport=FakeElasticsearchTransport(chunks),
            )
        )

    def test_remote_bm25_boundary_is_explicit(self):
        response = self.client.post(
            "/api/v1/rag/answers",
            json={
                "question": "How are candidates combined?",
                "document_ids": ["doc_fixture_001"],
                "stream": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.assertEqual(answer["status"], "COMPLETED")
        self.assertEqual(answer["warnings"], ["REMOTE_ELASTICSEARCH_BM25_FAKE_LLM"])

    def test_remote_backend_requires_an_index_name(self):
        with self.assertRaisesRegex(ValueError, "elasticsearch_index is required"):
            create_app(retrieval_backend="elasticsearch_bm25")


if __name__ == "__main__":
    unittest.main()
