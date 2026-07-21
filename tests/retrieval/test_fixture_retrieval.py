import unittest
from pathlib import Path

from backend.retrieval.fixture import (
    filter_authorized_chunks,
    load_chunks,
    load_scope,
    retrieve_chunks,
)


ROOT = Path(__file__).resolve().parents[2]


class FixtureRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = load_chunks(ROOT / "fixtures" / "chunks-v1.json")
        cls.scope = load_scope(ROOT / "fixtures" / "authorized-scope-v1.json")

    def test_filter_excludes_other_tenant_and_inactive_chunks(self):
        authorized = filter_authorized_chunks(self.chunks, self.scope)
        chunk_ids = {chunk["chunk_id"] for chunk in authorized}
        self.assertEqual(chunk_ids, {"chunk_fixture_001", "chunk_fixture_002"})

    def test_exact_unauthorized_terms_never_enter_candidates(self):
        candidates = retrieve_chunks("quantum entanglement", self.chunks, self.scope)
        self.assertEqual(candidates, [])

    def test_inactive_terms_never_enter_candidates(self):
        candidates = retrieve_chunks("obsolete deprecated scoring", self.chunks, self.scope)
        self.assertEqual(candidates, [])

    def test_retrieval_is_deterministic_and_relevant(self):
        question = "How are candidates combined before reranking?"
        first = retrieve_chunks(question, self.chunks, self.scope)
        second = retrieve_chunks(question, self.chunks, self.scope)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["chunk_id"], "chunk_fixture_001")

    def test_folder_only_scope_fails_closed_until_expanded(self):
        folder_scope = dict(self.scope)
        folder_scope["library_ids"] = []
        folder_scope["folder_ids"] = ["folder_fixture"]
        self.assertEqual(filter_authorized_chunks(self.chunks, folder_scope), [])

    def test_explicit_document_scope_authorizes_private_chunk(self):
        document_scope = dict(self.scope)
        document_scope["library_ids"] = []
        document_scope["document_ids"] = ["doc_fixture_001"]
        authorized = filter_authorized_chunks(self.chunks, document_scope)
        self.assertEqual(
            {chunk["chunk_id"] for chunk in authorized},
            {"chunk_fixture_001", "chunk_fixture_002"},
        )

    def test_public_chunk_requires_include_public(self):
        public_chunk = dict(self.chunks[0])
        public_chunk["visibility"] = "public"
        public_scope = dict(self.scope)
        public_scope["library_ids"] = []
        self.assertEqual(filter_authorized_chunks([public_chunk], public_scope), [])
        public_scope["include_public"] = True
        self.assertEqual(len(filter_authorized_chunks([public_chunk], public_scope)), 1)

    def test_tenant_chunk_requires_same_tenant(self):
        tenant_chunk = dict(self.chunks[0])
        tenant_chunk["visibility"] = "tenant"
        tenant_scope = dict(self.scope)
        tenant_scope["library_ids"] = []
        self.assertEqual(len(filter_authorized_chunks([tenant_chunk], tenant_scope)), 1)
        tenant_scope["tenant_id"] = "tenant_other"
        self.assertEqual(filter_authorized_chunks([tenant_chunk], tenant_scope), [])

    def test_malformed_scope_fails_closed(self):
        malformed_scope = dict(self.scope)
        del malformed_scope["tenant_id"]
        self.assertEqual(filter_authorized_chunks(self.chunks, malformed_scope), [])

    def test_malformed_chunk_fails_closed(self):
        malformed_chunk = dict(self.chunks[0])
        del malformed_chunk["tenant_id"]
        self.assertEqual(filter_authorized_chunks([malformed_chunk], self.scope), [])

    def test_blank_question_and_invalid_top_k_are_rejected(self):
        with self.assertRaises(ValueError):
            retrieve_chunks(" ", self.chunks, self.scope)
        with self.assertRaises(ValueError):
            retrieve_chunks("retrieval", self.chunks, self.scope, top_k=0)


if __name__ == "__main__":
    unittest.main()
