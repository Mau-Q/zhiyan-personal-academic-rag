"""Deterministic reciprocal-rank fusion over BM25 and local dense retrieval."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.retrieval.embedding import EmbeddingProvider
from backend.retrieval.sqlite_fts import SQLiteFtsIndex
from backend.retrieval.vector import DEFAULT_VECTOR_MIN_SCORE, LocalVectorIndex


JsonObject = dict[str, Any]
RETRIEVAL_BACKEND = "local_rrf_sqlite_fts5_dense_v1"
DEFAULT_RRF_K = 60
DEFAULT_CANDIDATE_K = 20


class LocalRrfHybridRetriever:
    def __init__(
        self,
        lexical_index: SQLiteFtsIndex,
        vector_index: LocalVectorIndex,
        embedding_provider: EmbeddingProvider,
        *,
        candidate_k: int = DEFAULT_CANDIDATE_K,
        rrf_k: int = DEFAULT_RRF_K,
        vector_min_score: float = DEFAULT_VECTOR_MIN_SCORE,
    ):
        if candidate_k < 1:
            raise ValueError("candidate_k must be at least 1")
        if rrf_k < 1:
            raise ValueError("rrf_k must be at least 1")
        if not -1.0 <= vector_min_score <= 1.0:
            raise ValueError("vector_min_score must be between -1 and 1")
        self.lexical_index = lexical_index
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.candidate_k = candidate_k
        self.rrf_k = rrf_k
        self.vector_min_score = vector_min_score

    def retrieve(
        self,
        question: str,
        scope: Mapping[str, Any],
        *,
        top_k: int = 3,
        expected_chunks: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[JsonObject]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        lexical = self.lexical_index.retrieve(
            question,
            scope,
            top_k=self.candidate_k,
            expected_chunks=expected_chunks,
        )
        vector = self.vector_index.retrieve(
            question,
            scope,
            self.embedding_provider,
            top_k=self.candidate_k,
            min_score=self.vector_min_score,
            expected_chunks=expected_chunks,
        )
        by_id: dict[str, JsonObject] = {}
        scores: dict[str, float] = {}
        best_rank: dict[str, int] = {}
        for ranking in (lexical, vector):
            for rank, chunk in enumerate(ranking, start=1):
                chunk_id = str(chunk["chunk_id"])
                by_id[chunk_id] = chunk
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (self.rrf_k + rank)
                best_rank[chunk_id] = min(best_rank.get(chunk_id, rank), rank)
        ordered_ids = sorted(
            scores,
            key=lambda chunk_id: (-scores[chunk_id], best_rank[chunk_id], chunk_id),
        )
        return [by_id[chunk_id] for chunk_id in ordered_ids[:top_k]]
