#!/usr/bin/env python3
"""Read-only, standard-library validation for the repository Harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "AGENTS.md",
    "docs/HARNESS_ARCHITECTURE.md",
    "docs/REQUIREMENTS_TRACEABILITY.md",
    "docs/PROJECT_GUARDRAILS.md",
    "docs/PRODUCT_DECISIONS.md",
    "docs/EXECUTION_CONTRACT.md",
    "docs/CURRENT_PHASE.md",
    "docs/PHASE_0_SCOPE_RESOURCE_SLO.md",
    "docs/PHASE_3_ENTRY_FREEZE.md",
    "docs/PHASE_3_COMPARISON_DEV_GATE.md",
    "docs/PHASE_3_COMPARISON_ROUTE_COVERAGE_GATE.md",
    "machine/project_state.json",
    "machine/feature_list.json",
    "machine/phase_zero_scope_resource_slo.json",
    "machine/phase3_entry_freeze.json",
    "machine/phase3_comparison_dev_gate.json",
    "machine/phase3_comparison_report_intake.json",
    "machine/phase3_comparison_route_coverage_gate.json",
    "machine/phase_result.schema.json",
    "machine/phase_result.template.json",
    "scripts/validate_harness_contract.py",
    "tests/harness/test_repository_harness.py",
)
CURRENT_PHASE_HEADINGS = (
    "# Current Phase",
    "## Status",
    "## 输入",
    "## 验收",
    "## Git",
    "## Current boundary",
    "## Next gate",
    "## Prohibited shortcuts",
)
FEATURE_STATUSES = {
    "READY",
    "COMPLETE",
    "COMPLETE_WITH_FAKE_LLM",
    "FIXTURE_BASELINE_READY",
    "LOCAL_3_PAPER_BASELINE_READY",
    "PARTIAL",
    "PENDING",
    "NOT_STARTED",
}
PHASE_REQUIRED_FIELDS = {
    "schema_version",
    "phase_id",
    "template_only",
    "result",
    "execution_boundary",
    "base_commit",
    "result_commit",
    "workspace_clean",
    "checks",
    "artifacts",
    "notes",
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FORBIDDEN_TEXT = re.compile(
    r"/Users/|file://|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}"
)
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")


def _read_json(relative_path: str) -> Any:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def check_required_files() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        raise ValueError(f"missing required Harness files: {', '.join(missing)}")


def check_project_state() -> None:
    state = _read_json("machine/project_state.json")
    if state.get("schema_version") != "project_state_v1":
        raise ValueError("project_state schema_version must be project_state_v1")
    if state.get("project_id") != "zhiyan-personal-academic-rag":
        raise ValueError("project_state project_id is invalid")
    current_phase = state.get("current_phase")
    source_authority = state.get("source_authority")
    harness = state.get("repository_harness")
    git_policy = state.get("git_policy")
    if not isinstance(current_phase, dict) or current_phase.get("status") != "READY":
        raise ValueError("project_state current_phase must be READY")
    if source_authority != {
        "title": "个人学术空间RAG问答系统建设与测试方案_副本.md",
        "sha256": "43fd5d4af4d38884c2449b9ff39fcee537cf27af5a7a700747a932be5f74dc78",
        "line_count": 725,
        "traceability_doc": "docs/REQUIREMENTS_TRACEABILITY.md",
        "source_phase": {"id": "phase-3", "status": "IN_PROGRESS"},
        "completed_source_phases": ["phase-0", "phase-1", "phase-2"],
    }:
        raise ValueError("project_state source_authority is invalid")
    if not isinstance(harness, dict) or harness.get("status") != "READY":
        raise ValueError("project_state repository_harness must be READY")
    if not isinstance(git_policy, dict) or git_policy != {
        "member_a_low_risk": "LOCAL_COMMIT_AFTER_LOCAL_GATES_PUSH_ONLY_EXPLICIT",
        "remote_operations": "USER_EXECUTED_FROM_VERSIONED_RUNBOOK",
        "high_risk": "PULL_REQUEST_AND_CONFIRMATION",
        "ci_mode": "CONDITIONAL_ACTIONS_CHECK",
        "history_repair": "FIX_FORWARD_NO_FORCE_PUSH",
    }:
        raise ValueError("project_state git_policy is invalid")
    current_phase_text = (ROOT / "docs/CURRENT_PHASE.md").read_text(encoding="utf-8")
    if current_phase.get("id") not in current_phase_text:
        raise ValueError("project_state current phase id is missing from CURRENT_PHASE")
    for key in ("authority_doc",):
        path = current_phase.get(key)
        if not isinstance(path, str) or not (ROOT / path).is_file():
            raise ValueError(f"project_state current_phase.{key} path is invalid")
    for key in ("entrypoint", "validator", "feature_list"):
        path = harness.get(key)
        if not isinstance(path, str) or not (ROOT / path).is_file():
            raise ValueError(f"project_state repository_harness.{key} path is invalid")
    traceability_path = source_authority["traceability_doc"]
    if not (ROOT / traceability_path).is_file():
        raise ValueError("project_state source_authority.traceability_doc path is invalid")
    traceability_text = (ROOT / traceability_path).read_text(encoding="utf-8")
    for expected in (
        source_authority["title"],
        source_authority["sha256"],
        f"`{source_authority['line_count']}`",
        "方案阶段 0/1/2 COMPLETE",
        "方案阶段 3 IN_PROGRESS",
    ):
        if expected not in traceability_text:
            raise ValueError(f"source authority identity missing from traceability: {expected}")


def check_feature_list() -> None:
    payload = _read_json("machine/feature_list.json")
    if payload.get("schema_version") != "feature_list_v1":
        raise ValueError("feature_list schema_version must be feature_list_v1")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("feature_list features must be a non-empty array")
    seen: set[str] = set()
    status_by_id: dict[str, str] = {}
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError("feature_list entries must be objects")
        feature_id = feature.get("id")
        if not isinstance(feature_id, str) or not feature_id or feature_id in seen:
            raise ValueError(f"invalid or duplicate feature id: {feature_id}")
        seen.add(feature_id)
        if feature.get("status") not in FEATURE_STATUSES:
            raise ValueError(f"invalid feature status for {feature_id}")
        status_by_id[feature_id] = feature["status"]
        evidence = feature.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"feature {feature_id} must have evidence paths")
        for relative_path in evidence:
            if not isinstance(relative_path, str) or not (ROOT / relative_path).is_file():
                raise ValueError(f"feature {feature_id} evidence path is invalid: {relative_path}")
    if status_by_id.get("repository_harness") != "READY":
        raise ValueError("repository_harness feature must be READY")
    phase3_feature = next(
        (
            feature
            for feature in features
            if feature.get("id")
            == "phase3_bilateral_comparison_query_decomposition"
        ),
        None,
    )
    if (
        not isinstance(phase3_feature, dict)
        or phase3_feature.get("status") != "PARTIAL"
        or phase3_feature.get("gate_status")
        != "SEVENTH_ATTEMPT_TRUSTWORTHY_DEV_QUALITY_FAIL_CLEAN_VARIABLE_DISABLED_TEST_SEALED"
    ):
        raise ValueError("phase 3 comparison feature gate status drifted")
    route_coverage_feature = next(
        (
            feature
            for feature in features
            if feature.get("id")
            == "phase3_bilateral_comparison_route_coverage_top3"
        ),
        None,
    )
    if (
        not isinstance(route_coverage_feature, dict)
        or route_coverage_feature.get("status") != "PARTIAL"
        or route_coverage_feature.get("gate_status")
        != "LOCAL_IMPLEMENTATION_READY_DEFAULT_OFF_REMOTE_DEV_NOT_RUN_TEST_SEALED"
    ):
        raise ValueError("phase 3 route coverage feature gate status drifted")


def validate_phase_result(payload: Any, *, require_concrete: bool) -> None:
    if not isinstance(payload, dict) or set(payload) != PHASE_REQUIRED_FIELDS:
        raise ValueError("phase result fields do not match phase_result_v1")
    if payload.get("schema_version") != "phase_result_v1":
        raise ValueError("phase result schema_version must be phase_result_v1")
    if not isinstance(payload.get("phase_id"), str) or not payload["phase_id"]:
        raise ValueError("phase result phase_id must be non-empty")
    if not isinstance(payload.get("template_only"), bool):
        raise ValueError("phase result template_only must be boolean")
    if require_concrete and payload["template_only"]:
        raise ValueError("concrete phase result cannot be template_only")
    if payload.get("result") not in {"PASS", "FAIL", "BLOCKED"}:
        raise ValueError("phase result result is invalid")
    if not isinstance(payload.get("execution_boundary"), str) or not payload["execution_boundary"]:
        raise ValueError("phase result execution_boundary must be non-empty")
    for field in ("base_commit", "result_commit"):
        value = payload.get(field)
        if value is not None and (
            not isinstance(value, str) or not COMMIT_PATTERN.fullmatch(value)
        ):
            raise ValueError(f"phase result {field} must be a commit SHA or null")
    workspace_clean = payload.get("workspace_clean")
    if workspace_clean is not None and not isinstance(workspace_clean, bool):
        raise ValueError("phase result workspace_clean is invalid")
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("phase result checks must be non-empty")
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"name", "status", "evidence"}:
            raise ValueError("phase result check shape is invalid")
        if check["status"] not in {"PASS", "FAIL", "NOT_RUN"}:
            raise ValueError("phase result check status is invalid")
        if (
            not isinstance(check["name"], str)
            or not check["name"]
            or not isinstance(check["evidence"], str)
            or not check["evidence"]
        ):
            raise ValueError("phase result check name and evidence must be non-empty")
    for field in ("artifacts", "notes"):
        values = payload.get(field)
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            raise ValueError(f"phase result {field} must contain non-empty strings")
    if require_concrete and payload["result"] == "PASS":
        if any(check["status"] != "PASS" for check in checks):
            raise ValueError("PASS phase result requires every check to PASS")
        if payload["workspace_clean"] is not True:
            raise ValueError("PASS phase result requires workspace_clean=true")
        if payload["base_commit"] is None or payload["result_commit"] is None:
            raise ValueError("PASS phase result requires base_commit and result_commit")


def check_phase_contract() -> None:
    schema = _read_json("machine/phase_result.schema.json")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("phase result schema must declare Draft 2020-12")
    if set(schema.get("required", [])) != PHASE_REQUIRED_FIELDS:
        raise ValueError("phase result schema required fields drifted")
    validate_phase_result(_read_json("machine/phase_result.template.json"), require_concrete=False)


def check_current_phase() -> None:
    text = (ROOT / "docs/CURRENT_PHASE.md").read_text(encoding="utf-8")
    missing = [heading for heading in CURRENT_PHASE_HEADINGS if heading not in text.splitlines()]
    if missing:
        raise ValueError(f"CURRENT_PHASE missing headings: {', '.join(missing)}")


def check_phase_zero_scope_resource_slo() -> None:
    payload = _read_json("machine/phase_zero_scope_resource_slo.json")
    if payload.get("schema_version") != "phase_zero_scope_resource_slo_v1":
        raise ValueError("phase zero scope schema_version is invalid")
    if payload.get("decision_id") != "PD-025":
        raise ValueError("phase zero scope decision_id must be PD-025")
    if payload.get("status") != "FROZEN_FOR_PHASE_1_VALIDATION":
        raise ValueError("phase zero scope status is not frozen")

    scope = payload.get("scope")
    if not isinstance(scope, dict) or {
        "nominal_paper_count": scope.get("nominal_paper_count"),
        "validation_upper_bound_paper_count": scope.get(
            "validation_upper_bound_paper_count"
        ),
        "planning_chunks_per_paper": scope.get("planning_chunks_per_paper"),
        "nominal_planning_chunk_count": scope.get("nominal_planning_chunk_count"),
        "validation_upper_bound_planning_chunk_count": scope.get(
            "validation_upper_bound_planning_chunk_count"
        ),
    } != {
        "nominal_paper_count": 500,
        "validation_upper_bound_paper_count": 1000,
        "planning_chunks_per_paper": 100,
        "nominal_planning_chunk_count": 50000,
        "validation_upper_bound_planning_chunk_count": 100000,
    }:
        raise ValueError("phase zero corpus capacity targets drifted")
    if scope.get("user_model") != "SINGLE_AUTHENTICATED_OWNER":
        raise ValueError("phase zero user model must remain single owner")
    if scope.get("knowledge_sources") != [
        "USER_UPLOADED_PAPER",
        "PUBLIC_PAPER_COLLECTED_INTO_PERSONAL_LIBRARY",
    ]:
        raise ValueError("phase zero knowledge sources drifted")
    if scope.get("excluded_from_mvp") != [
        "PUBLIC_LIBRARY_FEDERATED_SEARCH",
        "RESEARCH_GROUP_SHARED_LIBRARY",
        "CROSS_OWNER_RETRIEVAL",
    ]:
        raise ValueError("phase zero excluded scope drifted")

    traffic = payload.get("traffic")
    if not isinstance(traffic, dict) or {
        "sustained_answer_qps": traffic.get("sustained_answer_qps"),
        "peak_concurrent_answer_requests": traffic.get(
            "peak_concurrent_answer_requests"
        ),
        "peak_concurrent_ingestion_jobs": traffic.get("peak_concurrent_ingestion_jobs"),
        "measurement_window_seconds": traffic.get("measurement_window_seconds"),
        "warmup_request_count": traffic.get("warmup_request_count"),
    } != {
        "sustained_answer_qps": 0.2,
        "peak_concurrent_answer_requests": 2,
        "peak_concurrent_ingestion_jobs": 1,
        "measurement_window_seconds": 900,
        "warmup_request_count": 30,
    }:
        raise ValueError("phase zero traffic targets drifted")

    hardware = payload.get("hardware_budget")
    if not isinstance(hardware, dict) or {
        "deployment_host_count": hardware.get("deployment_host_count"),
        "new_hardware_procurement_cny": hardware.get("new_hardware_procurement_cny"),
        "cpu_physical_cores_max": hardware.get("cpu_physical_cores_max"),
        "ram_gib_max": hardware.get("ram_gib_max"),
        "gpu_count_max": hardware.get("gpu_count_max"),
        "gpu_vram_gib_max": hardware.get("gpu_vram_gib_max"),
        "persistent_disk_gib_max": hardware.get("persistent_disk_gib_max"),
        "external_api_monthly_cny_max": hardware.get(
            "external_api_monthly_cny_max"
        ),
    } != {
        "deployment_host_count": 1,
        "new_hardware_procurement_cny": 0,
        "cpu_physical_cores_max": 12,
        "ram_gib_max": 48,
        "gpu_count_max": 1,
        "gpu_vram_gib_max": 20,
        "persistent_disk_gib_max": 300,
        "external_api_monthly_cny_max": 0,
    }:
        raise ValueError("phase zero hardware budget drifted")

    slo = payload.get("slo_targets")
    expected_slo = {
        "retrieval_p95_ms_max": 300,
        "retrieval_p99_ms_max": 500,
        "ttft_p95_ms_max": 3000,
        "complete_answer_p95_ms_max": 10000,
        "end_to_end_p99_ms_max": 15000,
        "timeout_or_degraded_rate_max": 0.01,
        "owner_scope_correctness_min": 1.0,
        "cross_owner_leak_count_max": 0,
        "citation_target_integrity_min": 1.0,
    }
    if slo != expected_slo:
        raise ValueError("phase zero SLO targets drifted")
    validation = payload.get("validation")
    if not isinstance(validation, dict) or validation.get("capacity_and_latency") != (
        "PENDING_PHASE_1_TARGET_SCALE_TEST"
    ):
        raise ValueError("phase zero performance validation boundary is invalid")


def check_phase3_entry_freeze() -> None:
    payload = _read_json("machine/phase3_entry_freeze.json")
    if payload.get("schema_version") != "phase3_entry_freeze_v1":
        raise ValueError("phase 3 entry freeze schema_version is invalid")
    if payload.get("decision_id") != "PD-039":
        raise ValueError("phase 3 entry freeze decision_id must be PD-039")
    if payload.get("status") != "FROZEN_NOT_IMPLEMENTED":
        raise ValueError("phase 3 entry freeze must remain not implemented")
    if payload.get("source_phase") != {"id": "phase-3", "status": "NOT_STARTED"}:
        raise ValueError("phase 3 source phase must remain NOT_STARTED")

    identity = payload.get("sample_identity")
    expected_ids = [
        "local3.assisted.0033",
        "local3.assisted.0304",
        "local3.assisted.0383",
        "local3.assisted.0387",
    ]
    if not isinstance(identity, dict) or identity.get("question_ids") != expected_ids:
        raise ValueError("phase 3 target question ids drifted")
    if identity.get("sample_count") != len(expected_ids):
        raise ValueError("phase 3 target sample count drifted")
    if identity.get("sorted_newline_question_ids_sha256") != (
        "3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8"
    ):
        raise ValueError("phase 3 target identity digest drifted")

    variable = payload.get("single_enhancement_variable")
    if not isinstance(variable, dict) or variable.get("id") != (
        "BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1"
    ):
        raise ValueError("phase 3 single enhancement variable drifted")
    if variable.get("status") != "FROZEN_FOR_DEV_EXPERIMENT_NOT_IMPLEMENTED":
        raise ValueError("phase 3 enhancement must remain unimplemented")

    rollback = payload.get("disable_and_rollback")
    if not isinstance(rollback, dict) or rollback.get("default") is not False:
        raise ValueError("phase 3 enhancement switch must default to false")
    isolation = payload.get("split_isolation")
    if not isinstance(isolation, dict):
        raise ValueError("phase 3 split isolation is missing")
    if isolation.get("test", {}).get("status") != "SEALED":
        raise ValueError("phase 3 test split must remain sealed")
    if isolation.get("test", {}).get("tuning_allowed") is not False:
        raise ValueError("phase 3 test tuning must remain forbidden")
    if isolation.get("acceptance", {}).get("status") != (
        "SEALED_REQUIRES_EXPLICIT_AUTHORIZATION"
    ):
        raise ValueError("phase 3 acceptance split must require explicit authorization")
    if isolation.get("acceptance", {}).get("tuning_allowed") is not False:
        raise ValueError("phase 3 acceptance tuning must remain forbidden")

    debt = payload.get("independent_performance_debt")
    if not isinstance(debt, dict) or debt.get("retrieval_p95_ms_max") != 300:
        raise ValueError("phase 3 independent 300 ms performance debt drifted")
    if debt.get("must_not_be_combined_with_first_failure_enhancement") is not True:
        raise ValueError("phase 3 performance debt must remain an independent gate")


def check_phase3_comparison_dev_gate() -> None:
    payload = _read_json("machine/phase3_comparison_dev_gate.json")
    if payload.get("schema_version") != "phase3_comparison_dev_gate_v1":
        raise ValueError("phase 3 comparison dev gate schema_version is invalid")
    if payload.get("status") != (
        "SEVENTH_ATTEMPT_DEV_QUALITY_FAILED_CLEAN_VARIABLE_REJECTED"
    ):
        raise ValueError("phase 3 comparison dev gate status is invalid")
    if payload.get("source_phase") != {"id": "phase-3", "status": "IN_PROGRESS"}:
        raise ValueError("phase 3 comparison dev gate source phase is invalid")

    implementation = payload.get("implementation")
    if (
        not isinstance(implementation, dict)
        or implementation.get("decision_id") != "PD-040"
        or implementation.get("variable_id")
        != "BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1"
        or implementation.get("config_identity_decision_id") != "PD-043"
        or implementation.get("default_enabled") is not False
        or implementation.get("failure_policy") != "FALLBACK_TO_ORIGINAL_QUERY"
    ):
        raise ValueError("phase 3 comparison implementation boundary drifted")
    config_path = implementation.get("config")
    if not isinstance(config_path, str) or not (ROOT / config_path).is_file():
        raise ValueError("phase 3 comparison config path is invalid")
    if implementation.get("config_sha256") != (
        "87b969a1b0f006c3406ab01a24837c5ff129d08bedd0b2460a57122f9d0b0f2b"
    ):
        raise ValueError("phase 3 comparison config identity drifted")
    if implementation.get("config_identity_canonicalization") != (
        "LF_CANONICAL_TEXT_BYTES_CRLF_EQUIVALENT_CONTENT_DRIFT_REJECTED"
    ):
        raise ValueError("phase 3 comparison config canonicalization drifted")

    online = payload.get("preserved_online_path")
    if (
        not isinstance(online, dict)
        or online.get("candidate_k") != 20
        or online.get("rrf_k") != 60
        or online.get("final_top_k") != 3
        or online.get("reranker_enabled") is not False
        or online.get("additional_es_requests") != 0
        or online.get("additional_milvus_requests") != 0
        or online.get("new_llm_calls") != 0
    ):
        raise ValueError("phase 3 preserved online path drifted")

    evidence = payload.get("local_dev_plan_evidence")
    if (
        not isinstance(evidence, dict)
        or evidence.get("status") != "PASS"
        or evidence.get("target_case_count") != 4
        or evidence.get("control_original_query_preserved") != 4
        or evidence.get("treatment_applied") != 4
        or evidence.get("decomposition_p95_ms_max") != 5
    ):
        raise ValueError("phase 3 local dev plan evidence is invalid")
    paired = payload.get("paired_online_dev_quality")
    if (
        not isinstance(paired, dict)
        or paired.get("status") != "FAIL"
        or paired.get("decision") != "KEEP_COMPARISON_DECOMPOSITION_DISABLED"
        or paired.get("control_baseline", {}).get("strict_two_sided_passed") != 0
        or paired.get("treatment", {}).get("strict_two_sided_passed") != 0
        or paired.get("treatment_gain", {}).get(
            "macro_recall_at_3_absolute_gain"
        )
        != 0.0
        or paired.get("treatment_gain", {}).get(
            "macro_ndcg_at_3_absolute_gain"
        )
        != -0.017739
        or paired.get("fixed_15_canary_passed") != 14
        or paired.get("incremental_retrieval_p95_ms") != 24.101115
        or paired.get("decomposition_p95_ms") != 0.12922
        or paired.get("test") != "NOT_READ_NOT_RUN"
        or paired.get("acceptance") != "NOT_READ_NOT_RUN"
        or paired.get("performance_gate") != "PENDING_SEPARATE_300MS_GATE"
    ):
        raise ValueError("phase 3 paired online dev quality failure drifted")
    user_entry = payload.get("paired_online_user_entry")
    if (
        not isinstance(user_entry, dict)
        or user_entry.get("decision_id") != "PD-041"
        or user_entry.get("status")
        != "SEVENTH_ATTEMPT_COMPLETE_NO_RERUN_AUTHORIZED"
        or user_entry.get("cleanup_audit_decision_id") != "PD-044"
        or user_entry.get("cleanup_recovery_decision_id") != "PD-045"
        or user_entry.get("quality_top_k") != 3
        or user_entry.get("absolute_300ms_slo_adjudication") is not False
        or "TEST_ACCEPTANCE_EXCLUDED"
        not in str(user_entry.get("input_boundary", ""))
    ):
        raise ValueError("phase 3 paired online user entry boundary drifted")
    attempts = payload.get("windows_attempts")
    if (
        not isinstance(attempts, list)
        or len(attempts) != 7
        or any(not isinstance(attempt, dict) for attempt in attempts)
        or attempts[0].get("run_id") != "phase3_comparison_dev_20260723_01"
        or attempts[0].get("status") != "REJECTED_BEFORE_SERVICES"
        or attempts[0].get("adjudication_error_code")
        != "REPORT_CONFIG_IDENTITY_MISMATCH"
        or attempts[0].get("online_quality_executed") is not False
        or attempts[0].get("infrastructure_mutation_started") is not False
        or attempts[1].get("run_id") != "phase3_comparison_dev_20260723_02"
        or attempts[1].get("status") != "REJECTED_CLEANUP_PROOF_FAILED"
        or attempts[1].get("report_sha256")
        != "423d736d496be0afa1cc06a90e3402b060c519f74c17d9c4939e31a50304e276"
        or attempts[1].get("adjudication_error_code")
        != "REPORT_CLEANUP_PROOF_INVALID"
        or attempts[1].get("adjudication_sha256")
        != "74a599288445f1c2267f892a81b5f6b8bd3d5002d4a67e6be6700645d3516981"
        or attempts[2].get("run_id") != "phase3_comparison_dev_20260723_03"
        or attempts[2].get("status")
        != "REJECTED_CLEANUP_QUEUE_SCOPE_PROOF_FAILED"
        or attempts[2].get("cleanup_stage") != "VERIFY_QUEUE_SCOPE"
        or attempts[2].get("report_sha256")
        != "a45ef2f9f030feb6aaed05decb33a019cfa7920faf6e1f1abeb7189c242e339ec"
        or attempts[3].get("run_id") != "phase3_comparison_dev_20260723_04"
        or attempts[3].get("head_commit")
        != "b92e9ffa1d576aeef83dd028a28df09bf601d52e"
        or attempts[3].get("status")
        != "FAIL_RUN_CONTROL_NO_METRICS_CLEANUP_PASS"
        or attempts[3].get("primary_stage") != "RUN_CONTROL"
        or attempts[3].get("primary_error_code") != "PHASE3_GATE_FAILED"
        or attempts[3].get("report_sha256")
        != "2ca305dcd16820de4eb28863097f58c53ad5f9d678604c5251a65de70b2aa47c"
        or attempts[3].get("adjudication_sha256")
        != "b49bf9079ed3c9c7c2019a4e4836cdb9677dea07955675d6bfe1cdce25e4a4bf"
        or attempts[3].get("cleanup_status") != "PASS"
        or attempts[3].get("cleanup_jobs_succeeded") != 9
        or attempts[3].get("ready_reconciliation_failed_closed") is not True
        or attempts[3].get("deleted_answer_api_status") != 403
        or attempts[3].get("online_quality_executed") is not False
        or attempts[3].get("test") != "NOT_READ_NOT_RUN"
        or attempts[3].get("acceptance") != "NOT_READ_NOT_RUN"
        or attempts[4].get("run_id") != "phase3_comparison_dev_20260723_05"
        or attempts[4].get("head_commit")
        != "a669702b24880269a130f8e249126b30e17a2972"
        or attempts[4].get("status")
        != "FAIL_RUN_CONTROL_MILVUS_ROUTE_NO_METRICS_CLEANUP_PASS"
        or attempts[4].get("primary_stage") != "RUN_CONTROL"
        or attempts[4].get("primary_error_code")
        != "ONLINE_MILVUS_ROUTE_FAILED"
        or attempts[4].get("report_sha256")
        != "19a92545d6e87408462bdc38a72e3f4f69b5aa03edcaaed19400116aafba4cd4"
        or attempts[4].get("adjudication_sha256")
        != "f8f72c59278a2a7efb13b9b5917eab596779372e4b159677a32b7538b82a9a2d"
        or attempts[4].get("cleanup_status") != "PASS"
        or attempts[4].get("cleanup_jobs_succeeded") != 9
        or attempts[4].get("ready_reconciliation_failed_closed") is not True
        or attempts[4].get("deleted_answer_api_status") != 403
        or attempts[4].get("online_quality_executed") is not False
        or attempts[4].get("test") != "NOT_READ_NOT_RUN"
        or attempts[4].get("acceptance") != "NOT_READ_NOT_RUN"
        or attempts[5].get("run_id") != "phase3_comparison_dev_20260723_06"
        or attempts[5].get("head_commit")
        != "4771fe39ade2039a3251a6f8699a99fd1fb69b4d"
        or attempts[5].get("status")
        != "FAIL_RUN_CONTROL_MILVUS_ROUTE_IDENTITY_NO_METRICS_CLEANUP_PASS"
        or attempts[5].get("primary_stage") != "RUN_CONTROL"
        or attempts[5].get("primary_error_code")
        != "ONLINE_MILVUS_ROUTE_IDENTITY_FAILED"
        or attempts[5].get("report_sha256")
        != "fcbd2b472e21ad5554fb3ebb0389cde649fdfe80c4036c8bcc64a194fc4f70cb"
        or attempts[5].get("adjudication_sha256")
        != "a43f13f6e06f3d0c1b9aba405529a31a82b754477292220d9eac831cdcc6b779d"
        or attempts[5].get("cleanup_status") != "PASS"
        or attempts[5].get("cleanup_jobs_succeeded") != 9
        or attempts[5].get("ready_reconciliation_failed_closed") is not True
        or attempts[5].get("deleted_answer_api_status") != 403
        or attempts[5].get("online_quality_executed") is not False
        or attempts[5].get("test") != "NOT_READ_NOT_RUN"
        or attempts[5].get("acceptance") != "NOT_READ_NOT_RUN"
        or attempts[6].get("run_id") != "phase3_comparison_dev_20260723_07"
        or attempts[6].get("head_commit")
        != "ff370b512f88b7d847fa17f080946aab4050048c"
        or attempts[6].get("status")
        != "FAIL_COMPLETE_QUALITY_THRESHOLD_NOT_MET_CLEANUP_PASS"
        or attempts[6].get("report_error_code")
        != "QUALITY_OR_COST_THRESHOLD_NOT_MET"
        or attempts[6].get("primary_stage") != "COMPLETE"
        or attempts[6].get("primary_error_code") is not None
        or attempts[6].get("input_manifest_sha256")
        != "05c36a393a51a8aa705e17d1ac3895df074b9273f8af6bfad06c9904c458c63f"
        or attempts[6].get("config_sha256")
        != "87b969a1b0f006c3406ab01a24837c5ff129d08bedd0b2460a57122f9d0b0f2b"
        or attempts[6].get("target_ids_sha256")
        != "3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8"
        or attempts[6].get("report_sha256")
        != "3810ce9228f7ce9c65b5ebe031f1f5ca6a471fa665bf5d8c12a6e7cac6e01390"
        or attempts[6].get("adjudication_sha256")
        != "99530d236b8ca50b53de18557c9d43c7bcc63695a3c98fc9dba889b33cdaa036"
        or attempts[6].get("control_strict_two_sided_passed") != 0
        or attempts[6].get("treatment_strict_two_sided_passed") != 0
        or attempts[6].get("macro_ndcg_at_3_absolute_gain") != -0.017739
        or attempts[6].get("fixed_15_canary_passed") != 14
        or attempts[6].get("control_retrieval_p95_ms") != 704.53041
        or attempts[6].get("treatment_retrieval_p95_ms") != 728.631525
        or attempts[6].get("cleanup_status") != "PASS"
        or attempts[6].get("cleanup_jobs_succeeded") != 9
        or attempts[6].get("ready_reconciliation_failed_closed") is not True
        or attempts[6].get("deleted_answer_api_status") != 403
        or attempts[6].get("recovery_required") is not False
        or attempts[6].get("online_quality_executed") is not True
        or attempts[6].get("test") != "NOT_READ_NOT_RUN"
        or attempts[6].get("acceptance") != "NOT_READ_NOT_RUN"
    ):
        raise ValueError("phase 3 rejected Windows attempt evidence drifted")
    for field in (
        "package_builder",
        "runner",
        "report_adjudicator",
        "report_intake",
        "windows_powershell_51_entry",
        "cleanup_auditor",
        "windows_cleanup_audit_entry",
        "cleanup_recovery_runner",
        "windows_cleanup_recovery_entry",
        "runbook",
    ):
        relative_path = user_entry.get(field)
        if not isinstance(relative_path, str) or not (ROOT / relative_path).is_file():
            raise ValueError(f"phase 3 paired online user entry {field} is missing")
    isolation = payload.get("split_isolation")
    if (
        not isinstance(isolation, dict)
        or not str(isolation.get("test", "")).startswith("SEALED")
        or not str(isolation.get("acceptance", "")).startswith("SEALED")
    ):
        raise ValueError("phase 3 comparison split isolation drifted")
    performance = payload.get("independent_performance_gate")
    if (
        not isinstance(performance, dict)
        or performance.get("retrieval_p95_ms_max") != 300
        or performance.get(
            "must_not_be_combined_with_comparison_quality_change"
        )
        is not True
    ):
        raise ValueError("phase 3 independent performance gate drifted")
    cleanup_audit = payload.get("cleanup_audit_gate")
    if (
        not isinstance(cleanup_audit, dict)
        or cleanup_audit.get("status")
        != "FAIL_RESIDUAL_REQUIRES_RECOVERY_GATE"
        or cleanup_audit.get("run_id")
        != "phase3_comparison_dev_20260723_03"
        or cleanup_audit.get("mode")
        != "POSTGRESQL_READ_ONLY_OWNER_SCOPED_PLUS_GLOBAL_NONTERMINAL_COUNT"
        or cleanup_audit.get("audit_sha256")
        != "e9430be17811c60116630f718c182a3ffd0a12ffd83f753ebb5fdfba0420112b"
        or cleanup_audit.get("quality_rerun_allowed_before_clean") is not False
        or cleanup_audit.get("manual_cleanup_allowed") is not False
        or cleanup_audit.get("test_acceptance_read_allowed") is not False
    ):
        raise ValueError("phase 3 cleanup audit boundary drifted")
    recovery = payload.get("cleanup_recovery_gate")
    if (
        not isinstance(recovery, dict)
        or recovery.get("status") != "PASS"
        or recovery.get("decision_id") != "PD-047"
        or recovery.get("completion_decision_id") != "PD-048"
        or recovery.get("run_id") != "phase3_comparison_dev_20260723_03"
        or recovery.get("head_commit")
        != "c9c3705d70de7cb43812a8cd8a6a585da6eebcd9"
        or recovery.get("frozen_audit_sha256")
        != "e9430be17811c60116630f718c182a3ffd0a12ffd83f753ebb5fdfba0420112b"
        or recovery.get("single_action")
        != "RUN_EXISTING_PERSISTENT_CLEANUP_WORKER_MAX_NINE"
        or recovery.get("quality_gate_run") is not False
        or recovery.get("test_acceptance_read_allowed") is not False
        or recovery.get("performance_gate_run") is not False
        or recovery.get("service_restart_allowed") is not False
        or recovery.get("manual_delete_allowed") is not False
    ):
        raise ValueError("phase 3 cleanup recovery boundary drifted")
    recovery_result = payload.get("cleanup_recovery_result")
    if (
        not isinstance(recovery_result, dict)
        or recovery_result.get("run_id")
        != "phase3_comparison_dev_20260723_02"
        or recovery_result.get("status") != "PASS"
        or recovery_result.get("jobs_succeeded") != 9
        or recovery_result.get("post_chunk_rows") != 0
        or recovery_result.get("post_pdf_object_rows") != 0
        or recovery_result.get(
            "post_global_nonterminal_cleanup_job_count"
        )
        != 0
        or recovery_result.get("recovery_sha256")
        != "e9a9566ecfede9c30310f9831d8ebf22249cb5081eda69ba6f7dea48e26cb8fa"
        or recovery_result.get("post_recovery_audit_decision") != "CLEAN"
        or recovery_result.get("post_recovery_audit_sha256")
        != "f3c12a2f2f7c4d8e0f75ee8db7b483b44c6509cf65fa0f0ee03779e296252790"
        or recovery_result.get("quality_gate_run") is not False
        or recovery_result.get("test") != "NOT_READ_NOT_RUN"
        or recovery_result.get("acceptance") != "NOT_READ_NOT_RUN"
        or recovery_result.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 cleanup recovery evidence drifted")
    recovery_result_03 = payload.get("cleanup_recovery_result_03")
    if (
        not isinstance(recovery_result_03, dict)
        or recovery_result_03.get("run_id")
        != "phase3_comparison_dev_20260723_03"
        or recovery_result_03.get("status") != "PASS"
        or recovery_result_03.get("jobs_observed") != 9
        or recovery_result_03.get("jobs_succeeded") != 9
        or recovery_result_03.get("post_chunk_rows") != 0
        or recovery_result_03.get("post_pdf_object_rows") != 0
        or recovery_result_03.get(
            "post_global_nonterminal_cleanup_job_count"
        )
        != 0
        or recovery_result_03.get("recovery_sha256")
        != "94a10a54ffb6b326740e093db97d148891fd44898e7bc077e25fa4385b780cdb"
        or recovery_result_03.get("post_recovery_audit_decision") != "CLEAN"
        or recovery_result_03.get("post_recovery_audit_sha256")
        != "ffd2e805b857df1d4d7e256a00bf09b15992261a4a31960c7a2d55b8d504dbab"
        or recovery_result_03.get("quality_gate_run") is not False
        or recovery_result_03.get("test") != "NOT_READ_NOT_RUN"
        or recovery_result_03.get("acceptance") != "NOT_READ_NOT_RUN"
        or recovery_result_03.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 third cleanup recovery evidence drifted")
    runner_defect = payload.get("known_runner_defect")
    if (
        not isinstance(runner_defect, dict)
        or runner_defect.get("status")
        != "VERIFIED_FIXED_BY_FOURTH_WINDOWS_CLEANUP"
        or runner_defect.get("cause")
        != "PSYCOPG_DICT_ROW_WAS_TUPLE_UNPACKED_AS_COLUMN_NAMES"
        or runner_defect.get("repair")
        != "ACCESS_MAPPING_VALUES_BY_EXPLICIT_KEYS"
        or runner_defect.get("diagnostic_hardening")
        != "SANITIZED_PRIMARY_STAGE_REPORTED"
        or runner_defect.get("quality_variable_changed") is not False
        or runner_defect.get("quality_rerun_authorized") is not True
    ):
        raise ValueError("phase 3 runner defect repair boundary drifted")
    diagnostic = payload.get("control_failure_diagnostic_hardening")
    if (
        not isinstance(diagnostic, dict)
        or diagnostic.get("status") != "VERIFIED_BY_FIFTH_WINDOWS_COMPONENT_CODE"
        or diagnostic.get("decision_id") != "PD-049"
        or diagnostic.get("source_run_id")
        != "phase3_comparison_dev_20260723_04"
        or diagnostic.get("source_primary_stage") != "RUN_CONTROL"
        or diagnostic.get("classification")
        != "CONTROL_SUBSTAGE_PLUS_EXCEPTION_TYPE_CHAIN_TO_STABLE_COMPONENT_CODE_WITHOUT_EXCEPTION_TEXT"
        or diagnostic.get("additional_requests") != 0
        or diagnostic.get("quality_variable_changed") is not False
        or diagnostic.get("retrieval_parameters_changed") is not False
        or diagnostic.get("default_enabled") is not False
        or diagnostic.get("test") != "NOT_READ_NOT_RUN"
        or diagnostic.get("acceptance") != "NOT_READ_NOT_RUN"
        or diagnostic.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 Control failure diagnostic boundary drifted")
    milvus_diagnostic = payload.get("milvus_failure_diagnostic_hardening")
    if (
        not isinstance(milvus_diagnostic, dict)
        or milvus_diagnostic.get("status")
        != "VERIFIED_BY_SIXTH_WINDOWS_ROUTE_IDENTITY_CODE"
        or milvus_diagnostic.get("decision_id") != "PD-050"
        or milvus_diagnostic.get("source_run_id")
        != "phase3_comparison_dev_20260723_05"
        or milvus_diagnostic.get("source_primary_stage") != "RUN_CONTROL"
        or milvus_diagnostic.get("source_primary_error_code")
        != "ONLINE_MILVUS_ROUTE_FAILED"
        or milvus_diagnostic.get("stable_stages")
        != [
            "ROUTE_IDENTITY",
            "QUERY_EMBEDDING",
            "ANN_SEARCH",
            "RESPONSE_CONTRACT",
        ]
        or milvus_diagnostic.get("additional_requests") != 0
        or milvus_diagnostic.get("quality_variable_changed") is not False
        or milvus_diagnostic.get("retrieval_parameters_changed") is not False
        or milvus_diagnostic.get("default_enabled") is not False
        or milvus_diagnostic.get("test") != "NOT_READ_NOT_RUN"
        or milvus_diagnostic.get("acceptance") != "NOT_READ_NOT_RUN"
        or milvus_diagnostic.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 Milvus failure diagnostic boundary drifted")
    identity_fix = payload.get("milvus_route_identity_fix")
    if (
        not isinstance(identity_fix, dict)
        or identity_fix.get("status")
        != "VERIFIED_BY_SEVENTH_WINDOWS_COMPLETE_CONTROL_TREATMENT"
        or identity_fix.get("decision_id") != "PD-051"
        or identity_fix.get("source_run_id")
        != "phase3_comparison_dev_20260723_06"
        or identity_fix.get("source_primary_error_code")
        != "ONLINE_MILVUS_ROUTE_IDENTITY_FAILED"
        or identity_fix.get("ann_changed") is not False
        or identity_fix.get("embedding_changed") is not False
        or identity_fix.get("quality_variable_changed") is not False
        or identity_fix.get("retrieval_parameters_changed") is not False
        or identity_fix.get("default_enabled") is not False
        or identity_fix.get("test") != "NOT_READ_NOT_RUN"
        or identity_fix.get("acceptance") != "NOT_READ_NOT_RUN"
        or identity_fix.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 Milvus route identity fix boundary drifted")


def check_phase3_comparison_report_intake() -> None:
    payload = _read_json("machine/phase3_comparison_report_intake.json")
    if (
        payload.get("schema_version") != "phase3_comparison_report_intake_v1"
        or payload.get("decision_id") != "PD-042"
        or payload.get("repair_decision_id") != "PD-043"
        or payload.get("cleanup_audit_decision_id") != "PD-044"
        or payload.get("cleanup_recovery_decision_id") != "PD-045"
        or payload.get("cleanup_recovery_completion_decision_id") != "PD-046"
        or payload.get("control_failure_diagnostic_decision_id") != "PD-049"
        or payload.get("milvus_failure_diagnostic_decision_id") != "PD-050"
        or payload.get("milvus_route_identity_fix_decision_id") != "PD-051"
        or payload.get("seventh_attempt_quality_decision_id") != "PD-052"
        or payload.get("status")
        != "SEVENTH_ATTEMPT_TRUSTWORTHY_DEV_QUALITY_FAIL_CLEAN"
    ):
        raise ValueError("phase 3 report intake identity is invalid")
    implementation = payload.get("implementation")
    if not isinstance(implementation, dict):
        raise ValueError("phase 3 report intake implementation is invalid")
    for field in (
        "runner",
        "adjudicator",
        "windows_entry",
        "cleanup_auditor",
        "windows_cleanup_audit_entry",
        "cleanup_recovery_runner",
        "windows_cleanup_recovery_entry",
    ):
        relative_path = implementation.get(field)
        if not isinstance(relative_path, str) or not (ROOT / relative_path).is_file():
            raise ValueError(f"phase 3 report intake {field} is missing")
    tests = implementation.get("tests")
    if (
        not isinstance(tests, list)
        or len(tests) != 5
        or any(not isinstance(path, str) or not (ROOT / path).is_file() for path in tests)
    ):
        raise ValueError("phase 3 report intake tests are invalid")
    identity = payload.get("required_report_identity")
    if (
        not isinstance(identity, dict)
        or identity.get("head_commit")
        != "CALLER_PINNED_AND_MATCHED_TO_RUNNER_CHECKOUT"
        or identity.get("run_id") != "CALLER_PINNED"
        or identity.get("report_sha256") != "CALLER_PINNED"
        or identity.get("input_manifest_sha256") != "CALLER_PINNED"
        or identity.get("config_identity_canonicalization")
        != "LF_CANONICAL_TEXT_BYTES_CRLF_EQUIVALENT_CONTENT_DRIFT_REJECTED"
    ):
        raise ValueError("phase 3 report intake identity binding drifted")
    trust = payload.get("trust_preconditions")
    if (
        not isinstance(trust, dict)
        or trust.get("test") != "NOT_READ_NOT_RUN"
        or trust.get("acceptance") != "NOT_READ_NOT_RUN"
        or trust.get("cleanup_jobs_succeeded") != 9
        or trust.get("deleted_answer_api_status") != 403
        or trust.get("absolute_300ms_slo_conclusion_allowed") is not False
    ):
        raise ValueError("phase 3 report intake trust boundary drifted")
    outcomes = payload.get("outcomes")
    if not isinstance(outcomes, dict) or set(outcomes) != {
        "pass",
        "fail",
        "rejected",
    }:
        raise ValueError("phase 3 report intake outcomes are invalid")
    if any(
        not isinstance(outcome, dict)
        or outcome.get("default_enabled") is not False
        for outcome in outcomes.values()
    ):
        raise ValueError("phase 3 report intake must preserve default-off behavior")
    isolation = payload.get("split_and_gate_isolation")
    if (
        not isinstance(isolation, dict)
        or isolation.get("test") != "NO_AUTOMATIC_UNLOCK_OR_EXECUTION"
        or not str(isolation.get("acceptance", "")).startswith("SEALED")
        or isolation.get("performance") != "PENDING_SEPARATE_300MS_GATE"
    ):
        raise ValueError("phase 3 report intake gate isolation drifted")
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("phase 3 report intake evidence is invalid")
    attempts = evidence.get("attempts")
    if (
        not isinstance(attempts, list)
        or len(attempts) != 7
        or any(not isinstance(attempt, dict) for attempt in attempts)
        or attempts[0].get("status") != "REJECTED_BEFORE_SERVICES"
        or attempts[0].get("error_code") != "REPORT_CONFIG_IDENTITY_MISMATCH"
        or attempts[1].get("status") != "REJECTED_CLEANUP_PROOF_FAILED"
        or attempts[1].get("error_code") != "REPORT_CLEANUP_PROOF_INVALID"
        or attempts[1].get("adjudication_sha256")
        != "74a599288445f1c2267f892a81b5f6b8bd3d5002d4a67e6be6700645d3516981"
        or attempts[2].get("status")
        != "REJECTED_CLEANUP_QUEUE_SCOPE_PROOF_FAILED"
        or attempts[2].get("cleanup_stage") != "VERIFY_QUEUE_SCOPE"
        or attempts[2].get("report_sha256")
        != "a45ef2f9f030feb6aaed05decb33a019cfa7920faf6e1f1abeb7189c242e339ec"
        or attempts[3].get("run_id") != "phase3_comparison_dev_20260723_04"
        or attempts[3].get("status")
        != "FAIL_RUN_CONTROL_NO_METRICS_CLEANUP_PASS"
        or attempts[3].get("primary_stage") != "RUN_CONTROL"
        or attempts[3].get("report_sha256")
        != "2ca305dcd16820de4eb28863097f58c53ad5f9d678604c5251a65de70b2aa47c"
        or attempts[3].get("adjudication_sha256")
        != "b49bf9079ed3c9c7c2019a4e4836cdb9677dea07955675d6bfe1cdce25e4a4bf"
        or attempts[3].get("cleanup_status") != "PASS"
        or attempts[3].get("cleanup_jobs_succeeded") != 9
        or attempts[3].get("deleted_answer_api_status") != 403
        or attempts[3].get("test") != "NOT_READ_NOT_RUN"
        or attempts[3].get("acceptance") != "NOT_READ_NOT_RUN"
        or attempts[4].get("run_id") != "phase3_comparison_dev_20260723_05"
        or attempts[4].get("status")
        != "FAIL_RUN_CONTROL_MILVUS_ROUTE_NO_METRICS_CLEANUP_PASS"
        or attempts[4].get("error_code") != "ONLINE_MILVUS_ROUTE_FAILED"
        or attempts[4].get("primary_stage") != "RUN_CONTROL"
        or attempts[4].get("report_sha256")
        != "19a92545d6e87408462bdc38a72e3f4f69b5aa03edcaaed19400116aafba4cd4"
        or attempts[4].get("adjudication_sha256")
        != "f8f72c59278a2a7efb13b9b5917eab596779372e4b159677a32b7538b82a9a2d"
        or attempts[4].get("cleanup_status") != "PASS"
        or attempts[4].get("cleanup_jobs_succeeded") != 9
        or attempts[4].get("deleted_answer_api_status") != 403
        or attempts[4].get("test") != "NOT_READ_NOT_RUN"
        or attempts[4].get("acceptance") != "NOT_READ_NOT_RUN"
        or attempts[5].get("run_id") != "phase3_comparison_dev_20260723_06"
        or attempts[5].get("status")
        != "FAIL_RUN_CONTROL_MILVUS_ROUTE_IDENTITY_NO_METRICS_CLEANUP_PASS"
        or attempts[5].get("error_code")
        != "ONLINE_MILVUS_ROUTE_IDENTITY_FAILED"
        or attempts[5].get("primary_stage") != "RUN_CONTROL"
        or attempts[5].get("report_sha256")
        != "fcbd2b472e21ad5554fb3ebb0389cde649fdfe80c4036c8bcc64a194fc4f70cb"
        or attempts[5].get("adjudication_sha256")
        != "a43f13f6e06f3d0c1b9aba405529a31a82b754477292220d9eac831cdcc6b779d"
        or attempts[5].get("cleanup_status") != "PASS"
        or attempts[5].get("cleanup_jobs_succeeded") != 9
        or attempts[5].get("ready_reconciliation_failed_closed") is not True
        or attempts[5].get("deleted_answer_api_status") != 403
        or attempts[5].get("test") != "NOT_READ_NOT_RUN"
        or attempts[5].get("acceptance") != "NOT_READ_NOT_RUN"
        or attempts[6].get("run_id") != "phase3_comparison_dev_20260723_07"
        or attempts[6].get("head_commit")
        != "ff370b512f88b7d847fa17f080946aab4050048c"
        or attempts[6].get("status")
        != "FAIL_COMPLETE_QUALITY_THRESHOLD_NOT_MET_CLEANUP_PASS"
        or attempts[6].get("error_code")
        != "QUALITY_OR_COST_THRESHOLD_NOT_MET"
        or attempts[6].get("primary_stage") != "COMPLETE"
        or attempts[6].get("input_manifest_sha256")
        != "05c36a393a51a8aa705e17d1ac3895df074b9273f8af6bfad06c9904c458c63f"
        or attempts[6].get("config_sha256")
        != "87b969a1b0f006c3406ab01a24837c5ff129d08bedd0b2460a57122f9d0b0f2b"
        or attempts[6].get("target_ids_sha256")
        != "3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8"
        or attempts[6].get("report_sha256")
        != "3810ce9228f7ce9c65b5ebe031f1f5ca6a471fa665bf5d8c12a6e7cac6e01390"
        or attempts[6].get("adjudication_sha256")
        != "99530d236b8ca50b53de18557c9d43c7bcc63695a3c98fc9dba889b33cdaa036"
        or attempts[6].get("control_strict_two_sided_passed") != 0
        or attempts[6].get("treatment_strict_two_sided_passed") != 0
        or attempts[6].get("macro_ndcg_at_3_absolute_gain") != -0.017739
        or attempts[6].get("fixed_15_canary_passed") != 14
        or attempts[6].get("control_retrieval_p95_ms") != 704.53041
        or attempts[6].get("treatment_retrieval_p95_ms") != 728.631525
        or attempts[6].get("cleanup_status") != "PASS"
        or attempts[6].get("cleanup_jobs_succeeded") != 9
        or attempts[6].get("ready_reconciliation_failed_closed") is not True
        or attempts[6].get("deleted_answer_api_status") != 403
        or attempts[6].get("recovery_required") is not False
        or attempts[6].get("test") != "NOT_READ_NOT_RUN"
        or attempts[6].get("acceptance") != "NOT_READ_NOT_RUN"
    ):
        raise ValueError("phase 3 report intake rejected evidence drifted")
    audit = payload.get("cleanup_audit_boundary")
    if (
        not isinstance(audit, dict)
        or audit.get("target_run_id") != "phase3_comparison_dev_20260723_03"
        or audit.get("postgresql_transaction") != "READ_ONLY"
        or audit.get("audit_sha256")
        != "e9430be17811c60116630f718c182a3ffd0a12ffd83f753ebb5fdfba0420112b"
        or audit.get("observed_state")
        != "THREE_INACTIVE_VERSIONS_NINE_PENDING_CLEANUP_JOBS_316_CHUNKS_THREE_PDF_OBJECTS"
        or audit.get("quality_rerun_authorized") is not True
        or audit.get("manual_cleanup_authorized") is not False
        or audit.get("performance_gate") != "NOT_COMBINED"
        or audit.get("next_gate")
        != "NEW_RUN_ID_PAIRED_ONLINE_DEV_QUALITY_GATE"
    ):
        raise ValueError("phase 3 report intake cleanup audit boundary drifted")
    recovery = payload.get("cleanup_recovery_evidence")
    if (
        not isinstance(recovery, dict)
        or recovery.get("run_id")
        != "phase3_comparison_dev_20260723_02"
        or recovery.get("jobs_succeeded") != 9
        or recovery.get("post_chunk_rows") != 0
        or recovery.get("post_pdf_object_rows") != 0
        or recovery.get("post_global_nonterminal_cleanup_job_count") != 0
        or recovery.get("recovery_sha256")
        != "e9a9566ecfede9c30310f9831d8ebf22249cb5081eda69ba6f7dea48e26cb8fa"
        or recovery.get("post_recovery_audit") != "PASS_CLEAN"
        or recovery.get("post_recovery_audit_sha256")
        != "f3c12a2f2f7c4d8e0f75ee8db7b483b44c6509cf65fa0f0ee03779e296252790"
        or recovery.get("quality_gate_run") is not False
        or recovery.get("test") != "NOT_READ_NOT_RUN"
        or recovery.get("acceptance") != "NOT_READ_NOT_RUN"
        or recovery.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 report intake recovery evidence drifted")
    completed_recovery = payload.get("completed_cleanup_recovery_03")
    if (
        not isinstance(completed_recovery, dict)
        or completed_recovery.get("run_id")
        != "phase3_comparison_dev_20260723_03"
        or completed_recovery.get("status") != "PASS_CLEAN"
        or completed_recovery.get("frozen_audit_sha256")
        != "e9430be17811c60116630f718c182a3ffd0a12ffd83f753ebb5fdfba0420112b"
        or completed_recovery.get("recovery_sha256")
        != "94a10a54ffb6b326740e093db97d148891fd44898e7bc077e25fa4385b780cdb"
        or completed_recovery.get("jobs_succeeded") != 9
        or completed_recovery.get("post_chunk_rows") != 0
        or completed_recovery.get("post_pdf_object_rows") != 0
        or completed_recovery.get(
            "post_global_nonterminal_cleanup_job_count"
        )
        != 0
        or completed_recovery.get("post_recovery_audit_sha256")
        != "ffd2e805b857df1d4d7e256a00bf09b15992261a4a31960c7a2d55b8d504dbab"
        or completed_recovery.get("post_recovery_audit") != "PASS_CLEAN"
        or completed_recovery.get("quality_gate_run") is not False
        or completed_recovery.get("test") != "NOT_READ_NOT_RUN"
        or completed_recovery.get("acceptance") != "NOT_READ_NOT_RUN"
        or completed_recovery.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 completed third cleanup recovery boundary drifted")
    runner_repair = payload.get("runner_repair")
    if (
        not isinstance(runner_repair, dict)
        or runner_repair.get("status")
        != "VERIFIED_BY_FOURTH_WINDOWS_CLEANUP_PASS"
        or runner_repair.get("cause")
        != "PSYCOPG_DICT_ROW_WAS_TUPLE_UNPACKED_AS_COLUMN_NAMES"
        or runner_repair.get("repair")
        != "EXPLICIT_OWNER_VERSION_BACKEND_MAPPING_KEY_ACCESS"
        or runner_repair.get("diagnostic_hardening")
        != "REPORT_SANITIZED_PRIMARY_STAGE"
        or runner_repair.get("quality_variable_changed") is not False
        or runner_repair.get("default_enabled") is not False
    ):
        raise ValueError("phase 3 report intake runner repair boundary drifted")
    fourth_cleanup = payload.get("fourth_attempt_cleanup_proof")
    if (
        not isinstance(fourth_cleanup, dict)
        or fourth_cleanup.get("run_id")
        != "phase3_comparison_dev_20260723_04"
        or fourth_cleanup.get("status") != "PASS_CLEAN"
        or fourth_cleanup.get("jobs_succeeded") != 9
        or fourth_cleanup.get("ready_reconciliation_failed_closed") is not True
        or fourth_cleanup.get("deleted_answer_api_status") != 403
        or fourth_cleanup.get("recovery_required") is not False
        or fourth_cleanup.get("quality_metrics_available") is not False
        or fourth_cleanup.get("test") != "NOT_READ_NOT_RUN"
        or fourth_cleanup.get("acceptance") != "NOT_READ_NOT_RUN"
        or fourth_cleanup.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 fourth attempt cleanup proof drifted")
    diagnostic = payload.get("control_failure_diagnostic_hardening")
    if (
        not isinstance(diagnostic, dict)
        or diagnostic.get("status") != "VERIFIED_BY_FIFTH_WINDOWS_COMPONENT_CODE"
        or diagnostic.get("decision_id") != "PD-049"
        or diagnostic.get("classification")
        != "CONTROL_SUBSTAGE_PLUS_TYPE_ONLY_STABLE_COMPONENT_CODE_NO_EXCEPTION_TEXT"
        or diagnostic.get("additional_requests") != 0
        or diagnostic.get("quality_variable_changed") is not False
        or diagnostic.get("default_enabled") is not False
    ):
        raise ValueError("phase 3 report intake diagnostic boundary drifted")
    fifth_cleanup = payload.get("fifth_attempt_cleanup_proof")
    if (
        not isinstance(fifth_cleanup, dict)
        or fifth_cleanup.get("run_id")
        != "phase3_comparison_dev_20260723_05"
        or fifth_cleanup.get("status") != "PASS_CLEAN"
        or fifth_cleanup.get("jobs_succeeded") != 9
        or fifth_cleanup.get("ready_reconciliation_failed_closed") is not True
        or fifth_cleanup.get("deleted_answer_api_status") != 403
        or fifth_cleanup.get("recovery_required") is not False
        or fifth_cleanup.get("quality_metrics_available") is not False
        or fifth_cleanup.get("test") != "NOT_READ_NOT_RUN"
        or fifth_cleanup.get("acceptance") != "NOT_READ_NOT_RUN"
        or fifth_cleanup.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 fifth attempt cleanup proof drifted")
    milvus_diagnostic = payload.get("milvus_failure_diagnostic_hardening")
    if (
        not isinstance(milvus_diagnostic, dict)
        or milvus_diagnostic.get("status")
        != "VERIFIED_BY_SIXTH_WINDOWS_ROUTE_IDENTITY_CODE"
        or milvus_diagnostic.get("decision_id") != "PD-050"
        or milvus_diagnostic.get("additional_requests") != 0
        or milvus_diagnostic.get("quality_variable_changed") is not False
        or milvus_diagnostic.get("retrieval_parameters_changed") is not False
        or milvus_diagnostic.get("default_enabled") is not False
    ):
        raise ValueError("phase 3 report intake Milvus diagnostic boundary drifted")
    sixth_cleanup = payload.get("sixth_attempt_cleanup_proof")
    if (
        not isinstance(sixth_cleanup, dict)
        or sixth_cleanup.get("run_id")
        != "phase3_comparison_dev_20260723_06"
        or sixth_cleanup.get("status") != "PASS_CLEAN"
        or sixth_cleanup.get("jobs_succeeded") != 9
        or sixth_cleanup.get("ready_reconciliation_failed_closed") is not True
        or sixth_cleanup.get("deleted_answer_api_status") != 403
        or sixth_cleanup.get("recovery_required") is not False
        or sixth_cleanup.get("quality_metrics_available") is not False
        or sixth_cleanup.get("test") != "NOT_READ_NOT_RUN"
        or sixth_cleanup.get("acceptance") != "NOT_READ_NOT_RUN"
        or sixth_cleanup.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 sixth attempt cleanup proof drifted")
    identity_fix = payload.get("milvus_route_identity_fix")
    if (
        not isinstance(identity_fix, dict)
        or identity_fix.get("status")
        != "VERIFIED_BY_SEVENTH_WINDOWS_COMPLETE_CONTROL_TREATMENT"
        or identity_fix.get("decision_id") != "PD-051"
        or identity_fix.get("source_run_id")
        != "phase3_comparison_dev_20260723_06"
        or identity_fix.get("source_primary_error_code")
        != "ONLINE_MILVUS_ROUTE_IDENTITY_FAILED"
        or identity_fix.get("quality_variable_changed") is not False
        or identity_fix.get("retrieval_parameters_changed") is not False
        or identity_fix.get("default_enabled") is not False
        or identity_fix.get("test") != "NOT_READ_NOT_RUN"
        or identity_fix.get("acceptance") != "NOT_READ_NOT_RUN"
        or identity_fix.get("performance_gate") != "NOT_RUN"
    ):
        raise ValueError("phase 3 report intake Milvus identity fix drifted")
    seventh = payload.get("seventh_attempt_quality_result")
    if (
        not isinstance(seventh, dict)
        or seventh.get("status") != "FAIL_CLEAN"
        or seventh.get("decision_id") != "PD-052"
        or seventh.get("run_id") != "phase3_comparison_dev_20260723_07"
        or seventh.get("head_commit")
        != "ff370b512f88b7d847fa17f080946aab4050048c"
        or seventh.get("report_sha256")
        != "3810ce9228f7ce9c65b5ebe031f1f5ca6a471fa665bf5d8c12a6e7cac6e01390"
        or seventh.get("adjudication_sha256")
        != "99530d236b8ca50b53de18557c9d43c7bcc63695a3c98fc9dba889b33cdaa036"
        or seventh.get("error_code") != "QUALITY_OR_COST_THRESHOLD_NOT_MET"
        or seventh.get("decision") != "KEEP_COMPARISON_DECOMPOSITION_DISABLED"
        or seventh.get("control_strict_two_sided_passed") != 0
        or seventh.get("treatment_strict_two_sided_passed") != 0
        or seventh.get("macro_recall_at_3_absolute_gain") != 0.0
        or seventh.get("macro_ndcg_at_3_absolute_gain") != -0.017739
        or seventh.get("fixed_15_canary_passed") != 14
        or seventh.get("control_retrieval_p95_ms") != 704.53041
        or seventh.get("treatment_retrieval_p95_ms") != 728.631525
        or seventh.get("cleanup_status") != "PASS"
        or seventh.get("cleanup_jobs_succeeded") != 9
        or seventh.get("ready_reconciliation_failed_closed") is not True
        or seventh.get("deleted_answer_api_status") != 403
        or seventh.get("recovery_required") is not False
        or seventh.get("rerun_authorized") is not False
        or seventh.get("default_enabled") is not False
        or seventh.get("test") != "NOT_READ_NOT_RUN"
        or seventh.get("acceptance") != "NOT_READ_NOT_RUN"
        or seventh.get("performance_gate") != "PENDING_SEPARATE_300MS_GATE"
    ):
        raise ValueError("phase 3 seventh attempt quality result drifted")


def check_phase3_comparison_route_coverage_gate() -> None:
    payload = _read_json("machine/phase3_comparison_route_coverage_gate.json")
    if payload.get("schema_version") != (
        "phase3_comparison_route_coverage_gate_v1"
    ):
        raise ValueError("phase 3 route coverage schema_version is invalid")
    if payload.get("decision_ids") != ["PD-053", "PD-054"]:
        raise ValueError("phase 3 route coverage decision ids drifted")
    if payload.get("status") != (
        "LOCAL_IMPLEMENTATION_READY_DEFAULT_OFF_REMOTE_DEV_NOT_RUN"
    ):
        raise ValueError("phase 3 route coverage status is invalid")
    if payload.get("source_phase") != {"id": "phase-3", "status": "IN_PROGRESS"}:
        raise ValueError("phase 3 route coverage source phase is invalid")

    reuse = payload.get("reuse_review")
    if (
        not isinstance(reuse, dict)
        or reuse.get("decision")
        != "REUSE_EXISTING_NARROW_RETRIEVAL_CONTRACTS_WITHOUT_NEW_DEPENDENCY"
        or reuse.get("prior_project_result")
        != "NO_COMPATIBLE_GROUP_CONSTRAINED_FINAL_TOPK_SELECTOR_FOUND"
        or len(reuse.get("prior_projects_reviewed", [])) != 4
        or len(reuse.get("upstream_components_reviewed", [])) != 4
        or any(
            item.get("decision") != "NOT_ADOPTED"
            for item in reuse.get("upstream_components_reviewed", [])
            if isinstance(item, dict)
        )
    ):
        raise ValueError("phase 3 route coverage reuse review drifted")

    variable = payload.get("single_enhancement_variable")
    config_path = (
        "evaluation/phase3/bilateral-comparison-route-coverage-top3-v1.json"
    )
    if (
        not isinstance(variable, dict)
        or variable.get("id")
        != "BILATERAL_COMPARISON_ROUTE_COVERAGE_TOP3_V1"
        or variable.get("default_enabled") is not False
        or variable.get("reserved_switch")
        != "PHASE3_COMPARISON_ROUTE_COVERAGE_ENABLED"
        or variable.get("config") != config_path
        or variable.get("integration")
        != "OPTIONAL_FINAL_SELECTOR_AFTER_FULL_EXISTING_RRF_ORDER"
        or variable.get("score_policy") != "PRESERVE_ORIGINAL_RRF_SCORES"
        or variable.get("failure_policy")
        != "FALLBACK_TO_ORIGINAL_RRF_TOP3"
    ):
        raise ValueError("phase 3 route coverage variable contract drifted")
    config_bytes = (ROOT / config_path).read_bytes()
    if hashlib.sha256(config_bytes).hexdigest() != variable.get("config_sha256"):
        raise ValueError("phase 3 route coverage config identity drifted")

    path = payload.get("preserved_online_path")
    if (
        not isinstance(path, dict)
        or path.get("postgres_ready_owner_precondition") is not True
        or path.get(
            "persistent_document_version_chunk_identity_validation"
        )
        is not True
        or path.get("candidate_k") != 20
        or path.get("rrf_k") != 60
        or path.get("final_top_k") != 3
        or path.get("reranker_enabled") is not False
        or path.get("additional_es_requests") != 0
        or path.get("additional_milvus_requests") != 0
        or path.get("new_embedding_calls") != 0
        or path.get("new_llm_calls") != 0
        or path.get("candidate_expansion") is not False
    ):
        raise ValueError("phase 3 route coverage online path drifted")

    local_gate = payload.get("local_gate")
    future = payload.get("future_paired_dev_gate")
    if (
        not isinstance(local_gate, dict)
        or local_gate.get("status") != "PASS"
        or local_gate.get("quality_conclusion")
        != "NOT_CLAIMED_WITHOUT_PAIRED_ONLINE_DEV"
        or not isinstance(future, dict)
        or future.get("status") != "NOT_PREPARED_NOT_RUN"
        or future.get("run_id") is not None
        or future.get("sample_count") != 4
        or future.get("target_ids_sha256")
        != "3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8"
    ):
        raise ValueError("phase 3 route coverage local or future gate drifted")
    split = payload.get("split_isolation")
    performance = payload.get("independent_performance_gate")
    remote = payload.get("remote_boundary")
    if (
        not isinstance(split, dict)
        or split.get("test") != "NOT_READ_NOT_RUN"
        or not str(split.get("acceptance", "")).startswith("NOT_READ_NOT_RUN")
        or not isinstance(performance, dict)
        or performance.get("retrieval_p95_ms_max") != 300
        or performance.get(
            "must_not_be_combined_with_comparison_quality_change"
        )
        is not True
        or not isinstance(remote, dict)
        or any(remote.values())
    ):
        raise ValueError("phase 3 route coverage isolation boundary drifted")


def check_harness_links() -> None:
    for relative_path in ("AGENTS.md", "docs/HARNESS_ARCHITECTURE.md"):
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(text):
            if target.startswith(("http://", "https://", "#")):
                continue
            resolved = (ROOT / relative_path).parent / target.split("#", 1)[0]
            resolved = resolved.resolve()
            if not resolved.is_relative_to(ROOT.resolve()):
                raise ValueError(f"Harness link escapes repository in {relative_path}: {target}")
            if not resolved.exists():
                raise ValueError(f"broken Harness link in {relative_path}: {target}")


def check_harness_content_safety() -> None:
    paths = [ROOT / "AGENTS.md"]
    paths.extend((ROOT / "docs").glob("*.md"))
    paths.extend((ROOT / "machine").glob("*.json"))
    for path in paths:
        match = FORBIDDEN_TEXT.search(path.read_text(encoding="utf-8"))
        if match:
            raise ValueError(f"forbidden path or secret-shaped text in {path.relative_to(ROOT)}")


def check_tracked_artifact_boundary() -> None:
    tracked = _git("ls-files").splitlines()
    forbidden = [
        path
        for path in tracked
        if path.startswith("runtime/")
        or path.endswith(".pdf")
        or path == ".env"
        or path.startswith("data/")
        or path.startswith("storage/")
    ]
    if forbidden:
        raise ValueError(f"forbidden tracked artifacts: {', '.join(forbidden)}")


def check_clean_workspace() -> None:
    if _git("status", "--porcelain").strip():
        raise ValueError("workspace is not clean")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the repository Harness contract")
    parser.add_argument("--phase-result", type=Path)
    parser.add_argument("--require-clean", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    checks: list[tuple[str, Callable[[], None]]] = [
        ("required_files", check_required_files),
        ("project_state", check_project_state),
        ("feature_list", check_feature_list),
        ("phase_contract", check_phase_contract),
        ("current_phase", check_current_phase),
        ("phase_zero_scope_resource_slo", check_phase_zero_scope_resource_slo),
        ("phase3_entry_freeze", check_phase3_entry_freeze),
        ("phase3_comparison_dev_gate", check_phase3_comparison_dev_gate),
        ("phase3_comparison_report_intake", check_phase3_comparison_report_intake),
        (
            "phase3_comparison_route_coverage_gate",
            check_phase3_comparison_route_coverage_gate,
        ),
        ("harness_links", check_harness_links),
        ("content_safety", check_harness_content_safety),
        ("tracked_artifact_boundary", check_tracked_artifact_boundary),
    ]
    if args.phase_result is not None:
        phase_path = args.phase_result.resolve()
        checks.append(
            (
                "phase_result",
                lambda: validate_phase_result(
                    json.loads(phase_path.read_text(encoding="utf-8")),
                    require_concrete=True,
                ),
            )
        )
    if args.require_clean:
        checks.append(("clean_workspace", check_clean_workspace))

    failures: list[str] = []
    for name, check in checks:
        try:
            check()
            print(f"[PASS] {name}")
        except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            failures.append(name)
            print(f"[FAIL] {name}: {exc}")
    if failures:
        print(f"HARNESS_CONTRACT FAIL ({len(failures)} failed)")
        return 1
    print(f"HARNESS_CONTRACT PASS ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
