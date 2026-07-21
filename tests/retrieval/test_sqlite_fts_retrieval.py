import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.retrieval.fixture import load_chunks, load_scope
from backend.retrieval.sqlite_fts import IndexNotReadyError, SQLiteFtsIndex


ROOT = Path(__file__).resolve().parents[2]


class SQLiteFtsRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.index_path = Path(self.temporary_directory.name) / "chunks.sqlite"
        self.chunks = load_chunks(ROOT / "fixtures" / "chunks-v1.json")
        self.scope = load_scope(ROOT / "fixtures" / "authorized-scope-v1.json")
        self.index = SQLiteFtsIndex.build(self.index_path, self.chunks)

    def test_build_records_source_identity_and_chunk_count(self):
        metadata = self.index.inspect()
        self.assertEqual(metadata["schema_version"], "sqlite_fts_index_v1")
        self.assertEqual(metadata["retrieval_backend"], "sqlite_fts5_bm25")
        self.assertEqual(metadata["tokenizer"], "porter_unicode61")
        self.assertEqual(metadata["query_mode"], "OR")
        self.assertEqual(metadata["bm25_column_weights"], "2.0,1.0")
        self.assertEqual(metadata["chunk_count"], str(len(self.chunks)))
        self.assertEqual(len(metadata["source_chunks_sha256"]), 64)

    def test_bm25_retrieval_is_deterministic_and_relevant(self):
        question = "How are candidates combined before reranking?"
        first = self.index.retrieve(
            question, self.scope, expected_chunks=self.chunks
        )
        second = self.index.retrieve(
            question, self.scope, expected_chunks=self.chunks
        )
        self.assertEqual(first, second)
        self.assertEqual(first[0]["chunk_id"], "chunk_fixture_001")

    def test_unauthorized_and_inactive_matches_never_become_candidates(self):
        unauthorized = self.index.retrieve(
            "quantum entanglement", self.scope, expected_chunks=self.chunks
        )
        inactive = self.index.retrieve(
            "obsolete deprecated protocol", self.scope, expected_chunks=self.chunks
        )
        self.assertEqual(unauthorized, [])
        self.assertEqual(inactive, [])

    def test_query_syntax_is_tokenized_instead_of_executed(self):
        results = self.index.retrieve(
            'reranking") OR quantum*', self.scope, expected_chunks=self.chunks
        )
        self.assertTrue(results)
        self.assertEqual(
            {chunk["document_id"] for chunk in results}, {"doc_fixture_001"}
        )

    def test_stale_source_fingerprint_fails_closed(self):
        changed = [dict(chunk) for chunk in self.chunks]
        changed[0]["text"] += " changed"
        with self.assertRaisesRegex(IndexNotReadyError, "fingerprint"):
            self.index.retrieve("reranking", self.scope, expected_chunks=changed)
        with self.assertRaisesRegex(IndexNotReadyError, "fingerprint"):
            self.index.retrieve("what is the", self.scope, expected_chunks=changed)

    def test_duplicate_chunk_ids_are_rejected(self):
        duplicate = self.chunks + [dict(self.chunks[0])]
        with self.assertRaisesRegex(ValueError, "duplicate chunk_id"):
            SQLiteFtsIndex.build(self.index_path, duplicate)

    def test_algorithm_configuration_drift_fails_closed(self):
        connection = sqlite3.connect(self.index_path)
        try:
            connection.execute(
                "UPDATE index_metadata SET value = ? WHERE key = ?",
                ("unicode61", "tokenizer"),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(IndexNotReadyError, "tokenizer"):
            self.index.inspect()

    def test_cli_build_and_inspect(self):
        cli_index = Path(self.temporary_directory.name) / "cli.sqlite"
        completed = subprocess.run(
            [
                "python3",
                "-m",
                "backend.retrieval.sqlite_fts",
                "build",
                "--chunks",
                str(ROOT / "fixtures" / "chunks-v1.json"),
                "--output",
                str(cli_index),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["chunk_count"], str(len(self.chunks)))
        self.assertTrue(cli_index.is_file())


if __name__ == "__main__":
    unittest.main()
