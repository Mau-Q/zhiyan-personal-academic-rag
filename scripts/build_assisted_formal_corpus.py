#!/usr/bin/env python3
"""Group assisted candidates for leakage and import GPT-assisted formal records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import operator
import sys
from collections import Counter, defaultdict
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
    EvaluationManifestV1,
    sha256_file,
)
from backend.retrieval.embedding import OllamaEmbeddingProvider


QUESTION_SIMILARITY_THRESHOLD = 0.88
ANSWER_SIMILARITY_THRESHOLD = 0.92
SHARED_CHUNK_QUESTION_THRESHOLD = 0.82
JOINT_QUESTION_THRESHOLD = 0.76
JOINT_ANSWER_THRESHOLD = 0.88
SPLIT_TARGETS = {"dev": 300, "test": 100, "acceptance": 100}
SPLIT_PRIORITY = {"dev": 2, "test": 1, "acceptance": 0}


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


def _normalize_vectors(vectors: list[list[float]]) -> list[list[float]]:
    normalized: list[list[float]] = []
    dimensions: set[int] = set()
    for vector in vectors:
        converted = [float(value) for value in vector]
        norm = math.sqrt(sum(value * value for value in converted))
        if not converted or not math.isfinite(norm) or norm <= 0:
            raise ValueError("embedding vectors must be finite and non-zero")
        normalized.append([value / norm for value in converted])
        dimensions.add(len(converted))
    if len(dimensions) != 1:
        raise ValueError("embedding vectors have inconsistent dimensions")
    return normalized


def _question_text(row: dict[str, Any]) -> str:
    candidate = row["candidate"]
    history = "\n".join(
        f"{turn['role']}: {turn['content']}"
        for turn in candidate["conversation_history"]
    )
    return (history + "\nquestion: " + candidate["question"]).strip()


def _answer_text(row: dict[str, Any]) -> str:
    candidate = row["candidate"]
    claims = "\n".join(claim["text"] for claim in candidate["reference_claims"])
    points = "\n".join(candidate["acceptable_answer_points"])
    answer = (claims + "\n" + points).strip()
    if answer:
        return answer
    return f"NO SUPPORTING ANSWER: {candidate['answerability']}\n{candidate['question']}"


def load_or_create_embedding_cache(
    *,
    rows: list[dict[str, Any]],
    cache_path: Path,
    model: str,
    base_url: str,
    batch_size: int,
) -> tuple[list[list[float]], list[list[float]], dict[str, str]]:
    slot_ids = [row["slot"]["slot_id"] for row in rows]
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if cache.get("schema_version") != "assisted_leakage_embedding_cache_v1":
            raise ValueError("unsupported leakage embedding cache schema")
        if cache.get("slot_ids") != slot_ids:
            raise ValueError("leakage embedding cache slot order does not match candidates")
        identity = cache.get("model_identity")
        if not isinstance(identity, dict) or identity.get("model") not in {
            model,
            model.removesuffix(":latest"),
            f"{model}:latest",
        }:
            raise ValueError("leakage embedding cache model identity does not match")
        return (
            _normalize_vectors(cache["question_vectors"]),
            _normalize_vectors(cache["answer_vectors"]),
            {key: str(value) for key, value in identity.items()},
        )

    provider = OllamaEmbeddingProvider(
        model=model,
        base_url=base_url,
        batch_size=batch_size,
        timeout_seconds=180,
    )
    identity_value = provider.identity()
    question_vectors = _normalize_vectors(
        provider.embed([_question_text(row) for row in rows])
    )
    answer_vectors = _normalize_vectors(
        provider.embed([_answer_text(row) for row in rows])
    )
    identity = {
        "provider": identity_value.provider,
        "model": identity_value.model,
        "digest": identity_value.digest,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": "assisted_leakage_embedding_cache_v1",
                "slot_ids": slot_ids,
                "model_identity": identity,
                "question_vectors": question_vectors,
                "answer_vectors": answer_vectors,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return question_vectors, answer_vectors, identity


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(map(operator.mul, left, right))


def group_candidates(
    rows: list[dict[str, Any]],
    question_vectors: list[list[float]],
    answer_vectors: list[list[float]],
) -> tuple[list[list[int]], list[dict[str, Any]], dict[str, int], list[float]]:
    if len(rows) != len(question_vectors) or len(rows) != len(answer_vectors):
        raise ValueError("candidate and embedding counts do not match")
    parent = list(range(len(rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    pairs: list[dict[str, Any]] = []
    all_question_similarities: list[float] = []
    reason_counts: Counter[str] = Counter()
    for left_index, left in enumerate(rows):
        left_slot = left["slot"]
        left_chunks = set(left_slot["source_chunk_ids"])
        left_documents = set(left_slot["source_document_ids"])
        for right_index in range(left_index + 1, len(rows)):
            right = rows[right_index]
            right_slot = right["slot"]
            question_similarity = _cosine(
                question_vectors[left_index], question_vectors[right_index]
            )
            answer_similarity = _cosine(
                answer_vectors[left_index], answer_vectors[right_index]
            )
            all_question_similarities.append(question_similarity)
            shared_chunk = bool(left_chunks & set(right_slot["source_chunk_ids"]))
            shared_document = bool(
                left_documents & set(right_slot["source_document_ids"])
            )
            same_answerability = (
                left_slot["answerability"] == right_slot["answerability"]
            )
            reason: str | None = None
            if question_similarity >= QUESTION_SIMILARITY_THRESHOLD:
                reason = "QUESTION_SEMANTIC_0_88"
            elif (
                same_answerability
                and shared_document
                and answer_similarity >= ANSWER_SIMILARITY_THRESHOLD
            ):
                reason = "ANSWER_TEMPLATE_0_92_SAME_DOCUMENT"
            elif (
                shared_chunk
                and question_similarity >= SHARED_CHUNK_QUESTION_THRESHOLD
            ):
                reason = "QUESTION_SEMANTIC_0_82_SHARED_CHUNK"
            elif (
                same_answerability
                and shared_chunk
                and question_similarity >= JOINT_QUESTION_THRESHOLD
                and answer_similarity >= JOINT_ANSWER_THRESHOLD
            ):
                reason = "JOINT_QUESTION_ANSWER_SHARED_CHUNK"
            if reason is None:
                continue
            union(left_index, right_index)
            reason_counts[reason] += 1
            pairs.append(
                {
                    "left_slot_id": left_slot["slot_id"],
                    "right_slot_id": right_slot["slot_id"],
                    "left_split": left_slot["split"],
                    "right_split": right_slot["split"],
                    "question_similarity": round(question_similarity, 6),
                    "answer_similarity": round(answer_similarity, 6),
                    "shared_document": shared_document,
                    "shared_chunk": shared_chunk,
                    "reason": reason,
                }
            )
    components: defaultdict[int, list[int]] = defaultdict(list)
    for index in range(len(rows)):
        components[find(index)].append(index)
    groups = sorted(
        components.values(),
        key=lambda group: min(rows[index]["slot"]["slot_id"] for index in group),
    )
    return groups, pairs, dict(sorted(reason_counts.items())), all_question_similarities


def leakage_group_id(rows: list[dict[str, Any]], group: list[int]) -> str:
    slot_ids = sorted(rows[index]["slot"]["slot_id"] for index in group)
    digest = hashlib.sha256("\n".join(slot_ids).encode("utf-8")).hexdigest()[:20]
    return f"leakage.semantic.{digest}"


def assign_group_splits(
    rows: list[dict[str, Any]], groups: list[list[int]]
) -> dict[int, str]:
    if len(rows) != sum(len(group) for group in groups):
        raise ValueError("leakage groups do not cover each candidate exactly once")
    remaining = dict(SPLIT_TARGETS)
    assignments: dict[int, str] = {}
    multi_groups = sorted(
        (group for group in groups if len(group) > 1),
        key=lambda group: (
            -len(group),
            min(rows[index]["slot"]["slot_id"] for index in group),
        ),
    )
    for group in multi_groups:
        original = Counter(rows[index]["slot"]["split"] for index in group)
        eligible = [split for split, count in remaining.items() if count >= len(group)]
        if not eligible:
            raise ValueError("cannot assign a leakage group within split capacities")
        chosen = max(
            eligible,
            key=lambda split: (
                original[split],
                remaining[split] / SPLIT_TARGETS[split],
                SPLIT_PRIORITY[split],
            ),
        )
        for index in group:
            assignments[index] = chosen
        remaining[chosen] -= len(group)

    singleton_groups = sorted(
        (group for group in groups if len(group) == 1),
        key=lambda group: rows[group[0]]["slot"]["slot_id"],
    )
    for group in singleton_groups:
        index = group[0]
        original = rows[index]["slot"]["split"]
        if remaining[original] > 0:
            chosen = original
        else:
            chosen = max(
                remaining,
                key=lambda split: (remaining[split], SPLIT_PRIORITY[split]),
            )
        if remaining[chosen] <= 0:
            raise ValueError("cannot complete exact split allocation")
        assignments[index] = chosen
        remaining[chosen] -= 1
    if any(remaining.values()):
        raise ValueError(f"split allocation did not fill targets: {remaining}")
    return assignments


def build_formal_records(
    *,
    rows: list[dict[str, Any]],
    groups: list[list[int]],
    assignments: dict[int, str],
    dataset_version: str,
    submitted_at: datetime,
) -> tuple[list[EvaluationItemV1], list[AnnotationRecordV1]]:
    if submitted_at.tzinfo is None:
        raise ValueError("submitted_at must include a timezone")
    group_ids = {
        index: leakage_group_id(rows, group)
        for group in groups
        for index in group
    }
    items: list[EvaluationItemV1] = []
    annotations: list[AnnotationRecordV1] = []
    for index, row in enumerate(rows):
        slot = row["slot"]
        candidate = row["candidate"]
        execution = row["execution"]
        if execution.get("enable_thinking") is not False:
            raise ValueError(f"{slot['slot_id']}: GPT execution did not disable thinking")
        if execution.get("reasoning_present") is not False:
            raise ValueError(f"{slot['slot_id']}: GPT execution contains reasoning content")
        if execution.get("temperature") != 0:
            raise ValueError(f"{slot['slot_id']}: GPT execution temperature is not zero")
        annotation_id = f"ann.qwen.{slot['slot_id']}"
        split = assignments[index]
        item = EvaluationItemV1.model_validate(
            {
                "schema_version": "retrieval_evaluation_item_v1",
                "dataset_version": dataset_version,
                "question_id": slot["slot_id"],
                "split": split,
                "leakage_group_id": group_ids[index],
                "question": candidate["question"],
                "conversation_history": candidate["conversation_history"],
                "authorized_scope_ids": ["scope_local_3_paper_v1"],
                "question_types": candidate["question_types"],
                "language": slot["language"],
                "query_form": slot["query_form"],
                "expected_route": candidate["expected_route"],
                "expected_filters": {
                    "document_ids": candidate["expected_document_ids"],
                    "year_gte": None,
                    "year_lte": None,
                },
                "answerability": candidate["answerability"],
                "chunk_judgments": candidate["chunk_judgments"],
                "reference_claims": candidate["reference_claims"],
                "acceptable_answer_points": candidate["acceptable_answer_points"],
                "must_not_claim": candidate["must_not_claim"],
                "expected_citations": candidate["expected_citations"],
                "freshness_cutoff": candidate["freshness_cutoff"],
                "difficulty": slot["difficulty"],
                "annotation_status": "GPT_ASSISTED",
                "annotation_record_ids": [annotation_id],
                "final_annotation_id": None,
                "agreement_score": None,
                "blind_holdout": split == "acceptance",
            }
        )
        response_id = row["normalization"].get("source_response_id") or "unknown"
        actions = ",".join(row["normalization"].get("actions", [])) or "NONE"
        annotation = AnnotationRecordV1.model_validate(
            {
                "schema_version": "retrieval_annotation_record_v1",
                "annotation_id": annotation_id,
                "dataset_version": dataset_version,
                "question_id": slot["slot_id"],
                "role": "ANNOTATOR",
                "annotator_id": "qwen3.7-plus.assisted-v1",
                "actor_type": "GPT",
                "model_identity": execution["model"],
                "prompt_version": execution["prompt_version"],
                "temperature": execution["temperature"],
                "submitted_at": submitted_at,
                "answerability": candidate["answerability"],
                "expected_route": candidate["expected_route"],
                "chunk_judgments": candidate["chunk_judgments"],
                "notes": (
                    "Qwen candidate and first-pass labels; thinking disabled. "
                    f"source_response_id={response_id}; normalization_actions={actions}; "
                    f"original_split={slot['split']}; assigned_split={split}. "
                    "Human review remains pending where required by risk policy."
                ),
                "based_on_annotation_ids": [],
            }
        )
        items.append(item)
        annotations.append(annotation)
    return items, annotations


def _quantile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    position = fraction * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _write_jsonl(path: Path, values: list[Any]) -> None:
    path.write_text(
        "".join(
            json.dumps(
                value.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def build_corpus(
    *,
    candidates_path: Path,
    manifest_path: Path,
    embedding_cache_path: Path,
    report_path: Path,
    submitted_at: datetime,
    embedding_model: str = "bge-m3:latest",
    embedding_base_url: str = "http://127.0.0.1:11434",
    embedding_batch_size: int = 32,
) -> dict[str, Any]:
    rows = _load_jsonl(candidates_path)
    if len(rows) != 500:
        raise ValueError(f"expected 500 normalized candidates, found {len(rows)}")
    slot_ids = [row["slot"]["slot_id"] for row in rows]
    if len(slot_ids) != len(set(slot_ids)):
        raise ValueError("normalized candidates contain duplicate slot ids")
    try:
        manifest = EvaluationManifestV1.model_validate(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid evaluation manifest: {exc}") from exc
    if manifest.target_size != 500:
        raise ValueError("assisted corpus importer requires a target_size of 500")
    items_path = manifest_path.parent / manifest.items_path
    if manifest.annotation_records_path is None:
        raise ValueError("manifest must declare an annotation records path")
    annotations_path = manifest_path.parent / manifest.annotation_records_path
    if items_path.read_bytes() or annotations_path.read_bytes():
        raise ValueError("formal workspace is not empty; refusing to overwrite")

    question_vectors, answer_vectors, model_identity = load_or_create_embedding_cache(
        rows=rows,
        cache_path=embedding_cache_path,
        model=embedding_model,
        base_url=embedding_base_url,
        batch_size=embedding_batch_size,
    )
    groups, pairs, reason_counts, similarities = group_candidates(
        rows, question_vectors, answer_vectors
    )
    original_cross_split_groups = [
        group
        for group in groups
        if len({rows[index]["slot"]["split"] for index in group}) > 1
    ]
    assignments = assign_group_splits(rows, groups)
    items, annotations = build_formal_records(
        rows=rows,
        groups=groups,
        assignments=assignments,
        dataset_version=manifest.dataset_version,
        submitted_at=submitted_at,
    )
    _write_jsonl(items_path, items)
    _write_jsonl(annotations_path, annotations)
    manifest_value = manifest.model_dump(mode="json")
    manifest_value["status"] = "ANNOTATION"
    manifest_value["items_sha256"] = sha256_file(items_path)
    manifest_value["annotation_records_sha256"] = sha256_file(annotations_path)
    manifest_path.write_text(
        json.dumps(manifest_value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    sorted_similarities = sorted(similarities)
    group_sizes = Counter(len(group) for group in groups)
    moved = [
        index
        for index, split in assignments.items()
        if rows[index]["slot"]["split"] != split
    ]
    group_id_by_index = {
        index: leakage_group_id(rows, group)
        for group in groups
        for index in group
    }
    acceptance_ids = {item.question_id for item in items if item.split == "acceptance"}
    conflict_ids = {
        item.question_id
        for item in items
        if item.answerability == "CONFLICTING_EVIDENCE"
    }
    expert_ids = {
        item.question_id
        for item in items
        if item.difficulty == "hard" or "standards_freshness" in item.question_types
    }
    negative_or_security_ids = {
        item.question_id
        for item in items
        if item.answerability in {"NO_EVIDENCE", "FORBIDDEN"}
        or "adversarial_security" in item.question_types
    }
    risk_review_ids = (
        acceptance_ids | conflict_ids | expert_ids | negative_or_security_ids
    )
    low_risk_dev_test_ids = {
        item.question_id
        for item in items
        if item.split in {"dev", "test"}
        and item.difficulty != "hard"
        and "standards_freshness" not in item.question_types
    }
    reviewed_low_risk_ids = risk_review_ids & low_risk_dev_test_ids
    report = {
        "schema_version": "assisted_formal_corpus_build_report_v1",
        "status": "GPT_ASSISTED_500_HUMAN_RISK_REVIEW_PENDING",
        "candidate_count": len(rows),
        "item_count": len(items),
        "annotation_count": len(annotations),
        "embedding_model_identity": model_identity,
        "thresholds": {
            "question_similarity": QUESTION_SIMILARITY_THRESHOLD,
            "answer_similarity_same_document": ANSWER_SIMILARITY_THRESHOLD,
            "shared_chunk_question_similarity": SHARED_CHUNK_QUESTION_THRESHOLD,
            "joint_question_similarity": JOINT_QUESTION_THRESHOLD,
            "joint_answer_similarity": JOINT_ANSWER_THRESHOLD,
        },
        "question_similarity_quantiles": {
            str(fraction): round(_quantile(sorted_similarities, fraction), 6)
            for fraction in (0.5, 0.9, 0.95, 0.98, 0.99, 0.995, 0.999)
        },
        "matched_pair_count": len(pairs),
        "matched_pair_reason_counts": reason_counts,
        "matched_pairs": sorted(
            pairs,
            key=lambda pair: (
                -pair["question_similarity"],
                -pair["answer_similarity"],
                pair["left_slot_id"],
                pair["right_slot_id"],
            ),
        ),
        "leakage_group_count": len(groups),
        "multi_item_group_count": sum(len(group) > 1 for group in groups),
        "group_size_counts": {
            str(size): count for size, count in sorted(group_sizes.items())
        },
        "max_group_size": max(group_sizes),
        "cross_split_group_count_before_reassignment": len(
            original_cross_split_groups
        ),
        "cross_split_group_count_after_reassignment": 0,
        "reassigned_item_count": len(moved),
        "split_move_counts": {
            f"{source}->{target}": count
            for (source, target), count in sorted(
                Counter(
                    (rows[index]["slot"]["split"], assignments[index])
                    for index in moved
                ).items()
            )
        },
        "final_split_counts": dict(
            sorted(Counter(assignments.values()).items())
        ),
        "groups": [
            {
                "leakage_group_id": leakage_group_id(rows, group),
                "slot_ids": [rows[index]["slot"]["slot_id"] for index in group],
                "original_splits": dict(
                    sorted(
                        Counter(
                            rows[index]["slot"]["split"] for index in group
                        ).items()
                    )
                ),
                "assigned_split": assignments[group[0]],
            }
            for group in groups
        ],
        "assignment_by_slot_id": {
            rows[index]["slot"]["slot_id"]: {
                "leakage_group_id": group_id_by_index[index],
                "original_split": rows[index]["slot"]["split"],
                "assigned_split": assignments[index],
            }
            for index in range(len(rows))
        },
        "human_review_pending": {
            "acceptance_count": len(acceptance_ids),
            "conflicting_evidence_count": len(conflict_ids),
            "hard_or_standards_count": len(expert_ids),
            "negative_or_security_count": len(negative_or_security_ids),
            "unique_risk_review_count": len(risk_review_ids),
            "risk_review_low_risk_dev_test_count": len(reviewed_low_risk_ids),
            "risk_review_low_risk_dev_test_ratio": round(
                len(reviewed_low_risk_ids) / len(low_risk_dev_test_ids), 6
            ),
            "low_risk_dev_test_audit_min_ratio": 0.10,
        },
        "items_sha256": manifest_value["items_sha256"],
        "annotations_sha256": manifest_value["annotation_records_sha256"],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--embedding-cache", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--submitted-at", required=True)
    parser.add_argument("--embedding-model", default="bge-m3:latest")
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-batch-size", type=int, default=32)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = build_corpus(
            candidates_path=args.candidates,
            manifest_path=args.manifest,
            embedding_cache_path=args.embedding_cache,
            report_path=args.report,
            submitted_at=datetime.fromisoformat(args.submitted_at),
            embedding_model=args.embedding_model,
            embedding_base_url=args.embedding_base_url,
            embedding_batch_size=args.embedding_batch_size,
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"assisted formal corpus build error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "item_count": report["item_count"],
                "leakage_group_count": report["leakage_group_count"],
                "reassigned_item_count": report["reassigned_item_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
