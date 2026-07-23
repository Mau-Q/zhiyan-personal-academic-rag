from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_phase3_comparison_dev_package import (
    ASSETS,
    TARGET_IDS,
    TARGET_IDS_SHA256,
    _validate_output,
)
from scripts.run_phase3_comparison_paired_dev_gate import (
    CONFIG_SHA256,
    CONFIRMATION,
    EXPECTED_CLEANUP_JOBS,
    GateError,
    _latency_summary,
    _require_empty_cleanup_queue,
    _require_exact_cleanup_scope,
    _score,
    _strict_two_sided,
    build_parser,
    load_input_package,
    remap_runtime_chunks,
)
from backend.retrieval.online import OnlineRetrievalLatencyBreakdown


ROOT = Path(__file__).resolve().parents[2]
POWERSHELL_PATH = (
    ROOT
    / "deploy"
    / "remote"
    / "phase3-comparison-validation"
    / "run_phase3_comparison_paired_dev_gate.ps1"
)


def _latency(value: float) -> OnlineRetrievalLatencyBreakdown:
    return OnlineRetrievalLatencyBreakdown(
        route_count=2,
        ready_route_resolution_latency_ms=1.0,
        chunk_snapshot_latency_ms=1.0,
        elasticsearch_validation_work_latency_ms=1.0,
        elasticsearch_query_work_latency_ms=1.0,
        elasticsearch_total_work_latency_ms=1.0,
        milvus_validation_work_latency_ms=1.0,
        query_embedding_work_latency_ms=1.0,
        milvus_ann_search_work_latency_ms=1.0,
        milvus_total_work_latency_ms=1.0,
        backend_parallel_wall_latency_ms=1.0,
        ready_revalidation_latency_ms=1.0,
        rrf_fusion_latency_ms=1.0,
        total_latency_ms=value,
    )


class Phase3ComparisonPairedDevGateTests(unittest.TestCase):
    def test_frozen_contract_keeps_dev_only_inputs_and_nine_cleanup_jobs(self):
        self.assertEqual(len(ASSETS), 6)
        self.assertEqual(len(TARGET_IDS), 4)
        self.assertEqual(
            TARGET_IDS_SHA256,
            "3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8",
        )
        self.assertEqual(
            CONFIG_SHA256,
            "87b969a1b0f006c3406ab01a24837c5ff129d08bedd0b2460a57122f9d0b0f2b",
        )
        self.assertEqual(EXPECTED_CLEANUP_JOBS, 9)
        self.assertNotIn("test", " ".join(ASSETS))
        self.assertNotIn("acceptance", " ".join(ASSETS))

    def test_parser_requires_explicit_isolated_gate_arguments(self):
        args = build_parser().parse_args(
            [
                "--input-root",
                "runtime/input",
                "--expected-manifest-sha256",
                "0" * 64,
                "--run-id",
                "phase3_dev_001",
                "--expected-head-commit",
                "a" * 40,
                "--confirm",
                CONFIRMATION,
                "--output",
                "runtime/report.json",
            ]
        )
        self.assertEqual(args.latency_repetitions, 30)
        self.assertIn("canary", args.es_index_prefix)
        self.assertIn("canary", args.milvus_collection_prefix)

    def test_windows_entry_pins_repo_input_and_cleanup_before_reporting_success(self):
        script = POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn("Target: Windows PowerShell 5.1", script)
        self.assertLess(script.index("git fetch origin main"), script.index("Expand-Archive"))
        self.assertLess(script.index("Get-FileHash"), script.index("Expand-Archive"))
        self.assertIn("RUN_ISOLATED_PHASE3_COMPARISON_DEV_GATE", script)
        self.assertIn("'--expected-head-commit'", script)
        self.assertIn(
            "scripts/adjudicate_phase3_comparison_paired_dev_report.py",
            script,
        )
        self.assertIn("'--expected-input-manifest-sha256'", script)
        self.assertIn("$adjudication.status -ne 'PASS'", script)
        self.assertIn("$report.cleanup.jobs_succeeded -ne 9", script)
        self.assertIn("$report.cleanup.deleted_answer_api_status -ne 403", script)
        self.assertIn("Remove-Item -LiteralPath $inputRoot -Recurse -Force", script)
        summary = script[script.index("$summary = [ordered]@{") :]
        self.assertNotIn("question", summary.casefold())
        self.assertNotIn("evidence", summary.casefold())

    def test_package_output_must_be_a_runtime_zip(self):
        _validate_output(Path("runtime/phase3/input.zip"))
        for path in (
            Path("phase3.zip"),
            Path("runtime/phase3/input.json"),
            Path("runtime/../test/input.zip"),
        ):
            with self.assertRaises(ValueError):
                _validate_output(path)

    def test_manifest_validation_fails_closed_before_private_rows_are_read(self):
        with tempfile.TemporaryDirectory(dir="runtime") as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")
            with self.assertRaisesRegex(GateError, "INPUT_MANIFEST_IDENTITY_MISMATCH"):
                load_input_package(root.relative_to(Path.cwd()), expected_manifest_sha256="0" * 64)

    def test_runtime_chunk_remap_requires_exact_stable_identity(self):
        frozen = [
            {
                "chunk_id": "source_a",
                "document_id": "source_doc",
                "page_start": 1,
                "page_end": 1,
                "section_path": "Intro",
                "text": "stable text",
            }
        ]
        runtime = [
            {
                "chunk_id": "runtime_a",
                "document_id": "runtime_doc",
                "page_start": 1,
                "page_end": 1,
                "section_path": "Intro",
                "text": "stable text",
            }
        ]
        source_to_runtime, runtime_to_source = remap_runtime_chunks(
            frozen,
            runtime,
            {"source_doc": "runtime_doc"},
        )
        self.assertEqual(source_to_runtime, {"source_a": "runtime_a"})
        self.assertEqual(runtime_to_source, {"runtime_a": "source_a"})
        runtime[0]["text"] = "drift"
        with self.assertRaisesRegex(GateError, "RUNTIME_CHUNK_IDENTITY_MISMATCH"):
            remap_runtime_chunks(frozen, runtime, {"source_doc": "runtime_doc"})

    def test_cleanup_worker_scope_must_be_empty_then_exactly_canary_owned(self):
        class Cursor:
            def __init__(self, rows):
                self.rows = rows

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def execute(self, statement):
                self.statement = statement

            def fetchall(self):
                return self.rows

        class Connection:
            def __init__(self, rows):
                self.rows = rows

            def cursor(self):
                return Cursor(self.rows)

        _require_empty_cleanup_queue(Connection([]))
        with self.assertRaisesRegex(GateError, "CLEANUP_QUEUE_NOT_ISOLATED"):
            _require_empty_cleanup_queue(
                Connection([("other_owner", "other_version", "runtime_snapshot")])
            )
        expected_rows = [
            ("canary_owner", version, backend)
            for version in ("version_1", "version_2", "version_3")
            for backend in (
                "elasticsearch_chunks",
                "milvus_vectors",
                "runtime_snapshot",
            )
        ]
        _require_exact_cleanup_scope(
            Connection(expected_rows),
            owner_id="canary_owner",
            document_version_ids=["version_1", "version_2", "version_3"],
        )
        with self.assertRaisesRegex(GateError, "CLEANUP_QUEUE_SCOPE_MISMATCH"):
            _require_exact_cleanup_scope(
                Connection(expected_rows + [("other", "version_x", "runtime_snapshot")]),
                owner_id="canary_owner",
                document_version_ids=["version_1", "version_2", "version_3"],
            )

    def test_two_sided_metric_uses_relevant_chunk_and_document_identity(self):
        row = {
            "final_labels": {
                "chunk_judgments": [
                    {"chunk_id": "a", "document_id": "doc_a", "relevance": 3},
                    {"chunk_id": "b", "document_id": "doc_b", "relevance": 2},
                ]
            }
        }
        candidates = [{"chunk_id": "ra"}, {"chunk_id": "rb"}]
        mapping = {"ra": "a", "rb": "b"}
        self.assertTrue(_strict_two_sided(row, candidates, mapping))
        score = _score(row, candidates, mapping, k=3)
        self.assertEqual(score["recall"], 1.0)
        self.assertGreater(score["ndcg"], 0.0)

    def test_latency_summary_is_incremental_and_does_not_adjudicate_300ms(self):
        summary = _latency_summary(
            [_latency(float(value)) for value in range(30)],
            [_latency(float(value + 10)) for value in range(30)],
            [0.1] * 30,
        )
        self.assertEqual(summary["sample_count_per_arm"], 30)
        self.assertEqual(summary["incremental_retrieval_p95_ms"], 10.0)
        self.assertEqual(
            summary["absolute_300ms_adjudication"],
            "NOT_RUN_SEPARATE_PERFORMANCE_GATE",
        )


if __name__ == "__main__":
    unittest.main()
