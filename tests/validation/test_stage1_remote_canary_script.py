from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from backend.ingestion.persistent import RuntimeSnapshotPersistenceError
from backend.rag.generation import GenerationServiceError
from scripts.run_stage1_remote_canary import (
    EXPECTED_CLEANUP_JOBS,
    REPORT_SCHEMA_VERSION,
    _ObservedGenerationProvider,
    _generation_replay_byte_stable,
    _require_answer_api_gate,
    _sanitized_error_code,
    build_parser,
)


class Stage1RemoteCanaryScriptTests(unittest.TestCase):
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
