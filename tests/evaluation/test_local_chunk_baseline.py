import hashlib
import tempfile
import unittest
from pathlib import Path

from backend.evaluation.harness import load_cases
from scripts.run_local_chunk_baseline import (
    build_strategy_chunks,
    cases_for_backend,
    chunk_metrics,
    load_config,
    parse_pdf_arguments,
)
from tests.ingestion.pdf_fixture import synthetic_text_pdf


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "evaluation" / "local-3-paper-chunk-baseline-v1.json"
CASES_PATH = ROOT / "evaluation" / "suites" / "fixture-smoke-v1.jsonl"


class LocalChunkBaselineTests(unittest.TestCase):
    def test_tracked_config_pins_three_strategies_and_paper_hashes(self):
        config = load_config(CONFIG_PATH)

        self.assertEqual(
            config["strategies"],
            [
                "fixed_boundary_v1",
                "paragraph_sentence_v1",
                "section_parent_child_v1",
            ],
        )
        self.assertEqual(len(config["papers"]), 3)
        self.assertEqual(config["retrieval"]["top_k"], 3)
        self.assertEqual(config["retrieval"]["vector_min_score"], 0.5)

    def test_backend_cases_change_only_expected_execution_warning(self):
        cases = load_cases(CASES_PATH)

        sqlite_cases = cases_for_backend(cases, "sqlite_fts5")
        vector_cases = cases_for_backend(cases, "local_vector")

        self.assertEqual(
            sqlite_cases[0].expected.required_warnings,
            ["LOCAL_SQLITE_FTS5_FAKE_LLM"],
        )
        self.assertEqual(
            vector_cases[0].expected.required_warnings,
            ["LOCAL_REAL_VECTOR_FAKE_LLM"],
        )
        self.assertEqual(cases[0].expected.required_warnings, ["FIXTURE_ONLY_FAKE_LLM"])
        self.assertEqual(sqlite_cases[-1].expected.required_warnings, [])

    def test_pdf_arguments_reject_duplicate_document_identity(self):
        with self.assertRaisesRegex(ValueError, "duplicate --pdf document id"):
            parse_pdf_arguments(["doc_1=/tmp/a.pdf", "doc_1=/tmp/b.pdf"])

    def test_all_strategies_ingest_deterministically(self):
        pdf = synthetic_text_pdf(
            [
                "I. INTRODUCTION\nAlpha evidence sentence. Beta context sentence.",
                "II. RESULTS\nGamma evidence sentence. Delta conclusion sentence.",
            ]
        )
        digest = hashlib.sha256(pdf).hexdigest()
        config = {
            "papers": [
                {
                    "document_id": "doc_fixture",
                    "file_name": "fixture.pdf",
                    "sha256": digest,
                }
            ]
        }
        scope = {"tenant_id": "tenant_fixture", "library_ids": ["lib_fixture"]}
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "fixture.pdf"
            path.write_bytes(pdf)
            for strategy in (
                "fixed_boundary_v1",
                "paragraph_sentence_v1",
                "section_parent_child_v1",
            ):
                chunks, parse = build_strategy_chunks(
                    config, {"doc_fixture": path}, scope, strategy
                )
                self.assertTrue(chunks)
                self.assertTrue(parse["doc_fixture"]["deterministic_rerun"])
                self.assertEqual(parse["doc_fixture"]["parse_status"], "PASS")

    def test_chunk_metrics_preserve_page_and_parent_observations(self):
        metrics = chunk_metrics(
            [
                {
                    "chunk_id": "chunk_1",
                    "document_id": "doc_1",
                    "text": "abcd",
                    "page_start": 1,
                    "page_end": 1,
                    "parent_chunk_id": None,
                },
                {
                    "chunk_id": "chunk_2",
                    "document_id": "doc_1",
                    "text": "abcdefgh",
                    "page_start": 1,
                    "page_end": 2,
                    "parent_chunk_id": "parent_1",
                },
            ]
        )

        self.assertEqual(metrics["chunk_count"], 2)
        self.assertEqual(metrics["characters"]["median"], 6.0)
        self.assertEqual(metrics["multi_page_chunk_count"], 1)
        self.assertEqual(metrics["parent_linked_chunk_count"], 1)


if __name__ == "__main__":
    unittest.main()
