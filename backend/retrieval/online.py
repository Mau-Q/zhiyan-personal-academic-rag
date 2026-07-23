"""PostgreSQL-READY routing over version-scoped Elasticsearch and Milvus indexes."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol

from backend.retrieval.elasticsearch import (
    ElasticsearchBm25Index,
    ElasticsearchSearchLatencyBreakdown,
    ElasticsearchTransport,
)
from backend.retrieval.embedding import EmbeddingProvider
from backend.retrieval.milvus import (
    DEFAULT_VECTOR_MIN_SCORE,
    MilvusSearchLatencyBreakdown,
    MilvusTransport,
    MilvusVectorIndex,
)
from backend.retrieval.results import RankedChunk, chunks_only, validate_ranking
from backend.ingestion.models import ChunkRecordV1
from backend.storage.models import DocumentVersionLifecycleV1, LifecycleStatus


JsonObject = dict[str, Any]
ONLINE_RETRIEVAL_BACKEND = "online_ready_es_milvus_rrf_v1"
_CONTRACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class OnlineVisibilityError(RuntimeError):
    """Base failure for online scope or route proof."""


class OnlineScopeForbiddenError(OnlineVisibilityError):
    """Raised when requested documents are not READY for the authenticated owner."""


class OnlineVisibilityUnavailableError(OnlineVisibilityError):
    """Raised when PostgreSQL or either physical index route cannot be proven."""


class ReadyVersionRepository(Protocol):
    def resolve_online_versions(
        self, *, owner_id: str, document_ids: Sequence[str] = ()
    ) -> tuple[DocumentVersionLifecycleV1, ...]: ...


class VersionRouteInspector(Protocol):
    def verify_online_version(
        self,
        *,
        owner_id: str,
        document_id: str,
        document_version_id: str,
    ) -> str: ...


class ReadyChunkSnapshotRepository(Protocol):
    def load_online_chunks(
        self,
        *,
        owner_id: str,
        document_version_ids: Sequence[str],
    ) -> tuple[ChunkRecordV1, ...]: ...


@dataclass(frozen=True)
class OnlineVersionRoute:
    owner_id: str
    document_id: str
    document_version_id: str
    elasticsearch_index: str
    milvus_collection: str


@dataclass(frozen=True)
class OnlineRetrievalLatencyBreakdown:
    route_count: int
    ready_route_resolution_latency_ms: float
    chunk_snapshot_latency_ms: float
    elasticsearch_validation_work_latency_ms: float
    elasticsearch_query_work_latency_ms: float
    elasticsearch_total_work_latency_ms: float
    milvus_validation_work_latency_ms: float
    query_embedding_work_latency_ms: float
    milvus_ann_search_work_latency_ms: float
    milvus_total_work_latency_ms: float
    backend_parallel_wall_latency_ms: float
    ready_revalidation_latency_ms: float
    rrf_fusion_latency_ms: float
    total_latency_ms: float


class PostgresReadyRouteResolver:
    """Resolve physical routes only from exact active PostgreSQL versions."""

    def __init__(
        self,
        *,
        repository: ReadyVersionRepository,
        elasticsearch: VersionRouteInspector,
        milvus: VersionRouteInspector,
    ) -> None:
        self.repository = repository
        self.elasticsearch = elasticsearch
        self.milvus = milvus

    def resolve(
        self, *, owner_id: str, document_ids: Sequence[str]
    ) -> tuple[OnlineVersionRoute, ...]:
        requested = tuple(document_ids)
        if not _CONTRACT_ID_PATTERN.fullmatch(owner_id):
            raise OnlineScopeForbiddenError("authenticated owner identity is invalid")
        if len(requested) != len(set(requested)) or any(
            not _CONTRACT_ID_PATTERN.fullmatch(document_id)
            for document_id in requested
        ):
            raise OnlineScopeForbiddenError("requested document scope is invalid")
        try:
            versions = self.repository.resolve_online_versions(
                owner_id=owner_id,
                document_ids=requested,
            )
        except Exception as exc:
            raise OnlineVisibilityUnavailableError(
                "PostgreSQL READY visibility could not be resolved"
            ) from exc

        by_document: dict[str, DocumentVersionLifecycleV1] = {}
        for version in versions:
            if (
                version.owner_id != owner_id
                or version.lifecycle_status is not LifecycleStatus.READY
                or not version.is_active
                or version.document_id in by_document
            ):
                raise OnlineVisibilityUnavailableError(
                    "PostgreSQL returned inconsistent online version truth"
                )
            by_document[version.document_id] = version
        if requested and set(requested) != set(by_document):
            raise OnlineScopeForbiddenError(
                "one or more requested documents are not online for this owner"
            )

        routes: list[OnlineVersionRoute] = []
        for document_id in sorted(by_document):
            version = by_document[document_id]
            try:
                elasticsearch_index = self.elasticsearch.verify_online_version(
                    owner_id=owner_id,
                    document_id=document_id,
                    document_version_id=version.document_version_id,
                )
                milvus_collection = self.milvus.verify_online_version(
                    owner_id=owner_id,
                    document_id=document_id,
                    document_version_id=version.document_version_id,
                )
            except Exception as exc:
                raise OnlineVisibilityUnavailableError(
                    "READY version physical index route could not be verified"
                ) from exc
            routes.append(
                OnlineVersionRoute(
                    owner_id=owner_id,
                    document_id=document_id,
                    document_version_id=version.document_version_id,
                    elasticsearch_index=elasticsearch_index,
                    milvus_collection=milvus_collection,
                )
            )
        return tuple(routes)

    def revalidate(
        self,
        routes: Sequence[OnlineVersionRoute],
        *,
        owner_id: str,
        document_ids: Sequence[str],
    ) -> None:
        """Recheck PostgreSQL truth after retrieval to close the invalidation race."""

        try:
            versions = self.repository.resolve_online_versions(
                owner_id=owner_id,
                document_ids=document_ids,
            )
        except Exception as exc:
            raise OnlineVisibilityUnavailableError(
                "PostgreSQL READY visibility could not be revalidated"
            ) from exc
        expected = {
            (route.document_id, route.document_version_id)
            for route in routes
        }
        current = {
            (version.document_id, version.document_version_id)
            for version in versions
            if version.owner_id == owner_id
            and version.lifecycle_status is LifecycleStatus.READY
            and version.is_active
        }
        if current != expected or len(current) != len(versions):
            raise OnlineVisibilityUnavailableError(
                "PostgreSQL READY visibility changed during retrieval"
            )


class OnlineVersionRrfRetriever:
    """Search every READY version route and fuse backend-local ranks."""

    def __init__(
        self,
        *,
        resolver: PostgresReadyRouteResolver,
        elasticsearch_transport: ElasticsearchTransport,
        milvus_transport: MilvusTransport,
        embedding_provider: EmbeddingProvider,
        chunk_snapshots: ReadyChunkSnapshotRepository,
        candidate_k: int = 20,
        rrf_k: int = 60,
        vector_min_score: float = DEFAULT_VECTOR_MIN_SCORE,
        latency_observer: (
            Callable[[OnlineRetrievalLatencyBreakdown], None] | None
        ) = None,
    ) -> None:
        if candidate_k < 1 or rrf_k < 1:
            raise ValueError("online candidate_k and rrf_k must be positive")
        if not -1.0 <= vector_min_score <= 1.0:
            raise ValueError("online vector_min_score must be between -1 and 1")
        self.resolver = resolver
        self.elasticsearch_transport = elasticsearch_transport
        self.milvus_transport = milvus_transport
        self.embedding_provider = embedding_provider
        self.chunk_snapshots = chunk_snapshots
        self.candidate_k = candidate_k
        self.rrf_k = rrf_k
        self.vector_min_score = vector_min_score
        self.latency_observer = latency_observer

    def search(
        self,
        question: str,
        scope: Mapping[str, Any],
        *,
        owner_id: str,
        document_ids: Sequence[str],
        top_k: int = 3,
    ) -> list[RankedChunk]:
        if not question.strip() or top_k < 1:
            raise ValueError("online question or top_k is invalid")
        if scope.get("tenant_id") != owner_id or scope.get("user_id") != owner_id:
            raise OnlineScopeForbiddenError(
                "server authorization scope does not match authenticated owner"
            )
        total_started = time.perf_counter()
        ready_route_resolution_started = time.perf_counter()
        routes = self.resolver.resolve(owner_id=owner_id, document_ids=document_ids)
        ready_route_resolution_latency_ms = (
            time.perf_counter() - ready_route_resolution_started
        ) * 1000
        rankings: list[list[RankedChunk]] = []
        elasticsearch_timings: list[ElasticsearchSearchLatencyBreakdown] = []
        milvus_timings: list[MilvusSearchLatencyBreakdown] = []
        try:
            chunk_snapshot_started = time.perf_counter()
            chunks = [
                chunk.model_dump(mode="json")
                for chunk in self.chunk_snapshots.load_online_chunks(
                    owner_id=owner_id,
                    document_version_ids=[
                        route.document_version_id for route in routes
                    ],
                )
            ]
            chunk_snapshot_latency_ms = (
                time.perf_counter() - chunk_snapshot_started
            ) * 1000
            expected_versions = {
                route.document_version_id for route in routes
            }
            returned_versions = {str(chunk["version_id"]) for chunk in chunks}
            if returned_versions != expected_versions or len(
                {str(chunk["chunk_id"]) for chunk in chunks}
            ) != len(chunks):
                raise OnlineVisibilityUnavailableError(
                    "persisted Chunk snapshot does not match READY routes"
                )
            backend_parallel_wall_started = time.perf_counter()
            with ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="online-ready-retrieval",
            ) as executor:
                for route in routes:
                    expected_chunks = self._route_chunks(route=route, chunks=chunks)
                    staged_source_chunks = [
                        {**chunk, "is_active": False} for chunk in expected_chunks
                    ]
                    route_scope = dict(scope)
                    route_scope["document_ids"] = [route.document_id]
                    route_scope["library_ids"] = []
                    route_scope["folder_ids"] = []
                    elasticsearch_index = ElasticsearchBm25Index(
                        route.elasticsearch_index,
                        self.elasticsearch_transport,
                    )
                    milvus_index = MilvusVectorIndex(
                        route.milvus_collection,
                        self.milvus_transport,
                    )
                    lexical_kwargs: dict[str, Any] = {
                        "top_k": self.candidate_k,
                        "expected_chunks": expected_chunks,
                        "source_fingerprint_chunks": staged_source_chunks,
                    }
                    vector_kwargs: dict[str, Any] = {
                        "top_k": self.candidate_k,
                        "min_score": self.vector_min_score,
                        "expected_chunks": expected_chunks,
                        "source_fingerprint_chunks": staged_source_chunks,
                    }
                    if self.latency_observer is not None:
                        lexical_kwargs["timing_sink"] = (
                            elasticsearch_timings.append
                        )
                        vector_kwargs["timing_sink"] = milvus_timings.append
                    lexical_future = executor.submit(
                        elasticsearch_index.search,
                        question,
                        dict(route_scope),
                        **lexical_kwargs,
                    )
                    vector_future = executor.submit(
                        milvus_index.search,
                        question,
                        dict(route_scope),
                        self.embedding_provider,
                        **vector_kwargs,
                    )
                    lexical = lexical_future.result()
                    vector = vector_future.result()
                    self._validate_route_ranking(route, lexical)
                    self._validate_route_ranking(route, vector)
                    rankings.extend((lexical, vector))
            backend_parallel_wall_latency_ms = (
                time.perf_counter() - backend_parallel_wall_started
            ) * 1000
            ready_revalidation_started = time.perf_counter()
            self.resolver.revalidate(
                routes,
                owner_id=owner_id,
                document_ids=document_ids,
            )
            ready_revalidation_latency_ms = (
                time.perf_counter() - ready_revalidation_started
            ) * 1000
        except OnlineVisibilityError:
            raise
        except Exception as exc:
            raise OnlineVisibilityUnavailableError(
                "online version retrieval route failed closed"
            ) from exc
        rrf_fusion_started = time.perf_counter()
        fused = self._fuse(rankings, top_k=top_k)
        rrf_fusion_latency_ms = (time.perf_counter() - rrf_fusion_started) * 1000
        if self.latency_observer is not None:
            if len(elasticsearch_timings) != len(routes) or len(
                milvus_timings
            ) != len(routes):
                raise OnlineVisibilityUnavailableError(
                    "online retrieval latency breakdown is incomplete"
                )
            self.latency_observer(
                OnlineRetrievalLatencyBreakdown(
                    route_count=len(routes),
                    ready_route_resolution_latency_ms=(
                        ready_route_resolution_latency_ms
                    ),
                    chunk_snapshot_latency_ms=chunk_snapshot_latency_ms,
                    elasticsearch_validation_work_latency_ms=sum(
                        timing.validation_latency_ms
                        for timing in elasticsearch_timings
                    ),
                    elasticsearch_query_work_latency_ms=sum(
                        timing.query_latency_ms for timing in elasticsearch_timings
                    ),
                    elasticsearch_total_work_latency_ms=sum(
                        timing.total_latency_ms for timing in elasticsearch_timings
                    ),
                    milvus_validation_work_latency_ms=sum(
                        timing.validation_latency_ms for timing in milvus_timings
                    ),
                    query_embedding_work_latency_ms=sum(
                        timing.query_embedding_latency_ms
                        for timing in milvus_timings
                    ),
                    milvus_ann_search_work_latency_ms=sum(
                        timing.ann_search_latency_ms for timing in milvus_timings
                    ),
                    milvus_total_work_latency_ms=sum(
                        timing.total_latency_ms for timing in milvus_timings
                    ),
                    backend_parallel_wall_latency_ms=(
                        backend_parallel_wall_latency_ms
                    ),
                    ready_revalidation_latency_ms=(
                        ready_revalidation_latency_ms
                    ),
                    rrf_fusion_latency_ms=rrf_fusion_latency_ms,
                    total_latency_ms=(time.perf_counter() - total_started) * 1000,
                )
            )
        return fused

    def retrieve(
        self,
        question: str,
        scope: Mapping[str, Any],
        *,
        owner_id: str,
        document_ids: Sequence[str],
        top_k: int = 3,
    ) -> list[JsonObject]:
        return chunks_only(
            self.search(
                question,
                scope,
                owner_id=owner_id,
                document_ids=document_ids,
                top_k=top_k,
            )
        )

    @staticmethod
    def _route_chunks(
        *, route: OnlineVersionRoute, chunks: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        matched = [
            dict(chunk)
            for chunk in chunks
            if chunk.get("tenant_id") == route.owner_id
            and chunk.get("document_id") == route.document_id
            and chunk.get("version_id") == route.document_version_id
        ]
        if not matched:
            raise OnlineVisibilityUnavailableError(
                "READY route has no matching source Chunk snapshot"
            )
        return matched

    @staticmethod
    def _validate_route_ranking(
        route: OnlineVersionRoute, ranking: Sequence[RankedChunk]
    ) -> None:
        if ranking:
            validate_ranking(ranking, expected_backend=ranking[0].backend)
        for candidate in ranking:
            chunk = candidate.chunk
            if (
                chunk.get("tenant_id") != route.owner_id
                or chunk.get("document_id") != route.document_id
                or chunk.get("version_id") != route.document_version_id
                or chunk.get("is_active") is not True
            ):
                raise OnlineVisibilityUnavailableError(
                    "online candidate violates READY route identity"
                )

    def _fuse(
        self, rankings: Sequence[Sequence[RankedChunk]], *, top_k: int
    ) -> list[RankedChunk]:
        payloads: dict[str, JsonObject] = {}
        scores: dict[str, float] = {}
        best_rank: dict[str, int] = {}
        for ranking in rankings:
            for candidate in ranking:
                chunk_id = str(candidate.chunk["chunk_id"])
                existing = payloads.get(chunk_id)
                if existing is not None and existing != candidate.chunk:
                    raise OnlineVisibilityUnavailableError(
                        "online backends disagree on candidate payload"
                    )
                payloads[chunk_id] = candidate.chunk
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (
                    self.rrf_k + candidate.rank
                )
                best_rank[chunk_id] = min(
                    best_rank.get(chunk_id, candidate.rank), candidate.rank
                )
        ordered = sorted(
            scores,
            key=lambda chunk_id: (-scores[chunk_id], best_rank[chunk_id], chunk_id),
        )[:top_k]
        fused = [
            RankedChunk(
                backend=ONLINE_RETRIEVAL_BACKEND,
                rank=rank,
                score=scores[chunk_id],
                chunk=payloads[chunk_id],
            )
            for rank, chunk_id in enumerate(ordered, 1)
        ]
        validate_ranking(fused, expected_backend=ONLINE_RETRIEVAL_BACKEND)
        return fused
