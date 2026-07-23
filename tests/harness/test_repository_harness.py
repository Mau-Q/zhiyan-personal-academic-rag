import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


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
        self.assertIn(
            "run: .venv/bin/python -m pip install '.[dev]'",
            workflow,
        )
        self.assertNotIn("run: python -m pip install '.[dev]'", workflow)

    def test_phase_schema_and_template_are_draft_2020_12_valid(self):
        schema = json.loads(
            (ROOT / "machine" / "phase_result.schema.json").read_text(encoding="utf-8")
        )
        template = json.loads(
            (ROOT / "machine" / "phase_result.template.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(template)

    def test_feature_evidence_paths_exist(self):
        payload = json.loads(
            (ROOT / "machine" / "feature_list.json").read_text(encoding="utf-8")
        )
        feature_ids = [feature["id"] for feature in payload["features"]]
        self.assertEqual(len(feature_ids), len(set(feature_ids)))
        for feature in payload["features"]:
            self.assertTrue(feature["evidence"])
            for relative_path in feature["evidence"]:
                self.assertTrue((ROOT / relative_path).is_file(), relative_path)

    def test_current_phase_has_required_operational_sections(self):
        text = (ROOT / "docs" / "CURRENT_PHASE.md").read_text(encoding="utf-8")
        for heading in ("## 输入", "## 验收", "## Git"):
            self.assertIn(heading, text)

    def test_simplified_git_policy_is_machine_readable(self):
        state = json.loads(
            (ROOT / "machine" / "project_state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            state["git_policy"]["member_a_low_risk"],
            "LOCAL_COMMIT_AFTER_LOCAL_GATES_PUSH_ONLY_EXPLICIT",
        )
        self.assertEqual(
            state["git_policy"]["remote_operations"],
            "USER_EXECUTED_FROM_VERSIONED_RUNBOOK",
        )
        self.assertEqual(state["git_policy"]["ci_mode"], "CONDITIONAL_ACTIONS_CHECK")

    def test_highest_source_authority_is_machine_readable(self):
        state = json.loads(
            (ROOT / "machine" / "project_state.json").read_text(encoding="utf-8")
        )
        authority = state["source_authority"]
        self.assertEqual(
            authority["sha256"],
            "43fd5d4af4d38884c2449b9ff39fcee537cf27af5a7a700747a932be5f74dc78",
        )
        self.assertEqual(authority["line_count"], 725)
        self.assertEqual(
            authority["source_phase"], {"id": "phase-3", "status": "NOT_STARTED"}
        )
        self.assertEqual(
            authority["completed_source_phases"], ["phase-0", "phase-1", "phase-2"]
        )
        traceability = ROOT / authority["traceability_doc"]
        self.assertTrue(traceability.is_file())

    def test_phase_zero_scope_resource_and_slo_are_frozen(self):
        payload = json.loads(
            (ROOT / "machine" / "phase_zero_scope_resource_slo.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(payload["status"], "FROZEN_FOR_PHASE_1_VALIDATION")
        self.assertEqual(payload["scope"]["nominal_paper_count"], 500)
        self.assertEqual(payload["scope"]["validation_upper_bound_paper_count"], 1000)
        self.assertEqual(payload["traffic"]["peak_concurrent_answer_requests"], 2)
        self.assertEqual(payload["traffic"]["measurement_window_seconds"], 900)
        self.assertEqual(payload["hardware_budget"]["deployment_host_count"], 1)
        self.assertEqual(payload["hardware_budget"]["new_hardware_procurement_cny"], 0)
        self.assertEqual(payload["slo_targets"]["retrieval_p95_ms_max"], 300)
        self.assertEqual(payload["slo_targets"]["owner_scope_correctness_min"], 1.0)
        self.assertEqual(
            payload["validation"]["capacity_and_latency"],
            "PENDING_PHASE_1_TARGET_SCALE_TEST",
        )

    def test_phase_three_entry_is_frozen_without_starting_implementation(self):
        payload = json.loads(
            (ROOT / "machine" / "phase3_entry_freeze.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["status"], "FROZEN_NOT_IMPLEMENTED")
        self.assertEqual(
            payload["source_phase"], {"id": "phase-3", "status": "NOT_STARTED"}
        )
        self.assertEqual(payload["sample_identity"]["sample_count"], 4)
        self.assertEqual(
            payload["sample_identity"]["question_ids"],
            [
                "local3.assisted.0033",
                "local3.assisted.0304",
                "local3.assisted.0383",
                "local3.assisted.0387",
            ],
        )
        self.assertEqual(
            payload["single_enhancement_variable"]["id"],
            "BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1",
        )
        self.assertFalse(payload["disable_and_rollback"]["default"])
        self.assertEqual(payload["split_isolation"]["test"]["status"], "SEALED")
        self.assertFalse(payload["split_isolation"]["test"]["tuning_allowed"])
        self.assertEqual(
            payload["split_isolation"]["acceptance"]["status"],
            "SEALED_REQUIRES_EXPLICIT_AUTHORIZATION",
        )
        self.assertTrue(
            payload["independent_performance_debt"][
                "must_not_be_combined_with_first_failure_enhancement"
            ]
        )
        self.assertEqual(
            payload["independent_performance_debt"]["retrieval_p95_ms_max"], 300
        )

    def test_validator_rejects_template_as_concrete_phase_result(self):
        template = json.loads(
            (ROOT / "machine" / "phase_result.template.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            result_path = Path(temporary_directory) / "phase_result.json"
            result_path.write_text(json.dumps(template), encoding="utf-8")
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
