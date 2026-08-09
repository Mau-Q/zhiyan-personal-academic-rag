#!/usr/bin/env python3
"""Select two frozen historical QA cases into an ignored Competition V1 input."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE_MANIFEST_SHA256 = "a8dee26281ee1c953d1024c2686fca28e0d0195855cdde81ed142e791618fd39"
EXPECTED_SOURCE_SUITE_SHA256 = "c16d1ed1cc2915d6b7b1ba61754e0f077d62923730d7d221a6854b20a5782af3"
EXPECTED_PDF_SHA256 = "3e7e4628ffadc9183e85341b3a88050c3b58a06dec02926c8f2028b55879d6ea"
CASE_BINDINGS = {
    "COMP-QA-001": (
        "local3.answerable.tracer.max_risk",
        "94bfb8a74abb2897ce3e58c04df2092a34b1de0244053a76a8276c5a11caf757",
    ),
    "COMP-EVIDENCESET-001": (
        "local3.answerable.tracer.ingredients",
        "0962f57f9558c2279e1505a1ba38452294584d7ba44f61f58a573e1ad9284955",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _runtime_path(path: Path) -> Path:
    if path.is_absolute() or not path.parts or path.parts[0] != "runtime" or ".." in path.parts:
        raise ValueError("competition source and output paths must be repository-relative under runtime")
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to((ROOT / "runtime").resolve()):
        raise ValueError("competition runtime path escapes runtime")
    return resolved


def prepare(source_package: Path, output_directory: Path) -> dict[str, Any]:
    source_root = _runtime_path(source_package)
    output_root = _runtime_path(output_directory)
    manifest_path = source_root / "manifest.json"
    if _sha256(manifest_path) != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise ValueError("historical package manifest identity mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("package_id") != "phase2-academic-qa-acceptance-v2":
        raise ValueError("historical package ID mismatch")
    document = next(
        (
            value
            for value in manifest.get("documents", [])
            if isinstance(value, dict)
            and value.get("pdf_sha256") == EXPECTED_PDF_SHA256
        ),
        None,
    )
    if document is None:
        raise ValueError("frozen competition document is absent")
    suite_path = source_root / str(document["suite_path"])
    pdf_path = source_root / str(document["pdf_path"])
    if _sha256(suite_path) != EXPECTED_SOURCE_SUITE_SHA256:
        raise ValueError("historical question suite identity mismatch")
    if _sha256(pdf_path) != EXPECTED_PDF_SHA256:
        raise ValueError("historical PDF identity mismatch")
    source_suite = json.loads(suite_path.read_text(encoding="utf-8"))
    by_id = {
        value["case_id"]: value
        for value in source_suite.get("cases", [])
        if isinstance(value, dict) and isinstance(value.get("case_id"), str)
    }
    selected = []
    for scenario_id in ("COMP-QA-001", "COMP-EVIDENCESET-001"):
        case_id, expected_question_sha256 = CASE_BINDINGS[scenario_id]
        case = by_id.get(case_id)
        if case is None or _sha256_text(str(case.get("question", ""))) != expected_question_sha256:
            raise ValueError(f"historical question identity mismatch for {scenario_id}")
        selected.append(case)
    suite = {
        "schema_version": "phase2_academic_qa_suite_v1",
        "suite_id": "competition-v1.tracer.qa-and-evidence-set",
        "pdf_sha256": EXPECTED_PDF_SHA256,
        "cases": selected,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    selected_suite_path = output_root / "question-suite.json"
    selected_suite_path.write_text(
        json.dumps(suite, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    input_manifest = {
        "schema_version": "competition_input_manifest_v1",
        "pack_id": "RAG_COMPETITION_EVIDENCE_AND_HANDOFF_PACK_V1",
        "source_package_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "pdf_path": pdf_path.relative_to(ROOT).as_posix(),
        "pdf_sha256": EXPECTED_PDF_SHA256,
        "question_suite_path": selected_suite_path.relative_to(ROOT).as_posix(),
        "question_suite_sha256": _sha256(selected_suite_path),
        "scenario_bindings": {
            scenario_id: CASE_BINDINGS[scenario_id][0]
            for scenario_id in CASE_BINDINGS
        },
        "contains_private_question_text": True,
        "tracked_or_public": False,
    }
    input_manifest_path = output_root / "input-manifest.json"
    input_manifest_path.write_text(
        json.dumps(input_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return input_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-package", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = prepare(args.source_package, args.output_directory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "input_manifest": (
                    args.output_directory / "input-manifest.json"
                ).as_posix(),
                "question_suite_sha256": payload["question_suite_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
