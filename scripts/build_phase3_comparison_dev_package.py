#!/usr/bin/env python3
"""Build the private, dev-only input package for the Phase 3 paired online Gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if not sys.path or Path(sys.path[0]).resolve() != REPOSITORY_ROOT:
    sys.path.insert(0, str(REPOSITORY_ROOT))


SCHEMA_VERSION = "phase3_comparison_dev_input_manifest_v1"
TARGET_IDS = (
    "local3.assisted.0033",
    "local3.assisted.0304",
    "local3.assisted.0383",
    "local3.assisted.0387",
)
TARGET_IDS_SHA256 = (
    "3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8"
)
DEFAULT_OUTPUT = Path(
    "runtime/handoffs/phase3-comparison-paired-dev-input-v1.zip"
)
ASSETS = {
    "dev-review.jsonl": {
        "source": Path(
            "runtime/handoffs/member-b-phase2-4-dev-review-input-v1/"
            "dev-claim-evidence-review-input-v1.jsonl"
        ),
        "sha256": "13b7ddfb0185ba03f251664366d5ab28a0cae64adda9ef9a57da563be0ae2c6e",
        "count": 105,
    },
    "frozen-chunks.json": {
        "source": Path(
            "runtime/evaluation/mvp-175-remote-baseline-input-v1/chunks-v1.json"
        ),
        "sha256": "f7eb7e4a6c7820abde5523dca906df1d1a052e2e3b2174887781531295c7a282",
        "count": 316,
    },
    "fixed-15-canary.jsonl": {
        "source": Path(
            "runtime/evaluation/local-3-paper-v1/local-3-paper-v1.jsonl"
        ),
        "sha256": "a01ddcff397b9e2676c8545217261a09f48387ba16a9290146de76e57fbba89f",
        "count": 15,
    },
    "papers/doc_arxiv_2601_03260.pdf": {
        "sha256": "d509e0891cedd235251940fa57880bd31721e08a22379d922cddd534f62dce70",
    },
    "papers/doc_arxiv_2602_11409.pdf": {
        "sha256": "3e7e4628ffadc9183e85341b3a88050c3b58a06dec02926c8f2028b55879d6ea",
    },
    "papers/doc_arxiv_2603_04915.pdf": {
        "sha256": "ff3b39d94690de98cff09998c669b20333861d43b797ea000af812bc7f524dcf",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_output(path: Path) -> None:
    if path.is_absolute() or not path.parts or path.parts[0] != "runtime":
        raise ValueError("output must be a relative path under runtime")
    if ".." in path.parts or path.suffix.lower() != ".zip":
        raise ValueError("output must be a safe ZIP path under runtime")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    values = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not all(isinstance(value, dict) for value in values):
        raise ValueError(f"{path} contains a non-object JSONL row")
    return values


def _source_map(paper_sources: Mapping[str, Path]) -> dict[str, Path]:
    expected_papers = {
        path for path in ASSETS if path.startswith("papers/")
    }
    if set(paper_sources) != expected_papers:
        raise ValueError("exactly three frozen paper source paths are required")
    return {
        package_path: (
            paper_sources[package_path]
            if package_path in paper_sources
            else identity["source"]
        )
        for package_path, identity in ASSETS.items()
    }


def validate_sources(paper_sources: Mapping[str, Path]) -> tuple[dict[str, Any], dict[str, Path]]:
    sources = _source_map(paper_sources)
    artifacts: list[dict[str, Any]] = []
    for package_path, identity in ASSETS.items():
        source = sources[package_path]
        if not source.is_file() or _sha256(source) != identity["sha256"]:
            raise ValueError(f"private source identity drifted: {package_path}")
        artifact = {
            "path": package_path,
            "sha256": identity["sha256"],
            "size_bytes": source.stat().st_size,
        }
        if "count" in identity:
            artifact["record_count"] = identity["count"]
        artifacts.append(artifact)

    dev_rows = _jsonl(sources["dev-review.jsonl"])
    if len(dev_rows) != 105 or {row.get("split") for row in dev_rows} != {"dev"}:
        raise ValueError("dev review input must contain exactly 105 dev-only rows")
    if {row.get("question_id") for row in dev_rows if row.get("question_id") in TARGET_IDS} != set(
        TARGET_IDS
    ):
        raise ValueError("frozen target cases are incomplete")
    chunks = json.loads(sources["frozen-chunks.json"].read_text(encoding="utf-8"))
    if (
        not isinstance(chunks, list)
        or len(chunks) != 316
        or len({chunk.get("chunk_id") for chunk in chunks}) != 316
    ):
        raise ValueError("frozen Chunk input identity is invalid")
    canary = _jsonl(sources["fixed-15-canary.jsonl"])
    if len(canary) != 15:
        raise ValueError("fixed Canary must contain exactly 15 cases")
    categories = {category: 0 for category in ("ANSWERABLE", "NO_EVIDENCE", "FORBIDDEN")}
    for case in canary:
        category = case.get("category")
        if category not in categories:
            raise ValueError("fixed Canary category is invalid")
        categories[category] += 1
    if categories != {"ANSWERABLE": 9, "NO_EVIDENCE": 3, "FORBIDDEN": 3}:
        raise ValueError("fixed Canary category counts drifted")
    return {
        "schema_version": SCHEMA_VERSION,
        "split_boundary": "DEV_ONLY_TEST_AND_ACCEPTANCE_EXCLUDED",
        "strategy": "section_parent_child_v1",
        "target_question_ids": list(TARGET_IDS),
        "target_ids_sha256": TARGET_IDS_SHA256,
        "counts": {
            "dev_review_rows": 105,
            "frozen_chunks": 316,
            "fixed_canary": categories,
            "papers": 3,
        },
        "artifacts": artifacts,
    }, sources


def build_package(output: Path, *, paper_sources: Mapping[str, Path]) -> dict[str, Any]:
    _validate_output(output)
    manifest, sources = validate_sources(paper_sources)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    timestamp = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("manifest.json", timestamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, manifest_bytes)
        for package_path in ASSETS:
            info = zipfile.ZipInfo(package_path, timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, sources[package_path].read_bytes())
    return {
        "status": "PASS",
        "schema_version": SCHEMA_VERSION,
        "output": output.as_posix(),
        "package_sha256": _sha256(output),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "split_boundary": manifest["split_boundary"],
        "artifact_count": len(manifest["artifacts"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--paper-2601", type=Path, required=True)
    parser.add_argument("--paper-2602", type=Path, required=True)
    parser.add_argument("--paper-2603", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_package(
            args.output,
            paper_sources={
                "papers/doc_arxiv_2601_03260.pdf": args.paper_2601,
                "papers/doc_arxiv_2602_11409.pdf": args.paper_2602,
                "papers/doc_arxiv_2603_04915.pdf": args.paper_2603,
            },
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "status": "REFUSED",
                    "error_code": "PHASE3_DEV_PACKAGE_INVALID",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
