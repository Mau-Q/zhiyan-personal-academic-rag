import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.retrieval.fixture import load_chunks
from backend.retrieval.sqlite_fts import IndexNotReadyError, SQLiteFtsIndex


ROOT = Path(__file__).resolve().parents[2]


class SQLiteFtsRagAnswersApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.index_path = Path(self.temporary_directory.name) / "chunks.sqlite"
        self.chunks_path = ROOT / "fixtures" / "chunks-v1.json"
        SQLiteFtsIndex.build(self.index_path, load_chunks(self.chunks_path))
        self.client = TestClient(
            create_app(
                chunks_path=self.chunks_path,
                scope_path=ROOT / "fixtures" / "authorized-scope-v1.json",
                retrieval_backend="sqlite_fts5",
                index_path=self.index_path,
            )
        )

    def post_answer(self, question, document_ids):
        return self.client.post(
            "/api/v1/rag/answers",
            json={"question": question, "document_ids": document_ids, "stream": False},
        )

    def test_supported_question_uses_sqlite_evidence_boundary(self):
        response = self.post_answer(
            "How are candidates combined before reranking?", ["doc_fixture_001"]
        )
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.assertEqual(answer["status"], "COMPLETED")
        self.assertEqual(answer["warnings"], ["LOCAL_SQLITE_FTS5_FAKE_LLM"])
        self.assertEqual(answer["evidence"][0]["document_id"], "doc_fixture_001")

    def test_no_evidence_and_forbidden_scope_remain_distinct(self):
        no_evidence = self.post_answer("measured ocean temperature", ["doc_fixture_001"])
        forbidden = self.post_answer(
            "quantum entanglement", ["doc_fixture_private_other_tenant"]
        )
        self.assertEqual(no_evidence.status_code, 200)
        self.assertEqual(no_evidence.json()["status"], "NO_EVIDENCE")
        self.assertEqual(no_evidence.json()["warnings"], ["LOCAL_SQLITE_FTS5_ONLY"])
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json()["code"], "RAG_FORBIDDEN_SCOPE")

    def test_missing_or_stale_index_is_rejected_before_serving(self):
        with self.assertRaisesRegex(ValueError, "index_path is required"):
            create_app(retrieval_backend="sqlite_fts5")

        changed_chunks_path = Path(self.temporary_directory.name) / "changed.json"
        changed_chunks = load_chunks(self.chunks_path)
        changed_chunks[0]["text"] += " changed"
        changed_chunks_path.write_text(
            json.dumps(changed_chunks, ensure_ascii=False), encoding="utf-8"
        )
        with self.assertRaises(IndexNotReadyError):
            create_app(
                chunks_path=changed_chunks_path,
                retrieval_backend="sqlite_fts5",
                index_path=self.index_path,
            )


if __name__ == "__main__":
    unittest.main()
