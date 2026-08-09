#!/usr/bin/env python3
"""Validate Competition Pack V1 and resolve its exact runtime source commit."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.validation.competition import lf_canonical_text_sha256  # noqa: E402


MANIFEST = ROOT / "machine/competition/rag-competition-pack-v1.json"
PACK_SCHEMA = ROOT / "contracts/schemas/competition-pack-v1.schema.json"
SCENARIO_SCHEMA = ROOT / "contracts/schemas/competition-scenario-v1.schema.json"
SCENARIO_DIRECTORY = ROOT / "machine/competition/scenarios"
EXPECTED_SCENARIO_IDS = (
    "COMP-QA-001",
    "COMP-EVIDENCESET-001",
    "COMP-FAIL-CLOSED-001",
)
_COMMIT = re.compile(r"^[a-f0-9]{40}$")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository_path(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or path.as_posix() != relative or ".." in path.parts:
        raise ValueError(f"invalid repository path: {relative}")
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT.resolve()) or not resolved.is_file():
        raise ValueError(f"missing pack artifact: {relative}")
    return resolved


def validate_static() -> dict[str, Any]:
    pack_schema = _read_json(PACK_SCHEMA)
    scenario_schema = _read_json(SCENARIO_SCHEMA)
    Draft202012Validator.check_schema(pack_schema)
    Draft202012Validator.check_schema(scenario_schema)
    manifest = _read_json(MANIFEST)
    Draft202012Validator(pack_schema).validate(manifest)
    if tuple(manifest["scenario_ids"]) != EXPECTED_SCENARIO_IDS:
        raise ValueError("competition pack must list exactly the three frozen scenario IDs")
    scenario_paths = [ROOT / value for value in manifest["scenario_manifests"]]
    directory_paths = sorted(SCENARIO_DIRECTORY.glob("*.json"))
    if sorted(scenario_paths) != directory_paths or len(directory_paths) != 3:
        raise ValueError("competition scenario directory must contain exactly three manifests")
    observed_ids = []
    scenarios_by_id: dict[str, dict[str, Any]] = {}
    for path in scenario_paths:
        payload = _read_json(path)
        Draft202012Validator(scenario_schema).validate(payload)
        observed_ids.append(payload["scenario_id"])
        scenarios_by_id[payload["scenario_id"]] = payload
    if tuple(observed_ids) != EXPECTED_SCENARIO_IDS:
        raise ValueError("competition scenario manifest order or identity drifted")
    artifact_hashes = {
        relative: lf_canonical_text_sha256(_repository_path(relative))
        for relative in manifest["tracked_pack_artifacts"]
    }
    if manifest["retrieval"] != {
        "backend": "POSTGRES_READY_ES_MILVUS_RANK_ONLY_RRF",
        "candidate_k": 20,
        "rrf_k": 60,
        "top_k": 3,
    }:
        raise ValueError("competition retrieval identity drifted")
    if manifest["reranker"]["default"] != "OFF":
        raise ValueError("competition default Reranker must remain OFF")
    if manifest["evidence_set"]["mode"] != "AUDIT_ONLY":
        raise ValueError("competition EvidenceSet mode must remain AUDIT_ONLY")
    if manifest["tracked_text_identity"] != {
        "mode": "LF_CANONICAL_UTF8_TEXT",
        "accepted_line_endings": ["LF", "CRLF_EQUIVALENT"],
        "rejected": [
            "UTF8_BOM",
            "LONE_CARRIAGE_RETURN",
            "INVALID_UTF8",
            "CONTENT_DRIFT",
        ],
    }:
        raise ValueError("competition tracked text identity contract drifted")
    if manifest["source_commit"]["value"] is not None:
        raise ValueError("tracked competition manifest must not fabricate a source commit")
    if (
        manifest["generation"]["prompt_sha256"]
        != "796bf2fad94a92584d604479fb921bd98e72e4b97ecc09d6e49eaa2c0c71df71"
        or manifest["generation"]["thinking"] is not False
    ):
        raise ValueError("competition generation Prompt or thinking identity drifted")
    for scenario_id in EXPECTED_SCENARIO_IDS[:2]:
        question = scenarios_by_id[scenario_id]["question"]
        if question.get("tracked_text") is not False or "text" in question:
            raise ValueError("historical competition question text must remain runtime-only")
    historical = {value["id"]: value for value in manifest["historical_real_gates"]}
    phase4 = historical["phase4-multi-evidence-set"]
    if (
        lf_canonical_text_sha256(_repository_path(phase4["reference"]))
        != phase4["reference_sha256"]
    ):
        raise ValueError("historical EvidenceSet gate reference drifted")
    return {"manifest": manifest, "artifact_hashes": artifact_hashes}


def finalize(*, expected_head: str, output: Path) -> dict[str, Any]:
    if not _COMMIT.fullmatch(expected_head):
        raise ValueError("expected HEAD must be a full lowercase Git commit")
    if output.is_absolute() or not output.parts or output.parts[0] != "runtime":
        raise ValueError("finalized manifest output must be under runtime")
    head = _git("rev-parse", "HEAD")
    if head != expected_head:
        raise ValueError("current HEAD does not match the expected competition commit")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("tracked worktree must be clean before competition finalization")
    validated = validate_static()
    finalized = json.loads(json.dumps(validated["manifest"], ensure_ascii=False))
    finalized["status"] = "READY_FOR_USER_REAL_REPRODUCTION_GATE"
    finalized["source_commit"] = {
        "binding_mode": "EXACT_GIT_HEAD",
        "value": head,
        "requires_clean_worktree": True,
    }
    finalized["resolved_tracked_artifact_sha256"] = validated["artifact_hashes"]
    output_path = (ROOT / output).resolve()
    if not output_path.is_relative_to((ROOT / "runtime").resolve()):
        raise ValueError("finalized manifest output escapes runtime")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(finalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return finalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if bool(args.expected_head) != bool(args.output):
            raise ValueError("--expected-head and --output must be provided together")
        if args.expected_head:
            payload = finalize(expected_head=args.expected_head, output=args.output)
            result = {
                "status": "PASS",
                "mode": "FINALIZED_EXACT_HEAD",
                "source_commit": payload["source_commit"]["value"],
                "output": args.output.as_posix(),
            }
        else:
            validated = validate_static()
            result = {
                "status": "PASS",
                "mode": "STATIC_PRECOMMIT",
                "scenario_count": len(validated["manifest"]["scenario_ids"]),
                "artifact_count": len(validated["artifact_hashes"]),
            }
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
