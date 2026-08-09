import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from scripts import validate_harness_contract as harness


ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@contextmanager
def isolated_tracked_repository():
    with tempfile.TemporaryDirectory() as temporary_directory:
        repository = Path(temporary_directory) / "repository"
        repository.mkdir()
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        for raw_relative_path in tracked:
            if not raw_relative_path:
                continue
            relative_path = Path(raw_relative_path.decode("utf-8"))
            source = ROOT / relative_path
            destination = repository / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        subprocess.run(
            ["git", "init", "-q"],
            cwd=repository,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "-f", "."],
            cwd=repository,
            check=True,
            capture_output=True,
        )
        with patch.object(harness, "ROOT", repository):
            yield repository


class RepositoryHarnessTests(unittest.TestCase):
    def test_repository_harness_validator_passes(self):
        completed = subprocess.run(
            [sys.executable, "scripts/validate_harness_contract.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("HARNESS_CONTRACT PASS", completed.stdout)

    def test_makefile_pins_all_repository_commands_to_project_virtualenv(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("PROJECT_PYTHON := .venv/bin/python", makefile)
        self.assertIn("PROJECT_PYTHON := .venv/Scripts/python.exe", makefile)
        self.assertIn("$(error Project virtualenv is missing", makefile)
        self.assertNotRegex(makefile, r"(?m)^\tpython3(?:\s|$)")

        agent_entry = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("make harness-validate", agent_entry)
        self.assertNotIn("python3 scripts/validate_harness_contract.py", agent_entry)

        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_environment = subprocess.run(
                ["make", "-f", str(ROOT / "Makefile"), "harness-validate"],
                cwd=temporary_directory,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(missing_environment.returncode, 0)
        self.assertIn(
            "Project virtualenv is missing",
            missing_environment.stdout + missing_environment.stderr,
        )

    def test_github_actions_builds_the_required_project_virtualenv(self):
        workflow = (
            ROOT / ".github" / "workflows" / "contracts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("run: python -m venv .venv", workflow)
        self.assertIn("run: .venv/bin/python -m pip install '.[dev]'", workflow)
        self.assertNotIn("run: python -m pip install '.[dev]'", workflow)

    def test_phase_schema_and_template_are_draft_2020_12_valid(self):
        schema = _read_json(ROOT / "machine" / "phase_result.schema.json")
        template = _read_json(ROOT / "machine" / "phase_result.template.json")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(template)

    def test_current_feature_and_gate_references_are_valid(self):
        harness.check_feature_list()
        payload = _read_json(ROOT / "machine" / "feature_list.json")
        self.assertEqual(payload["schema_version"], "feature_list_v2")
        for feature in payload["features"]:
            gate_records = feature.get("gate_records", [])
            self.assertEqual(len(gate_records), len(set(gate_records)))
            self.assertTrue(set(gate_records).issubset(feature["evidence"]))

    def test_validator_no_longer_contains_historical_gate_outcomes(self):
        validator = (ROOT / "scripts" / "validate_harness_contract.py").read_text(
            encoding="utf-8"
        )
        for historical_interpreter_token in (
            "SEVENTH_ATTEMPT",
            "REMOTE_DEV_QUALITY_FAILED",
            "phase3_comparison_dev_20260723",
            "FORMAL_DETERMINISTIC_MULTI_EVIDENCE_AUDIT_READY",
        ):
            self.assertNotIn(historical_interpreter_token, validator)

    def test_legal_business_gate_outcome_change_needs_no_validator_edit(self):
        with isolated_tracked_repository() as repository:
            gate_path = (
                repository / "machine" / "phase4_claim_evidence_core_gate.json"
            )
            gate = _read_json(gate_path)
            gate["status"] = "LOCAL_CORE_READY_AUDIT_REVIEW_COMPLETE"
            _write_json(gate_path, gate)

            harness.check_feature_list()

    def test_unknown_feature_status_vocabulary_fails_closed(self):
        with isolated_tracked_repository() as repository:
            feature_path = repository / "machine" / "feature_list.json"
            payload = _read_json(feature_path)
            payload["features"][0]["status"] = "PROMOTED"
            _write_json(feature_path, payload)

            with self.assertRaisesRegex(ValueError, "invalid feature status"):
                harness.check_feature_list()

    def test_unknown_business_gate_lifecycle_vocabulary_fails_closed(self):
        with isolated_tracked_repository() as repository:
            gate_path = (
                repository / "machine" / "phase4_claim_evidence_core_gate.json"
            )
            gate = _read_json(gate_path)
            gate["status"] = "BANANA"
            _write_json(gate_path, gate)

            with self.assertRaisesRegex(ValueError, "legal lifecycle token"):
                harness.check_feature_list()

    def test_missing_gate_reference_fails_closed(self):
        with isolated_tracked_repository() as repository:
            feature_path = repository / "machine" / "feature_list.json"
            payload = _read_json(feature_path)
            feature = next(
                item
                for item in payload["features"]
                if item["id"] == "phase4_claim_evidence_core"
            )
            missing = "machine/phase4_missing_gate.json"
            current = feature["gate_records"][0]
            feature["gate_records"][0] = missing
            feature["evidence"][feature["evidence"].index(current)] = missing
            _write_json(feature_path, payload)

            with self.assertRaisesRegex(ValueError, "path is invalid"):
                harness.check_feature_list()

    def test_untracked_authoritative_reference_fails_closed(self):
        with isolated_tracked_repository() as repository:
            feature_path = repository / "machine" / "feature_list.json"
            payload = _read_json(feature_path)
            feature = next(
                item
                for item in payload["features"]
                if item["id"] == "phase4_claim_evidence_core"
            )
            untracked = "machine/phase4_untracked_gate.json"
            _write_json(
                repository / untracked,
                {
                    "schema_version": "phase4_untracked_gate_v1",
                    "status": "PENDING",
                },
            )
            feature["gate_records"].append(untracked)
            feature["evidence"].append(untracked)
            _write_json(feature_path, payload)

            with self.assertRaisesRegex(ValueError, "not Git tracked"):
                harness.check_feature_list()

    def test_malformed_gate_record_fails_closed(self):
        with isolated_tracked_repository() as repository:
            gate_path = (
                repository / "machine" / "phase4_claim_evidence_core_gate.json"
            )
            gate = _read_json(gate_path)
            del gate["status"]
            _write_json(gate_path, gate)

            with self.assertRaisesRegex(ValueError, "gate_records"):
                harness.check_feature_list()

    def test_gate_schema_version_must_match_record_path(self):
        with isolated_tracked_repository() as repository:
            gate_path = (
                repository / "machine" / "phase4_claim_evidence_core_gate.json"
            )
            gate = _read_json(gate_path)
            gate["schema_version"] = "unrelated_gate_v1"
            _write_json(gate_path, gate)

            with self.assertRaisesRegex(ValueError, "schema_version is invalid"):
                harness.check_feature_list()

    def test_current_phase_missing_authority_fails_closed(self):
        with isolated_tracked_repository() as repository:
            state_path = repository / "machine" / "project_state.json"
            state = _read_json(state_path)
            state["current_phase"]["authority_doc"] = "docs/DOES_NOT_EXIST.md"
            _write_json(state_path, state)

            with self.assertRaisesRegex(ValueError, "path is invalid"):
                harness.check_project_state()

    def test_current_phase_has_required_operational_sections(self):
        text = (ROOT / "docs" / "CURRENT_PHASE.md").read_text(encoding="utf-8")
        for heading in ("## 输入", "## 验收", "## Git"):
            self.assertIn(heading, text)

    def test_source_authority_identity_resolves_from_machine_state(self):
        state = _read_json(ROOT / "machine" / "project_state.json")
        authority = state["source_authority"]
        traceability = (ROOT / authority["traceability_doc"]).read_text(
            encoding="utf-8"
        )
        self.assertIn(authority["title"], traceability)
        self.assertIn(authority["sha256"], traceability)
        self.assertIn(f"`{authority['line_count']}`", traceability)

    def test_validator_rejects_template_as_concrete_phase_result(self):
        template = _read_json(ROOT / "machine" / "phase_result.template.json")
        with tempfile.TemporaryDirectory() as temporary_directory:
            result_path = Path(temporary_directory) / "phase_result.json"
            _write_json(result_path, template)
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate_harness_contract.py",
                    "--phase-result",
                    str(result_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("concrete phase result cannot be template_only", completed.stdout)


if __name__ == "__main__":
    unittest.main()
