#!/usr/bin/env python3
"""Read-only, standard-library validation for the repository Harness."""

from __future__ import annotations

import argparse
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
    "machine/project_state.json",
    "machine/feature_list.json",
    "machine/phase_zero_scope_resource_slo.json",
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
        "source_phase": {"id": "phase-3", "status": "NOT_STARTED"},
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
        "方案阶段 3 NOT_STARTED",
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
