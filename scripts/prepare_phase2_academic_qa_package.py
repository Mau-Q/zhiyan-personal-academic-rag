#!/usr/bin/env python3
"""Build the private fixed-document Stage 2 academic-QA acceptance package."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.formal_corpus import sha256_file
from backend.evaluation.harness import EvaluationCaseV1, load_cases
from scripts.prepare_risk_review_package import (
    _sha256_bytes,
    _write_deterministic_zip,
)

POLICY_SCHEMA_VERSIONS = frozenset(
    {
        "phase2_academic_qa_acceptance_policy_v1",
        "phase2_academic_qa_acceptance_policy_v2",
    }
)
SUITE_SCHEMA_VERSION = "phase2_academic_qa_suite_v1"
MANIFEST_SCHEMA_VERSION = "phase2_academic_qa_package_manifest_v1"


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _load_policy(path: Path) -> dict[str, Any]:
    policy = _load_json(path)
    schema_version = policy.get("schema_version")
    if schema_version not in POLICY_SCHEMA_VERSIONS:
        raise ValueError("unsupported academic-QA acceptance policy schema")
    selection = policy.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("acceptance selection policy is missing")
    case_ids = selection.get("case_ids")
    required_count = selection.get("required_case_count")
    if (
        not isinstance(case_ids, list)
        or not all(isinstance(value, str) and value for value in case_ids)
        or len(case_ids) != len(set(case_ids))
        or required_count != len(case_ids)
    ):
        raise ValueError("acceptance case selection is not exact and unique")
    generation = policy.get("generation")
    if not isinstance(generation, dict) or generation.get("think") is not False:
        raise ValueError("acceptance generation must freeze think=false")
    retrieval = policy.get("retrieval")
    if not isinstance(retrieval, dict) or retrieval.get("parameters_changed") is not False:
        raise ValueError("acceptance retrieval parameters must remain unchanged")
    corrections = policy.get("location_corrections", [])
    if schema_version.endswith("_v1") and corrections:
        raise ValueError("v1 acceptance policy cannot contain location corrections")
    if schema_version.endswith("_v2") and not corrections:
        raise ValueError("v2 acceptance policy requires a location correction")
    _location_correction_map(corrections, selected_case_ids=set(case_ids))
    return policy


def _parse_pdf_arguments(values: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        document_id, separator, raw_path = value.partition("=")
        if not separator or not document_id or not raw_path or document_id in result:
            raise ValueError("--pdf must be a unique document_id=path mapping")
        result[document_id] = Path(raw_path)
    return result


def _page_ranges(value: object, *, field: str) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty page-range array")
    ranges: list[tuple[int, int]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{field} entry must be an object")
        page_start = item.get("page_start")
        page_end = item.get("page_end")
        if (
            not isinstance(page_start, int)
            or isinstance(page_start, bool)
            or not isinstance(page_end, int)
            or isinstance(page_end, bool)
            or page_start < 1
            or page_end < page_start
        ):
            raise ValueError(f"{field} contains an invalid page range")
        identity = (page_start, page_end)
        if identity in ranges:
            raise ValueError(f"{field} contains a duplicate page range")
        ranges.append(identity)
    return tuple(ranges)


def _serialize_page_ranges(values: Sequence[tuple[int, int]]) -> list[dict[str, int]]:
    return [
        {"page_start": page_start, "page_end": page_end}
        for page_start, page_end in values
    ]


def _location_correction_map(
    value: object,
    *,
    selected_case_ids: set[str],
) -> dict[str, dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError("location_corrections must be an array")
    result: dict[str, dict[str, object]] = {}
    for correction in value:
        if not isinstance(correction, dict):
            raise ValueError("location correction must be an object")
        case_id = correction.get("case_id")
        if (
            not isinstance(case_id, str)
            or case_id not in selected_case_ids
            or case_id in result
        ):
            raise ValueError("location correction Case ID is invalid or duplicated")
        if correction.get("basis") != "PDF_VISUAL_VERIFIED_MULTIPLE_VALID_LOCATIONS":
            raise ValueError("location correction basis is not allowlisted")
        source = _page_ranges(
            correction.get("source_page_ranges"),
            field=f"{case_id}.source_page_ranges",
        )
        accepted = _page_ranges(
            correction.get("accepted_page_ranges"),
            field=f"{case_id}.accepted_page_ranges",
        )
        if any(
            not any(
                accepted_start <= source_start and accepted_end >= source_end
                for accepted_start, accepted_end in accepted
            )
            for source_start, source_end in source
        ):
            raise ValueError("location correction cannot discard the frozen source range")
        result[case_id] = {
            "case_id": case_id,
            "basis": correction["basis"],
            "source_page_ranges": source,
            "accepted_page_ranges": accepted,
        }
    return result


def _required_page_ranges(
    case: EvaluationCaseV1,
    correction: Mapping[str, object] | None = None,
) -> list[dict[str, int]]:
    if case.category != "ANSWERABLE" or len(case.document_ids) != 1:
        raise ValueError(f"{case.case_id}: acceptance case must be single-document ANSWERABLE")
    targets = case.expected.required_evidence
    if not targets:
        raise ValueError(f"{case.case_id}: target page is required")
    document_id = case.document_ids[0]
    ranges = []
    seen: set[tuple[int, int]] = set()
    for target in targets:
        if target.document_id != document_id:
            raise ValueError(f"{case.case_id}: target document differs from request scope")
        identity = (target.page_start, target.page_end)
        if identity not in seen:
            seen.add(identity)
            ranges.append({"page_start": identity[0], "page_end": identity[1]})
    if correction is None:
        return ranges
    source = _serialize_page_ranges(correction["source_page_ranges"])
    if source != ranges:
        raise ValueError(f"{case.case_id}: location correction source range drift")
    return _serialize_page_ranges(correction["accepted_page_ranges"])


def _paper_map(path: Path) -> dict[str, dict[str, str]]:
    payload = _load_json(path)
    papers = payload.get("papers")
    if not isinstance(papers, list):
        raise ValueError("paper manifest has no papers")
    result: dict[str, dict[str, str]] = {}
    for paper in papers:
        if not isinstance(paper, dict):
            raise ValueError("paper manifest entry must be an object")
        document_id = paper.get("document_id")
        file_name = paper.get("file_name")
        digest = paper.get("sha256")
        if (
            not isinstance(document_id, str)
            or not isinstance(file_name, str)
            or Path(file_name).name != file_name
            or not isinstance(digest, str)
            or len(digest) != 64
            or document_id in result
        ):
            raise ValueError("paper manifest identity is invalid or duplicated")
        result[document_id] = {
            "file_name": file_name,
            "sha256": digest,
        }
    return result


def prepare_package(
    *,
    policy_path: Path,
    cases_path: Path,
    papers_path: Path,
    pdf_paths: Mapping[str, Path],
    output_dir: Path,
    created_at: datetime,
) -> dict[str, Any]:
    if created_at.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory is not empty; refusing to overwrite")
    policy = _load_policy(policy_path)
    if sha256_file(cases_path) != policy.get("source_cases_sha256"):
        raise ValueError("source academic-QA cases digest mismatch")
    if sha256_file(papers_path) != policy.get("source_papers_sha256"):
        raise ValueError("source paper manifest digest mismatch")

    all_cases = {case.case_id: case for case in load_cases(cases_path)}
    selected_ids = policy["selection"]["case_ids"]
    if any(case_id not in all_cases for case_id in selected_ids):
        raise ValueError("selected academic-QA case is missing")
    selected_cases = [all_cases[case_id] for case_id in selected_ids]
    corrections = _location_correction_map(
        policy.get("location_corrections", []),
        selected_case_ids=set(selected_ids),
    )
    papers = _paper_map(papers_path)
    grouped: dict[str, list[EvaluationCaseV1]] = defaultdict(list)
    for case in selected_cases:
        _required_page_ranges(case, corrections.get(case.case_id))
        grouped[case.document_ids[0]].append(case)
    expected_per_document = policy["selection"]["required_cases_per_document"]
    if not grouped or any(len(values) != expected_per_document for values in grouped.values()):
        raise ValueError("academic-QA cases per document do not match the frozen policy")
    if set(pdf_paths) != set(grouped):
        raise ValueError("PDF mappings must exactly cover selected documents")

    files: dict[str, bytes] = {}
    documents: list[dict[str, Any]] = []
    for document_id in sorted(grouped):
        paper = papers.get(document_id)
        if paper is None:
            raise ValueError(f"selected document is absent from paper manifest: {document_id}")
        pdf_path = pdf_paths[document_id]
        pdf_bytes = pdf_path.read_bytes()
        pdf_sha256 = sha256(pdf_bytes).hexdigest()
        if pdf_sha256 != paper["sha256"]:
            raise ValueError(f"PDF identity mismatch: {document_id}")
        suite = {
            "schema_version": SUITE_SCHEMA_VERSION,
            "suite_id": f"{policy['package_id']}.{document_id}",
            "pdf_sha256": pdf_sha256,
            "cases": [
                {
                    "case_id": case.case_id,
                    "question": case.question,
                    "required_page_ranges": _required_page_ranges(
                        case,
                        corrections.get(case.case_id),
                    ),
                }
                for case in grouped[document_id]
            ],
        }
        suite_name = f"suites/{document_id}.json"
        suite_bytes = _json_bytes(suite)
        pdf_name = f"papers/{paper['file_name']}"
        files[suite_name] = suite_bytes
        files[pdf_name] = pdf_bytes
        documents.append(
            {
                "document_id": document_id,
                "pdf_path": pdf_name,
                "pdf_sha256": pdf_sha256,
                "suite_path": suite_name,
                "suite_sha256": _sha256_bytes(suite_bytes),
                "case_ids": [case.case_id for case in grouped[document_id]],
                "case_count": len(grouped[document_id]),
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": "READY_FOR_USER_REMOTE_EXECUTION",
        "package_id": policy["package_id"],
        "created_at": created_at.isoformat(),
        "policy_sha256": sha256_file(policy_path),
        "source_cases_sha256": sha256_file(cases_path),
        "source_papers_sha256": sha256_file(papers_path),
        "case_count": len(selected_cases),
        "document_count": len(documents),
        "generation": policy["generation"],
        "retrieval": policy["retrieval"],
        "location_corrections": [
            {
                "case_id": correction["case_id"],
                "basis": correction["basis"],
                "source_page_ranges": _serialize_page_ranges(
                    correction["source_page_ranges"]
                ),
                "accepted_page_ranges": _serialize_page_ranges(
                    correction["accepted_page_ranges"]
                ),
            }
            for correction in corrections.values()
        ],
        "documents": documents,
        "privacy": policy["privacy"],
    }
    files["manifest.json"] = _json_bytes(manifest)
    files["SHA256SUMS"] = "".join(
        f"{_sha256_bytes(value)}  {name}\n" for name, value in sorted(files.items())
    ).encode("utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        target = output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    zip_path = output_dir / f"{policy['package_id']}.zip"
    _write_deterministic_zip(zip_path, files, created_at)
    report = {
        **manifest,
        "manifest_sha256": _sha256_bytes(files["manifest.json"]),
        "zip_sha256": sha256_file(zip_path),
        "zip_members": sorted(files),
    }
    (output_dir / "package-report.json").write_bytes(_json_bytes(report))
    return report


def _runtime_output(path: Path) -> Path:
    if path.is_absolute() or not path.parts or path.parts[0] != "runtime" or ".." in path.parts:
        raise ValueError("private package output must be under runtime/")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--papers", type=Path, required=True)
    parser.add_argument("--pdf", action="append", default=[], required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--created-at", required=True)
    args = parser.parse_args()
    try:
        report = prepare_package(
            policy_path=args.policy,
            cases_path=args.cases,
            papers_path=args.papers,
            pdf_paths=_parse_pdf_arguments(args.pdf),
            output_dir=_runtime_output(args.output_dir),
            created_at=datetime.fromisoformat(args.created_at),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Phase 2 academic-QA package error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
