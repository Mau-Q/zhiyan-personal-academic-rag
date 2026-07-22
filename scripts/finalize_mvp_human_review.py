#!/usr/bin/env python3
"""Validate AI pre-review decisions and record explicit human sign-off."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.formal_corpus import (
    EvaluationItemV1,
    load_manifest_and_items,
    sha256_file,
)
from scripts.prepare_risk_review_package import _serialize_jsonl, _sha256_bytes

EXPECTED_COUNT = 175
OUTCOMES = {"APPROVE_AS_IS", "EDIT_LABELS"}
CHECK_RESULTS = {"PASS", "FAIL"}
AI_NOTE_SUFFIXES = (
    " AI 独立预审意见，不构成人工签署。",
    "AI 独立预审意见，不构成人工签署。",
)


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


def _proposal_labels(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in entry["proposal"].items()
        if key != "labels_sha256"
    }


def validate_pre_review_decision(
    decision: dict[str, Any],
    *,
    queue_entry: dict[str, Any],
    source_item: EvaluationItemV1,
) -> None:
    question_id = queue_entry["question_id"]
    if decision.get("schema_version") != "mvp_initial_review_decision_v1":
        raise ValueError(f"{question_id}: unsupported decision schema")
    if decision.get("question_id") != question_id:
        raise ValueError(f"{question_id}: decision question id drift")
    if decision.get("review_id") != queue_entry["review_id"]:
        raise ValueError(f"{question_id}: decision review id drift")
    if decision.get("proposal_labels_sha256") != queue_entry["proposal"]["labels_sha256"]:
        raise ValueError(f"{question_id}: proposal hash drift")
    outcome = decision.get("review_outcome")
    if outcome not in OUTCOMES:
        raise ValueError(f"{question_id}: review outcome must be complete and non-rejected")
    checks = decision.get("review_checks")
    if not isinstance(checks, dict) or set(checks) != set(queue_entry["review_checks"]):
        raise ValueError(f"{question_id}: review check identity drift")
    if set(checks.values()) - CHECK_RESULTS:
        raise ValueError(f"{question_id}: review checks must not contain PENDING")
    corrected = decision.get("corrected_labels")
    proposal = _proposal_labels(queue_entry)
    if outcome == "APPROVE_AS_IS":
        if corrected != proposal:
            raise ValueError(f"{question_id}: approved labels differ from proposal")
        if "FAIL" in checks.values():
            raise ValueError(f"{question_id}: approved decision contains failed checks")
    if outcome == "EDIT_LABELS":
        if corrected == proposal:
            raise ValueError(f"{question_id}: edited decision did not change labels")
        if "FAIL" not in checks.values():
            raise ValueError(f"{question_id}: edited decision has no failed check")
    if not isinstance(decision.get("reviewer_id"), str) or not decision["reviewer_id"]:
        raise ValueError(f"{question_id}: pre-review reviewer id is missing")
    pre_reviewed_at = decision.get("reviewed_at")
    if not isinstance(pre_reviewed_at, str):
        raise ValueError(f"{question_id}: pre-review time is missing")
    reviewed_at = datetime.fromisoformat(pre_reviewed_at)
    if reviewed_at.tzinfo is None:
        raise ValueError(f"{question_id}: pre-review time must include a timezone")

    evidence_by_id = {
        value["chunk_id"]: value
        for value in queue_entry.get("frozen_evidence_chunks", [])
    }
    claim_ids = {value["claim_id"] for value in corrected["reference_claims"]}
    for judgment in corrected["chunk_judgments"]:
        evidence = evidence_by_id.get(judgment["chunk_id"])
        if evidence is None:
            raise ValueError(f"{question_id}: corrected judgment uses unknown chunk")
        if (
            judgment["document_id"],
            judgment["page_start"],
            judgment["page_end"],
        ) != (
            evidence["document_id"],
            evidence["page_start"],
            evidence["page_end"],
        ):
            raise ValueError(f"{question_id}: corrected chunk identity drift")
        if set(judgment["supports_claims"]) - claim_ids:
            raise ValueError(f"{question_id}: corrected judgment uses unknown claim")
    if set(corrected["expected_citations"]) - set(evidence_by_id):
        raise ValueError(f"{question_id}: corrected citation is outside frozen evidence")
    payload = source_item.model_dump(mode="json")
    payload.update(corrected)
    EvaluationItemV1.model_validate(payload)


def _human_note(
    source_note: str,
    *,
    reviewer_id: str,
    expert_reviewer_id: str | None,
) -> str:
    note = source_note.strip()
    for suffix in AI_NOTE_SUFFIXES:
        if note.endswith(suffix.strip()):
            note = note[: -len(suffix.strip())].rstrip()
            break
    confirmation = (
        f"人工评审者 {reviewer_id} 已结合冻结问题、证据和标签"
        "逐项复核并确认。"
    )
    if expert_reviewer_id is not None:
        confirmation += f" 专家题由授权专家 {expert_reviewer_id} 最终签署。"
    return f"{note} {confirmation}".strip()


def finalize_decision(
    decision: dict[str, Any],
    *,
    queue_entry: dict[str, Any],
    reviewer_id: str,
    expert_reviewer_id: str,
    reviewed_at: datetime,
) -> dict[str, Any]:
    finalized = json.loads(json.dumps(decision, ensure_ascii=False))
    expert_required = queue_entry["required_reviewer_mode"] == "HUMAN_EXPERT"
    finalized["reviewer_id"] = reviewer_id
    finalized["reviewed_at"] = reviewed_at.isoformat()
    finalized["expert_confirmation"] = "APPROVE" if expert_required else "NOT_REQUIRED"
    finalized["reviewer_notes"] = _human_note(
        decision.get("reviewer_notes", ""),
        reviewer_id=reviewer_id,
        expert_reviewer_id=expert_reviewer_id if expert_required else None,
    )
    return finalized


def finalize_review(
    *,
    manifest_path: Path,
    queue_path: Path,
    pre_review_path: Path,
    output_dir: Path,
    reviewer_id: str,
    expert_reviewer_id: str,
    reviewed_at: datetime,
) -> dict[str, Any]:
    if reviewed_at.tzinfo is None:
        raise ValueError("reviewed_at must include a timezone")
    if not reviewer_id.strip() or not expert_reviewer_id.strip():
        raise ValueError("reviewer ids must not be blank")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory is not empty; refusing to overwrite")

    queue = _load_jsonl(queue_path)
    pre_review = _load_jsonl(pre_review_path)
    _, source_items, _ = load_manifest_and_items(manifest_path)
    if len(queue) != EXPECTED_COUNT or len(pre_review) != EXPECTED_COUNT:
        raise ValueError("human review finalization requires exactly 175 records")
    queue_by_id = {value["question_id"]: value for value in queue}
    pre_review_by_id = {value["question_id"]: value for value in pre_review}
    source_by_id = {value.question_id: value for value in source_items}
    if len(queue_by_id) != EXPECTED_COUNT or len(pre_review_by_id) != EXPECTED_COUNT:
        raise ValueError("queue and decisions must contain unique question ids")
    if set(queue_by_id) != set(pre_review_by_id):
        raise ValueError("queue and decision question ids do not match")

    finalized: list[dict[str, Any]] = []
    for queue_entry in queue:
        question_id = queue_entry["question_id"]
        source_item = source_by_id.get(question_id)
        if source_item is None:
            raise ValueError(f"{question_id}: source evaluation item is missing")
        decision = pre_review_by_id[question_id]
        validate_pre_review_decision(
            decision,
            queue_entry=queue_entry,
            source_item=source_item,
        )
        finalized.append(
            finalize_decision(
                decision,
                queue_entry=queue_entry,
                reviewer_id=reviewer_id,
                expert_reviewer_id=expert_reviewer_id,
                reviewed_at=reviewed_at,
            )
        )

    final_bytes = _serialize_jsonl(finalized)
    pre_review_bytes = pre_review_path.read_bytes()
    outcome_counts = Counter(value["review_outcome"] for value in finalized)
    expert_count = sum(
        value["required_reviewer_mode"] == "HUMAN_EXPERT" for value in queue
    )
    report = {
        "schema_version": "mvp_human_review_finalization_report_v1",
        "status": "HUMAN_VALIDATED_175_OF_175",
        "human_reviewed_at": reviewed_at.isoformat(),
        "human_reviewer_id": reviewer_id,
        "expert_reviewer_id": expert_reviewer_id,
        "human_validated_count": len(finalized),
        "expert_signed_count": expert_count,
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "edited_label_count": outcome_counts["EDIT_LABELS"],
        "queue_sha256": sha256_file(queue_path),
        "ai_pre_review_sha256": _sha256_bytes(pre_review_bytes),
        "human_decisions_sha256": _sha256_bytes(final_bytes),
    }
    report_bytes = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    files = {
        "mvp-initial-review-decisions-ai-prereview-v1.jsonl": pre_review_bytes,
        "mvp-initial-review-decisions-v1.jsonl": final_bytes,
        "human-review-finalization-report.json": report_bytes,
    }
    files["SHA256SUMS"] = "".join(
        f"{_sha256_bytes(value)}  {name}\n" for name, value in sorted(files.items())
    ).encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (output_dir / name).write_bytes(value)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--pre-review", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--expert-reviewer-id", required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--attest-all-reviewed", action="store_true")
    parser.add_argument("--attest-expert-authorized", action="store_true")
    args = parser.parse_args()
    if not args.attest_all_reviewed or not args.attest_expert_authorized:
        print("explicit human and expert attestations are required", file=sys.stderr)
        return 2
    try:
        report = finalize_review(
            manifest_path=args.manifest,
            queue_path=args.queue,
            pre_review_path=args.pre_review,
            output_dir=args.output_dir,
            reviewer_id=args.reviewer_id,
            expert_reviewer_id=args.expert_reviewer_id,
            reviewed_at=datetime.fromisoformat(args.reviewed_at),
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"MVP human review finalization error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
