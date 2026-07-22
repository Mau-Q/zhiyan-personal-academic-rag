import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"
EXAMPLES = ROOT / "contracts" / "examples"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class ContractTests(unittest.TestCase):
    def validator(self, schema_name: str) -> Draft202012Validator:
        schema = load_json(SCHEMAS / schema_name)
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema, format_checker=FormatChecker())

    def test_all_json_schemas_are_valid(self):
        schemas = sorted(SCHEMAS.glob("*.schema.json"))
        self.assertGreaterEqual(len(schemas), 5)
        for path in schemas:
            with self.subTest(schema=path.name):
                Draft202012Validator.check_schema(load_json(path))

    def test_core_examples_match_schemas(self):
        pairs = {
            "chunk-record-v1.schema.json": "chunk-record-v1.json",
            "authorized-scope-v1.schema.json": "authorized-scope-v1.json",
            "index-version-v1.schema.json": "index-version-v1.json",
            "document-identity-v1.schema.json": "document-identity-v1.json",
            "document-version-lifecycle-v1.schema.json": "document-version-lifecycle-v1.json",
            "rag-answer-v1.schema.json": "rag-answer-v1.json",
            "trace-v1.schema.json": "trace-v1.json",
            "retrieval-evaluation-item-v1.schema.json": "retrieval-evaluation-item-v1.json",
            "retrieval-annotation-record-v1.schema.json": "retrieval-annotation-record-v1.json",
            "retrieval-ranking-result-v1.schema.json": "retrieval-ranking-result-v1.json",
        }
        for schema_name, example_name in pairs.items():
            with self.subTest(example=example_name):
                self.validator(schema_name).validate(load_json(EXAMPLES / example_name))

    def test_formal_evaluation_manifest_matches_generated_contract(self):
        payload = load_json(ROOT / "evaluation" / "formal" / "fixture-manifest-v1.json")
        self.validator("retrieval-evaluation-manifest-v1.schema.json").validate(payload)

    def test_no_evidence_is_an_explicit_empty_evidence_result(self):
        payload = load_json(EXAMPLES / "rag-no-evidence-v1.json")
        self.validator("rag-answer-v1.schema.json").validate(payload)
        self.assertEqual(payload["status"], "NO_EVIDENCE")
        self.assertEqual(payload["evidence"], [])
        self.assertEqual(payload["citations"], [])
        self.assertTrue(payload["answer"])

    def test_citations_only_reference_returned_evidence(self):
        payload = load_json(EXAMPLES / "rag-answer-v1.json")
        evidence_ids = {item["evidence_id"] for item in payload["evidence"]}
        for citation in payload["citations"]:
            self.assertIn(citation["evidence_id"], evidence_ids)

    def test_fixture_chunks_match_chunk_record_contract(self):
        chunks = load_json(ROOT / "fixtures" / "chunks-v1.json")
        validator = self.validator("chunk-record-v1.schema.json")
        self.assertGreaterEqual(len(chunks), 2)
        for chunk in chunks:
            validator.validate(chunk)
            self.assertLessEqual(chunk["page_start"], chunk["page_end"])

    def test_fixture_scope_matches_authorized_scope_contract(self):
        scope = load_json(ROOT / "fixtures" / "authorized-scope-v1.json")
        self.validator("authorized-scope-v1.schema.json").validate(scope)

    def test_fixture_neighbor_links_are_reciprocal(self):
        chunks = load_json(ROOT / "fixtures" / "chunks-v1.json")
        by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
        for chunk in chunks:
            next_id = chunk["next_chunk_id"]
            if next_id is not None:
                self.assertIn(next_id, by_id)
                self.assertEqual(by_id[next_id]["previous_chunk_id"], chunk["chunk_id"])

    def test_document_identity_policy_is_owner_scoped_and_immutable(self):
        policy = load_json(ROOT / "contracts" / "data-identity-lifecycle-v1.json")
        mapping = policy["identity_mapping"]

        self.assertEqual(policy["source_of_truth"], "POSTGRESQL")
        self.assertEqual(mapping["mapping_scope"], "OWNER_SCOPED")
        self.assertEqual(
            mapping["unique_constraints"], [["document_id"], ["owner_id", "paper_id"]]
        )
        self.assertTrue(mapping["bidirectional_lookup_requires_owner_id"])
        self.assertEqual(mapping["client_trusted_fields"], [])
        self.assertEqual(
            set(mapping["immutable_fields"]),
            {"owner_id", "paper_id", "document_id", "source_type"},
        )
        self.assertEqual(
            policy["lifecycle"]["allowed_transitions"]["READY"], ["INACTIVE"]
        )

    def test_ready_lifecycle_requires_both_indexes_and_no_soft_delete(self):
        payload = load_json(EXAMPLES / "document-version-lifecycle-v1.json")
        validator = self.validator("document-version-lifecycle-v1.schema.json")
        validator.validate(payload)

        missing_vector = deepcopy(payload)
        missing_vector["index_states"]["milvus_vectors"] = "PENDING"
        self.assertTrue(list(validator.iter_errors(missing_vector)))

        deleted_ready = deepcopy(payload)
        deleted_ready["delete_time"] = "2026-07-22T00:03:00Z"
        self.assertTrue(list(validator.iter_errors(deleted_ready)))

    def test_inactive_and_failed_lifecycle_states_fail_closed(self):
        payload = load_json(EXAMPLES / "document-version-lifecycle-v1.json")
        validator = self.validator("document-version-lifecycle-v1.schema.json")

        inactive = deepcopy(payload)
        inactive["lifecycle_status"] = "INACTIVE"
        self.assertTrue(list(validator.iter_errors(inactive)))
        inactive["delete_time"] = "2026-07-22T00:03:00Z"
        validator.validate(inactive)

        processing_deleted = deepcopy(inactive)
        processing_deleted["lifecycle_status"] = "PROCESSING"
        self.assertTrue(list(validator.iter_errors(processing_deleted)))

        failed = deepcopy(payload)
        failed["lifecycle_status"] = "FAILED"
        self.assertTrue(list(validator.iter_errors(failed)))
        failed["failure_code"] = "RAG_INDEX_NOT_READY"
        validator.validate(failed)

    def test_sample_catalog_contains_metadata_only(self):
        catalog = load_json(ROOT / "fixtures" / "sample-corpus-v1.json")
        self.assertEqual(catalog["storage_policy"], "local_only")
        self.assertFalse(catalog["redistribution_allowed"])
        self.assertGreaterEqual(len(catalog["documents"]), 5)
        for document in catalog["documents"]:
            self.assertRegex(document["sha256"], r"^[a-f0-9]{64}$")
            self.assertTrue(document["source_url"].startswith("https://arxiv.org/pdf/"))
            self.assertFalse(Path(document["file_name"]).is_absolute())

    def test_openapi_exposes_only_the_stage_zero_answer_endpoint(self):
        spec = load_json(ROOT / "contracts" / "openapi.json")
        self.assertEqual(spec["openapi"], "3.1.0")
        self.assertEqual(set(spec["paths"]), {"/api/v1/rag/answers"})
        operation = spec["paths"]["/api/v1/rag/answers"]["post"]
        self.assertIn("200", operation["responses"])
        self.assertIn("403", operation["responses"])
        self.assertIn("422", operation["responses"])


if __name__ == "__main__":
    unittest.main()
