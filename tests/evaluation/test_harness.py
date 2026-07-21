import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backend.evaluation.harness import DEFAULT_CASES_PATH, load_cases, run_suite
from backend.rag.sqlite_fts_consumer import SQLITE_FTS_EXECUTION_BOUNDARY
from backend.rag.vector_consumer import RRF_EXECUTION_BOUNDARY, VECTOR_EXECUTION_BOUNDARY
from backend.retrieval.fixture import load_chunks
from backend.retrieval.sqlite_fts import SQLiteFtsIndex
from backend.retrieval.vector import LocalVectorIndex
from tests.retrieval.fake_embedding import FakeEmbeddingProvider


ROOT = Path(__file__).resolve().parents[2]
SQLITE_CASES_PATH = ROOT / "evaluation" / "suites" / "fixture-sqlite-fts-v1.jsonl"


class EvaluationHarnessTests(unittest.TestCase):
    def test_checked_in_fixture_suite_passes_all_three_categories(self):
        report = run_suite(load_cases(DEFAULT_CASES_PATH), suite_id="fixture-smoke-v1")

        self.assertEqual(report["summary"]["total"], 6)
        self.assertEqual(report["summary"]["passed"], 6)
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(
            set(report["summary"]["categories"]),
            {"ANSWERABLE", "NO_EVIDENCE", "FORBIDDEN"},
        )
        self.assertEqual(report["execution_boundary"], "LOCAL_API_FAKE_LLM")

    def test_missing_required_page_is_reported_as_failure(self):
        case = load_cases(DEFAULT_CASES_PATH)[0].model_copy(deep=True)
        case.expected.required_evidence[0].page_start = 99
        case.expected.required_evidence[0].page_end = 99

        report = run_suite([case], suite_id="expected-failure")

        self.assertEqual(report["summary"]["failed"], 1)
        self.assertIn("required_evidence missing", report["results"][0]["failures"][0])

    def test_duplicate_case_ids_are_rejected(self):
        first_line = DEFAULT_CASES_PATH.read_text(encoding="utf-8").splitlines()[0]
        with tempfile.TemporaryDirectory() as temporary_directory:
            cases_path = Path(temporary_directory) / "duplicates.jsonl"
            cases_path.write_text(f"{first_line}\n{first_line}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate evaluation case_id"):
                load_cases(cases_path)

    def test_category_contract_mismatch_is_rejected(self):
        payload = json.loads(DEFAULT_CASES_PATH.read_text(encoding="utf-8").splitlines()[0])
        payload["expected"]["answer_status"] = "NO_EVIDENCE"
        with tempfile.TemporaryDirectory() as temporary_directory:
            cases_path = Path(temporary_directory) / "invalid-category.jsonl"
            cases_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ANSWERABLE requires"):
                load_cases(cases_path)

    def test_cli_writes_machine_readable_report_and_returns_zero(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "report.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.evaluation.harness",
                    "--output",
                    str(report_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["passed"], 6)
            self.assertIn("6/6 cases passed", completed.stdout)

    def test_same_suite_runs_through_sqlite_fts_backend(self):
        cases = load_cases(SQLITE_CASES_PATH)

        with tempfile.TemporaryDirectory() as temporary_directory:
            index_path = Path(temporary_directory) / "chunks.sqlite"
            SQLiteFtsIndex.build(
                index_path, load_chunks(ROOT / "fixtures" / "chunks-v1.json")
            )
            report = run_suite(
                cases,
                suite_id="fixture-sqlite-fts-v1",
                retrieval_backend="sqlite_fts5",
                index_path=index_path,
            )

        self.assertEqual(report["summary"]["passed"], 6)
        self.assertEqual(report["retrieval_backend"], "sqlite_fts5")
        self.assertEqual(
            report["execution_boundary"], SQLITE_FTS_EXECUTION_BOUNDARY
        )

    def test_same_suite_runs_through_vector_and_rrf_backends(self):
        cases = load_cases(SQLITE_CASES_PATH)
        chunks = load_chunks(ROOT / "fixtures" / "chunks-v1.json")
        provider = FakeEmbeddingProvider()

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            vector_path = temporary / "chunks.vector.sqlite"
            fts_path = temporary / "chunks.fts.sqlite"
            LocalVectorIndex.build(vector_path, chunks, provider)
            SQLiteFtsIndex.build(fts_path, chunks)

            vector_cases = [case.model_copy(deep=True) for case in cases]
            for case in vector_cases:
                if case.category == "ANSWERABLE":
                    case.expected.required_warnings = ["LOCAL_REAL_VECTOR_FAKE_LLM"]
                elif case.category == "NO_EVIDENCE":
                    case.expected.required_warnings = ["LOCAL_REAL_VECTOR_ONLY"]
            vector_report = run_suite(
                vector_cases,
                suite_id="fixture-vector-v1",
                retrieval_backend="local_vector",
                vector_index_path=vector_path,
                embedding_provider=provider,
                embedding_model="semantic-fixture-v1",
                vector_min_score=0.5,
            )

            rrf_cases = [case.model_copy(deep=True) for case in cases]
            for case in rrf_cases:
                if case.category == "ANSWERABLE":
                    case.expected.required_warnings = ["LOCAL_RRF_HYBRID_FAKE_LLM"]
                elif case.category == "NO_EVIDENCE":
                    case.expected.required_warnings = ["LOCAL_RRF_HYBRID_ONLY"]
            rrf_report = run_suite(
                rrf_cases,
                suite_id="fixture-rrf-v1",
                retrieval_backend="local_rrf",
                index_path=fts_path,
                vector_index_path=vector_path,
                embedding_provider=provider,
                embedding_model="semantic-fixture-v1",
                vector_min_score=0.5,
            )

        self.assertEqual(vector_report["summary"]["passed"], 6)
        self.assertEqual(vector_report["execution_boundary"], VECTOR_EXECUTION_BOUNDARY)
        self.assertEqual(
            vector_report["retrieval_configuration"]["embedding_model_digest"],
            provider.digest,
        )
        self.assertEqual(vector_report["retrieval_configuration"]["embedding_dimension"], 4)
        self.assertEqual(rrf_report["summary"]["passed"], 6)
        self.assertEqual(rrf_report["execution_boundary"], RRF_EXECUTION_BOUNDARY)


if __name__ == "__main__":
    unittest.main()
