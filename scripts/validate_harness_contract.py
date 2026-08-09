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
    "machine/project_state.json",
    "machine/feature_list.json",
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
FEATURE_OWNERS = {"A", "SHARED", "USER"}
CURRENT_PHASE_STATUSES = {"READY", "IN_PROGRESS", "BLOCKED", "COMPLETE"}
SOURCE_PHASE_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "PARTIAL", "COMPLETE"}
BUSINESS_GATE_LIFECYCLE_TOKENS = {
    "BLOCKED",
    "COMPLETE",
    "COMPLETED",
    "FAIL",
    "FAILED",
    "FAILURE",
    "FROZEN",
    "IN_PROGRESS",
    "NOT_STARTED",
    "PASS",
    "PENDING",
    "READY",
    "REJECTED",
}
PROJECT_STATE_FIELDS = {
    "schema_version",
    "project_id",
    "repository",
    "default_branch",
    "visibility",
    "source_authority",
    "current_phase",
    "repository_harness",
    "git_policy",
    "execution_boundaries",
}
GIT_POLICY_FIELDS = {
    "member_a_low_risk",
    "remote_operations",
    "high_risk",
    "ci_mode",
    "history_repair",
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
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LOWER_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
PHASE_IDENTIFIER = re.compile(r"^phase-[0-9]+$")
SCHEMA_VERSION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*_v[1-9][0-9]*$")
UPPER_STATUS_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")


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


def _tracked_paths() -> set[str]:
    return set(_git("ls-files").splitlines())


def _repository_file(
    relative_path: Any,
    *,
    context: str,
    tracked: set[str],
) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError(f"{context} must be a non-empty repository path")
    path = Path(relative_path)
    if path.is_absolute():
        raise ValueError(f"{context} must be repository-relative: {relative_path}")
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise ValueError(f"{context} escapes repository: {relative_path}")
    normalized = path.as_posix()
    if normalized != relative_path or not resolved.is_file():
        raise ValueError(f"{context} path is invalid: {relative_path}")
    if normalized not in tracked:
        raise ValueError(f"{context} is not Git tracked: {relative_path}")
    return resolved


def _validate_upper_status(
    value: Any, *, context: str, max_length: int = 240
) -> str:
    if (
        not isinstance(value, str)
        or len(value) > max_length
        or UPPER_STATUS_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(f"{context} must use the uppercase status vocabulary")
    return value


def validate_business_gate_record(payload: Any, *, relative_path: str) -> None:
    """Validate the common gate envelope without interpreting its outcome."""

    if not isinstance(payload, dict):
        raise ValueError(f"business gate record must be an object: {relative_path}")
    schema_version = payload.get("schema_version")
    expected_prefix = f"{Path(relative_path).stem}_v"
    if (
        not isinstance(schema_version, str)
        or SCHEMA_VERSION_PATTERN.fullmatch(schema_version) is None
        or not schema_version.startswith(expected_prefix)
    ):
        raise ValueError(f"business gate schema_version is invalid: {relative_path}")
    status = _validate_upper_status(
        payload.get("status"), context=f"business gate {relative_path} status"
    )
    if not any(
        status == token
        or status.startswith(f"{token}_")
        or status.endswith(f"_{token}")
        or f"_{token}_" in status
        for token in BUSINESS_GATE_LIFECYCLE_TOKENS
    ):
        raise ValueError(
            f"business gate {relative_path} status lacks a legal lifecycle token"
        )
    decision_ids: list[Any] = []
    if "decision_id" in payload:
        decision_ids.append(payload["decision_id"])
    if "decision_ids" in payload:
        values = payload["decision_ids"]
        if not isinstance(values, list) or not values:
            raise ValueError(f"business gate {relative_path} decision_ids is invalid")
        decision_ids.extend(values)
    if any(
        not isinstance(decision_id, str)
        or re.fullmatch(r"PD-[0-9]+", decision_id) is None
        for decision_id in decision_ids
    ):
        raise ValueError(f"business gate {relative_path} decision identity is invalid")
    source_phase = payload.get("source_phase")
    if source_phase is not None and (
        not isinstance(source_phase, dict)
        or set(source_phase) != {"id", "status"}
        or not isinstance(source_phase.get("id"), str)
        or PHASE_IDENTIFIER.fullmatch(source_phase["id"]) is None
        or source_phase.get("status") not in SOURCE_PHASE_STATUSES
    ):
        raise ValueError(f"business gate {relative_path} source_phase is invalid")


def check_project_state() -> None:
    state = _read_json("machine/project_state.json")
    tracked = _tracked_paths()
    if not isinstance(state, dict) or set(state) != PROJECT_STATE_FIELDS:
        raise ValueError("project_state fields do not match project_state_v1")
    if state.get("schema_version") != "project_state_v1":
        raise ValueError("project_state schema_version must be project_state_v1")
    if state.get("project_id") != "zhiyan-personal-academic-rag":
        raise ValueError("project_state project_id is invalid")
    if (
        not isinstance(state.get("repository"), str)
        or not state["repository"]
        or state.get("default_branch") != "main"
        or state.get("visibility") not in {"PRIVATE", "PUBLIC"}
    ):
        raise ValueError("project_state repository identity is invalid")
    current_phase = state.get("current_phase")
    source_authority = state.get("source_authority")
    harness = state.get("repository_harness")
    git_policy = state.get("git_policy")
    if (
        not isinstance(current_phase, dict)
        or set(current_phase) != {"id", "status", "authority_doc"}
        or not isinstance(current_phase.get("id"), str)
        or not current_phase["id"]
        or current_phase.get("status") not in CURRENT_PHASE_STATUSES
    ):
        raise ValueError("project_state current_phase is invalid")
    if not isinstance(source_authority, dict) or set(source_authority) != {
        "title",
        "sha256",
        "line_count",
        "traceability_doc",
        "source_phase",
        "completed_source_phases",
    }:
        raise ValueError("project_state source_authority shape is invalid")
    if (
        not isinstance(source_authority.get("title"), str)
        or not source_authority["title"]
        or not isinstance(source_authority.get("sha256"), str)
        or SHA256_PATTERN.fullmatch(source_authority["sha256"]) is None
        or not isinstance(source_authority.get("line_count"), int)
        or source_authority["line_count"] <= 0
    ):
        raise ValueError("project_state source_authority identity is invalid")
    source_phase = source_authority.get("source_phase")
    completed_source_phases = source_authority.get("completed_source_phases")
    if (
        not isinstance(source_phase, dict)
        or set(source_phase) != {"id", "status"}
        or not isinstance(source_phase.get("id"), str)
        or PHASE_IDENTIFIER.fullmatch(source_phase["id"]) is None
        or source_phase.get("status") not in SOURCE_PHASE_STATUSES
        or not isinstance(completed_source_phases, list)
        or len(completed_source_phases) != len(set(completed_source_phases))
        or any(
            not isinstance(phase_id, str)
            or PHASE_IDENTIFIER.fullmatch(phase_id) is None
            for phase_id in completed_source_phases
        )
        or source_phase["id"] in completed_source_phases
    ):
        raise ValueError("project_state source phase pointers are invalid")
    if (
        not isinstance(harness, dict)
        or set(harness) != {"status", "entrypoint", "validator", "feature_list"}
        or harness.get("status") != "READY"
    ):
        raise ValueError("project_state repository_harness is invalid")
    if not isinstance(git_policy, dict) or set(git_policy) != GIT_POLICY_FIELDS:
        raise ValueError("project_state git_policy is invalid")
    for key, value in git_policy.items():
        _validate_upper_status(value, context=f"project_state git_policy.{key}")
    execution_boundaries = state.get("execution_boundaries")
    if not isinstance(execution_boundaries, dict) or not execution_boundaries:
        raise ValueError("project_state execution_boundaries must be a non-empty object")
    for key, value in execution_boundaries.items():
        if not isinstance(key, str) or LOWER_IDENTIFIER.fullmatch(key) is None:
            raise ValueError(f"project_state execution boundary key is invalid: {key}")
        _validate_upper_status(
            value,
            context=f"project_state execution_boundaries.{key}",
            max_length=2000,
        )
    current_phase_path = _repository_file(
        current_phase.get("authority_doc"),
        context="project_state current_phase.authority_doc",
        tracked=tracked,
    )
    current_phase_text = current_phase_path.read_text(encoding="utf-8")
    if current_phase.get("id") not in current_phase_text:
        raise ValueError("project_state current phase id is missing from CURRENT_PHASE")
    for key in ("entrypoint", "validator", "feature_list"):
        _repository_file(
            harness.get(key),
            context=f"project_state repository_harness.{key}",
            tracked=tracked,
        )
    traceability = _repository_file(
        source_authority["traceability_doc"],
        context="project_state source_authority.traceability_doc",
        tracked=tracked,
    )
    traceability_text = traceability.read_text(encoding="utf-8")
    for expected in (
        source_authority["title"],
        source_authority["sha256"],
        f"`{source_authority['line_count']}`",
    ):
        if expected not in traceability_text:
            raise ValueError(f"source authority identity missing from traceability: {expected}")


def check_feature_list() -> None:
    payload = _read_json("machine/feature_list.json")
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "features"}:
        raise ValueError("feature_list fields do not match feature_list_v2")
    if payload.get("schema_version") != "feature_list_v2":
        raise ValueError("feature_list schema_version must be feature_list_v2")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("feature_list features must be a non-empty array")
    tracked = _tracked_paths()
    seen: set[str] = set()
    status_by_id: dict[str, str] = {}
    for feature in features:
        if not isinstance(feature, dict) or not {"id", "status", "owner", "evidence"}.issubset(
            feature
        ):
            raise ValueError("feature_list entries must be objects")
        unknown_fields = set(feature) - {
            "id",
            "status",
            "owner",
            "evidence",
            "gate_records",
        }
        if unknown_fields:
            raise ValueError(
                f"feature_list entry has unsupported fields: {', '.join(sorted(unknown_fields))}"
            )
        feature_id = feature.get("id")
        if (
            not isinstance(feature_id, str)
            or LOWER_IDENTIFIER.fullmatch(feature_id) is None
            or feature_id in seen
        ):
            raise ValueError(f"invalid or duplicate feature id: {feature_id}")
        seen.add(feature_id)
        if feature.get("status") not in FEATURE_STATUSES:
            raise ValueError(f"invalid feature status for {feature_id}")
        if feature.get("owner") not in FEATURE_OWNERS:
            raise ValueError(f"invalid feature owner for {feature_id}")
        status_by_id[feature_id] = feature["status"]
        evidence = feature.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or len(evidence) != len(set(evidence))
        ):
            raise ValueError(f"feature {feature_id} must have evidence paths")
        for relative_path in evidence:
            _repository_file(
                relative_path,
                context=f"feature {feature_id} evidence",
                tracked=tracked,
            )
        detected_gate_records: list[str] = []
        for relative_path in evidence:
            if (
                relative_path.startswith("machine/")
                and relative_path.endswith(".json")
                and relative_path
                not in {
                    "machine/project_state.json",
                    "machine/feature_list.json",
                    "machine/phase_result.schema.json",
                    "machine/phase_result.template.json",
                }
            ):
                candidate = _read_json(relative_path)
                if isinstance(candidate, dict) and {
                    "schema_version",
                    "status",
                }.issubset(candidate):
                    detected_gate_records.append(relative_path)
        gate_records = feature.get("gate_records", [])
        if (
            not isinstance(gate_records, list)
            or len(gate_records) != len(set(gate_records))
            or set(gate_records) != set(detected_gate_records)
        ):
            raise ValueError(
                f"feature {feature_id} gate_records must identify every business gate evidence record"
            )
        for relative_path in gate_records:
            validate_business_gate_record(
                _read_json(relative_path), relative_path=relative_path
            )
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


def check_current_product_scope() -> None:
    payload = _read_json("machine/phase_zero_scope_resource_slo.json")
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
        raise ValueError("current corpus capacity targets drifted")
    if scope.get("user_model") != "SINGLE_AUTHENTICATED_OWNER":
        raise ValueError("current user model must remain single owner")
    if scope.get("knowledge_sources") != [
        "USER_UPLOADED_PAPER",
        "PUBLIC_PAPER_COLLECTED_INTO_PERSONAL_LIBRARY",
    ]:
        raise ValueError("current knowledge sources drifted")
    if scope.get("excluded_from_mvp") != [
        "PUBLIC_LIBRARY_FEDERATED_SEARCH",
        "RESEARCH_GROUP_SHARED_LIBRARY",
        "CROSS_OWNER_RETRIEVAL",
    ]:
        raise ValueError("current excluded scope drifted")

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
        raise ValueError("current traffic targets drifted")

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
        raise ValueError("current hardware budget drifted")

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
        raise ValueError("current SLO targets drifted")


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
        ("current_product_scope", check_current_product_scope),
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
