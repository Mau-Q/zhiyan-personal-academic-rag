"""RAG consumer backed by remote Elasticsearch BM25 and a Fake LLM."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.rag.answer_builder import build_answer
from backend.retrieval.elasticsearch import ElasticsearchBm25Index


ELASTICSEARCH_EXECUTION_BOUNDARY = "REMOTE_API_ELASTICSEARCH_BM25_FAKE_LLM"
ELASTICSEARCH_COMPLETED_WARNING = "REMOTE_ELASTICSEARCH_BM25_FAKE_LLM"
ELASTICSEARCH_NO_EVIDENCE_WARNING = "REMOTE_ELASTICSEARCH_BM25_ONLY"


def answer_elasticsearch_question(
    question: str,
    scope: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    index: ElasticsearchBm25Index,
    *,
    top_k: int = 3,
) -> dict[str, Any]:
    retrieved = index.retrieve(
        question,
        scope,
        top_k=top_k,
        expected_chunks=chunks,
    )
    return build_answer(
        question,
        scope,
        retrieved,
        execution_boundary=ELASTICSEARCH_EXECUTION_BOUNDARY,
        completed_warning=ELASTICSEARCH_COMPLETED_WARNING,
        no_evidence_warning=ELASTICSEARCH_NO_EVIDENCE_WARNING,
        answer_prefix="依据当前授权 Elasticsearch BM25 证据：",
    )

