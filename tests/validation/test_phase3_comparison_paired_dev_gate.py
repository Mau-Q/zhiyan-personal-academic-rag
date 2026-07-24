from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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
    ROUTE_COVERAGE_CONFIG_SHA256,
    ROUTE_COVERAGE_CONFIRMATION,
    ROUTE_COVERAGE_VARIABLE_ID,
    GateError,
    _cleanup_failure_summary,
    _lf_canonical_sha256,
    _latency_summary,
    _require_empty_cleanup_queue,
    _require_exact_cleanup_scope,
    _retrieval_failure_code,
    _score,
    _strict_two_sided,
    build_parser,
    load_input_package,
    remap_runtime_chunks,
)
from backend.retrieval.elasticsearch import ElasticsearchIndexNotReadyError
from backend.retrieval.embedding import EmbeddingServiceError
from backend.retrieval.milvus import MilvusIndexNotReadyError, MilvusSearchStageError
from backend.retrieval.online import (
    OnlineRetrievalLatencyBreakdown,
    OnlineScopeForbiddenError,
    OnlineVisibilityUnavailableError,
)
from backend.storage.postgres import PostgresFactSourceError


ROOT = Path(__file__).resolve().parents[2]
POWERSHELL_PATH = (
    ROOT
    / "deploy"
    / "remote"
    / "phase3-comparison-validation"
    / "run_phase3_comparison_paired_dev_gate.ps1"
)
AUDIT_POWERSHELL_PATH = (
    ROOT
    / "deploy"
    / "remote"
    / "phase3-comparison-validation"
    / "audit_phase3_comparison_cleanup_state.ps1"
)
RECOVERY_POWERSHELL_PATH = (
    ROOT
    / "deploy"
    / "remote"
    / "phase3-comparison-validation"
    / "recover_phase3_comparison_cleanup.ps1"
)
CLOSEOUT_POWERSHELL_PATH = (
    ROOT
    / "deploy"
    / "remote"
    / "phase3-comparison-validation"
    / "verify_phase3_comparison_closeout.ps1"
)
STATIC_CHECK_POWERSHELL_PATH = ROOT / "scripts" / "check_powershell.ps1"


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

    def test_config_identity_accepts_only_lf_or_equivalent_crlf_bytes(self):
        source = (
            ROOT
            / "evaluation"
            / "phase3"
            / "bilateral-comparison-query-decomposition-v1.json"
        ).read_bytes()
        self.assertEqual(
            _lf_canonical_sha256(
                ROOT
                / "evaluation"
                / "phase3"
                / "bilateral-comparison-query-decomposition-v1.json"
            ),
            CONFIG_SHA256,
        )
        with tempfile.TemporaryDirectory(dir="runtime") as temporary:
            root = Path(temporary)
            crlf = root / "config-crlf.json"
            crlf.write_bytes(source.replace(b"\n", b"\r\n"))
            self.assertEqual(_lf_canonical_sha256(crlf), CONFIG_SHA256)

            changed = root / "config-content-drift.json"
            changed.write_bytes(
                source.replace(b'"default_enabled": false', b'"default_enabled": true')
            )
            self.assertNotEqual(_lf_canonical_sha256(changed), CONFIG_SHA256)

            bom = root / "config-bom.json"
            bom.write_bytes(b"\xef\xbb\xbf" + source)
            self.assertNotEqual(_lf_canonical_sha256(bom), CONFIG_SHA256)

            invalid = root / "config-lone-cr.json"
            invalid.write_bytes(source + b"\r")
            with self.assertRaisesRegex(GateError, "CONFIG_LINE_ENDING_INVALID"):
                _lf_canonical_sha256(invalid)
        self.assertEqual(
            _lf_canonical_sha256(
                ROOT
                / "evaluation"
                / "phase3"
                / "bilateral-comparison-route-coverage-top3-v1.json"
            ),
            ROUTE_COVERAGE_CONFIG_SHA256,
        )

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
        self.assertNotEqual(CONFIRMATION, ROUTE_COVERAGE_CONFIRMATION)

    def test_windows_entry_pins_repo_input_and_cleanup_before_reporting_success(self):
        script = POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn("Target: Windows PowerShell 5.1", script)
        self.assertLess(script.index("git fetch origin main"), script.index("Expand-Archive"))
        self.assertLess(script.index("Get-FileHash"), script.index("Expand-Archive"))
        self.assertIn("RUN_ISOLATED_PHASE3_COMPARISON_DEV_GATE", script)
        self.assertIn("RUN_ISOLATED_PHASE3_ROUTE_COVERAGE_DEV_GATE", script)
        self.assertIn(ROUTE_COVERAGE_VARIABLE_ID, script)
        self.assertIn("'--variable-id'", script)
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
        self.assertIn("function Get-OptionalJsonProperty", script)
        summary = script[script.index("$summary = [ordered]@{") :]
        self.assertIn(
            "primary_error_code = Get-OptionalJsonProperty "
            "-InputObject $report -PropertyPath @('primary_error_code')",
            summary,
        )
        self.assertIn(
            "control_strict_two_sided_passed = Get-OptionalJsonProperty",
            summary,
        )
        self.assertNotIn(
            "primary_error_code = $report.primary_error_code",
            summary,
        )
        self.assertNotIn("question", summary.casefold())
        self.assertNotIn("evidence", summary.casefold())

    def test_cleanup_failure_keeps_stable_stage_and_partial_progress(self):
        summary = _cleanup_failure_summary(
            stage="RUN_WORKER",
            scheduled_versions=3,
            cleanup_results=(
                SimpleNamespace(succeeded=True),
                SimpleNamespace(succeeded=False),
            ),
            inactive_403=False,
            reconciliation_failed_closed=False,
        )
        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["stage"], "RUN_WORKER")
        self.assertEqual(summary["jobs_succeeded"], 1)
        self.assertEqual(summary["jobs_observed"], 2)
        self.assertEqual(summary["jobs_expected"], 9)
        self.assertEqual(
            summary["error_code"],
            "CLEANUP_WORKER_EXECUTION_FAILED",
        )

    def test_retrieval_failure_code_uses_only_stable_component_taxonomy(self):
        failures = (
            (
                EmbeddingServiceError("private embedding detail"),
                "ONLINE_EMBEDDING_SERVICE_FAILED",
            ),
            (
                ElasticsearchIndexNotReadyError("private ES detail"),
                "ONLINE_ELASTICSEARCH_ROUTE_FAILED",
            ),
            (
                MilvusIndexNotReadyError("private Milvus detail"),
                "ONLINE_MILVUS_ROUTE_FAILED",
            ),
            (
                PostgresFactSourceError("private PostgreSQL detail"),
                "ONLINE_POSTGRES_READY_ROUTE_FAILED",
            ),
            (
                OnlineScopeForbiddenError("private scope detail"),
                "ONLINE_SCOPE_FORBIDDEN",
            ),
        )
        for cause, expected in failures:
            try:
                raise cause
            except BaseException as inner:
                try:
                    raise OnlineVisibilityUnavailableError(
                        "generic visibility detail"
                    ) from inner
                except BaseException as outer:
                    code = _retrieval_failure_code(outer)
            self.assertEqual(code, expected)
            self.assertNotIn("private", code.casefold())
        self.assertEqual(
            _retrieval_failure_code(
                OnlineVisibilityUnavailableError("private visibility detail")
            ),
            "ONLINE_VISIBILITY_PROOF_FAILED",
        )
        self.assertEqual(
            _retrieval_failure_code(RuntimeError("private unknown detail")),
            "ONLINE_RETRIEVAL_UNCLASSIFIED_FAILURE",
        )

    def test_retrieval_failure_code_splits_milvus_search_stages(self):
        expected = {
            "ROUTE_IDENTITY": "ONLINE_MILVUS_ROUTE_IDENTITY_FAILED",
            "QUERY_EMBEDDING": "ONLINE_MILVUS_QUERY_EMBEDDING_FAILED",
            "ANN_SEARCH": "ONLINE_MILVUS_ANN_SEARCH_FAILED",
            "RESPONSE_CONTRACT": "ONLINE_MILVUS_RESPONSE_CONTRACT_FAILED",
        }
        for stage, code in expected.items():
            with self.subTest(stage=stage):
                try:
                    raise MilvusSearchStageError(stage)
                except BaseException as inner:
                    try:
                        raise OnlineVisibilityUnavailableError(
                            "private visibility detail"
                        ) from inner
                    except BaseException as outer:
                        observed = _retrieval_failure_code(outer)
                self.assertEqual(observed, code)
                self.assertNotIn("private", observed.casefold())

    def test_windows_cleanup_audit_is_read_only_and_pinned(self):
        script = AUDIT_POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn("Target: Windows PowerShell 5.1", script)
        self.assertIn("$headCommit -ne $ExpectedHeadCommit", script)
        self.assertIn("scripts/audit_phase3_comparison_cleanup_state.py", script)
        self.assertIn("-AsSecureString", script)
        self.assertNotIn("Restart-Service", script)
        self.assertNotIn("Start-Service", script)
        self.assertNotIn("Stop-Service", script)
        self.assertNotIn("PHASE3_COMPARISON_DECOMPOSITION_ENABLED", script)
        self.assertIn("$audit.decision -ne 'CLEAN'", script)
        auditor = (
            ROOT / "scripts" / "audit_phase3_comparison_cleanup_state.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
            auditor,
        )

    def test_windows_recovery_is_exact_and_runs_post_recovery_audit(self):
        script = RECOVERY_POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn("Target: Windows PowerShell 5.1", script)
        self.assertIn("$headCommit -ne $ExpectedHeadCommit", script)
        self.assertIn("RECOVER_EXACT_PHASE3_COMPARISON_02_CLEANUP", script)
        self.assertIn("RECOVER_EXACT_PHASE3_COMPARISON_03_CLEANUP", script)
        self.assertIn(
            "'phase3_comparison_dev_20260723_03'",
            script,
        )
        self.assertIn("'--run-id'", script)
        self.assertIn("scripts/recover_phase3_comparison_cleanup.py", script)
        self.assertIn("scripts/audit_phase3_comparison_cleanup_state.py", script)
        self.assertIn("-AsSecureString", script)
        self.assertNotIn("Restart-Service", script)
        self.assertNotIn("Start-Service", script)
        self.assertNotIn("Stop-Service", script)
        self.assertNotIn("run_phase3_comparison_paired_dev_gate.py", script)
        self.assertIn("$audit.decision -ne 'CLEAN'", script)

    def test_windows_closeout_verifier_is_absolute_safe_and_read_only(self):
        script = CLOSEOUT_POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn("Target: Windows PowerShell 5.1", script)
        self.assertIn("[string]$ExpectedHeadCommit", script)
        self.assertIn("$headCommit -ne $ExpectedHeadCommit", script)
        self.assertIn("$originCommit -ne $ExpectedHeadCommit", script)
        self.assertIn("$runnerPath = Join-Path", script)
        self.assertIn("Parser]::ParseFile(", script)
        self.assertIn("$runnerPath,", script)
        self.assertIn("-RepositoryRoot $RepositoryRoot", script)
        self.assertIn("-SettingsPath $settingsPath", script)
        self.assertIn("Set-StrictMode -Version 2.0", script)
        self.assertIn("Get-OptionalJsonProperty", script)
        self.assertNotIn("& $runnerPath", script)
        self.assertNotIn(".venv\\Scripts\\python.exe", script)
        self.assertNotIn("Restart-Service", script)
        self.assertNotIn("Start-Service", script)
        self.assertNotIn("Stop-Service", script)

        static_check = STATIC_CHECK_POWERSHELL_PATH.read_text(encoding="utf-8")
        parameter_block = static_check[: static_check.index("$ErrorActionPreference")]
        self.assertNotIn("$PSScriptRoot", parameter_block)
        self.assertIn(
            "$RepositoryRoot = Split-Path -Parent $PSScriptRoot",
            static_check,
        )

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
                Connection(
                    [
                        {
                            "owner_id": "other_owner",
                            "document_version_id": "other_version",
                            "backend": "runtime_snapshot",
                        }
                    ]
                )
            )
        expected_rows = [
            {
                "owner_id": "canary_owner",
                "document_version_id": version,
                "backend": backend,
            }
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
                Connection(
                    expected_rows
                    + [
                        {
                            "owner_id": "other",
                            "document_version_id": "version_x",
                            "backend": "runtime_snapshot",
                        }
                    ]
                ),
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
        selection = _latency_summary(
            [_latency(float(value)) for value in range(30)],
            [_latency(float(value + 10)) for value in range(30)],
            [0.2] * 30,
            variable_cost_name="selection",
        )
        self.assertEqual(selection["selection_p95_ms"], 0.2)
        self.assertNotIn("decomposition_p95_ms", selection)


if __name__ == "__main__":
    unittest.main()
