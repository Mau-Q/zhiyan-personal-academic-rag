"""RAG consumer for PostgreSQL-READY version routes with a Fake LLM."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from backend.rag.answer_builder import build_answer
from backend.retrieval.online import OnlineVersionRrfRetriever
from backend.retrieval.online_reranker import (
    ONLINE_RERANKER_APPLIED_WARNING,
    ONLINE_RERANKER_EXECUTION_BOUNDARY,
    ONLINE_RERANKER_FALLBACK_WARNING,
    OnlineFixedCrossEncoderReranker,
)


ONLINE_EXECUTION_BOUNDARY = "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_FAKE_LLM"
ONLINE_COMPLETED_WARNING = "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_FAKE_LLM"
ONLINE_NO_EVIDENCE_WARNING = "ONLINE_POSTGRES_READY_NO_EVIDENCE"
ONLINE_RERANKER_FALLBACK_BOUNDARY = (
    "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_RERANKER_FALLBACK_FAKE_LLM"
)


@dataclass(frozen=True)
class OnlineRetrievalObservation:
    reranker_status: str
    reranker_failure_code: str | None
    candidate_count: int
    output_count: int
    base_retrieval_latency_ms: float
    reranker_latency_ms: float
    combined_retrieval_latency_ms: float


def answer_online_ready_question(
    question: str,
    scope: Mapping[str, Any],
    retriever: OnlineVersionRrfRetriever,
    *,
    owner_id: str,
    document_ids: Sequence[str],
    top_k: int = 3,
    reranker: OnlineFixedCrossEncoderReranker | None = None,
    observation_sink: Callable[[OnlineRetrievalObservation], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    retrieved = retriever.retrieve(
        question,
        scope,
        owner_id=owner_id,
        document_ids=document_ids,
        top_k=reranker.config.candidate_top_k if reranker is not None else top_k,
    )
    base_latency_ms = (time.perf_counter() - started) * 1000
    execution_boundary = ONLINE_EXECUTION_BOUNDARY
    completed_warning = ONLINE_COMPLETED_WARNING
    reranker_status = "NOT_CONFIGURED"
    reranker_failure_code = None
    reranker_latency_ms = 0.0
    candidate_count = len(retrieved)
    if reranker is not None:
        outcome = reranker.rerank(
            question,
            retrieved,
            owner_id=owner_id,
            document_ids=document_ids,
            top_k=top_k,
        )
        retrieved = list(outcome.chunks)
        reranker_status = outcome.status
        reranker_failure_code = outcome.failure_code
        reranker_latency_ms = outcome.reranker_latency_ms
        candidate_count = outcome.candidate_count
        if outcome.status == "APPLIED":
            execution_boundary = ONLINE_RERANKER_EXECUTION_BOUNDARY
            completed_warning = ONLINE_RERANKER_APPLIED_WARNING
        elif outcome.status == "FALLBACK":
            execution_boundary = ONLINE_RERANKER_FALLBACK_BOUNDARY
            completed_warning = ONLINE_RERANKER_FALLBACK_WARNING
    combined_latency_ms = (time.perf_counter() - started) * 1000
    if observation_sink is not None:
        observation_sink(
            OnlineRetrievalObservation(
                reranker_status=reranker_status,
                reranker_failure_code=reranker_failure_code,
                candidate_count=candidate_count,
                output_count=len(retrieved),
                base_retrieval_latency_ms=base_latency_ms,
                reranker_latency_ms=reranker_latency_ms,
                combined_retrieval_latency_ms=combined_latency_ms,
            )
        )
    return build_answer(
        question,
        scope,
        retrieved,
        execution_boundary=execution_boundary,
        completed_warning=completed_warning,
        no_evidence_warning=ONLINE_NO_EVIDENCE_WARNING,
        answer_prefix="依据 PostgreSQL READY 门禁下的 ES/Milvus 证据：",
    )
