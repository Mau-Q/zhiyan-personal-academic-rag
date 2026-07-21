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
            "DIRECT_MAIN_AFTER_LOCAL_GATES",
        )
        self.assertEqual(state["git_policy"]["member_b_remote"], "PULL_REQUEST")
        self.assertEqual(state["git_policy"]["ci_mode"], "CONDITIONAL_ACTIONS_CHECK")

    def test_highest_source_authority_is_machine_readable(self):
        state = json.loads(
            (ROOT / "machine" / "project_state.json").read_text(encoding="utf-8")
        )
        authority = state["source_authority"]
        self.assertEqual(
            authority["sha256"],
            "ae2ea50d200c74e4c85595afaa5316e6cabd9d782dcc9e4a9ed673891bd9430e",
        )
        self.assertEqual(authority["line_count"], 2074)
        self.assertEqual(authority["source_phase"]["status"], "IN_PROGRESS")
        traceability = ROOT / authority["traceability_doc"]
        self.assertTrue(traceability.is_file())

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
