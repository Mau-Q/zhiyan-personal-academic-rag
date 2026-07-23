from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backend.ingestion.persistent import RuntimeSnapshotPersistenceError
from backend.rag.generation import GenerationServiceError
from backend.rag.online_consumer import OnlineRetrievalObservation
from scripts.run_stage1_remote_canary import (
    AcademicQaGateError,
    AnswerHttpGateError,
    EXPECTED_CLEANUP_JOBS,
    ONLINE_RERANKER_COMBINED_P95_LIMIT_MS,
    ONLINE_RERANKER_MINIMUM_LATENCY_SAMPLES,
    REPOSITORY_ROOT,
    REPORT_SCHEMA_VERSION,
    _ObservedGenerationProvider,
    _build_closed_online_reranker_failure_report,
    _build_failure_report,
    _generation_replay_byte_stable,
    _load_academic_question_suite,
    _require_academic_answer_identity_and_location,
    _require_answer_api_gate,
    _sanitized_error_code,
    _summarize_online_reranker_observations,
    build_parser,
)


class Stage1RemoteCanaryScriptTests(unittest.TestCase):
    def test_repository_script_prefers_its_checkout_over_installed_wheel(self):
        self.assertEqual(Path(sys.path[0]).resolve(), REPOSITORY_ROOT)

    def test_v2_contract_includes_runtime_storage_and_three_cleanup_jobs(self):
        args = build_parser().parse_args(
            [
                "--pdf",
                "runtime/canary.pdf",
                "--expected-sha256",
                "0" * 64,
                "--run-id",
                "canary_001",
                "--confirm",
                "RUN_ISOLATED_STAGE1_CANARY",
                "--output",
                "runtime/report.json",
            ]
        )

        self.assertEqual(REPORT_SCHEMA_VERSION, "stage1_remote_canary_report_v2")
        self.assertEqual(EXPECTED_CLEANUP_JOBS, 3)
        self.assertEqual(
            args.pdf_object_root,
            Path("runtime") / "stage1-pdf-objects",
        )
        self.assertEqual(args.online_reranker_latency_repetitions, 0)

    def test_academic_question_suite_pins_digest_pdf_and_target_pages(self):
        with tempfile.TemporaryDirectory(dir="runtime") as temporary:
            path = Path(temporary) / "suite.json"
            payload = {
                "schema_version": "phase2_academic_qa_suite_v1",
                "suite_id": "phase2.qa.doc1",
                "pdf_sha256": "a" * 64,
                "cases": [
                    {
                        "case_id": "qa.case1",
                        "question": "What result was reported?",
                        "required_page_ranges": [{"page_start": 3, "page_end": 4}],
                    }
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()

            suite = _load_academic_question_suite(
                path.relative_to(Path.cwd()),
                expected_sha256=digest,
                expected_pdf_sha256="a" * 64,
            )

            self.assertEqual(suite.suite_id, "phase2.qa.doc1")
            self.assertEqual(suite.cases[0].required_page_ranges, ((3, 4),))

    def test_academic_answer_requires_active_version_identity_and_target_page(self):
        payload = {
            "evidence": [
                {
                    "document_id": "doc_1",
                    "version_id": "version_1",
                    "page_start": 3,
                    "page_end": 4,
                }
            ]
        }
        _require_academic_answer_identity_and_location(
            payload,
            case_id="qa.case1",
            generation_phase="initial",
            document_id="doc_1",
            document_version_id="version_1",
            required_page_ranges=((4, 4),),
        )
        with self.assertRaisesRegex(RuntimeError, "ACADEMIC_QA_LOCATION_GATE_FAILED"):
            _require_academic_answer_identity_and_location(
                payload,
                case_id="qa.case1",
                generation_phase="initial",
                document_id="doc_1",
                document_version_id="version_1",
                required_page_ranges=((8, 8),),
            )
        with self.assertRaisesRegex(RuntimeError, "ACADEMIC_QA_EVIDENCE_IDENTITY_FAILED"):
            _require_academic_answer_identity_and_location(
                payload,
                case_id="qa.case1",
                generation_phase="initial",
                document_id="doc_1",
                document_version_id="version_2",
                required_page_ranges=((3, 3),),
            )

    def test_academic_location_failure_exposes_only_case_and_page_ranges(self):
        payload = {
            "evidence": [
                {
                    "document_id": "doc_1",
                    "version_id": "version_1",
                    "page_start": 7,
                    "page_end": 8,
                    "text": "private evidence must not enter the diagnostic",
                },
                {
                    "document_id": "doc_1",
                    "version_id": "version_1",
                    "page_start": 2,
                    "page_end": 2,
                },
            ]
        }

        with self.assertRaises(AcademicQaGateError) as raised:
            _require_academic_answer_identity_and_location(
                payload,
                case_id="qa.case1",
                generation_phase="replay",
                document_id="doc_1",
                document_version_id="version_1",
                required_page_ranges=((4, 4),),
            )

        error = raised.exception
        self.assertEqual(_sanitized_error_code(error), "ACADEMIC_QA_LOCATION_GATE_FAILED")
        self.assertEqual(
            error.sanitized_detail(),
            {
                "case_id": "qa.case1",
                "generation_phase": "replay",
                "required_page_ranges": [{"page_start": 4, "page_end": 4}],
                "observed_evidence_page_ranges": [
                    {"page_start": 2, "page_end": 2},
                    {"page_start": 7, "page_end": 8},
                ],
            },
        )
        self.assertNotIn("private", json.dumps(error.sanitized_detail()))
        self.assertNotIn("document_id", error.sanitized_detail())

        report = _build_failure_report("phase2_qa_01", error)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["error_code"], "ACADEMIC_QA_LOCATION_GATE_FAILED")
        self.assertEqual(report["academic_qa_failure"], error.sanitized_detail())
        serialized = json.dumps(report)
        self.assertNotIn("private evidence", serialized)
        self.assertNotIn("document_id", serialized)

    def test_academic_suite_requires_real_generation_identity_before_services(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_stage1_remote_canary.py",
                "--pdf",
                "does-not-exist.pdf",
                "--expected-sha256",
                "0" * 64,
                "--run-id",
                "canary_001",
                "--confirm",
                "RUN_ISOLATED_STAGE1_CANARY",
                "--output",
                "runtime/should-not-exist.json",
                "--question-suite",
                "runtime/does-not-exist.json",
                "--expected-question-suite-sha256",
                "0" * 64,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("ACADEMIC_QA_REQUIRES_REAL_GENERATION", result.stderr)
        self.assertNotIn("does-not-exist", result.stderr)

    def test_online_reranker_arguments_must_be_complete_before_services(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_stage1_remote_canary.py",
                "--pdf",
                "does-not-exist.pdf",
                "--expected-sha256",
                "0" * 64,
                "--run-id",
                "canary_001",
                "--confirm",
                "RUN_ISOLATED_STAGE1_CANARY",
                "--output",
                "runtime/should-not-exist.json",
                "--online-reranker-config",
                "evaluation/reranker/"
                "online-fixed-cross-encoder-windows-rtx4090-v1.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("ONLINE_RERANKER_CONFIG_INCOMPLETE", result.stderr)
        self.assertNotIn("does-not-exist", result.stderr)

    def test_online_reranker_latency_summary_requires_applied_bounded_samples(self):
        observations = [
            OnlineRetrievalObservation(
                reranker_status="APPLIED",
                reranker_failure_code=None,
                candidate_count=20,
                output_count=3,
                base_retrieval_latency_ms=50.0,
                reranker_latency_ms=100.0 + position,
                combined_retrieval_latency_ms=150.0 + position,
            )
            for position in range(ONLINE_RERANKER_MINIMUM_LATENCY_SAMPLES)
        ]

        summary = _summarize_online_reranker_observations(observations)

        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(
            summary["sample_count"],
            ONLINE_RERANKER_MINIMUM_LATENCY_SAMPLES,
        )
        self.assertLess(
            summary["combined_retrieval_latency_ms_p95"],
            ONLINE_RERANKER_COMBINED_P95_LIMIT_MS,
        )
        self.assertEqual(summary["fallback_count"], 0)
        self.assertFalse(summary["candidate_set_expanded"])

        fallback = list(observations)
        fallback[-1] = OnlineRetrievalObservation(
            reranker_status="FALLBACK",
            reranker_failure_code="MODEL_SCORING_UNAVAILABLE",
            candidate_count=20,
            output_count=3,
            base_retrieval_latency_ms=50.0,
            reranker_latency_ms=1.0,
            combined_retrieval_latency_ms=51.0,
        )
        fallback_summary = _summarize_online_reranker_observations(fallback)
        self.assertEqual(fallback_summary["status"], "FAIL")
        self.assertEqual(
            fallback_summary["error_code"],
            "ONLINE_RERANKER_FALLBACK_OBSERVED",
        )
        self.assertEqual(fallback_summary["fallback_count"], 1)

    def test_online_reranker_p95_failure_retains_metrics_and_cleanup_evidence(self):
        observations = [
            OnlineRetrievalObservation(
                reranker_status="APPLIED",
                reranker_failure_code=None,
                candidate_count=20,
                output_count=3,
                base_retrieval_latency_ms=180.0 + position,
                reranker_latency_ms=140.0 + position,
                combined_retrieval_latency_ms=320.0 + (2 * position),
            )
            for position in range(ONLINE_RERANKER_MINIMUM_LATENCY_SAMPLES)
        ]

        summary = _summarize_online_reranker_observations(observations)
        report = _build_closed_online_reranker_failure_report(
            run_id="online_reranker_parallel_001",
            error_code="ONLINE_RERANKER_COMBINED_P95_EXCEEDED",
            online_reranker_report=summary,
            resumed_from_ready=True,
            cleanup_jobs_succeeded=EXPECTED_CLEANUP_JOBS,
            inactive_visibility_proven=True,
            inactive_answer_api_status=403,
        )

        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(
            summary["error_code"],
            "ONLINE_RERANKER_COMBINED_P95_EXCEEDED",
        )
        self.assertGreater(
            summary["combined_retrieval_latency_ms_p95"],
            ONLINE_RERANKER_COMBINED_P95_LIMIT_MS,
        )
        self.assertEqual(summary["fallback_count"], 0)
        self.assertFalse(summary["candidate_set_expanded"])
        self.assertEqual(report["online_reranker"], summary)
        self.assertEqual(report["cleanup_jobs_succeeded"], EXPECTED_CLEANUP_JOBS)
        self.assertTrue(report["inactive_visibility_proven"])
        self.assertEqual(report["inactive_answer_api_status"], 403)

    def test_online_reranker_failure_is_deferred_until_lifecycle_cleanup(self):
        source = (
            Path("scripts") / "run_stage1_remote_canary.py"
        ).read_text(encoding="utf-8")

        self.assertLess(
            source.index('raise RuntimeError("RUNTIME_SNAPSHOT_CLEANUP_FAILED")'),
            source.index("failure = _build_closed_online_reranker_failure_report("),
        )
        self.assertLess(
            source.index('raise RuntimeError("INACTIVE_ANSWER_API_REMAINED_VISIBLE")'),
            source.index("failure = _build_closed_online_reranker_failure_report("),
        )

    def test_mutation_requires_exact_confirmation_before_pdf_or_services(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_stage1_remote_canary.py",
                "--pdf",
                "does-not-exist.pdf",
                "--expected-sha256",
                "0" * 64,
                "--run-id",
                "canary_001",
                "--confirm",
                "NO",
                "--output",
                "runtime/should-not-exist.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("EXPLICIT_CONFIRMATION_REQUIRED", result.stderr)
        self.assertNotIn("does-not-exist", result.stderr)

    def test_snapshot_failure_uses_stable_sanitized_error_code(self):
        error = RuntimeSnapshotPersistenceError(
            "CHUNK_SNAPSHOT_PERSIST_FAILED",
            "safe outer message",
        )

        self.assertEqual(
            _sanitized_error_code(error),
            "CHUNK_SNAPSHOT_PERSIST_FAILED",
        )
        self.assertEqual(
            _sanitized_error_code(
                RuntimeError("PERSISTED_SNAPSHOT_ANSWER_API_FAILED")
            ),
            "PERSISTED_SNAPSHOT_ANSWER_API_FAILED",
        )
        self.assertEqual(
            _sanitized_error_code(
                RuntimeError("REAL_GENERATION_INITIAL_FAILED_CLOSED")
            ),
            "REAL_GENERATION_INITIAL_FAILED_CLOSED",
        )
        self.assertEqual(_sanitized_error_code(ValueError("secret")), "ValueError")

    def test_answer_http_failure_reports_only_status_and_allowlisted_code(self):
        with self.assertRaises(AnswerHttpGateError) as raised:
            _require_answer_api_gate(
                status_code=403,
                payload={
                    "code": "RAG_FORBIDDEN_SCOPE",
                    "message": "private response detail",
                },
                generation_enabled=True,
                http_error_code="RAG_FORBIDDEN_SCOPE",
            )

        error = raised.exception
        self.assertEqual(
            _sanitized_error_code(error),
            "PERSISTED_SNAPSHOT_ANSWER_HTTP_FAILED",
        )
        self.assertEqual(
            error.sanitized_detail(),
            {
                "generation_phase": "initial",
                "http_status": 403,
                "api_error_code": "RAG_FORBIDDEN_SCOPE",
            },
        )
        report = _build_failure_report("phase2_qa_01", error)
        self.assertEqual(report["answer_http_failure"], error.sanitized_detail())
        self.assertNotIn("private", json.dumps(report))

    def test_answer_http_failure_redacts_unallowlisted_api_code(self):
        with self.assertRaises(AnswerHttpGateError) as raised:
            _require_answer_api_gate(
                status_code=503,
                payload={"code": "private:error:value"},
                generation_enabled=True,
                replay=True,
                http_error_code="private:error:value",
            )

        error = raised.exception
        self.assertEqual(
            _sanitized_error_code(error),
            "REAL_GENERATION_REPLAY_HTTP_FAILED",
        )
        self.assertEqual(
            error.sanitized_detail(),
            {
                "generation_phase": "replay",
                "http_status": 503,
                "api_error_code": None,
            },
        )

    def test_generation_model_and_digest_must_be_supplied_together(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_stage1_remote_canary.py",
                "--pdf",
                "does-not-exist.pdf",
                "--expected-sha256",
                "0" * 64,
                "--run-id",
                "canary_001",
                "--confirm",
                "RUN_ISOLATED_STAGE1_CANARY",
                "--output",
                "runtime/should-not-exist.json",
                "--generation-model",
                "llama3.2:latest",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("GENERATION_IDENTITY_INCOMPLETE", result.stderr)
        self.assertNotIn("does-not-exist", result.stderr)

    def test_generation_failure_is_classified_without_exposing_warning(self):
        with self.assertRaisesRegex(
            RuntimeError, "^REAL_GENERATION_INITIAL_FAILED_CLOSED$"
        ):
            _require_answer_api_gate(
                status_code=200,
                payload={
                    "status": "DEGRADED",
                    "evidence": [{"evidence_id": "evidence_001"}],
                    "warnings": [
                        "REAL_GENERATION_OLLAMA_LLAMA3_2_LATEST_"
                        "A80C4F17ACD5_ACADEMIC_EVIDENCE_ANSWER_V1_"
                        "FAILED_CLOSED_EVIDENCE_ONLY"
                    ],
                },
                generation_enabled=True,
            )

    def test_generation_failure_uses_observed_allowlisted_detail(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "^REAL_GENERATION_INITIAL_OLLAMA_ANSWER_SCHEMA_INVALID$",
        ):
            _require_answer_api_gate(
                status_code=200,
                payload={
                    "status": "DEGRADED",
                    "evidence": [{"evidence_id": "evidence_001"}],
                    "warnings": ["BOUNDARY_FAILED_CLOSED_EVIDENCE_ONLY"],
                },
                generation_enabled=True,
                generation_failure_code="OLLAMA_ANSWER_SCHEMA_INVALID",
            )
        self.assertEqual(
            _sanitized_error_code(
                RuntimeError(
                    "REAL_GENERATION_INITIAL_OLLAMA_ANSWER_SCHEMA_INVALID"
                )
            ),
            "REAL_GENERATION_INITIAL_OLLAMA_ANSWER_SCHEMA_INVALID",
        )

    def test_generation_observer_captures_code_without_exception_detail(self):
        class FailingProvider:
            def configured_identity(self):
                return None

            def generate(self, question, evidence):
                del question, evidence
                raise GenerationServiceError(
                    "OLLAMA_CHAT_INCOMPLETE",
                    "private upstream detail",
                )

        observer = _ObservedGenerationProvider(FailingProvider())
        with self.assertRaises(GenerationServiceError):
            observer.generate("question", [])
        self.assertEqual(observer.failure_code, "OLLAMA_CHAT_INCOMPLETE")

    def test_generation_replay_citation_gate_has_stable_error_code(self):
        with self.assertRaisesRegex(
            RuntimeError, "^REAL_GENERATION_REPLAY_CITATION_GATE_FAILED$"
        ):
            _require_answer_api_gate(
                status_code=200,
                payload={
                    "status": "COMPLETED",
                    "evidence": [{"evidence_id": "evidence_001"}],
                    "warnings": ["UNEXPECTED_WARNING"],
                },
                generation_enabled=True,
                replay=True,
            )

    def test_generation_gate_accepts_completed_validated_evidence(self):
        _require_answer_api_gate(
            status_code=200,
            payload={
                "status": "COMPLETED",
                "evidence": [{"evidence_id": "evidence_001"}],
                "warnings": [
                    "REAL_GENERATION_OLLAMA_LLAMA3_2_LATEST_"
                    "A80C4F17ACD5_ACADEMIC_EVIDENCE_ANSWER_V1_"
                    "CITATION_IDS_VALIDATED"
                ],
            },
            generation_enabled=True,
        )

    def test_generation_replay_records_non_byte_stable_valid_answers(self):
        self.assertFalse(
            _generation_replay_byte_stable(
                {"answer": "证据未提及资助机构。[1]", "citations": [1]},
                {"answer": "提供的证据没有说明资助机构。[1]", "citations": [1]},
            )
        )

    def test_generation_replay_requires_same_validated_citations(self):
        with self.assertRaisesRegex(
            RuntimeError, "^REAL_GENERATION_REPLAY_CITATION_MISMATCH$"
        ):
            _generation_replay_byte_stable(
                {"answer": "结论。[1]", "citations": [1]},
                {"answer": "结论。[2]", "citations": [2]},
            )


if __name__ == "__main__":
    unittest.main()
