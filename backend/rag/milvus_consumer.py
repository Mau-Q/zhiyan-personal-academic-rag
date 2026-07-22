"""RAG consumer backed by remote Milvus/BGE-M3 and a Fake LLM."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.rag.answer_builder import build_answer
from backend.retrieval.embedding import EmbeddingProvider
from backend.retrieval.milvus import DEFAULT_VECTOR_MIN_SCORE, MilvusVectorIndex


MILVUS_EXECUTION_BOUNDARY = "REMOTE_API_MILVUS_BGE_M3_FAKE_LLM"
MILVUS_COMPLETED_WARNING = "REMOTE_MILVUS_BGE_M3_FAKE_LLM"
MILVUS_NO_EVIDENCE_WARNING = "REMOTE_MILVUS_BGE_M3_ONLY"


def answer_milvus_question(
    question: str,
    scope: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    index: MilvusVectorIndex,
    provider: EmbeddingProvider,
    *,
    top_k: int = 3,
    min_score: float = DEFAULT_VECTOR_MIN_SCORE,
) -> dict[str, Any]:
    retrieved = index.retrieve(
        question, scope, provider, top_k=top_k, min_score=min_score, expected_chunks=chunks
    )
    return build_answer(
        question,
        scope,
        retrieved,
        execution_boundary=MILVUS_EXECUTION_BOUNDARY,
        completed_warning=MILVUS_COMPLETED_WARNING,
        no_evidence_warning=MILVUS_NO_EVIDENCE_WARNING,
        answer_prefix="依据当前授权 Milvus/BGE-M3 向量证据：",
    )
