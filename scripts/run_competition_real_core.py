#!/usr/bin/env python3
"""Run Competition V1 through the existing isolated real Stage-1 assembly."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
if not sys.path or Path(sys.path[0]).resolve() != ROOT:
    sys.path.insert(0, str(ROOT))

from backend.validation.competition import (  # noqa: E402
    CompetitionCapture,
    SCENARIO_IDS,
    build_redacted_result,
    read_json,
    write_json,
)
from scripts.run_stage1_remote_canary import (  # noqa: E402
    AcademicQuestionCase,
    GenerationResult,
    main as run_stage1,
)


CONFIRMATION = "RUN_COMPETITION_REAL_CORE_V1"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
_COMMIT = re.compile(r"^[a-f0-9]{40}$")


def _runtime_path(path: Path, *, must_exist: bool = False) -> Path:
    if path.is_absolute() or not path.parts or path.parts[0] != "runtime" or ".." in path.parts:
        raise ValueError("competition paths must be repository-relative under runtime")
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to((ROOT / "runtime").resolve()):
        raise ValueError("competition path escapes runtime")
    if must_exist and not resolved.is_file():
        raise ValueError(f"competition runtime file is missing: {path.as_posix()}")
    return resolved


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _failed_result(
    *,
    run_id: str,
    source_commit: str,
    input_manifest: Mapping[str, object],
    stage1_report: Mapping[str, object],
    stage1_report_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": "competition_redacted_result_v1",
        "pack_id": "RAG_COMPETITION_EVIDENCE_AND_HANDOFF_PACK_V1",
        "pack_version": "v1",
        "status": "FAIL",
        "run_identity": {
            "run_id": run_id,
            "execution_boundary": "REAL_CORE_ATTEMPT_FAILED_CLOSED",
            "fixture_or_fake_used": False,
            "stable_error_code": stage1_report.get("error_code"),
        },
        "source_identity": {
            "source_commit": source_commit,
            "pdf_sha256": input_manifest.get("pdf_sha256"),
            "question_suite_sha256": input_manifest.get("question_suite_sha256"),
        },
        "scenarios": [
            {"scenario_id": scenario_id, "status": "FAIL", "proof_observed": False}
            for scenario_id in SCENARIO_IDS
        ],
        "cleanup": {
            "status": "UNKNOWN_REQUIRES_SAME_RUN_RESUME_OR_OPERATOR_AUDIT",
            "cleanup_jobs_succeeded": stage1_report.get("cleanup_jobs_succeeded"),
            "runtime_snapshot_cleanup_proven": stage1_report.get("runtime_snapshot_cleanup_proven"),
            "inactive_visibility_proven": stage1_report.get("inactive_visibility_proven"),
            "inactive_answer_api_status": stage1_report.get("inactive_answer_api_status"),
        },
        "privacy": {
            "runtime_only": True,
            "contains_pdf_bytes": False,
            "contains_database_url_or_secret": False,
            "contains_private_reasoning": False,
        },
        "hashes": {
            "stage1_private_report_sha256": stage1_report_sha256
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalized-manifest", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.confirm != CONFIRMATION or not _RUN_ID.fullmatch(args.run_id):
        print('{"status":"REFUSED","error_code":"COMPETITION_CONFIRMATION_OR_RUN_ID_INVALID"}', file=sys.stderr)
        return 2
    try:
        finalized_path = _runtime_path(args.finalized_manifest, must_exist=True)
        input_path = _runtime_path(args.input_manifest, must_exist=True)
        output_root = _runtime_path(args.output_directory)
        finalized = read_json(finalized_path)
        input_manifest = read_json(input_path)
        tracked_manifest = read_json(
            ROOT / "machine/competition/rag-competition-pack-v1.json"
        )
        source_commit = finalized.get("source_commit")
        source_value = source_commit.get("value") if isinstance(source_commit, dict) else None
        if not isinstance(source_value, str) or not _COMMIT.fullmatch(source_value):
            raise ValueError("finalized competition source commit is invalid")
        if source_value != _git_head():
            raise ValueError("finalized competition source commit does not equal HEAD")
        if finalized.get("status") != "READY_FOR_USER_REAL_REPRODUCTION_GATE":
            raise ValueError("competition manifest is not ready for the user Gate")
        for key, expected_value in tracked_manifest.items():
            if key != "source_commit" and finalized.get(key) != expected_value:
                raise ValueError(f"finalized competition manifest drifted at {key}")
        artifact_hashes = finalized.get("resolved_tracked_artifact_sha256")
        expected_artifacts = tracked_manifest.get("tracked_pack_artifacts")
        if (
            not isinstance(artifact_hashes, dict)
            or not isinstance(expected_artifacts, list)
            or set(artifact_hashes) != set(expected_artifacts)
        ):
            raise ValueError("finalized competition artifact hash set is invalid")
        for relative in expected_artifacts:
            path = (ROOT / str(relative)).resolve()
            if (
                not path.is_relative_to(ROOT.resolve())
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest()
                != artifact_hashes.get(relative)
            ):
                raise ValueError(f"finalized competition artifact drifted: {relative}")
        if input_manifest.get("pack_id") != finalized.get("pack_id"):
            raise ValueError("competition input pack identity mismatch")
        expected_bindings = {
            "COMP-QA-001": "local3.answerable.tracer.max_risk",
            "COMP-EVIDENCESET-001": "local3.answerable.tracer.ingredients",
        }
        if input_manifest.get("scenario_bindings") != expected_bindings:
            raise ValueError("competition input scenario bindings drifted")
        pdf_path = Path(str(input_manifest.get("pdf_path", "")))
        suite_path = Path(str(input_manifest.get("question_suite_path", "")))
        _runtime_path(pdf_path, must_exist=True)
        _runtime_path(suite_path, must_exist=True)
        suite_payload = read_json(ROOT / suite_path)
        cases = {
            value.get("case_id"): value
            for value in suite_payload.get("cases", [])
            if isinstance(value, dict)
        }
        for scenario_path_value in tracked_manifest["scenario_manifests"][:2]:
            scenario = read_json(ROOT / str(scenario_path_value))
            source_case_id = scenario["input_identity"]["source_case_id"]
            case = cases.get(source_case_id)
            question = case.get("question") if isinstance(case, dict) else None
            if (
                not isinstance(question, str)
                or hashlib.sha256(question.encode("utf-8")).hexdigest()
                != scenario["input_identity"]["question_sha256"]
            ):
                raise ValueError(
                    f"competition runtime question identity drifted: {scenario['scenario_id']}"
                )
        output_root.mkdir(parents=True, exist_ok=True)
        stage1_report_relative = (args.output_directory / "stage1-report.json").as_posix()
        captures: list[CompetitionCapture] = []

        def observe(
            case: AcademicQuestionCase,
            initial_payload: Mapping[str, object],
            replay_payload: Mapping[str, object] | None,
            generation_result: GenerationResult | None,
        ) -> None:
            captures.append(
                CompetitionCapture(
                    case_id=case.case_id,
                    question=case.question,
                    initial_payload=dict(initial_payload),
                    replay_payload=(dict(replay_payload) if replay_payload is not None else None),
                    generation_result=generation_result,
                )
            )

        generation = finalized["generation"]
        exit_code = run_stage1(
            [
                "--pdf", pdf_path.as_posix(),
                "--expected-sha256", str(input_manifest["pdf_sha256"]),
                "--run-id", args.run_id,
                "--confirm", "RUN_ISOLATED_STAGE1_CANARY",
                "--output", stage1_report_relative,
                "--pdf-object-root", (args.output_directory / "pdf-objects").as_posix(),
                "--es-index-prefix", "zhiyan-competition-canary",
                "--milvus-collection-prefix", "zhiyan_competition_canary",
                "--generation-model", str(generation["model"]),
                "--generation-model-digest", str(generation["model_digest"]),
                "--question-suite", suite_path.as_posix(),
                "--expected-question-suite-sha256", str(input_manifest["question_suite_sha256"]),
            ],
            result_observer=observe,
        )
        stage1_report = read_json(ROOT / stage1_report_relative)
        stage1_report_sha256 = hashlib.sha256(
            (ROOT / stage1_report_relative).read_bytes()
        ).hexdigest()
        if exit_code == 0 and stage1_report.get("status") == "PASS":
            redacted = build_redacted_result(
                finalized_manifest=finalized,
                input_manifest=input_manifest,
                run_id=args.run_id,
                captures=captures,
                stage1_report=stage1_report,
                stage1_report_sha256=stage1_report_sha256,
            )
        else:
            redacted = _failed_result(
                run_id=args.run_id,
                source_commit=source_value,
                input_manifest=input_manifest,
                stage1_report=stage1_report,
                stage1_report_sha256=stage1_report_sha256,
            )
        schema = read_json(ROOT / "contracts/schemas/competition-redacted-result-v1.schema.json")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(redacted)
        redacted_path = output_root / "redacted-results.json"
        write_json(redacted_path, redacted)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1
    summary = {
        "status": redacted["status"],
        "source_commit": source_value,
        "scenario_count": len(redacted["scenarios"]),
        "cleanup_status": redacted["cleanup"]["status"],
        "redacted_result": redacted_path.relative_to(ROOT).as_posix(),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if redacted["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
