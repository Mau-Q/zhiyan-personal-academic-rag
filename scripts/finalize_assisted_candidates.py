#!/usr/bin/env python3
"""Merge, normalize, and validate Qwen-assisted evaluation candidates."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.formal_corpus import EvaluationItemV1


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
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


def load_requests(batch_dir: Path) -> dict[str, dict[str, Any]]:
    requests: dict[str, dict[str, Any]] = {}
    for path in sorted(batch_dir.glob("batch-*.jsonl")):
        for value in _load_jsonl(path):
            if value.get("schema_version") != "assisted_question_generation_request_v1":
                raise ValueError(f"unsupported request schema in {path}")
            slot_id = value["slot"]["slot_id"]
            if slot_id in requests:
                raise ValueError(f"duplicate request slot id: {slot_id}")
            requests[slot_id] = value
    if len(requests) != 500:
        raise ValueError(f"expected 500 requests, found {len(requests)}")
    return requests


def _result_map(path: Path) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for item in _load_jsonl(path):
        slot_id = item["candidate"]["slot_id"]
        if slot_id in values:
            raise ValueError(f"duplicate result slot id in {path}: {slot_id}")
        values[slot_id] = item
    return values


def merge_results(
    raw_results: Path, repair_results: list[Path]
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    merged = _result_map(raw_results)
    source_version = {slot_id: "raw" for slot_id in merged}
    for index, path in enumerate(repair_results, start=1):
        for slot_id, item in _result_map(path).items():
            if slot_id not in merged:
                raise ValueError(f"repair references unknown slot id: {slot_id}")
            merged[slot_id] = item
            source_version[slot_id] = f"repair_v{index}"
    counts = Counter(source_version.values())
    return merged, dict(sorted(counts.items()))


def normalize_candidate(
    *,
    request: dict[str, Any],
    result: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    candidate = json.loads(json.dumps(result["candidate"], ensure_ascii=False))
    slot = request["slot"]
    actions: list[str] = []
    primary_type = slot["primary_question_type"]
    if candidate["question_types"] != [primary_type]:
        actions.append("SET_PRIMARY_QUESTION_TYPE_FROM_SLOT")
    candidate["question_types"] = [primary_type]
    if candidate["expected_route"] != "HYBRID_QA":
        actions.append("SET_EXPECTED_ROUTE_HYBRID_QA")
    candidate["expected_route"] = "HYBRID_QA"
    if candidate["answerability"] != slot["answerability"]:
        raise ValueError(f"{slot['slot_id']}: answerability still drifts after repair")

    allowed_chunks = {
        value["chunk_id"]: value for value in request["evidence_chunks"]
    }
    claims: list[dict[str, Any]] = []
    seen_claims: set[str] = set()
    for claim in candidate["reference_claims"]:
        if not isinstance(claim, dict):
            raise ValueError(f"{slot['slot_id']}: reference claim must be an object")
        claim_id = claim.get("claim_id")
        text = claim.get("text")
        if not isinstance(claim_id, str) or not isinstance(text, str) or not text.strip():
            raise ValueError(f"{slot['slot_id']}: invalid reference claim")
        if claim_id in seen_claims:
            actions.append("DROP_DUPLICATE_REFERENCE_CLAIM")
            continue
        seen_claims.add(claim_id)
        if not isinstance(claim.get("required"), bool):
            claim["required"] = True
            actions.append("DEFAULT_REFERENCE_CLAIM_REQUIRED_TRUE")
        claims.append(claim)
    candidate["reference_claims"] = claims

    judgments: list[dict[str, Any]] = []
    seen_chunks: set[str] = set()
    for judgment in candidate["chunk_judgments"]:
        if not isinstance(judgment, dict):
            raise ValueError(f"{slot['slot_id']}: chunk judgment must be an object")
        chunk_id = judgment.get("chunk_id")
        if chunk_id not in allowed_chunks:
            raise ValueError(f"{slot['slot_id']}: judgment references unknown chunk")
        if chunk_id in seen_chunks:
            actions.append("DROP_DUPLICATE_CHUNK_JUDGMENT")
            continue
        seen_chunks.add(chunk_id)
        source = allowed_chunks[chunk_id]
        canonical_metadata = (
            source["document_id"],
            source["page_start"],
            source["page_end"],
        )
        current_metadata = (
            judgment.get("document_id"),
            judgment.get("page_start"),
            judgment.get("page_end"),
        )
        if current_metadata != canonical_metadata:
            actions.append("CANONICALIZE_CHUNK_METADATA_FROM_SOURCE")
        judgment["document_id"] = source["document_id"]
        judgment["page_start"] = source["page_start"]
        judgment["page_end"] = source["page_end"]
        supports = judgment.get("supports_claims", [])
        if not isinstance(supports, list):
            raise ValueError(f"{slot['slot_id']}: supports_claims must be a list")
        normalized_supports = list(
            dict.fromkeys(
                value
                for value in supports
                if isinstance(value, str) and value in seen_claims
            )
        )
        if normalized_supports != supports:
            actions.append("FILTER_UNKNOWN_OR_DUPLICATE_CLAIM_LINKS")
        judgment["supports_claims"] = normalized_supports
        if candidate["answerability"] in {"NO_EVIDENCE", "FORBIDDEN"}:
            relevance = int(judgment.get("relevance", 0))
            if relevance > 1 or judgment["supports_claims"]:
                actions.append("ENFORCE_NON_SUPPORTING_NEGATIVE_JUDGMENT")
            judgment["relevance"] = min(relevance, 1)
            judgment["supports_claims"] = []
        judgments.append(judgment)
    candidate["chunk_judgments"] = judgments

    if candidate["answerability"] in {"NO_EVIDENCE", "FORBIDDEN"}:
        if candidate["reference_claims"] or candidate["acceptable_answer_points"]:
            actions.append("CLEAR_SUPPORT_CONTENT_FOR_NEGATIVE_ITEM")
        candidate["reference_claims"] = []
        candidate["acceptable_answer_points"] = []
    relevant_chunks = [
        judgment["chunk_id"]
        for judgment in judgments
        if judgment.get("relevance", 0) >= 2
    ]
    if candidate["expected_citations"] != relevant_chunks:
        actions.append("DERIVE_EXPECTED_CITATIONS_FROM_RELEVANT_JUDGMENTS")
    candidate["expected_citations"] = relevant_chunks
    source_documents = list(dict.fromkeys(slot["source_document_ids"]))
    if candidate["expected_document_ids"] != source_documents:
        actions.append("SET_EXPECTED_DOCUMENTS_FROM_SLOT")
    candidate["expected_document_ids"] = source_documents
    candidate["conversation_history"] = [
        value
        for value in candidate["conversation_history"]
        if isinstance(value, dict)
        and value.get("role") in {"user", "assistant"}
        and isinstance(value.get("content"), str)
        and value["content"].strip()
    ]
    candidate["acceptable_answer_points"] = [
        value for value in candidate["acceptable_answer_points"] if isinstance(value, str)
    ]
    candidate["must_not_claim"] = [
        value for value in candidate["must_not_claim"] if isinstance(value, str)
    ]
    return candidate, list(dict.fromkeys(actions))


def build_draft_item(
    *, request: dict[str, Any], candidate: dict[str, Any]
) -> EvaluationItemV1:
    slot = request["slot"]
    return EvaluationItemV1.model_validate(
        {
            "schema_version": "retrieval_evaluation_item_v1",
            "dataset_version": "local-3-paper-assisted-v1",
            "question_id": slot["slot_id"],
            "split": slot["split"],
            "leakage_group_id": f"leakage.{slot['slot_id']}",
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
            "annotation_status": "DRAFT",
            "annotation_record_ids": [],
            "final_annotation_id": None,
            "agreement_score": None,
            "blind_holdout": slot["blind_holdout"],
        }
    )


def finalize(
    *,
    batch_dir: Path,
    raw_results: Path,
    repair_results: list[Path],
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory is not empty; refusing to overwrite")
    requests = load_requests(batch_dir)
    merged, source_counts = merge_results(raw_results, repair_results)
    if set(merged) != set(requests):
        raise ValueError("result slot coverage does not match request slot coverage")
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_values: list[dict[str, Any]] = []
    draft_items: list[EvaluationItemV1] = []
    action_counts: Counter[str] = Counter()
    questions: defaultdict[str, list[str]] = defaultdict(list)
    semantic_review_slots: list[str] = []
    for slot_id in sorted(requests):
        result = merged[slot_id]
        candidate, actions = normalize_candidate(
            request=requests[slot_id], result=result
        )
        draft_item = build_draft_item(request=requests[slot_id], candidate=candidate)
        for action in actions:
            action_counts[action] += 1
        normalized_question = " ".join(candidate["question"].split()).casefold()
        questions[normalized_question].append(slot_id)
        if candidate["answerability"] == "CONFLICTING_EVIDENCE":
            semantic_review_slots.append(slot_id)
        normalized_values.append(
            {
                "schema_version": "assisted_question_normalized_candidate_v1",
                "slot": requests[slot_id]["slot"],
                "candidate": candidate,
                "execution": result["execution"],
                "normalization": {
                    "actions": actions,
                    "source_response_id": result["execution"].get("response_id"),
                },
            }
        )
        draft_items.append(draft_item)
    duplicate_groups = [value for value in questions.values() if len(value) > 1]
    if duplicate_groups:
        raise ValueError(f"normalized questions still contain duplicates: {duplicate_groups}")
    (output_dir / "normalized-candidates-v1.jsonl").write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
            for value in normalized_values
        ),
        encoding="utf-8",
    )
    (output_dir / "draft-items-v1.jsonl").write_text(
        "".join(
            json.dumps(
                item.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
            for item in draft_items
        ),
        encoding="utf-8",
    )
    report = {
        "schema_version": "assisted_candidate_finalization_report_v1",
        "target_count": 500,
        "normalized_candidate_count": len(normalized_values),
        "formal_draft_item_count": len(draft_items),
        "unique_question_count": len(questions),
        "source_result_counts": source_counts,
        "normalization_action_counts": dict(sorted(action_counts.items())),
        "semantic_review_required_count": len(semantic_review_slots),
        "semantic_review_slot_ids": semantic_review_slots,
        "status": "PASS_WITH_TARGETED_HUMAN_REVIEW_PENDING",
    }
    (output_dir / "finalization-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--raw-results", type=Path, required=True)
    parser.add_argument("--repair-results", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = finalize(
            batch_dir=args.batch_dir,
            raw_results=args.raw_results,
            repair_results=args.repair_results,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"assisted candidate finalization error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
