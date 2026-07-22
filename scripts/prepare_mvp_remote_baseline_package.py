#!/usr/bin/env python3
"""Build the private 175-item ES-only and Milvus-only baseline input package."""

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

from backend.evaluation.formal_corpus import load_manifest_and_items, sha256_file
from backend.evaluation.harness import EvaluationCaseV1
from backend.retrieval.fixture import load_chunks, load_scope
from backend.retrieval.remote_config import load_remote_retrieval_config
from scripts.finalize_mvp_human_review import (
    _load_jsonl,
    validate_pre_review_decision,
)
from scripts.prepare_risk_review_package import (
    _serialize_jsonl,
    _sha256_bytes,
    _write_deterministic_zip,
)

EXPECTED_COUNT = 175
BACKEND_WARNINGS = {
    "elasticsearch_bm25": {
        "ANSWERABLE": "REMOTE_ELASTICSEARCH_BM25_FAKE_LLM",
        "NO_EVIDENCE": "REMOTE_ELASTICSEARCH_BM25_ONLY",
    },
    "milvus_vector": {
        "ANSWERABLE": "REMOTE_MILVUS_BGE_M3_FAKE_LLM",
        "NO_EVIDENCE": "REMOTE_MILVUS_BGE_M3_ONLY",
    },
}


def _harness_category(answerability: str) -> str:
    if answerability in {
        "ANSWERABLE",
        "PARTIALLY_ANSWERABLE",
        "CONFLICTING_EVIDENCE",
    }:
        return "ANSWERABLE"
    if answerability == "NO_EVIDENCE":
        return "NO_EVIDENCE"
    if answerability == "FORBIDDEN":
        return "FORBIDDEN"
    raise ValueError(f"unsupported answerability: {answerability}")


def _evidence_targets(labels: dict[str, Any]) -> list[dict[str, Any]]:
    judgment_by_id = {
        value["chunk_id"]: value for value in labels["chunk_judgments"]
    }
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for chunk_id in labels["expected_citations"]:
        judgment = judgment_by_id.get(chunk_id)
        if judgment is None:
            raise ValueError(f"expected citation has no judgment: {chunk_id}")
        identity = (
            judgment["document_id"],
            judgment["page_start"],
            judgment["page_end"],
        )
        if identity in seen:
            continue
        seen.add(identity)
        targets.append(
            {
                "document_id": identity[0],
                "page_start": identity[1],
                "page_end": identity[2],
            }
        )
    return targets


def build_case(
    queue_entry: dict[str, Any],
    decision: dict[str, Any],
    *,
    backend: str,
) -> dict[str, Any]:
    if backend not in BACKEND_WARNINGS:
        raise ValueError(f"unsupported MVP baseline backend: {backend}")
    labels = decision["corrected_labels"]
    answerability = labels["answerability"]
    category = _harness_category(answerability)
    expected: dict[str, Any]
    if category == "ANSWERABLE":
        targets = _evidence_targets(labels)
        if not targets:
            raise ValueError(f"{decision['question_id']}: answerable item has no target")
        expected = {
            "http_status": 200,
            "answer_status": "COMPLETED",
            "min_evidence_count": 1,
            "required_evidence": targets,
            "required_warnings": [BACKEND_WARNINGS[backend]["ANSWERABLE"]],
        }
    elif category == "NO_EVIDENCE":
        expected = {
            "http_status": 200,
            "answer_status": "NO_EVIDENCE",
            "min_evidence_count": 0,
            "max_evidence_count": 0,
            "required_warnings": [BACKEND_WARNINGS[backend]["NO_EVIDENCE"]],
        }
    else:
        expected = {
            "http_status": 403,
            "error_code": "RAG_FORBIDDEN_SCOPE",
            "min_evidence_count": 0,
            "max_evidence_count": 0,
            "forbidden_document_ids": labels["expected_filters"]["document_ids"],
        }
    value = {
        "case_id": decision["question_id"],
        "category": category,
        "question": queue_entry["question"],
        "document_ids": labels["expected_filters"]["document_ids"],
        "expected": expected,
    }
    return EvaluationCaseV1.model_validate(value).model_dump(
        mode="json", exclude_none=True
    )


def prepare_package(
    *,
    source_manifest_path: Path,
    queue_path: Path,
    decisions_path: Path,
    chunks_path: Path,
    scope_path: Path,
    remote_config_path: Path,
    output_dir: Path,
    created_at: datetime,
) -> dict[str, Any]:
    if created_at.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory is not empty; refusing to overwrite")
    queue = _load_jsonl(queue_path)
    decisions = _load_jsonl(decisions_path)
    _, source_items, _ = load_manifest_and_items(source_manifest_path)
    chunks = load_chunks(chunks_path)
    load_scope(scope_path)
    config = load_remote_retrieval_config(remote_config_path)
    if len(queue) != EXPECTED_COUNT or len(decisions) != EXPECTED_COUNT:
        raise ValueError("MVP remote baseline package requires exactly 175 records")
    queue_by_id = {value["question_id"]: value for value in queue}
    decisions_by_id = {value["question_id"]: value for value in decisions}
    source_by_id = {value.question_id: value for value in source_items}
    if len(queue_by_id) != EXPECTED_COUNT or len(decisions_by_id) != EXPECTED_COUNT:
        raise ValueError("MVP baseline inputs contain duplicate question ids")
    if set(queue_by_id) != set(decisions_by_id):
        raise ValueError("MVP queue and decisions do not cover the same questions")

    es_cases: list[dict[str, Any]] = []
    milvus_cases: list[dict[str, Any]] = []
    case_metadata: list[dict[str, Any]] = []
    for queue_entry in queue:
        question_id = queue_entry["question_id"]
        decision = decisions_by_id[question_id]
        source_item = source_by_id.get(question_id)
        if source_item is None:
            raise ValueError(f"{question_id}: source item is missing")
        validate_pre_review_decision(
            decision,
            queue_entry=queue_entry,
            source_item=source_item,
        )
        if decision["reviewer_id"].lower().startswith("ai"):
            raise ValueError(f"{question_id}: AI pre-review is not human validation")
        if queue_entry["required_reviewer_mode"] == "HUMAN_EXPERT":
            if decision["expert_confirmation"] != "APPROVE":
                raise ValueError(f"{question_id}: expert sign-off is incomplete")
        es_cases.append(build_case(queue_entry, decision, backend="elasticsearch_bm25"))
        milvus_cases.append(build_case(queue_entry, decision, backend="milvus_vector"))
        case_metadata.append(
            {
                "case_id": question_id,
                "mvp_split": queue_entry["mvp_split"],
                "selected_category": queue_entry["selected_category"],
                "source_answerability": decision["corrected_labels"]["answerability"],
            }
        )

    es_bytes = _serialize_jsonl(es_cases)
    milvus_bytes = _serialize_jsonl(milvus_cases)
    metadata_bytes = _serialize_jsonl(case_metadata)
    category_counts = Counter(value["selected_category"] for value in case_metadata)
    split_counts = Counter(value["mvp_split"] for value in case_metadata)
    answerability_counts = Counter(value["source_answerability"] for value in case_metadata)
    summary = {
        "schema_version": "mvp_remote_baseline_input_summary_v1",
        "status": "MVP_175_REMOTE_ES_MILVUS_BASELINE_INPUT_READY",
        "created_at": created_at.isoformat(),
        "case_count": len(es_cases),
        "category_counts": dict(sorted(category_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "answerability_counts": dict(sorted(answerability_counts.items())),
        "chunks_sha256": sha256_file(chunks_path),
        "chunk_count": len(chunks),
        "scope_sha256": sha256_file(scope_path),
        "queue_sha256": sha256_file(queue_path),
        "human_decisions_sha256": sha256_file(decisions_path),
        "remote_config_sha256": sha256_file(remote_config_path),
        "elasticsearch_index": config.elasticsearch.index,
        "milvus_collection": config.milvus.collection,
        "embedding_model": config.milvus.embedding_model,
        "top_k": config.fusion.top_k,
        "vector_min_score": config.fusion.vector_min_score,
    }
    summary_bytes = (
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    files = {
        "authorized-scope-v1.json": scope_path.read_bytes(),
        "cases-elasticsearch-v1.jsonl": es_bytes,
        "cases-milvus-v1.jsonl": milvus_bytes,
        "case-metadata-v1.jsonl": metadata_bytes,
        "chunks-v1.json": chunks_path.read_bytes(),
        "mvp-initial-review-decisions-v1.jsonl": decisions_path.read_bytes(),
        "mvp-initial-review-queue-v1.jsonl": queue_path.read_bytes(),
        "remote-retrieval-config-v1.json": remote_config_path.read_bytes(),
        "baseline-input-summary.json": summary_bytes,
    }
    files["SHA256SUMS"] = "".join(
        f"{_sha256_bytes(value)}  {name}\n" for name, value in sorted(files.items())
    ).encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (output_dir / name).write_bytes(value)
    zip_path = output_dir / "mvp-175-remote-baseline-input-v1.zip"
    _write_deterministic_zip(zip_path, files, created_at)
    report = {
        **summary,
        "elasticsearch_cases_sha256": _sha256_bytes(es_bytes),
        "milvus_cases_sha256": _sha256_bytes(milvus_bytes),
        "zip_sha256": sha256_file(zip_path),
        "zip_members": sorted(files),
    }
    (output_dir / "package-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--remote-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--created-at", required=True)
    args = parser.parse_args()
    try:
        report = prepare_package(
            source_manifest_path=args.source_manifest,
            queue_path=args.queue,
            decisions_path=args.decisions,
            chunks_path=args.chunks,
            scope_path=args.scope,
            remote_config_path=args.remote_config,
            output_dir=args.output_dir,
            created_at=datetime.fromisoformat(args.created_at),
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"MVP remote baseline package error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
