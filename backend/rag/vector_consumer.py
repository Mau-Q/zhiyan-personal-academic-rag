"""RAG consumers for real local dense and RRF retrieval with Fake LLM output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.rag.answer_builder import build_answer
from backend.retrieval.embedding import EmbeddingProvider
from backend.retrieval.hybrid import LocalRrfHybridRetriever
from backend.retrieval.vector import DEFAULT_VECTOR_MIN_SCORE, LocalVectorIndex


VECTOR_EXECUTION_BOUNDARY = "LOCAL_API_REAL_VECTOR_FAKE_LLM"
VECTOR_COMPLETED_WARNING = "LOCAL_REAL_VECTOR_FAKE_LLM"
VECTOR_NO_EVIDENCE_WARNING = "LOCAL_REAL_VECTOR_ONLY"
RRF_EXECUTION_BOUNDARY = "LOCAL_API_RRF_HYBRID_FAKE_LLM"
RRF_COMPLETED_WARNING = "LOCAL_RRF_HYBRID_FAKE_LLM"
RRF_NO_EVIDENCE_WARNING = "LOCAL_RRF_HYBRID_ONLY"


def answer_vector_question(
    question: str,
    scope: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    index: LocalVectorIndex,
    provider: EmbeddingProvider,
    *,
    top_k: int = 3,
    min_score: float = DEFAULT_VECTOR_MIN_SCORE,
) -> dict[str, Any]:
    retrieved = index.retrieve(
        question,
        scope,
        provider,
        top_k=top_k,
        min_score=min_score,
        expected_chunks=chunks,
    )
    return build_answer(
        question,
        scope,
        retrieved,
        execution_boundary=VECTOR_EXECUTION_BOUNDARY,
        completed_warning=VECTOR_COMPLETED_WARNING,
        no_evidence_warning=VECTOR_NO_EVIDENCE_WARNING,
        answer_prefix="依据当前授权本地真实向量证据：",
    )


def answer_rrf_question(
    question: str,
    scope: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    retriever: LocalRrfHybridRetriever,
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
        execution_boundary=RRF_EXECUTION_BOUNDARY,
        completed_warning=RRF_COMPLETED_WARNING,
        no_evidence_warning=RRF_NO_EVIDENCE_WARNING,
        answer_prefix="依据当前授权本地 RRF 混合检索证据：",
    )
