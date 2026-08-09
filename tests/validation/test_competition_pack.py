from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from backend.rag.claim_evidence import GeneratedClaim
from backend.rag.generation import GenerationModelIdentity, GenerationResult
from backend.validation.competition import (
    CompetitionCapture,
    build_redacted_result,
    lf_canonical_text_sha256,
    redact_text,
)
from scripts import prepare_competition_input
from scripts.run_competition_real_core import _validate_finalized_artifact_hashes
from scripts.run_stage1_remote_canary import (
    _ObservedGenerationProvider,
    _require_answer_api_gate,
)
from scripts.validate_competition_pack import (
    EXPECTED_SCENARIO_IDS,
    validate_static,
)


ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StaticCompetitionPackTests(unittest.TestCase):
    def test_manifest_has_exactly_three_valid_scenarios(self):
        validated = validate_static()
        self.assertEqual(
            tuple(validated["manifest"]["scenario_ids"]),
            EXPECTED_SCENARIO_IDS,
        )
        self.assertEqual(len(validated["manifest"]["scenario_manifests"]), 3)

    def test_tracked_pack_text_identity_accepts_equivalent_crlf(self):
        manifest = json.loads(
            (ROOT / "machine/competition/rag-competition-pack-v1.json").read_text(
                encoding="utf-8"
            )
        )
        runtime = ROOT / "runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as temporary:
            temp_root = Path(temporary)
            phase4_reference = next(
                gate["reference"]
                for gate in manifest["historical_real_gates"]
                if gate["id"] == "phase4-multi-evidence-set"
            )
            tracked_paths = [*manifest["tracked_pack_artifacts"], phase4_reference]
            crlf_paths = {}
            expected_hashes = {}
            for index, relative in enumerate(tracked_paths):
                source = ROOT / relative
                expected = lf_canonical_text_sha256(source)
                crlf = temp_root / f"artifact-{index}"
                crlf.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
                crlf_paths[relative] = crlf
                expected_hashes[relative] = expected
                self.assertEqual(
                    lf_canonical_text_sha256(crlf),
                    expected,
                    msg=relative,
                )
            with patch(
                "scripts.validate_competition_pack._repository_path",
                side_effect=lambda relative: crlf_paths[relative],
            ):
                validated = validate_static()
            self.assertEqual(
                validated["artifact_hashes"],
                {
                    relative: expected_hashes[relative]
                    for relative in manifest["tracked_pack_artifacts"]
                },
            )

    def test_tracked_text_identity_rejects_bom_lone_cr_and_content_drift(self):
        runtime = ROOT / "runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as temporary:
            temp_root = Path(temporary)
            lf = temp_root / "lf.json"
            crlf = temp_root / "crlf.json"
            bom = temp_root / "bom.json"
            lone_cr = temp_root / "lone-cr.json"
            drift = temp_root / "drift.json"
            lf.write_bytes(b'{"status":"READY"}\n')
            crlf.write_bytes(b'{"status":"READY"}\r\n')
            bom.write_bytes(b'\xef\xbb\xbf{"status":"READY"}\n')
            lone_cr.write_bytes(b'{"status":"READY"}\r')
            drift.write_bytes(b'{"status":"CHANGED"}\n')

            expected = lf_canonical_text_sha256(lf)
            self.assertEqual(lf_canonical_text_sha256(crlf), expected)
            self.assertNotEqual(lf_canonical_text_sha256(drift), expected)
            with self.assertRaisesRegex(ValueError, "UTF-8 BOM"):
                lf_canonical_text_sha256(bom)
            with self.assertRaisesRegex(ValueError, "lone carriage return"):
                lf_canonical_text_sha256(lone_cr)

    def test_real_core_revalidates_finalized_artifacts_with_crlf_equivalence(self):
        relative = "machine/competition/rag-competition-pack-v1.json"
        source = ROOT / relative
        runtime = ROOT / "runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as temporary:
            repository_root = Path(temporary)
            target = repository_root / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
            finalized = {
                "resolved_tracked_artifact_sha256": {
                    relative: lf_canonical_text_sha256(source)
                }
            }
            tracked_manifest = {"tracked_pack_artifacts": [relative]}

            _validate_finalized_artifact_hashes(
                finalized,
                tracked_manifest,
                repository_root=repository_root,
            )
            target.write_bytes(target.read_bytes().replace(b'"v1"', b'"changed"', 1))
            with self.assertRaisesRegex(
                ValueError,
                "finalized competition artifact drifted",
            ):
                _validate_finalized_artifact_hashes(
                    finalized,
                    tracked_manifest,
                    repository_root=repository_root,
                )

    def test_competition_accepts_current_audit_only_citation_proof(self):
        _require_answer_api_gate(
            status_code=200,
            payload={
                "status": "COMPLETED",
                "evidence": [{"evidence_id": "evidence_001"}],
                "warnings": [
                    "REAL_GENERATION_OLLAMA_QWEN3_14B_"
                    "ACADEMIC_EVIDENCE_ANSWER_V1_"
                    "CITATION_IDS_VALIDATED_"
                    "CLAIM_EVIDENCE_AUDIT_PASS_NOT_ENFORCED"
                ],
            },
            generation_enabled=True,
        )

    def test_redaction_removes_connections_secrets_hosts_and_paths(self):
        value = (
            "postgresql://alice:pw@127.0.0.1:5432/db "
            "token=abc C:\\private\\trace.json /Users/alice/private.txt"
        )
        redacted = redact_text(value, maximum_length=1000)
        self.assertNotIn("alice:pw", redacted)
        self.assertNotIn("127.0.0.1", redacted)
        self.assertNotIn("abc", redacted)
        self.assertNotIn("C:\\private", redacted)
        self.assertNotIn("/Users/alice", redacted)

    def test_generation_observer_retains_structured_result_only_in_memory(self):
        identity = GenerationModelIdentity(
            provider="test",
            model="test-model",
            digest="a" * 64,
        )
        expected = GenerationResult(
            answer="Supported [1]",
            identity=identity,
            claims=(GeneratedClaim(text="Supported", citation_ids=(1,)),),
        )

        class Delegate:
            def configured_identity(self):
                return identity

            def generate(self, question, evidence):
                del question, evidence
                return expected

        observer = _ObservedGenerationProvider(Delegate())
        self.assertEqual(observer.generate("question", [{"quote": "Supported"}]), expected)
        self.assertEqual(observer.last_result, expected)
        self.assertIsNone(observer.failure_code)


class CompetitionInputTests(unittest.TestCase):
    def test_private_historical_input_is_selected_by_hash_without_copying_pdf(self):
        runtime = ROOT / "runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as temporary:
            temp_root = Path(temporary)
            source = temp_root / "source"
            output = temp_root / "output"
            (source / "suites").mkdir(parents=True)
            (source / "papers").mkdir()
            pdf = source / "papers/paper.pdf"
            pdf.write_bytes(b"representative public paper bytes")
            cases = []
            for scenario_id, (case_id, _) in prepare_competition_input.CASE_BINDINGS.items():
                cases.append(
                    {
                        "case_id": case_id,
                        "question": f"question for {scenario_id}",
                        "required_page_ranges": [{"page_start": 1, "page_end": 1}],
                    }
                )
            suite = source / "suites/suite.json"
            suite.write_text(
                json.dumps(
                    {
                        "schema_version": "phase2_academic_qa_suite_v1",
                        "suite_id": "test-suite",
                        "pdf_sha256": sha256(pdf),
                        "cases": cases,
                    }
                ),
                encoding="utf-8",
            )
            manifest = source / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "package_id": "phase2-academic-qa-acceptance-v2",
                        "documents": [
                            {
                                "pdf_sha256": sha256(pdf),
                                "pdf_path": "papers/paper.pdf",
                                "suite_path": "suites/suite.json",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            question_hashes = {
                scenario_id: hashlib.sha256(
                    f"question for {scenario_id}".encode("utf-8")
                ).hexdigest()
                for scenario_id in prepare_competition_input.CASE_BINDINGS
            }
            bindings = {
                scenario_id: (case_id, question_hashes[scenario_id])
                for scenario_id, (case_id, _) in prepare_competition_input.CASE_BINDINGS.items()
            }
            with (
                patch.object(
                    prepare_competition_input,
                    "EXPECTED_SOURCE_MANIFEST_SHA256",
                    sha256(manifest),
                ),
                patch.object(
                    prepare_competition_input,
                    "EXPECTED_SOURCE_SUITE_SHA256",
                    sha256(suite),
                ),
                patch.object(
                    prepare_competition_input,
                    "EXPECTED_PDF_SHA256",
                    sha256(pdf),
                ),
                patch.object(prepare_competition_input, "CASE_BINDINGS", bindings),
            ):
                result = prepare_competition_input.prepare(
                    source.relative_to(ROOT),
                    output.relative_to(ROOT),
                )
            self.assertTrue(result["contains_private_question_text"])
            self.assertFalse(result["tracked_or_public"])
            self.assertEqual(result["pdf_path"], pdf.relative_to(ROOT).as_posix())
            self.assertFalse((output / "paper.pdf").exists())


class RedactedResultTests(unittest.TestCase):
    def evidence(self, position: int, text: str) -> dict[str, object]:
        return {
            "evidence_id": f"evidence_{position}",
            "chunk_id": f"chunk_{position}",
            "document_id": "document_alpha",
            "version_id": "version_alpha",
            "section_path": "Results",
            "page_start": position,
            "page_end": position,
            "quote": text,
        }

    def payload(self, answer: str) -> dict[str, object]:
        evidence = [
            self.evidence(1, "The study enrolled 240 participants."),
            self.evidence(2, "The observation window was 12 weeks."),
        ]
        return {
            "status": "COMPLETED",
            "answer": answer,
            "evidence": evidence,
            "citations": [
                {
                    "citation_id": f"citation_{index}",
                    "evidence_id": value["evidence_id"],
                    "document_id": value["document_id"],
                    "page_start": value["page_start"],
                    "page_end": value["page_end"],
                }
                for index, value in enumerate(evidence, start=1)
            ],
        }

    def test_real_capture_builds_three_scenarios_and_audit_only_multi_evidence(self):
        identity = GenerationModelIdentity(
            provider="ollama",
            model="qwen3:14b",
            digest="b" * 64,
        )
        qa_payload = self.payload("The study enrolled 240 participants. [1]")
        audit_payload = self.payload(
            "The study enrolled 240 participants; the observation window was 12 weeks. [1][2]"
        )
        captures = [
            CompetitionCapture(
                case_id="qa-case",
                question="qa question",
                initial_payload=qa_payload,
                replay_payload=qa_payload,
                generation_result=GenerationResult(
                    answer=str(qa_payload["answer"]),
                    identity=identity,
                    claims=(
                        GeneratedClaim(
                            text="The study enrolled 240 participants.",
                            citation_ids=(1,),
                        ),
                    ),
                ),
            ),
            CompetitionCapture(
                case_id="audit-case",
                question="audit question",
                initial_payload=audit_payload,
                replay_payload=audit_payload,
                generation_result=GenerationResult(
                    answer=str(audit_payload["answer"]),
                    identity=identity,
                    claims=(
                        GeneratedClaim(
                            text=(
                                "The study enrolled 240 participants; "
                                "the observation window was 12 weeks."
                            ),
                            citation_ids=(1, 2),
                        ),
                    ),
                ),
            ),
        ]
        result = build_redacted_result(
            finalized_manifest={"source_commit": {"value": "c" * 40}},
            input_manifest={
                "pdf_sha256": "d" * 64,
                "question_suite_sha256": "e" * 64,
                "scenario_bindings": {
                    "COMP-QA-001": "qa-case",
                    "COMP-EVIDENCESET-001": "audit-case",
                },
            },
            run_id="competition_test_01",
            captures=captures,
            stage1_report={
                "owner_id": "owner_alpha",
                "answer_generation_boundary": "REAL_GENERATION_QWEN",
                "generation_identity": {"model": "qwen3:14b"},
                "cleanup_jobs_succeeded": 3,
                "runtime_snapshot_cleanup_proven": True,
                "inactive_visibility_proven": True,
                "inactive_answer_api_status": 403,
            },
        )
        schema = json.loads(
            (ROOT / "contracts/schemas/competition-redacted-result-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator(schema).validate(result)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["scenarios"]), 3)
        audit = result["scenarios"][1]["evidence_set_audit"]
        self.assertEqual(audit["mode"], "AUDIT_ONLY")
        self.assertEqual(audit["multi_evidence_claim_count"], 1)
        self.assertFalse(audit["human_semantic_gold"])


if __name__ == "__main__":
    unittest.main()
