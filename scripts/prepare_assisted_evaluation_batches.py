#!/usr/bin/env python3
"""Prepare deterministic 500-slot GPT prompt batches over a frozen chunk snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.ingestion.models import ChunkRecordV1


SINGLE_DOCUMENT_TYPES = {
    "exact_lookup",
    "single_document_fact",
    "single_document_explanation",
    "teaching_explanation",
    "standards_freshness",
}
CROSS_DOCUMENT_TYPES = {
    "cross_document_semantic",
    "comparison",
    "multi_hop",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _expanded_quota(quota: dict[str, int], target_size: int, label: str) -> list[str]:
    if any(not isinstance(value, int) or value < 0 for value in quota.values()):
        raise ValueError(f"{label} quotas must be non-negative integers")
    if sum(quota.values()) != target_size:
        raise ValueError(f"{label} quotas must sum to target_size")
    return [name for name, count in quota.items() for _ in range(count)]


def _load_policy(path: Path) -> dict[str, Any]:
    policy = _load_json(path)
    if policy.get("schema_version") != "assisted_evaluation_policy_v1":
        raise ValueError("unsupported assisted evaluation policy")
    target_size = policy.get("target_size")
    if target_size != 500:
        raise ValueError("assisted evaluation target_size must remain 500")
    for field in (
        "split_quotas",
        "primary_question_type_quotas",
        "language_quotas",
        "query_form_quotas",
        "difficulty_quotas",
        "answerability_quotas",
    ):
        _expanded_quota(policy[field], target_size, field)
    batch_size = policy.get("batch_size")
    if not isinstance(batch_size, int) or batch_size < 1 or target_size % batch_size:
        raise ValueError("batch_size must be a positive divisor of target_size")
    return policy


def _load_chunks(path: Path) -> list[ChunkRecordV1]:
    payload = _load_json(path)
    if not isinstance(payload, list) or not payload:
        raise ValueError("chunks must be a non-empty JSON array")
    try:
        chunks = [ChunkRecordV1.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise ValueError(f"chunks violate ChunkRecordV1: {exc}") from exc
    if any(not chunk.is_active for chunk in chunks):
        raise ValueError("prompt batches cannot include inactive chunks")
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise ValueError("prompt batches cannot include duplicate chunk_id values")
    return chunks


def _shuffled_quota(
    quota: dict[str, int], target_size: int, randomizer: random.Random
) -> list[str]:
    values = _expanded_quota(quota, target_size, "distribution")
    randomizer.shuffle(values)
    return values


def _assign_difficulty(primary_types: list[str], quota: dict[str, int]) -> list[str]:
    hard_count = quota["hard"]
    standards = [
        index
        for index, question_type in enumerate(primary_types)
        if question_type == "standards_freshness"
    ]
    if hard_count > len(standards):
        raise ValueError("hard quota cannot exceed standards_freshness quota")
    values = ["medium"] * len(primary_types)
    for index in standards[:hard_count]:
        values[index] = "hard"
    easy_needed = quota["easy"]
    for index, value in enumerate(values):
        if easy_needed and value == "medium":
            values[index] = "easy"
            easy_needed -= 1
    if Counter(values) != Counter(quota):
        raise ValueError("difficulty quotas cannot be assigned under current constraints")
    return values


def _assign_answerability(
    primary_types: list[str], quota: dict[str, int]
) -> list[str]:
    values: list[str | None] = [None] * len(primary_types)
    assignments = (
        ("adversarial_security", "FORBIDDEN"),
        ("no_answer_evidence_insufficient", "NO_EVIDENCE"),
    )
    for question_type, answerability in assignments:
        indices = [
            index
            for index, value in enumerate(primary_types)
            if value == question_type
        ]
        if len(indices) != quota[answerability]:
            raise ValueError(f"{question_type} quota must equal {answerability} quota")
        for index in indices:
            values[index] = answerability
    remaining_by_type = [
        index
        for index, value in enumerate(primary_types)
        if value in {"multi_hop", "comparison", "cross_document_semantic"}
        and values[index] is None
    ]
    for index in remaining_by_type[: quota["CONFLICTING_EVIDENCE"]]:
        values[index] = "CONFLICTING_EVIDENCE"
    unassigned = [index for index, value in enumerate(values) if value is None]
    for index in unassigned[: quota["PARTIALLY_ANSWERABLE"]]:
        values[index] = "PARTIALLY_ANSWERABLE"
    for index, value in enumerate(values):
        if value is None:
            values[index] = "ANSWERABLE"
    finalized = [value for value in values if value is not None]
    if Counter(finalized) != Counter(quota):
        raise ValueError("answerability quotas cannot be assigned under current constraints")
    return finalized


def _chunk_payload(chunk: ChunkRecordV1) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "section_path": chunk.section_path,
        "text": chunk.text,
    }


def prepare_batches(
    *,
    policy_path: Path,
    chunks_path: Path,
    prompt_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory is not empty; refusing to overwrite")
    policy = _load_policy(policy_path)
    chunks = _load_chunks(chunks_path)
    prompt_text = prompt_path.read_text(encoding="utf-8")
    target_size = policy["target_size"]
    randomizer = random.Random(policy["seed"])
    primary_types = _shuffled_quota(
        policy["primary_question_type_quotas"], target_size, randomizer
    )
    splits = _shuffled_quota(policy["split_quotas"], target_size, randomizer)
    languages = _shuffled_quota(policy["language_quotas"], target_size, randomizer)
    query_forms = _shuffled_quota(
        policy["query_form_quotas"], target_size, randomizer
    )
    difficulties = _assign_difficulty(primary_types, policy["difficulty_quotas"])
    answerabilities = _assign_answerability(
        primary_types, policy["answerability_quotas"]
    )

    by_document: dict[str, list[ChunkRecordV1]] = defaultdict(list)
    for chunk in chunks:
        by_document[chunk.document_id].append(chunk)
    document_ids = sorted(by_document)
    if len(document_ids) < 2:
        raise ValueError("500-item assisted evaluation requires at least two documents")
    for records in by_document.values():
        records.sort(key=lambda value: (value.page_start, value.chunk_id))

    document_offsets = Counter()
    slots: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    for index in range(target_size):
        question_type = primary_types[index]
        if question_type == "adversarial_security":
            selected_documents: list[str] = []
            selected_chunks: list[ChunkRecordV1] = []
        elif question_type in CROSS_DOCUMENT_TYPES:
            first = index % len(document_ids)
            selected_documents = [
                document_ids[first],
                document_ids[(first + 1) % len(document_ids)],
            ]
            selected_chunks = []
            for document_id in selected_documents:
                records = by_document[document_id]
                start = document_offsets[document_id] % len(records)
                take = 2
                selected_chunks.extend(
                    records[(start + offset) % len(records)] for offset in range(take)
                )
                document_offsets[document_id] += take
        else:
            document_id = document_ids[index % len(document_ids)]
            selected_documents = [document_id]
            records = by_document[document_id]
            start = document_offsets[document_id] % len(records)
            take = policy["generation_policy"][
                "max_context_chunks_single_document"
            ]
            selected_chunks = [
                records[(start + offset) % len(records)] for offset in range(take)
            ]
            document_offsets[document_id] += take
        slot_id = f"local3.assisted.{index + 1:04d}"
        requires_expert = (
            question_type
            in set(policy["review_policy"]["expert_review_question_types"])
            or difficulties[index]
            in set(policy["review_policy"]["expert_review_difficulties"])
        )
        slot = {
            "slot_id": slot_id,
            "split": splits[index],
            "primary_question_type": question_type,
            "language": languages[index],
            "query_form": query_forms[index],
            "difficulty": difficulties[index],
            "answerability": answerabilities[index],
            "source_document_ids": selected_documents,
            "source_chunk_ids": [chunk.chunk_id for chunk in selected_chunks],
            "blind_holdout": splits[index] == "acceptance",
            "requires_human_confirmation": splits[index] == "acceptance",
            "requires_human_adjudication": (
                answerabilities[index] == "CONFLICTING_EVIDENCE"
            ),
            "requires_expert_review": requires_expert,
        }
        slots.append(slot)
        requests.append(
            {
                "schema_version": "assisted_question_generation_request_v1",
                "prompt_version": policy["generation_policy"]["prompt_version"],
                "temperature": policy["generation_policy"]["temperature"],
                "slot": slot,
                "evidence_chunks": [_chunk_payload(chunk) for chunk in selected_chunks],
                "instructions": prompt_text,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    slots_payload = "".join(
        json.dumps(slot, ensure_ascii=False, separators=(",", ":")) + "\n"
        for slot in slots
    )
    (output_dir / "slots-v1.jsonl").write_text(slots_payload, encoding="utf-8")
    batch_size = policy["batch_size"]
    batch_dir = output_dir / "batches"
    batch_dir.mkdir()
    for start in range(0, target_size, batch_size):
        batch = requests[start : start + batch_size]
        batch_path = batch_dir / f"batch-{start // batch_size + 1:03d}.jsonl"
        batch_path.write_text(
            "".join(
                json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n"
                for request in batch
            ),
            encoding="utf-8",
        )
    report = {
        "schema_version": "assisted_evaluation_batch_report_v1",
        "policy_id": policy["policy_id"],
        "target_size": target_size,
        "slot_count": len(slots),
        "batch_size": batch_size,
        "batch_count": target_size // batch_size,
        "source_document_count": len(document_ids),
        "source_chunk_count": len(chunks),
        "slot_sha256": hashlib.sha256(slots_payload.encode("utf-8")).hexdigest(),
        "distributions": {
            "split": dict(sorted(Counter(splits).items())),
            "primary_question_type": dict(sorted(Counter(primary_types).items())),
            "language": dict(sorted(Counter(languages).items())),
            "query_form": dict(sorted(Counter(query_forms).items())),
            "difficulty": dict(sorted(Counter(difficulties).items())),
            "answerability": dict(sorted(Counter(answerabilities).items())),
        },
        "status": "PROMPT_BATCHES_READY_MODEL_EXECUTION_PENDING",
    }
    (output_dir / "batch-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare GPT evaluation prompt batches")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = prepare_batches(
            policy_path=args.policy,
            chunks_path=args.chunks,
            prompt_path=args.prompt,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"evaluation batch preparation error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
