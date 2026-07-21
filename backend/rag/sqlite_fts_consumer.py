"""RAG consumer that uses the local SQLite FTS5/BM25 index and Fake LLM output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.rag.answer_builder import build_answer
from backend.retrieval.sqlite_fts import SQLiteFtsIndex


SQLITE_FTS_EXECUTION_BOUNDARY = "LOCAL_API_SQLITE_FTS5_FAKE_LLM"
SQLITE_FTS_COMPLETED_WARNING = "LOCAL_SQLITE_FTS5_FAKE_LLM"
SQLITE_FTS_NO_EVIDENCE_WARNING = "LOCAL_SQLITE_FTS5_ONLY"


def answer_sqlite_fts_question(
    question: str,
    scope: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    index: SQLiteFtsIndex,
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
        execution_boundary=SQLITE_FTS_EXECUTION_BOUNDARY,
        completed_warning=SQLITE_FTS_COMPLETED_WARNING,
        no_evidence_warning=SQLITE_FTS_NO_EVIDENCE_WARNING,
        answer_prefix="依据当前授权 SQLite FTS5 证据：",
    )
