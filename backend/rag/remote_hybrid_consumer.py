"""RAG consumer backed by remote Elasticsearch + Milvus RRF and a Fake LLM."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.rag.answer_builder import build_answer
from backend.retrieval.remote_hybrid import RemoteRrfHybridRetriever


REMOTE_RRF_EXECUTION_BOUNDARY = "REMOTE_API_ES_MILVUS_RRF_BGE_M3_FAKE_LLM"
REMOTE_RRF_COMPLETED_WARNING = "REMOTE_ES_MILVUS_RRF_BGE_M3_FAKE_LLM"
REMOTE_RRF_NO_EVIDENCE_WARNING = "REMOTE_ES_MILVUS_RRF_BGE_M3_ONLY"


def answer_remote_rrf_question(
    question: str,
    scope: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    retriever: RemoteRrfHybridRetriever,
    *,
    top_k: int = 3,
) -> dict[str, Any]:
    retrieved = retriever.retrieve(
        question,
        scope,
        top_k=top_k,
        expected_chunks=chunks,
    )
    return build_answer(
        question,
        scope,
        retrieved,
        execution_boundary=REMOTE_RRF_EXECUTION_BOUNDARY,
        completed_warning=REMOTE_RRF_COMPLETED_WARNING,
        no_evidence_warning=REMOTE_RRF_NO_EVIDENCE_WARNING,
        answer_prefix="依据当前授权 Elasticsearch + Milvus RRF 证据：",
    )
