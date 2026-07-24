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

    def test_phase_four_claim_evidence_core_is_local_and_partial(self):
        payload = json.loads(
            (
                ROOT / "machine" / "phase4_claim_evidence_core_gate.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            payload["status"],
            "LOCAL_CORE_READY_ONLINE_HARD_JUDGMENT_DEFERRED",
        )
        self.assertEqual(payload["reuse"]["new_dependencies"], [])
        self.assertFalse(payload["phase_boundary"]["phase4_complete"])
        self.assertFalse(
            payload["phase_boundary"]["online_hard_judgment_enabled"]
        )
        self.assertEqual(
            payload["scope"]["knowledge_base_integration"],
            "OUT_OF_SCOPE_OTHER_OWNER",
        )
        self.assertEqual(payload["scope"]["test"], "NOT_READ_NOT_RUN")
        self.assertEqual(payload["scope"]["acceptance"], "NOT_READ_NOT_RUN")
        self.assertFalse(
            payload["implementation"]["public_rag_answer_schema_changed"]
        )
        self.assertFalse(payload["implementation"]["prompt_identity_changed"])

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
            authority["source_phase"], {"id": "phase-4", "status": "IN_PROGRESS"}
        )
        self.assertEqual(
            authority["completed_source_phases"],
            ["phase-0", "phase-1", "phase-2"],
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

    def test_phase_three_comparison_dev_failure_keeps_variable_disabled(self):
        feature_payload = json.loads(
            (ROOT / "machine" / "feature_list.json").read_text(encoding="utf-8")
        )
        phase3_feature = next(
            feature
            for feature in feature_payload["features"]
            if feature["id"] == "phase3_bilateral_comparison_query_decomposition"
        )
        self.assertEqual(phase3_feature["status"], "PARTIAL")
        self.assertEqual(
            phase3_feature["gate_status"],
            "SEVENTH_ATTEMPT_TRUSTWORTHY_DEV_QUALITY_FAIL_CLEAN_VARIABLE_DISABLED_TEST_SEALED",
        )
        payload = json.loads(
            (ROOT / "machine" / "phase3_comparison_dev_gate.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            payload["status"],
            "SEVENTH_ATTEMPT_DEV_QUALITY_FAILED_CLEAN_VARIABLE_REJECTED",
        )
        self.assertEqual(
            payload["source_phase"], {"id": "phase-3", "status": "IN_PROGRESS"}
        )
        self.assertEqual(
            payload["implementation"]["variable_id"],
            "BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1",
        )
        self.assertFalse(payload["implementation"]["default_enabled"])
        self.assertEqual(payload["preserved_online_path"]["candidate_k"], 20)
        self.assertEqual(payload["preserved_online_path"]["rrf_k"], 60)
        self.assertFalse(payload["preserved_online_path"]["reranker_enabled"])
        self.assertEqual(
            payload["paired_online_dev_quality"]["status"],
            "FAIL",
        )
        self.assertEqual(
            payload["paired_online_dev_quality"]["decision"],
            "KEEP_COMPARISON_DECOMPOSITION_DISABLED",
        )
        self.assertEqual(
            payload["paired_online_user_entry"]["status"],
            "SEVENTH_ATTEMPT_COMPLETE_NO_RERUN_AUTHORIZED",
        )
        self.assertEqual(
            payload["windows_attempts"][0]["status"],
            "REJECTED_BEFORE_SERVICES",
        )
        self.assertFalse(payload["windows_attempts"][0]["online_quality_executed"])
        self.assertFalse(
            payload["windows_attempts"][0]["infrastructure_mutation_started"]
        )
        self.assertEqual(
            payload["windows_attempts"][1]["status"],
            "REJECTED_CLEANUP_PROOF_FAILED",
        )
        self.assertEqual(
            payload["windows_attempts"][1]["adjudication_error_code"],
            "REPORT_CLEANUP_PROOF_INVALID",
        )
        self.assertEqual(
            payload["windows_attempts"][2]["cleanup_stage"],
            "VERIFY_QUEUE_SCOPE",
        )
        self.assertEqual(
            payload["cleanup_audit_gate"]["mode"],
            "POSTGRESQL_READ_ONLY_OWNER_SCOPED_PLUS_GLOBAL_NONTERMINAL_COUNT",
        )
        self.assertFalse(
            payload["cleanup_audit_gate"]["quality_rerun_allowed_before_clean"]
        )
        self.assertEqual(
            payload["cleanup_recovery_gate"]["single_action"],
            "RUN_EXISTING_PERSISTENT_CLEANUP_WORKER_MAX_NINE",
        )
        self.assertEqual(
            payload["cleanup_recovery_gate"]["status"],
            "PASS",
        )
        self.assertFalse(payload["cleanup_recovery_gate"]["quality_gate_run"])
        self.assertEqual(payload["cleanup_recovery_result"]["jobs_succeeded"], 9)
        self.assertEqual(
            payload["cleanup_recovery_result"]["post_recovery_audit_decision"],
            "CLEAN",
        )
        self.assertEqual(
            payload["cleanup_recovery_result_03"]["recovery_sha256"],
            "94a10a54ffb6b326740e093db97d148891fd44898e7bc077e25fa4385b780cdb",
        )
        self.assertEqual(
            payload["cleanup_recovery_result_03"][
                "post_recovery_audit_sha256"
            ],
            "ffd2e805b857df1d4d7e256a00bf09b15992261a4a31960c7a2d55b8d504dbab",
        )
        self.assertTrue(
            payload["known_runner_defect"]["quality_rerun_authorized"]
        )
        self.assertFalse(
            payload["known_runner_defect"]["quality_variable_changed"]
        )
        self.assertEqual(
            payload["windows_attempts"][3]["primary_stage"],
            "RUN_CONTROL",
        )
        self.assertEqual(
            payload["windows_attempts"][3]["report_sha256"],
            "2ca305dcd16820de4eb28863097f58c53ad5f9d678604c5251a65de70b2aa47c",
        )
        self.assertEqual(
            payload["windows_attempts"][3]["cleanup_status"],
            "PASS",
        )
        self.assertEqual(
            payload["windows_attempts"][4]["primary_error_code"],
            "ONLINE_MILVUS_ROUTE_FAILED",
        )
        self.assertEqual(
            payload["windows_attempts"][4]["report_sha256"],
            "19a92545d6e87408462bdc38a72e3f4f69b5aa03edcaaed19400116aafba4cd4",
        )
        self.assertEqual(
            payload["windows_attempts"][4]["cleanup_status"],
            "PASS",
        )
        self.assertEqual(
            payload["windows_attempts"][5]["primary_error_code"],
            "ONLINE_MILVUS_ROUTE_IDENTITY_FAILED",
        )
        self.assertEqual(
            payload["windows_attempts"][5]["report_sha256"],
            "fcbd2b472e21ad5554fb3ebb0389cde649fdfe80c4036c8bcc64a194fc4f70cb",
        )
        self.assertEqual(
            payload["windows_attempts"][5]["cleanup_status"],
            "PASS",
        )
        self.assertEqual(
            payload["windows_attempts"][6]["status"],
            "FAIL_COMPLETE_QUALITY_THRESHOLD_NOT_MET_CLEANUP_PASS",
        )
        self.assertEqual(
            payload["windows_attempts"][6]["report_sha256"],
            "3810ce9228f7ce9c65b5ebe031f1f5ca6a471fa665bf5d8c12a6e7cac6e01390",
        )
        self.assertEqual(
            payload["windows_attempts"][6]["adjudication_sha256"],
            "99530d236b8ca50b53de18557c9d43c7bcc63695a3c98fc9dba889b33cdaa036",
        )
        self.assertEqual(
            payload["windows_attempts"][6]["control_strict_two_sided_passed"],
            0,
        )
        self.assertEqual(
            payload["windows_attempts"][6]["treatment_strict_two_sided_passed"],
            0,
        )
        self.assertEqual(
            payload["windows_attempts"][6]["macro_ndcg_at_3_absolute_gain"],
            -0.017739,
        )
        self.assertEqual(payload["windows_attempts"][6]["cleanup_status"], "PASS")
        self.assertFalse(payload["windows_attempts"][6]["recovery_required"])
        self.assertTrue(payload["windows_attempts"][6]["online_quality_executed"])
        self.assertEqual(
            payload["control_failure_diagnostic_hardening"][
                "additional_requests"
            ],
            0,
        )
        self.assertFalse(
            payload["control_failure_diagnostic_hardening"][
                "quality_variable_changed"
            ]
        )
        self.assertEqual(
            payload["milvus_failure_diagnostic_hardening"]["stable_stages"],
            [
                "ROUTE_IDENTITY",
                "QUERY_EMBEDDING",
                "ANN_SEARCH",
                "RESPONSE_CONTRACT",
            ],
        )
        self.assertEqual(
            payload["milvus_route_identity_fix"]["decision_id"],
            "PD-051",
        )
        self.assertFalse(
            payload["milvus_route_identity_fix"]["quality_variable_changed"]
        )
        self.assertFalse(
            payload["paired_online_user_entry"][
                "absolute_300ms_slo_adjudication"
            ]
        )
        self.assertTrue(payload["split_isolation"]["test"].startswith("SEALED"))
        self.assertTrue(
            payload["split_isolation"]["acceptance"].startswith("SEALED")
        )

    def test_phase_three_report_intake_cannot_unlock_test(self):
        payload = json.loads(
            (ROOT / "machine" / "phase3_comparison_report_intake.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            payload["status"],
            "SEVENTH_ATTEMPT_TRUSTWORTHY_DEV_QUALITY_FAIL_CLEAN",
        )
        self.assertEqual(payload["decision_id"], "PD-042")
        self.assertEqual(
            payload["required_report_identity"]["head_commit"],
            "CALLER_PINNED_AND_MATCHED_TO_RUNNER_CHECKOUT",
        )
        self.assertEqual(
            payload["trust_preconditions"]["test"],
            "NOT_READ_NOT_RUN",
        )
        self.assertEqual(
            payload["trust_preconditions"]["acceptance"],
            "NOT_READ_NOT_RUN",
        )
        self.assertFalse(
            payload["trust_preconditions"]["absolute_300ms_slo_conclusion_allowed"]
        )
        for outcome in payload["outcomes"].values():
            self.assertFalse(outcome["default_enabled"])
            self.assertTrue(outcome["test_gate"].startswith("SEALED"))
        self.assertEqual(
            payload["split_and_gate_isolation"]["test"],
            "NO_AUTOMATIC_UNLOCK_OR_EXECUTION",
        )
        self.assertEqual(
            payload["evidence"]["attempts"][0]["status"],
            "REJECTED_BEFORE_SERVICES",
        )
        self.assertEqual(
            payload["evidence"]["attempts"][1]["error_code"],
            "REPORT_CLEANUP_PROOF_INVALID",
        )
        self.assertEqual(
            payload["cleanup_audit_boundary"]["postgresql_transaction"],
            "READ_ONLY",
        )
        self.assertTrue(
            payload["cleanup_audit_boundary"]["quality_rerun_authorized"]
        )
        self.assertEqual(
            payload["cleanup_audit_boundary"]["next_gate"],
            "NEW_RUN_ID_PAIRED_ONLINE_DEV_QUALITY_GATE",
        )
        self.assertEqual(
            payload["cleanup_recovery_evidence"]["post_recovery_audit"],
            "PASS_CLEAN",
        )
        self.assertEqual(
            payload["completed_cleanup_recovery_03"]["run_id"],
            "phase3_comparison_dev_20260723_03",
        )
        self.assertEqual(
            payload["completed_cleanup_recovery_03"]["post_recovery_audit"],
            "PASS_CLEAN",
        )
        self.assertFalse(payload["runner_repair"]["quality_variable_changed"])
        self.assertEqual(
            payload["evidence"]["attempts"][3]["primary_stage"],
            "RUN_CONTROL",
        )
        self.assertEqual(
            payload["fourth_attempt_cleanup_proof"]["status"],
            "PASS_CLEAN",
        )
        self.assertFalse(
            payload["fourth_attempt_cleanup_proof"]["recovery_required"]
        )
        self.assertEqual(
            payload["control_failure_diagnostic_hardening"]["additional_requests"],
            0,
        )
        self.assertEqual(
            payload["evidence"]["attempts"][4]["error_code"],
            "ONLINE_MILVUS_ROUTE_FAILED",
        )
        self.assertEqual(
            payload["fifth_attempt_cleanup_proof"]["status"],
            "PASS_CLEAN",
        )
        self.assertEqual(
            payload["milvus_failure_diagnostic_hardening"][
                "additional_requests"
            ],
            0,
        )
        self.assertEqual(
            payload["evidence"]["attempts"][5]["error_code"],
            "ONLINE_MILVUS_ROUTE_IDENTITY_FAILED",
        )
        self.assertEqual(
            payload["sixth_attempt_cleanup_proof"]["status"],
            "PASS_CLEAN",
        )
        self.assertEqual(
            payload["milvus_route_identity_fix"]["decision_id"],
            "PD-051",
        )
        self.assertEqual(
            payload["evidence"]["attempts"][6]["error_code"],
            "QUALITY_OR_COST_THRESHOLD_NOT_MET",
        )
        self.assertEqual(
            payload["evidence"]["attempts"][6]["cleanup_status"],
            "PASS",
        )
        self.assertEqual(
            payload["seventh_attempt_quality_result"]["decision_id"],
            "PD-052",
        )
        self.assertEqual(
            payload["seventh_attempt_quality_result"]["decision"],
            "KEEP_COMPARISON_DECOMPOSITION_DISABLED",
        )
        self.assertFalse(
            payload["seventh_attempt_quality_result"]["recovery_required"]
        )
        self.assertFalse(
            payload["seventh_attempt_quality_result"]["rerun_authorized"]
        )
        self.assertFalse(
            payload["seventh_attempt_quality_result"]["default_enabled"]
        )

    def test_phase_three_route_coverage_is_local_default_off_and_reuse_first(self):
        payload = json.loads(
            (
                ROOT
                / "machine"
                / "phase3_comparison_route_coverage_gate.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            payload["status"],
            "REMOTE_DEV_QUALITY_FAILED_CLEAN_VARIABLE_DISABLED",
        )
        self.assertEqual(
            payload["decision_ids"],
            [
                "PD-053",
                "PD-054",
                "PD-055",
                "PD-056",
                "PD-057",
                "PD-058",
                "PD-059",
            ],
        )
        self.assertEqual(
            payload["reuse_review"]["decision"],
            "REUSE_EXISTING_NARROW_RETRIEVAL_CONTRACTS_WITHOUT_NEW_DEPENDENCY",
        )
        self.assertEqual(
            payload["single_enhancement_variable"]["id"],
            "BILATERAL_COMPARISON_ROUTE_COVERAGE_TOP3_V1",
        )
        self.assertFalse(
            payload["single_enhancement_variable"]["default_enabled"]
        )
        self.assertEqual(payload["preserved_online_path"]["candidate_k"], 20)
        self.assertEqual(payload["preserved_online_path"]["rrf_k"], 60)
        self.assertEqual(payload["preserved_online_path"]["final_top_k"], 3)
        self.assertFalse(payload["preserved_online_path"]["reranker_enabled"])
        self.assertFalse(payload["preserved_online_path"]["candidate_expansion"])
        self.assertEqual(
            payload["future_paired_dev_gate"]["status"],
            "COMPLETE_FAIL_CLEAN",
        )
        self.assertEqual(
            payload["future_paired_dev_gate"]["run_id"],
            "phase3_comparison_route_coverage_dev_20260724_01",
        )
        self.assertEqual(payload["split_isolation"]["test"], "NOT_READ_NOT_RUN")
        self.assertTrue(
            payload["remote_boundary"]["windows_run_id_assigned"]
        )
        self.assertFalse(
            payload["remote_boundary"]["windows_command_authorized"]
        )
        self.assertFalse(payload["remote_boundary"]["remote_host_operated"])
        result = payload["remote_paired_dev_result"]
        self.assertEqual(result["status"], "FAIL_CLEAN")
        self.assertEqual(
            result["decision"],
            "KEEP_COMPARISON_ROUTE_COVERAGE_DISABLED",
        )
        self.assertEqual(result["variable_observation"]["applied"], 4)
        self.assertEqual(
            result["variable_observation"]["selection_changed"],
            3,
        )
        self.assertEqual(result["cleanup"]["jobs_succeeded"], 9)
        self.assertFalse(result["recovery_required"])
        self.assertFalse(result["rerun_authorized"])
        self.assertFalse(
            payload["powershell_summary_defect"]["quality_rerun_required"]
        )
        self.assertFalse(
            payload["windows_closeout_verification"]["quality_gate_rerun"]
        )
        self.assertFalse(
            payload["windows_closeout_verification"][
                "windows_external_module_required"
            ]
        )
        self.assertEqual(
            payload["windows_closeout_verification"]["third_attempt_status"],
            "PASS",
        )
        self.assertEqual(
            payload["windows_closeout_verification"]["status"],
            "PASS_COMPLETE",
        )
        self.assertFalse(
            payload["windows_closeout_verification"]["recheck_required"]
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
