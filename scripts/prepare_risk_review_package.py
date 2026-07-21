#!/usr/bin/env python3
"""Build one deduplicated human risk-review package for the assisted corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.formal_corpus import (
    AnnotationRecordV1,
    EvaluationItemV1,
    load_manifest_and_items,
    sha256_file,
)


RISK_REASON_ORDER = (
    "CONFLICTING_EVIDENCE_CONFIRMATION",
    "SECURITY_BOUNDARY_CONFIRMATION",
    "EXPERT_REVIEW",
    "ACCEPTANCE_CONFIRMATION",
    "NO_EVIDENCE_CONFIRMATION",
)
RISK_REASON_PRIORITY = {
    "CONFLICTING_EVIDENCE_CONFIRMATION": 0,
    "SECURITY_BOUNDARY_CONFIRMATION": 0,
    "EXPERT_REVIEW": 1,
    "ACCEPTANCE_CONFIRMATION": 1,
    "NO_EVIDENCE_CONFIRMATION": 2,
}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL value must be an object at {path}:{line_number}")
        values.append(value)
    return values


def load_generation_requests(batch_dir: Path) -> dict[str, dict[str, Any]]:
    requests: dict[str, dict[str, Any]] = {}
    for path in sorted(batch_dir.glob("batch-*.jsonl")):
        for value in _load_jsonl(path):
            if value.get("schema_version") != "assisted_question_generation_request_v1":
                raise ValueError(f"unsupported generation request schema in {path}")
            slot_id = value.get("slot", {}).get("slot_id")
            if not isinstance(slot_id, str) or not slot_id:
                raise ValueError(f"generation request has no slot id in {path}")
            if slot_id in requests:
                raise ValueError(f"duplicate generation request slot id: {slot_id}")
            requests[slot_id] = value
    if len(requests) != 500:
        raise ValueError(f"expected 500 generation requests, found {len(requests)}")
    return requests


def risk_reasons(item: EvaluationItemV1) -> list[str]:
    reasons: set[str] = set()
    if item.answerability == "CONFLICTING_EVIDENCE":
        reasons.add("CONFLICTING_EVIDENCE_CONFIRMATION")
    if item.answerability == "FORBIDDEN" or "adversarial_security" in item.question_types:
        reasons.add("SECURITY_BOUNDARY_CONFIRMATION")
    if item.difficulty == "hard" or "standards_freshness" in item.question_types:
        reasons.add("EXPERT_REVIEW")
    if item.split == "acceptance":
        reasons.add("ACCEPTANCE_CONFIRMATION")
    if item.answerability == "NO_EVIDENCE":
        reasons.add("NO_EVIDENCE_CONFIRMATION")
    return [reason for reason in RISK_REASON_ORDER if reason in reasons]


def _priority(reasons: list[str]) -> str:
    rank = min(RISK_REASON_PRIORITY[reason] for reason in reasons)
    return f"P{rank}"


def _labels_payload(item: EvaluationItemV1) -> dict[str, Any]:
    return {
        "answerability": item.answerability,
        "expected_route": item.expected_route,
        "chunk_judgments": [
            judgment.model_dump(mode="json") for judgment in item.chunk_judgments
        ],
    }


def _labels_sha256(item: EvaluationItemV1) -> str:
    payload = json.dumps(
        _labels_payload(item),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_review_entry(
    *,
    item: EvaluationItemV1,
    annotation: AnnotationRecordV1,
    request: dict[str, Any],
) -> dict[str, Any] | None:
    reasons = risk_reasons(item)
    if not reasons:
        return None
    if annotation.actor_type != "GPT" or annotation.role != "ANNOTATOR":
        raise ValueError(f"{item.question_id}: assisted proposal is not a GPT annotation")
    if annotation.question_id != item.question_id:
        raise ValueError(f"{item.question_id}: annotation question id does not match")
    if (
        annotation.answerability != item.answerability
        or annotation.expected_route != item.expected_route
        or annotation.chunk_judgments != item.chunk_judgments
    ):
        raise ValueError(f"{item.question_id}: GPT proposal does not match formal item")
    if request["slot"]["slot_id"] != item.question_id:
        raise ValueError(f"{item.question_id}: generation request does not match")
    evidence_by_id = {
        chunk["chunk_id"]: chunk for chunk in request.get("evidence_chunks", [])
    }
    for judgment in item.chunk_judgments:
        evidence = evidence_by_id.get(judgment.chunk_id)
        if evidence is None:
            raise ValueError(
                f"{item.question_id}: judgment chunk is absent from frozen evidence"
            )
        identity = (
            evidence["document_id"],
            evidence["page_start"],
            evidence["page_end"],
        )
        if identity != (
            judgment.document_id,
            judgment.page_start,
            judgment.page_end,
        ):
            raise ValueError(f"{item.question_id}: evidence metadata drift detected")
    return {
        "schema_version": "assisted_risk_review_item_v1",
        "review_id": f"review.{item.question_id}",
        "question_id": item.question_id,
        "priority": _priority(reasons),
        "review_reasons": reasons,
        "required_reviewer_mode": (
            "HUMAN_EXPERT" if "EXPERT_REVIEW" in reasons else "HUMAN_REVIEWER"
        ),
        "split": item.split,
        "blind_holdout": item.blind_holdout,
        "leakage_group_id": item.leakage_group_id,
        "question": item.question,
        "conversation_history": [
            turn.model_dump(mode="json") for turn in item.conversation_history
        ],
        "question_types": item.question_types,
        "language": item.language,
        "query_form": item.query_form,
        "difficulty": item.difficulty,
        "expected_filters": item.expected_filters.model_dump(mode="json"),
        "gpt_proposal": {
            "annotation_id": annotation.annotation_id,
            "model_identity": annotation.model_identity,
            "prompt_version": annotation.prompt_version,
            "temperature": annotation.temperature,
            **_labels_payload(item),
            "reference_claims": [
                claim.model_dump(mode="json") for claim in item.reference_claims
            ],
            "acceptable_answer_points": item.acceptable_answer_points,
            "must_not_claim": item.must_not_claim,
            "expected_citations": item.expected_citations,
            "labels_sha256": _labels_sha256(item),
        },
        "frozen_evidence_chunks": request.get("evidence_chunks", []),
        "review_checks": [
            "QUESTION_AND_SCOPE_MATCH",
            "ANSWERABILITY_IS_CORRECT",
            "RELEVANCE_0_TO_3_IS_CORRECT",
            "CLAIM_LINKS_ARE_SUPPORTED",
            "NO_UNSUPPORTED_OR_FORBIDDEN_CONTENT",
        ],
    }


def build_decision_template(entry: dict[str, Any]) -> dict[str, Any]:
    proposal = entry["gpt_proposal"]
    return {
        "schema_version": "assisted_risk_review_decision_v1",
        "review_id": entry["review_id"],
        "question_id": entry["question_id"],
        "review_reasons": entry["review_reasons"],
        "required_reviewer_mode": entry["required_reviewer_mode"],
        "proposal_labels_sha256": proposal["labels_sha256"],
        "review_outcome": "PENDING",
        "reviewer_id": "",
        "reviewed_at": None,
        "corrected_labels": {
            "answerability": proposal["answerability"],
            "expected_route": proposal["expected_route"],
            "chunk_judgments": proposal["chunk_judgments"],
        },
        "expert_confirmation": (
            "PENDING"
            if entry["required_reviewer_mode"] == "HUMAN_EXPERT"
            else "NOT_REQUIRED"
        ),
        "reviewer_notes": "",
    }


def _serialize_jsonl(values: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
        for value in values
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _readme(created_at: datetime, entry_count: int) -> bytes:
    text = f"""# 500 题风险驱动人工复核包 V1

创建时间：`{created_at.isoformat()}`

本包包含 {entry_count} 个去重风险题。不要把同一题因多个风险原因重复评审。

## 使用方式

1. `risk-review-queue-v1.jsonl` 是只读证据队列，每行一题；
2. 只编辑 `risk-review-decisions-v1.jsonl`；
3. `review_outcome` 只能填写 `APPROVE_AS_IS`、`EDIT_LABELS` 或 `REJECT_ITEM`；
4. `APPROVE_AS_IS` 保留预填标签；`EDIT_LABELS` 同步修改 `corrected_labels`；
5. 填写项目内假名 `reviewer_id`、带时区的 `reviewed_at` 和简短说明；
6. `HUMAN_EXPERT` 题必须由具备相应领域能力的人复核，并填写 `expert_confirmation=APPROVE` 或 `REJECT`；
7. Acceptance、冲突、无证据、越权和安全题不能只用第二次 GPT 调用代替人工。

## 结果边界

本包含私有题目和冻结 Chunk 文本，只能在授权范围内本地流转。填写完成后仍须通过导入器校验标签、Reviewer 身份、时间戳和谱系；不能直接手工把 Manifest 改成 `LOCKED`。
"""
    return text.encode("utf-8")


def _zip_datetime(created_at: datetime) -> tuple[int, int, int, int, int, int]:
    return (
        created_at.year,
        created_at.month,
        created_at.day,
        created_at.hour,
        created_at.minute,
        created_at.second,
    )


def _write_deterministic_zip(
    path: Path, files: dict[str, bytes], created_at: datetime
) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=_zip_datetime(created_at))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])


def prepare_review_package(
    *,
    manifest_path: Path,
    batch_dir: Path,
    output_dir: Path,
    created_at: datetime,
    expected_review_count: int = 213,
) -> dict[str, Any]:
    if created_at.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory is not empty; refusing to overwrite")
    manifest, items, annotations = load_manifest_and_items(manifest_path)
    if len(items) != 500 or len(annotations) != 500:
        raise ValueError("risk review package requires 500 items and 500 annotations")
    if manifest.status != "ANNOTATION":
        raise ValueError("risk review package requires manifest status ANNOTATION")
    annotation_by_id = {record.annotation_id: record for record in annotations}
    if len(annotation_by_id) != len(annotations):
        raise ValueError("annotation ids must be unique")
    requests = load_generation_requests(batch_dir)

    entries: list[dict[str, Any]] = []
    for item in items:
        if item.annotation_status != "GPT_ASSISTED":
            raise ValueError(f"{item.question_id}: item is not GPT_ASSISTED")
        if len(item.annotation_record_ids) != 1:
            raise ValueError(f"{item.question_id}: expected one GPT proposal")
        annotation = annotation_by_id.get(item.annotation_record_ids[0])
        if annotation is None:
            raise ValueError(f"{item.question_id}: GPT proposal is missing")
        request = requests.get(item.question_id)
        if request is None:
            raise ValueError(f"{item.question_id}: generation request is missing")
        entry = build_review_entry(
            item=item,
            annotation=annotation,
            request=request,
        )
        if entry is not None:
            entries.append(entry)
    entries.sort(
        key=lambda entry: (
            int(entry["priority"][1:]),
            entry["question_id"],
        )
    )
    if len(entries) != expected_review_count:
        raise ValueError(
            f"expected {expected_review_count} unique risk items, found {len(entries)}"
        )
    if len({entry["question_id"] for entry in entries}) != len(entries):
        raise ValueError("risk review package contains duplicate question ids")
    decisions = [build_decision_template(entry) for entry in entries]

    reason_counts = Counter(
        reason for entry in entries for reason in entry["review_reasons"]
    )
    priority_counts = Counter(entry["priority"] for entry in entries)
    reviewer_mode_counts = Counter(
        entry["required_reviewer_mode"] for entry in entries
    )
    split_counts = Counter(entry["split"] for entry in entries)
    low_risk_dev_test = [
        item
        for item in items
        if item.split in {"dev", "test"}
        and item.difficulty != "hard"
        and "standards_freshness" not in item.question_types
    ]
    low_risk_review_ids = {
        entry["question_id"]
        for entry in entries
        if entry["split"] in {"dev", "test"}
        and entry["difficulty"] != "hard"
        and "standards_freshness" not in entry["question_types"]
    }
    summary = {
        "schema_version": "assisted_risk_review_summary_v1",
        "dataset_id": manifest.dataset_id,
        "dataset_version": manifest.dataset_version,
        "created_at": created_at.isoformat(),
        "input_items_sha256": manifest.items_sha256,
        "input_annotations_sha256": manifest.annotation_records_sha256,
        "input_item_count": len(items),
        "input_annotation_count": len(annotations),
        "unique_review_item_count": len(entries),
        "reason_counts": dict(sorted(reason_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "reviewer_mode_counts": dict(sorted(reviewer_mode_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "low_risk_dev_test_count": len(low_risk_dev_test),
        "reviewed_low_risk_dev_test_count": len(low_risk_review_ids),
        "reviewed_low_risk_dev_test_ratio": round(
            len(low_risk_review_ids) / len(low_risk_dev_test), 6
        ),
        "decision_status": "ALL_PENDING",
    }
    queue_bytes = _serialize_jsonl(entries)
    decision_bytes = _serialize_jsonl(decisions)
    summary_bytes = (
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    readme_bytes = _readme(created_at, len(entries))
    package_files = {
        "README.md": readme_bytes,
        "risk-review-decisions-v1.jsonl": decision_bytes,
        "risk-review-queue-v1.jsonl": queue_bytes,
        "risk-review-summary.json": summary_bytes,
    }
    checksums = "".join(
        f"{_sha256_bytes(value)}  {name}\n"
        for name, value in sorted(package_files.items())
    ).encode("utf-8")
    package_files["SHA256SUMS"] = checksums

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in package_files.items():
        (output_dir / name).write_bytes(value)
    zip_path = output_dir / "risk-review-package-v1.zip"
    _write_deterministic_zip(zip_path, package_files, created_at)
    report = {
        **summary,
        "queue_sha256": _sha256_bytes(queue_bytes),
        "decisions_sha256": _sha256_bytes(decision_bytes),
        "zip_path": zip_path.name,
        "zip_sha256": sha256_file(zip_path),
        "zip_members": sorted(package_files),
        "status": "RISK_REVIEW_PACKAGE_READY_DECISIONS_0_OF_213",
    }
    (output_dir / "package-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--expected-review-count", type=int, default=213)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = prepare_review_package(
            manifest_path=args.manifest,
            batch_dir=args.batch_dir,
            output_dir=args.output_dir,
            created_at=datetime.fromisoformat(args.created_at),
            expected_review_count=args.expected_review_count,
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"risk review package error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "unique_review_item_count": report["unique_review_item_count"],
                "zip_sha256": report["zip_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
