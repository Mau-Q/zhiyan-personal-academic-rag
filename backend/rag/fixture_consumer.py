"""Deterministic member-A consumer for the Stage 0 RAG contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.retrieval.fixture import load_chunks, load_scope, retrieve_chunks


JsonObject = dict[str, Any]


def _request_identity(question: str, scope: Mapping[str, Any]) -> tuple[str, str]:
    canonical_scope = json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{question.strip()}\n{canonical_scope}".encode()).hexdigest()[:20]
    return f"request_{digest}", f"trace_{digest}"


def _no_evidence_answer(request_id: str, trace_id: str) -> JsonObject:
    return {
        "request_id": request_id,
        "trace_id": trace_id,
        "status": "NO_EVIDENCE",
        "answer": "当前授权文献范围内没有足够证据回答该问题。",
        "evidence": [],
        "citations": [],
        "warnings": ["FIXTURE_ONLY"],
    }


def _completed_answer(
    request_id: str, trace_id: str, chunks: Sequence[Mapping[str, Any]]
) -> JsonObject:
    evidence: list[JsonObject] = []
    citations: list[JsonObject] = []
    answer_parts: list[str] = []

    for position, chunk in enumerate(chunks, start=1):
        evidence_id = f"evidence_{position:03d}"
        citation_id = f"citation_{position:03d}"
        evidence.append(
            {
                "evidence_id": evidence_id,
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk["document_id"],
                "version_id": chunk["version_id"],
                "section_path": chunk["section_path"],
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "quote": chunk["text"],
            }
        )
        citations.append(
            {
                "citation_id": citation_id,
                "evidence_id": evidence_id,
                "document_id": chunk["document_id"],
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
            }
        )
        answer_parts.append(f"{chunk['text']} [{position}]")

    return {
        "request_id": request_id,
        "trace_id": trace_id,
        "status": "COMPLETED",
        "answer": "依据当前授权 Fixture 证据：" + " ".join(answer_parts),
        "evidence": evidence,
        "citations": citations,
        "warnings": ["FIXTURE_ONLY_FAKE_LLM"],
    }


def answer_fixture_question(
    question: str,
    scope: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    *,
    top_k: int = 3,
) -> JsonObject:
    """Return a deterministic RagAnswerV1 from authorized fixture chunks."""

    request_id, trace_id = _request_identity(question, scope)
    retrieved = retrieve_chunks(question, chunks, scope, top_k=top_k)
    if not retrieved:
        return _no_evidence_answer(request_id, trace_id)
    return _completed_answer(request_id, trace_id, retrieved)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Stage 0 fixture-only RAG consumer")
    parser.add_argument(
        "--question", required=True, help="Question to match against authorized chunks"
    )
    parser.add_argument(
        "--scope",
        type=Path,
        default=Path("fixtures/authorized-scope-v1.json"),
        help="AuthorizedScopeV1 JSON path",
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=Path("fixtures/chunks-v1.json"),
        help="ChunkRecordV1 fixture array path",
    )
    parser.add_argument("--top-k", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    answer = answer_fixture_question(
        args.question,
        load_scope(args.scope),
        load_chunks(args.chunks),
        top_k=args.top_k,
    )
    print(json.dumps(answer, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
