#!/usr/bin/env python3
"""Freeze a local ChunkRecordV1 snapshot and initialize a 500-item workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.formal_corpus import EvaluationManifestV1, validate_corpus
from backend.ingestion.models import ChunkRecordV1


TARGET_SIZE = 500
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
STRATIFICATION_TARGETS = [
    {"question_type": "exact_lookup", "min_ratio": 0.08, "max_ratio": 0.12},
    {"question_type": "single_document_fact", "min_ratio": 0.12, "max_ratio": 0.18},
    {
        "question_type": "single_document_explanation",
        "min_ratio": 0.08,
        "max_ratio": 0.12,
    },
    {
        "question_type": "cross_document_semantic",
        "min_ratio": 0.12,
        "max_ratio": 0.18,
    },
    {"question_type": "comparison", "min_ratio": 0.08, "max_ratio": 0.12},
    {"question_type": "multi_hop", "min_ratio": 0.08, "max_ratio": 0.12},
    {
        "question_type": "teaching_explanation",
        "min_ratio": 0.03,
        "max_ratio": 0.07,
    },
    {
        "question_type": "standards_freshness",
        "min_ratio": 0.08,
        "max_ratio": 0.12,
    },
    {
        "question_type": "no_answer_evidence_insufficient",
        "min_ratio": 0.10,
        "max_ratio": 0.20,
    },
    {
        "question_type": "adversarial_security",
        "min_ratio": 0.05,
        "max_ratio": 0.10,
    },
]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _load_chunks(path: Path) -> list[ChunkRecordV1]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read chunk snapshot: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("chunk snapshot must be a non-empty JSON array")
    try:
        chunks = [ChunkRecordV1.model_validate(record) for record in payload]
    except ValidationError as exc:
        raise ValueError(f"chunk snapshot violates ChunkRecordV1: {exc}") from exc
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("chunk snapshot contains duplicate chunk_id values")
    if any(not chunk.is_active for chunk in chunks):
        raise ValueError("evaluation source snapshot cannot contain inactive chunks")
    return chunks


def _document_summaries(chunks: list[ChunkRecordV1]) -> list[dict[str, Any]]:
    by_document: dict[str, list[ChunkRecordV1]] = defaultdict(list)
    for chunk in chunks:
        by_document[chunk.document_id].append(chunk)
    summaries: list[dict[str, Any]] = []
    for document_id, records in sorted(by_document.items()):
        ordered = sorted(records, key=lambda value: value.chunk_id)
        summaries.append(
            {
                "document_id": document_id,
                "version_ids": sorted({record.version_id for record in ordered}),
                "chunk_count": len(ordered),
                "page_start": min(record.page_start for record in ordered),
                "page_end": max(record.page_end for record in ordered),
                "document_chunk_content_sha256": _canonical_sha256(
                    [
                        {
                            "chunk_id": record.chunk_id,
                            "page_start": record.page_start,
                            "page_end": record.page_end,
                            "section_path": record.section_path,
                            "text": record.text,
                        }
                        for record in ordered
                    ]
                ),
            }
        )
    return summaries


def initialize_workspace(
    *,
    chunks_path: Path,
    output_dir: Path,
    corpus_id: str,
    dataset_id: str,
    dataset_version: str,
    created_at: datetime,
) -> dict[str, Any]:
    if created_at.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory is not empty; refusing to overwrite")
    chunks = _load_chunks(chunks_path)
    chunk_bytes = chunks_path.read_bytes()
    chunk_snapshot_sha256 = _sha256_bytes(chunk_bytes)
    documents = _document_summaries(chunks)
    corpus_sha256 = _canonical_sha256(documents)

    output_dir.mkdir(parents=True, exist_ok=True)
    items_path = output_dir / "items-v1.jsonl"
    annotations_path = output_dir / "annotations-v1.jsonl"
    items_path.write_bytes(b"")
    annotations_path.write_bytes(b"")

    source_snapshot = {
        "schema_version": "evaluation_source_snapshot_v1",
        "corpus_id": corpus_id,
        "corpus_sha256": corpus_sha256,
        "chunk_snapshot_sha256": chunk_snapshot_sha256,
        "created_at": created_at.isoformat(),
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "documents": documents,
        "boundary": "LOCAL_PRIVATE_RUNTIME_SOURCE_ONLY",
    }
    (output_dir / "source-snapshot-v1.json").write_text(
        json.dumps(source_snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest_payload = {
        "schema_version": "retrieval_evaluation_manifest_v1",
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "status": "DATA_COLLECTION",
        "target_size": TARGET_SIZE,
        "source_snapshot": {
            "corpus_id": corpus_id,
            "corpus_sha256": corpus_sha256,
            "chunk_snapshot_sha256": chunk_snapshot_sha256,
            "created_at": created_at.isoformat(),
        },
        "items_path": items_path.name,
        "items_sha256": EMPTY_SHA256,
        "annotation_records_path": annotations_path.name,
        "annotation_records_sha256": EMPTY_SHA256,
        "split_policy": {
            "dev_ratio": 0.6,
            "test_ratio": 0.2,
            "acceptance_ratio": 0.2,
            "ratio_tolerance": 0.02,
            "acceptance_blind": True,
            "online_hard_cases_separate": True,
        },
        "stratification_targets": STRATIFICATION_TARGETS,
        "quality_gates": {
            "minimum_independent_annotators": 2,
            "relevance_scale": "0_3",
            "expert_review_question_types": ["standards_freshness"],
            "expert_review_difficulties": ["hard"],
        },
    }
    manifest = EvaluationManifestV1.model_validate(manifest_payload)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    report = validate_corpus(manifest_path)
    initialization_report = {
        "schema_version": "assisted_evaluation_initialization_report_v1",
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "source_document_count": len(documents),
        "source_chunk_count": len(chunks),
        "target_size": TARGET_SIZE,
        "item_count": 0,
        "status": "SOURCE_FROZEN_DATA_COLLECTION_PENDING",
        "engineering_ready": report["engineering_ready"],
        "lock_ready": report["lock_ready"],
    }
    (output_dir / "initialization-report.json").write_text(
        json.dumps(initialization_report, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return initialization_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize a GPT-assisted 500-item evaluation workspace"
    )
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--created-at", type=datetime.fromisoformat, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = initialize_workspace(
            chunks_path=args.chunks,
            output_dir=args.output_dir,
            corpus_id=args.corpus_id,
            dataset_id=args.dataset_id,
            dataset_version=args.dataset_version,
            created_at=args.created_at,
        )
    except (OSError, ValueError, ValidationError) as exc:
        print(f"evaluation workspace initialization error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
