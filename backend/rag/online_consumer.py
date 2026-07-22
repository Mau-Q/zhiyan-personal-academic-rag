"""RAG consumer for PostgreSQL-READY version routes with a Fake LLM."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.rag.answer_builder import build_answer
from backend.retrieval.online import OnlineVersionRrfRetriever


ONLINE_EXECUTION_BOUNDARY = "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_FAKE_LLM"
ONLINE_COMPLETED_WARNING = "ONLINE_POSTGRES_READY_ES_MILVUS_RRF_FAKE_LLM"
ONLINE_NO_EVIDENCE_WARNING = "ONLINE_POSTGRES_READY_NO_EVIDENCE"


def answer_online_ready_question(
    question: str,
    scope: Mapping[str, Any],
    retriever: OnlineVersionRrfRetriever,
    *,
    owner_id: str,
    document_ids: Sequence[str],
    top_k: int = 3,
) -> dict[str, Any]:
    retrieved = retriever.retrieve(
        question,
        scope,
        owner_id=owner_id,
        document_ids=document_ids,
        top_k=top_k,
    )
    return build_answer(
        question,
        scope,
        retrieved,
        execution_boundary=ONLINE_EXECUTION_BOUNDARY,
        completed_warning=ONLINE_COMPLETED_WARNING,
        no_evidence_warning=ONLINE_NO_EVIDENCE_WARNING,
        answer_prefix="依据 PostgreSQL READY 门禁下的 ES/Milvus 证据：",
    )
