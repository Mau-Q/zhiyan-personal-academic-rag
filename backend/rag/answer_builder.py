"""Shared deterministic RagAnswerV1 construction from already-retrieved chunks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


JsonObject = dict[str, Any]


def request_identity(
    question: str, scope: Mapping[str, Any], execution_boundary: str
) -> tuple[str, str]:
    canonical_scope = json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        f"{execution_boundary}\n{question.strip()}\n{canonical_scope}".encode()
    ).hexdigest()[:20]
    return f"request_{digest}", f"trace_{digest}"


def build_answer(
    question: str,
    scope: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    *,
    execution_boundary: str,
    completed_warning: str,
    no_evidence_warning: str,
    answer_prefix: str,
) -> JsonObject:
    request_id, trace_id = request_identity(question, scope, execution_boundary)
    if not chunks:
        return {
            "request_id": request_id,
            "trace_id": trace_id,
            "status": "NO_EVIDENCE",
            "answer": "当前授权文献范围内没有足够证据回答该问题。",
            "evidence": [],
            "citations": [],
            "warnings": [no_evidence_warning],
        }

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
        "answer": answer_prefix + " ".join(answer_parts),
        "evidence": evidence,
        "citations": citations,
        "warnings": [completed_warning],
    }
