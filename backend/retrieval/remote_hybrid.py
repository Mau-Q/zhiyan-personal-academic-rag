"""Minimal reciprocal-rank fusion over remote Elasticsearch and Milvus."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.retrieval.elasticsearch import ElasticsearchBm25Index
from backend.retrieval.embedding import EmbeddingProvider
from backend.retrieval.milvus import MilvusVectorIndex
from backend.retrieval.results import RankedChunk, chunks_only, validate_ranking


JsonObject = dict[str, Any]
RETRIEVAL_BACKEND = "remote_rrf_elasticsearch_milvus_v1"


class RemoteRrfHybridRetriever:
    """Fuse two identity-checked authorized rankings without comparing raw scores."""

    def __init__(
        self,
        elasticsearch_index: ElasticsearchBm25Index,
        milvus_index: MilvusVectorIndex,
        embedding_provider: EmbeddingProvider,
        *,
        candidate_k: int = 20,
        rrf_k: int = 60,
        vector_min_score: float = 0.5,
    ):
        if candidate_k < 1 or rrf_k < 1:
            raise ValueError("candidate_k and rrf_k must be at least 1")
        if not -1.0 <= vector_min_score <= 1.0:
            raise ValueError("vector_min_score must be between -1 and 1")
        self.elasticsearch_index = elasticsearch_index
        self.milvus_index = milvus_index
        self.embedding_provider = embedding_provider
        self.candidate_k = candidate_k
        self.rrf_k = rrf_k
        self.vector_min_score = vector_min_score

    def search(
        self,
        question: str,
        scope: Mapping[str, Any],
        *,
        top_k: int = 3,
        expected_chunks: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[RankedChunk]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        rankings = (
            self.elasticsearch_index.search(
                question,
                scope,
                top_k=self.candidate_k,
                expected_chunks=expected_chunks,
            ),
            self.milvus_index.search(
                question,
                scope,
                self.embedding_provider,
                top_k=self.candidate_k,
                min_score=self.vector_min_score,
                expected_chunks=expected_chunks,
            ),
        )
        for ranking in rankings:
            if ranking:
                validate_ranking(ranking, expected_backend=ranking[0].backend)

        by_id: dict[str, JsonObject] = {}
        scores: dict[str, float] = {}
        best_rank: dict[str, int] = {}
        for ranking in rankings:
            for candidate in ranking:
                chunk_id = str(candidate.chunk["chunk_id"])
                existing = by_id.get(chunk_id)
                if existing is not None and existing != candidate.chunk:
                    raise ValueError("remote retrieval candidate payloads disagree")
                by_id[chunk_id] = candidate.chunk
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (
                    self.rrf_k + candidate.rank
                )
                best_rank[chunk_id] = min(
                    best_rank.get(chunk_id, candidate.rank), candidate.rank
                )

        ordered_ids = sorted(
            scores,
            key=lambda chunk_id: (-scores[chunk_id], best_rank[chunk_id], chunk_id),
        )[:top_k]
        fused = [
            RankedChunk(
                backend=RETRIEVAL_BACKEND,
                rank=rank,
                score=scores[chunk_id],
                chunk=by_id[chunk_id],
            )
            for rank, chunk_id in enumerate(ordered_ids, 1)
        ]
        validate_ranking(fused, expected_backend=RETRIEVAL_BACKEND)
        return fused

    def retrieve(
        self,
        question: str,
        scope: Mapping[str, Any],
        *,
        top_k: int = 3,
        expected_chunks: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[JsonObject]:
        return chunks_only(
            self.search(
                question,
                scope,
                top_k=top_k,
                expected_chunks=expected_chunks,
            )
        )
