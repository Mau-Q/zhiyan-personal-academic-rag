#!/usr/bin/env python3
"""Select and package the 175-item human-validated MVP initial corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.formal_corpus import (
    EvaluationItemV1,
    load_manifest_and_items,
    sha256_file,
)
from scripts.prepare_risk_review_package import (
    _serialize_jsonl,
    _sha256_bytes,
    _write_deterministic_zip,
    load_generation_requests,
)

CATEGORIES = (
    "exact_lookup",
    "single_document_fact",
    "semantic_rewrite",
    "comparison",
    "evidence_boundary",
    "security",
)
SPLITS = ("dev", "test", "acceptance")


def classify_item(item: Any) -> str | None:
    question_types = set(item.question_types)
    if item.answerability == "FORBIDDEN" or "adversarial_security" in question_types:
        return "security"
    if item.answerability in {
        "NO_EVIDENCE",
        "PARTIALLY_ANSWERABLE",
        "CONFLICTING_EVIDENCE",
    }:
        return "evidence_boundary"
    if "exact_lookup" in question_types:
        return "exact_lookup"
    if "single_document_fact" in question_types:
        return "single_document_fact"
    if "comparison" in question_types:
        return "comparison"
    if question_types & {
        "single_document_explanation",
        "cross_document_semantic",
        "teaching_explanation",
        "multi_hop",
        "standards_freshness",
    }:
        return "semantic_rewrite"
    return None


def _stable_key(seed: int, category: str, question_id: str) -> str:
    return hashlib.sha256(f"{seed}:{category}:{question_id}".encode()).hexdigest()


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("schema_version") != "mvp_initial_review_policy_v1":
        raise ValueError("unsupported MVP initial review policy schema")
    target_size = policy.get("target_size")
    if not isinstance(target_size, int) or target_size <= 0:
        raise ValueError("policy target_size must be positive")
    if set(policy.get("category_quotas", {})) != set(CATEGORIES):
        raise ValueError("policy category quotas do not match fixed categories")
    if set(policy.get("split_quotas", {})) != set(SPLITS):
        raise ValueError("policy split quotas do not match fixed splits")
    if sum(policy["category_quotas"].values()) != target_size:
        raise ValueError("category quotas do not sum to target_size")
    if sum(policy["split_quotas"].values()) != target_size:
        raise ValueError("split quotas do not sum to target_size")
    category_splits = policy.get("category_split_quotas", {})
    if set(category_splits) != set(CATEGORIES):
        raise ValueError("category split quotas do not match fixed categories")
    accumulated = Counter()
    for category in CATEGORIES:
        split_quotas = category_splits[category]
        if set(split_quotas) != set(SPLITS):
            raise ValueError(f"{category}: invalid split quotas")
        if sum(split_quotas.values()) != policy["category_quotas"][category]:
            raise ValueError(f"{category}: split quotas do not sum to category quota")
        accumulated.update(split_quotas)
    if dict(accumulated) != policy["split_quotas"]:
        raise ValueError("category split quotas do not reproduce global split quotas")


def select_items(
    items: Iterable[Any], policy: dict[str, Any]
) -> list[tuple[Any, str, str]]:
    validate_policy(policy)
    seed = policy["seed"]
    by_category: dict[str, list[Any]] = {category: [] for category in CATEGORIES}
    for item in items:
        category = classify_item(item)
        if category is not None:
            by_category[category].append(item)
    selected: list[tuple[Any, str, str]] = []
    used_groups: set[str] = set()
    for category in CATEGORIES:
        candidates = sorted(
            by_category[category],
            key=lambda item: _stable_key(seed, category, item.question_id),
        )
        unique_candidates = []
        for item in candidates:
            if item.leakage_group_id in used_groups:
                continue
            unique_candidates.append(item)
            used_groups.add(item.leakage_group_id)
            if len(unique_candidates) == policy["category_quotas"][category]:
                break
        if len(unique_candidates) != policy["category_quotas"][category]:
            raise ValueError(
                f"{category}: insufficient unique leakage groups for requested quota"
            )
        offset = 0
        for split in SPLITS:
            count = policy["category_split_quotas"][category][split]
            for item in unique_candidates[offset : offset + count]:
                selected.append((item, category, split))
            offset += count
    if len(selected) != policy["target_size"]:
        raise ValueError("selected item count does not match target_size")
    if len({item.question_id for item, _, _ in selected}) != len(selected):
        raise ValueError("selection contains duplicate question ids")
    if len({item.leakage_group_id for item, _, _ in selected}) != len(selected):
        raise ValueError("selection contains duplicate leakage groups")
    return sorted(selected, key=lambda value: (SPLITS.index(value[2]), value[0].question_id))


def _proposal_payload(item: EvaluationItemV1) -> dict[str, Any]:
    return {
        "answerability": item.answerability,
        "expected_route": item.expected_route,
        "expected_filters": item.expected_filters.model_dump(mode="json"),
        "chunk_judgments": [value.model_dump(mode="json") for value in item.chunk_judgments],
        "reference_claims": [value.model_dump(mode="json") for value in item.reference_claims],
        "acceptable_answer_points": item.acceptable_answer_points,
        "must_not_claim": item.must_not_claim,
        "expected_citations": item.expected_citations,
    }


def _payload_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_queue_entry(
    item: EvaluationItemV1,
    *,
    category: str,
    mvp_split: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    evidence_by_id = {
        value["chunk_id"]: value for value in request.get("evidence_chunks", [])
    }
    for judgment in item.chunk_judgments:
        evidence = evidence_by_id.get(judgment.chunk_id)
        if evidence is None:
            raise ValueError(f"{item.question_id}: frozen evidence chunk is missing")
        if (
            evidence["document_id"],
            evidence["page_start"],
            evidence["page_end"],
        ) != (judgment.document_id, judgment.page_start, judgment.page_end):
            raise ValueError(f"{item.question_id}: frozen evidence identity drift")
    proposal = _proposal_payload(item)
    expert_required = item.difficulty == "hard" or "standards_freshness" in item.question_types
    return {
        "schema_version": "mvp_initial_review_item_v1",
        "review_id": f"mvp175.{item.question_id}",
        "question_id": item.question_id,
        "selected_category": category,
        "mvp_split": mvp_split,
        "source_split": item.split,
        "blind_holdout": mvp_split == "acceptance",
        "leakage_group_id": item.leakage_group_id,
        "required_reviewer_mode": "HUMAN_EXPERT" if expert_required else "HUMAN_REVIEWER",
        "question": item.question,
        "conversation_history": [value.model_dump(mode="json") for value in item.conversation_history],
        "authorized_scope_ids": item.authorized_scope_ids,
        "question_types": item.question_types,
        "language": item.language,
        "query_form": item.query_form,
        "difficulty": item.difficulty,
        "proposal_origin": (
            "GPT_ASSISTED" if item.annotation_status == "GPT_ASSISTED"
            else "AI_AUDITED_ENGINEERING_DRAFT_NOT_HUMAN"
        ),
        "proposal": {**proposal, "labels_sha256": _payload_sha256(proposal)},
        "frozen_evidence_chunks": request.get("evidence_chunks", []),
        "review_checks": [
            "QUESTION_AND_SCOPE_MATCH",
            "ANSWERABILITY_IS_CORRECT",
            "RELEVANCE_0_TO_3_IS_CORRECT",
            "CLAIM_EVIDENCE_LINKS_ARE_SUPPORTED",
            "ANSWER_POINTS_AND_MUST_NOT_CLAIMS_ARE_CORRECT",
            "EXPECTED_CITATIONS_EXIST_AND_ARE_AUTHORIZED",
        ],
    }


def build_decision(entry: dict[str, Any]) -> dict[str, Any]:
    proposal = entry["proposal"]
    corrected = {key: value for key, value in proposal.items() if key != "labels_sha256"}
    return {
        "schema_version": "mvp_initial_review_decision_v1",
        "review_id": entry["review_id"],
        "question_id": entry["question_id"],
        "proposal_labels_sha256": proposal["labels_sha256"],
        "review_outcome": "PENDING",
        "reviewer_id": "",
        "reviewed_at": None,
        "review_checks": {name: "PENDING" for name in entry["review_checks"]},
        "corrected_labels": corrected,
        "expert_confirmation": (
            "PENDING" if entry["required_reviewer_mode"] == "HUMAN_EXPERT" else "NOT_REQUIRED"
        ),
        "reviewer_notes": "",
    }


def _readme(created_at: datetime) -> bytes:
    return f"""# MVP 初始 175 题人工校验包 V1

创建时间：`{created_at.isoformat()}`

本包从现有 500 题工程候选池确定性选出 175 题，不生成新题。全部题目都需要真实人工校验；当前决策全部为 `PENDING`。

1. `mvp-initial-review-queue-v1.jsonl` 只读；
2. 只编辑 `mvp-initial-review-decisions-v1.jsonl`；
3. `review_outcome` 填写 `APPROVE_AS_IS`、`EDIT_LABELS` 或 `REJECT_ITEM`；
4. 逐项完成 `review_checks`，填写项目内假名 `reviewer_id`和带时区的 `reviewed_at`；
5. `HUMAN_EXPERT` 题需填写 `expert_confirmation=APPROVE` 或 `REJECT`；
6. GPT 或外部 AI 复核不能代替本包的人工校验。

本包含私有问题和冻结证据，只在授权范围内本地流转，不进入 Git。
""".encode("utf-8")


def prepare_package(
    *,
    manifest_path: Path,
    batch_dir: Path,
    policy_path: Path,
    output_dir: Path,
    created_at: datetime,
) -> dict[str, Any]:
    if created_at.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory is not empty; refusing to overwrite")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    manifest, items, _ = load_manifest_and_items(manifest_path)
    if len(items) != 500:
        raise ValueError("MVP initial selection requires the existing 500-item pool")
    selected = select_items(items, policy)
    requests = load_generation_requests(batch_dir)
    entries = [
        build_queue_entry(
            item,
            category=category,
            mvp_split=split,
            request=requests[item.question_id],
        )
        for item, category, split in selected
    ]
    decisions = [build_decision(entry) for entry in entries]
    category_counts = Counter(entry["selected_category"] for entry in entries)
    split_counts = Counter(entry["mvp_split"] for entry in entries)
    reviewer_counts = Counter(entry["required_reviewer_mode"] for entry in entries)
    summary = {
        "schema_version": "mvp_initial_review_summary_v1",
        "policy_id": policy["policy_id"],
        "created_at": created_at.isoformat(),
        "source_dataset_id": manifest.dataset_id,
        "source_dataset_version": manifest.dataset_version,
        "source_items_sha256": manifest.items_sha256,
        "source_chunk_snapshot_sha256": manifest.source_snapshot.chunk_snapshot_sha256,
        "selected_count": len(entries),
        "unique_leakage_group_count": len({entry["leakage_group_id"] for entry in entries}),
        "category_counts": dict(sorted(category_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "reviewer_mode_counts": dict(sorted(reviewer_counts.items())),
        "human_decisions_complete": 0,
        "decision_status": "ALL_PENDING",
    }
    queue_bytes = _serialize_jsonl(entries)
    decision_bytes = _serialize_jsonl(decisions)
    summary_bytes = (json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    files = {
        "README.md": _readme(created_at),
        "mvp-initial-review-queue-v1.jsonl": queue_bytes,
        "mvp-initial-review-decisions-v1.jsonl": decision_bytes,
        "mvp-initial-review-summary.json": summary_bytes,
    }
    files["SHA256SUMS"] = "".join(
        f"{_sha256_bytes(value)}  {name}\n" for name, value in sorted(files.items())
    ).encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (output_dir / name).write_bytes(value)
    zip_path = output_dir / "mvp-initial-175-review-v1.zip"
    _write_deterministic_zip(zip_path, files, created_at)
    report = {
        **summary,
        "policy_sha256": sha256_file(policy_path),
        "queue_sha256": _sha256_bytes(queue_bytes),
        "decisions_sha256": _sha256_bytes(decision_bytes),
        "zip_path": zip_path.name,
        "zip_sha256": sha256_file(zip_path),
        "zip_members": sorted(files),
        "status": "MVP_INITIAL_175_SELECTED_HUMAN_DECISIONS_0_OF_175",
    }
    (output_dir / "package-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--created-at", required=True)
    args = parser.parse_args()
    try:
        report = prepare_package(
            manifest_path=args.manifest,
            batch_dir=args.batch_dir,
            policy_path=args.policy,
            output_dir=args.output_dir,
            created_at=datetime.fromisoformat(args.created_at),
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"MVP initial review package error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "zip_sha256": report["zip_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
