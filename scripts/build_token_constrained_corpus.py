#!/usr/bin/env python3
"""Derive a lower-cost engineering corpus from an external AI review."""

from __future__ import annotations

import argparse
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
    EvaluationManifestV1,
    load_manifest_and_items,
    sha256_file,
    validate_corpus,
)


ALLOWED_OUTCOMES = {"APPROVE_AS_IS", "EDIT_LABELS", "REJECT_ITEM"}


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


def _unique_by_question_id(
    values: list[dict[str, Any]], label: str
) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for value in values:
        question_id = value.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            raise ValueError(f"{label} record has no question_id")
        if question_id in mapped:
            raise ValueError(f"duplicate {label} question_id: {question_id}")
        mapped[question_id] = value
    return mapped


def derive_items(
    *,
    source_items: list[EvaluationItemV1],
    queue: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    dataset_version: str,
) -> tuple[list[EvaluationItemV1], dict[str, Any]]:
    queue_by_id = _unique_by_question_id(queue, "queue")
    decision_by_id = _unique_by_question_id(decisions, "decision")
    if set(queue_by_id) != set(decision_by_id):
        raise ValueError("review queue and decision coverage do not match")
    outcome_counts: Counter[str] = Counter()
    reviewer_counts: Counter[str] = Counter()
    rejected_ids: list[str] = []
    edited_ids: list[str] = []
    for question_id, decision in decision_by_id.items():
        queued = queue_by_id[question_id]
        if decision.get("schema_version") != "assisted_risk_review_decision_v1":
            raise ValueError(f"{question_id}: unsupported decision schema")
        outcome = decision.get("review_outcome")
        if outcome not in ALLOWED_OUTCOMES:
            raise ValueError(f"{question_id}: unresolved or invalid review outcome")
        if decision.get("review_id") != queued.get("review_id"):
            raise ValueError(f"{question_id}: review id does not match queue")
        if decision.get("review_reasons") != queued.get("review_reasons"):
            raise ValueError(f"{question_id}: review reasons do not match queue")
        if decision.get("required_reviewer_mode") != queued.get(
            "required_reviewer_mode"
        ):
            raise ValueError(f"{question_id}: reviewer mode does not match queue")
        if decision.get("proposal_labels_sha256") != queued["gpt_proposal"].get(
            "labels_sha256"
        ):
            raise ValueError(f"{question_id}: proposal label hash drift")
        reviewer_id = decision.get("reviewer_id")
        reviewed_at = decision.get("reviewed_at")
        if not isinstance(reviewer_id, str) or not reviewer_id.strip():
            raise ValueError(f"{question_id}: reviewer_id is missing")
        if not isinstance(reviewed_at, str):
            raise ValueError(f"{question_id}: reviewed_at is missing")
        if datetime.fromisoformat(reviewed_at).tzinfo is None:
            raise ValueError(f"{question_id}: reviewed_at must include a timezone")
        if not str(decision.get("reviewer_notes", "")).strip():
            raise ValueError(f"{question_id}: reviewer notes are required")
        proposal = {
            key: queued["gpt_proposal"][key]
            for key in ("answerability", "expected_route", "chunk_judgments")
        }
        corrected = decision.get("corrected_labels")
        if not isinstance(corrected, dict):
            raise ValueError(f"{question_id}: corrected_labels is missing")
        if outcome == "APPROVE_AS_IS" and corrected != proposal:
            raise ValueError(f"{question_id}: approved labels differ from proposal")
        if outcome == "EDIT_LABELS" and corrected == proposal:
            raise ValueError(f"{question_id}: edited labels did not change")
        expert = decision.get("expert_confirmation")
        if queued["required_reviewer_mode"] == "HUMAN_EXPERT":
            if expert not in {"APPROVE", "REJECT"}:
                raise ValueError(f"{question_id}: expert confirmation is unresolved")
            if (expert == "REJECT") != (outcome == "REJECT_ITEM"):
                raise ValueError(f"{question_id}: expert and review outcomes disagree")
        elif expert != "NOT_REQUIRED":
            raise ValueError(f"{question_id}: unexpected expert confirmation")
        outcome_counts[outcome] += 1
        reviewer_counts[reviewer_id] += 1

    derived: list[EvaluationItemV1] = []
    source_ids = {item.question_id for item in source_items}
    if not set(queue_by_id).issubset(source_ids):
        raise ValueError("review queue references unknown source items")
    for source_item in source_items:
        decision = decision_by_id.get(source_item.question_id)
        if decision and decision["review_outcome"] == "REJECT_ITEM":
            rejected_ids.append(source_item.question_id)
            continue
        payload = source_item.model_dump(mode="json")
        if decision and decision["review_outcome"] == "EDIT_LABELS":
            payload.update(decision["corrected_labels"])
            payload["expected_citations"] = [
                judgment["chunk_id"]
                for judgment in payload["chunk_judgments"]
                if judgment["relevance"] >= 2
            ]
            edited_ids.append(source_item.question_id)
        payload.update(
            {
                "dataset_version": dataset_version,
                "annotation_status": "DRAFT",
                "annotation_record_ids": [],
                "final_annotation_id": None,
                "agreement_score": None,
            }
        )
        derived.append(EvaluationItemV1.model_validate(payload))
    return derived, {
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "reviewer_counts": dict(sorted(reviewer_counts.items())),
        "edited_item_count": len(edited_ids),
        "edited_question_ids": sorted(edited_ids),
        "excluded_item_count": len(rejected_ids),
        "excluded_question_ids": sorted(rejected_ids),
    }


def build_token_constrained_corpus(
    *,
    source_manifest_path: Path,
    queue_path: Path,
    decisions_path: Path,
    output_dir: Path,
    created_at: datetime,
) -> dict[str, Any]:
    if created_at.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory is not empty; refusing to overwrite")
    source_manifest, source_items, _ = load_manifest_and_items(source_manifest_path)
    dataset_version = "local-3-paper-token-constrained-v1"
    items, audit = derive_items(
        source_items=source_items,
        queue=_load_jsonl(queue_path),
        decisions=_load_jsonl(decisions_path),
        dataset_version=dataset_version,
    )
    if len(items) != 482 or audit["edited_item_count"] != 40:
        raise ValueError("expected 482 retained items and 40 edited items")
    output_dir.mkdir(parents=True, exist_ok=True)
    items_path = output_dir / "items-v1.jsonl"
    annotations_path = output_dir / "annotations-v1.jsonl"
    items_path.write_text(
        "".join(
            json.dumps(
                item.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
            for item in items
        ),
        encoding="utf-8",
    )
    annotations_path.write_bytes(b"")
    manifest_value = source_manifest.model_dump(mode="json")
    manifest_value.update(
        {
            "dataset_id": "local-3-paper-token-constrained-evaluation-v1",
            "dataset_version": dataset_version,
            "status": "DATA_COLLECTION",
            "target_size": len(items),
            "items_path": items_path.name,
            "items_sha256": sha256_file(items_path),
            "annotation_records_path": annotations_path.name,
            "annotation_records_sha256": sha256_file(annotations_path),
        }
    )
    manifest = EvaluationManifestV1.model_validate(manifest_value)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    formal_report = validate_corpus(manifest_path)
    (output_dir / "validation-report.json").write_text(
        json.dumps(formal_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = {
        "schema_version": "token_constrained_corpus_report_v1",
        "status": "TOKEN_CONSTRAINED_ENGINEERING_CORPUS_READY",
        "quality_mode": "LOWER_COST_LOWER_CONFIDENCE_EXTERNAL_AI_AUDIT",
        "created_at": created_at.isoformat(),
        "source_dataset_id": source_manifest.dataset_id,
        "source_item_count": len(source_items),
        "source_items_sha256": source_manifest.items_sha256,
        "review_queue_sha256": sha256_file(queue_path),
        "review_decisions_sha256": sha256_file(decisions_path),
        "retained_item_count": len(items),
        "split_counts": dict(sorted(Counter(item.split for item in items).items())),
        "human_review_count": 0,
        "highest_plan_satisfied": False,
        "accepted_quality_reductions": [
            "EXTERNAL_AI_REVIEW_USED_INSTEAD_OF_HUMAN_RISK_REVIEW",
            "18_REJECTED_ITEMS_EXCLUDED_WITHOUT_REGENERATION",
            "FORMAL_500_TARGET_RETAINED_SEPARATELY_NOT_REPLACED",
        ],
        **audit,
        "formal_validation_engineering_ready": formal_report["engineering_ready"],
        "formal_validation_lock_ready": formal_report["lock_ready"],
        "items_sha256": manifest.items_sha256,
    }
    (output_dir / "token-constrained-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--created-at", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = build_token_constrained_corpus(
            source_manifest_path=args.source_manifest,
            queue_path=args.queue,
            decisions_path=args.decisions,
            output_dir=args.output_dir,
            created_at=datetime.fromisoformat(args.created_at),
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"token-constrained corpus error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({key: report[key] for key in ("status", "retained_item_count", "edited_item_count", "excluded_item_count")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
