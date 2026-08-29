"""PostgreSQL-READY routing over version-scoped Elasticsearch and Milvus indexes."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

from backend.retrieval.comparison_decomposition import RouteQueryPlan
from backend.retrieval.comparison_route_coverage import RouteCoveragePlan
from backend.retrieval.elasticsearch import (
    RETRIEVAL_BACKEND as ELASTICSEARCH_RETRIEVAL_BACKEND,
    ElasticsearchBm25Index,
    ElasticsearchSearchLatencyBreakdown,
    ElasticsearchTransport,
)
from backend.retrieval.embedding import EmbeddingModelIdentity, EmbeddingProvider
from backend.retrieval.milvus import (
    DEFAULT_VECTOR_MIN_SCORE,
    RETRIEVAL_BACKEND as MILVUS_RETRIEVAL_BACKEND,
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
        metadata_sink: Callable[[Mapping[str, str]], None] | None = None,
    ) -> str: ...


class ReadyChunkSnapshotRepository(Protocol):
    def load_online_chunks(
        self,
        *,
        owner_id: str,
        document_version_ids: Sequence[str],
    ) -> tuple[ChunkRecordV1, ...]: ...


class OnlineRouteQueryPlanner(Protocol):
    def plan(
        self,
        question: str,
        *,
        document_ids: Sequence[str],
    ) -> RouteQueryPlan: ...


class OnlineFinalCandidateSelector(Protocol):
    def plan(
        self,
        question: str,
        candidates: Sequence[RankedChunk],
        *,
        document_ids: Sequence[str],
        top_k: int,
    ) -> RouteCoveragePlan: ...


@dataclass(frozen=True)
class _SharedQueryEmbeddings:
    vectors_by_query: Mapping[str, Sequence[float]]
    latency_ms: float


@dataclass(frozen=True)
class _PrewarmedQueryEmbedding:
    question: str
    vector: tuple[float, ...]
    latency_ms: float


@dataclass(frozen=True)
class OnlineReadyRouteLatencyBreakdown:
    """Sanitized timings for one PostgreSQL READY route-resolution stage."""

    route_count: int
    postgres_ready_lookup_latency_ms: float
    physical_route_verification_wall_latency_ms: float
    elasticsearch_route_verification_work_latency_ms: float
    milvus_route_verification_work_latency_ms: float
    total_latency_ms: float


class _RequestEmbeddingProvider:
    """Share model identity and query vectors only within one online request."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider
        self._lock = Lock()
        self._identity: EmbeddingModelIdentity | None = None
        self._vectors: dict[str, tuple[float, ...]] = {}

    def identity(self) -> EmbeddingModelIdentity:
        with self._lock:
            if self._identity is None:
                self._identity = self._provider.identity()
            return self._identity

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        requested = tuple(texts)
        if not requested:
            return []
        with self._lock:
            unique_missing = tuple(
                text for text in dict.fromkeys(requested) if text not in self._vectors
            )
            if unique_missing:
                vectors = self._provider.embed(unique_missing)
                if len(vectors) != len(unique_missing):
                    raise ValueError(
                        "embedding provider must return one vector per query"
                    )
                for text, vector in zip(unique_missing, vectors, strict=True):
                    cached = tuple(float(value) for value in vector)
                    if not cached:
                        raise ValueError("embedding provider returned an empty query vector")
                    self._vectors[text] = cached
            return [list(self._vectors[text]) for text in requested]


@dataclass(frozen=True)
class OnlineVersionRoute:
    owner_id: str
    document_id: str
    document_version_id: str
    elasticsearch_index: str
    milvus_collection: str
    elasticsearch_verification_metadata: tuple[tuple[str, str], ...] = ()
    milvus_verification_metadata: tuple[tuple[str, str], ...] = ()


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
    ready_postgres_lookup_latency_ms: float = 0.0
    ready_physical_verification_wall_latency_ms: float = 0.0
    ready_elasticsearch_verification_work_latency_ms: float = 0.0
    ready_milvus_verification_work_latency_ms: float = 0.0


@dataclass(frozen=True)
class OnlineRouteCandidateRanking:
    """One backend ranking returned to fusion for one READY version route."""

    route: OnlineVersionRoute
    backend: str
    candidates: tuple[RankedChunk, ...]


@dataclass(frozen=True)
class OnlineCandidateLadderObservation:
    """Read-only internal snapshot of the candidates used by one search."""

    routes: tuple[OnlineVersionRoute, ...]
    route_rankings: tuple[OnlineRouteCandidateRanking, ...]
    fused_candidates: tuple[RankedChunk, ...]
    final_candidates: tuple[RankedChunk, ...]
    candidate_k: int
    rrf_k: int
    final_top_k: int
    vector_min_score: float
    pre_cutoff_ranking_observed: bool = False


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

    @staticmethod
    def _verify_physical_route(
        inspector: VersionRouteInspector,
        route_kwargs: Mapping[str, Any],
        metadata_holder: list[Mapping[str, str]],
    ) -> tuple[str, float, tuple[tuple[str, str], ...]]:
        started = time.perf_counter()
        route = inspector.verify_online_version(
            **dict(route_kwargs),
            metadata_sink=metadata_holder.append,
        )
        if len(metadata_holder) > 1:
            raise ValueError("online physical route verification metadata is duplicated")
        metadata = (
            tuple(sorted((str(key), str(value)) for key, value in metadata_holder[0].items()))
            if metadata_holder
            else ()
        )
        return route, (time.perf_counter() - started) * 1000, metadata

    def resolve(
        self,
        *,
        owner_id: str,
        document_ids: Sequence[str],
        timing_sink: Callable[[OnlineReadyRouteLatencyBreakdown], None] | None = None,
        postgresql_ready_hook: Callable[[], None] | None = None,
    ) -> tuple[OnlineVersionRoute, ...]:
        total_started = time.perf_counter()
        requested = tuple(document_ids)
        if not _CONTRACT_ID_PATTERN.fullmatch(owner_id):
            raise OnlineScopeForbiddenError("authenticated owner identity is invalid")
        if len(requested) != len(set(requested)) or any(
            not _CONTRACT_ID_PATTERN.fullmatch(document_id)
            for document_id in requested
        ):
            raise OnlineScopeForbiddenError("requested document scope is invalid")
        postgres_started = time.perf_counter()
        try:
            versions = self.repository.resolve_online_versions(
                owner_id=owner_id,
                document_ids=requested,
            )
        except Exception as exc:
            raise OnlineVisibilityUnavailableError(
                "PostgreSQL READY visibility could not be resolved"
            ) from exc
        postgres_ready_lookup_latency_ms = (
            time.perf_counter() - postgres_started
        ) * 1000

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

        ordered_document_ids = tuple(sorted(by_document))
        if not ordered_document_ids:
            if timing_sink is not None:
                timing_sink(
                    OnlineReadyRouteLatencyBreakdown(
                        route_count=0,
                        postgres_ready_lookup_latency_ms=(
                            postgres_ready_lookup_latency_ms
                        ),
                        physical_route_verification_wall_latency_ms=0.0,
                        elasticsearch_route_verification_work_latency_ms=0.0,
                        milvus_route_verification_work_latency_ms=0.0,
                        total_latency_ms=(time.perf_counter() - total_started) * 1000,
                    )
                )
            return ()

        if postgresql_ready_hook is not None:
            try:
                postgresql_ready_hook()
            except Exception as exc:
                raise OnlineVisibilityUnavailableError(
                    "online query prewarm could not be scheduled"
                ) from exc

        routes: list[OnlineVersionRoute] = []
        elasticsearch_verification_work_latency_ms = 0.0
        milvus_verification_work_latency_ms = 0.0
        physical_verification_started = time.perf_counter()
        try:
            max_workers = min(max(2, len(ordered_document_ids) * 2), 32)
            with ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="online-ready-route-verification",
            ) as executor:
                verification_futures: dict[
                    str,
                    tuple[
                        Future[tuple[str, float, tuple[tuple[str, str], ...]]],
                        Future[tuple[str, float, tuple[tuple[str, str], ...]]],
                    ],
                ] = {}
                for document_id in ordered_document_ids:
                    version = by_document[document_id]
                    route_kwargs = {
                        "owner_id": owner_id,
                        "document_id": document_id,
                        "document_version_id": version.document_version_id,
                    }
                    verification_futures[document_id] = (
                        executor.submit(
                            self._verify_physical_route,
                            self.elasticsearch,
                            route_kwargs,
                            [],
                        ),
                        executor.submit(
                            self._verify_physical_route,
                            self.milvus,
                            route_kwargs,
                            [],
                        ),
                    )

                for document_id in ordered_document_ids:
                    version = by_document[document_id]
                    elasticsearch_future, milvus_future = verification_futures[
                        document_id
                    ]
                    (
                        elasticsearch_index,
                        elasticsearch_latency_ms,
                        elasticsearch_metadata,
                    ) = elasticsearch_future.result()
                    milvus_collection, milvus_latency_ms, milvus_metadata = (
                        milvus_future.result()
                    )
                    elasticsearch_verification_work_latency_ms += (
                        elasticsearch_latency_ms
                    )
                    milvus_verification_work_latency_ms += milvus_latency_ms
                    routes.append(
                        OnlineVersionRoute(
                            owner_id=owner_id,
                            document_id=document_id,
                            document_version_id=version.document_version_id,
                            elasticsearch_index=elasticsearch_index,
                            milvus_collection=milvus_collection,
                            elasticsearch_verification_metadata=elasticsearch_metadata,
                            milvus_verification_metadata=milvus_metadata,
                        )
                    )
        except Exception as exc:
            raise OnlineVisibilityUnavailableError(
                "READY version physical index route could not be verified"
            ) from exc
        physical_verification_wall_latency_ms = (
            time.perf_counter() - physical_verification_started
        ) * 1000
        if timing_sink is not None:
            timing_sink(
                OnlineReadyRouteLatencyBreakdown(
                    route_count=len(ordered_document_ids),
                    postgres_ready_lookup_latency_ms=postgres_ready_lookup_latency_ms,
                    physical_route_verification_wall_latency_ms=(
                        physical_verification_wall_latency_ms
                    ),
                    elasticsearch_route_verification_work_latency_ms=(
                        elasticsearch_verification_work_latency_ms
                    ),
                    milvus_route_verification_work_latency_ms=(
                        milvus_verification_work_latency_ms
                    ),
                    total_latency_ms=(time.perf_counter() - total_started) * 1000,
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
        route_query_planner: OnlineRouteQueryPlanner | None = None,
        final_candidate_selector: OnlineFinalCandidateSelector | None = None,
        latency_observer: (
            Callable[[OnlineRetrievalLatencyBreakdown], None] | None
        ) = None,
        candidate_ladder_observer: (
            Callable[[OnlineCandidateLadderObservation], None] | None
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
        self.route_query_planner = route_query_planner
        self.final_candidate_selector = final_candidate_selector
        self.latency_observer = latency_observer
        self.candidate_ladder_observer = candidate_ladder_observer

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
        request_embedding_provider = _RequestEmbeddingProvider(self.embedding_provider)
        prewarm_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="online-query-embedding-prewarm",
        )
        prewarm_future: Future[_PrewarmedQueryEmbedding] | None = None

        def start_query_embedding_prewarm() -> None:
            nonlocal prewarm_future
            if self.route_query_planner is not None or prewarm_future is not None:
                return
            prewarm_future = prewarm_executor.submit(
                self._embed_single_query,
                request_embedding_provider,
                question,
            )

        ready_route_resolution_started = time.perf_counter()
        ready_route_latency_breakdowns: list[
            OnlineReadyRouteLatencyBreakdown
        ] = []
        try:
            routes = self.resolver.resolve(
                owner_id=owner_id,
                document_ids=document_ids,
                timing_sink=(
                    ready_route_latency_breakdowns.append
                    if self.latency_observer is not None
                    else None
                ),
                postgresql_ready_hook=start_query_embedding_prewarm,
            )
            ready_route_resolution_latency_ms = (
                time.perf_counter() - ready_route_resolution_started
            ) * 1000
            if routes and self.route_query_planner is None and prewarm_future is None:
                # Keep custom resolver implementations compatible with the overlap
                # optimization when they do not invoke the optional hook.
                start_query_embedding_prewarm()
        except BaseException:
            prewarm_executor.shutdown(wait=True, cancel_futures=True)
            raise
        route_queries = {route.document_id: question for route in routes}
        if self.route_query_planner is not None:
            try:
                query_plan = self.route_query_planner.plan(
                    question,
                    document_ids=[route.document_id for route in routes],
                )
                if (
                    query_plan.status == "APPLIED"
                    and set(query_plan.queries) == set(route_queries)
                    and all(
                        isinstance(route_question, str)
                        and route_question.strip()
                        for route_question in query_plan.queries.values()
                    )
                ):
                    route_queries = dict(query_plan.queries)
            except Exception:
                # The frozen failure policy keeps the authorized original-query path.
                route_queries = {route.document_id: question for route in routes}
        rankings: list[list[RankedChunk]] = []
        route_rankings: list[OnlineRouteCandidateRanking] = []
        elasticsearch_timings: list[ElasticsearchSearchLatencyBreakdown] = []
        milvus_timings: list[MilvusSearchLatencyBreakdown] = []
        query_embedding_latency_ms = 0.0
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
            if routes:
                max_workers = min(max(3, len(routes) * 2 + 1), 32)
                with ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix="online-ready-retrieval",
                ) as executor:
                    if prewarm_future is not None and all(
                        route_question == question
                        for route_question in route_queries.values()
                    ):
                        query_embedding_future: Future[_SharedQueryEmbeddings] = (
                            executor.submit(
                                self._shared_embeddings_from_prewarm,
                                prewarm_future,
                                question,
                            )
                        )
                    else:
                        query_embedding_future = executor.submit(
                            self._embed_route_queries,
                            request_embedding_provider,
                            route_queries,
                        )
                    route_jobs = []
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
                        if route.elasticsearch_verification_metadata:
                            lexical_kwargs["verified_metadata"] = dict(
                                route.elasticsearch_verification_metadata
                            )
                        if route.milvus_verification_metadata:
                            vector_kwargs["verified_metadata"] = dict(
                                route.milvus_verification_metadata
                            )
                        if self.latency_observer is not None:
                            lexical_kwargs["timing_sink"] = (
                                elasticsearch_timings.append
                            )
                            vector_kwargs["timing_sink"] = milvus_timings.append
                        route_question = route_queries[route.document_id]
                        lexical_future = executor.submit(
                            elasticsearch_index.search,
                            route_question,
                            dict(route_scope),
                            **lexical_kwargs,
                        )
                        vector_future = executor.submit(
                            self._search_vector_route,
                            milvus_index,
                            route_question,
                            dict(route_scope),
                            request_embedding_provider,
                            query_embedding_future,
                            vector_kwargs,
                        )
                        route_jobs.append((route, lexical_future, vector_future))

                    shared_embeddings = query_embedding_future.result()
                    query_embedding_latency_ms = shared_embeddings.latency_ms
                    for route, lexical_future, vector_future in route_jobs:
                        lexical = lexical_future.result()
                        vector = vector_future.result()
                        self._validate_route_ranking(route, lexical)
                        self._validate_route_ranking(route, vector)
                        rankings.extend((lexical, vector))
                        route_rankings.extend(
                            (
                                OnlineRouteCandidateRanking(
                                    route=route,
                                    backend=ELASTICSEARCH_RETRIEVAL_BACKEND,
                                    candidates=tuple(lexical),
                                ),
                                OnlineRouteCandidateRanking(
                                    route=route,
                                    backend=MILVUS_RETRIEVAL_BACKEND,
                                    candidates=tuple(vector),
                                ),
                            )
                        )
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
        finally:
            prewarm_executor.shutdown(wait=True, cancel_futures=True)
        rrf_fusion_started = time.perf_counter()
        fused_candidates = self._fuse(
            rankings,
            top_k=(
                None
                if self.final_candidate_selector is not None
                or self.candidate_ladder_observer is not None
                else top_k
            ),
        )
        fused = fused_candidates[:top_k]
        if self.final_candidate_selector is not None:
            try:
                selection = self.final_candidate_selector.plan(
                    question,
                    fused_candidates,
                    document_ids=[route.document_id for route in routes],
                    top_k=top_k,
                )
                if selection.status == "APPLIED":
                    fused = self._apply_selection(
                        fused_candidates,
                        selection.selected_chunk_ids,
                        top_k=top_k,
                    )
            except Exception:
                # Optional quality selection may only fall back to original RRF.
                fused = fused_candidates[:top_k]
        rrf_fusion_latency_ms = (time.perf_counter() - rrf_fusion_started) * 1000
        if self.candidate_ladder_observer is not None:
            try:
                self.candidate_ladder_observer(
                    OnlineCandidateLadderObservation(
                        routes=tuple(routes),
                        route_rankings=tuple(route_rankings),
                        fused_candidates=tuple(fused_candidates),
                        final_candidates=tuple(fused),
                        candidate_k=self.candidate_k,
                        rrf_k=self.rrf_k,
                        final_top_k=top_k,
                        vector_min_score=self.vector_min_score,
                    )
                )
            except Exception as exc:
                raise OnlineVisibilityUnavailableError(
                    "online candidate ladder diagnostic capture failed closed"
                ) from exc
        if self.latency_observer is not None:
            if len(elasticsearch_timings) != len(routes) or len(
                milvus_timings
            ) != len(routes):
                raise OnlineVisibilityUnavailableError(
                    "online retrieval latency breakdown is incomplete"
                )
            if len(ready_route_latency_breakdowns) > 1:
                raise OnlineVisibilityUnavailableError(
                    "online READY route latency breakdown is duplicated"
                )
            ready_route_breakdown = (
                ready_route_latency_breakdowns[0]
                if ready_route_latency_breakdowns
                else None
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
                    query_embedding_work_latency_ms=(
                        query_embedding_latency_ms
                        + sum(
                            timing.query_embedding_latency_ms
                            for timing in milvus_timings
                        )
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
                    ready_postgres_lookup_latency_ms=(
                        ready_route_breakdown.postgres_ready_lookup_latency_ms
                        if ready_route_breakdown is not None
                        else 0.0
                    ),
                    ready_physical_verification_wall_latency_ms=(
                        ready_route_breakdown.physical_route_verification_wall_latency_ms
                        if ready_route_breakdown is not None
                        else 0.0
                    ),
                    ready_elasticsearch_verification_work_latency_ms=(
                        ready_route_breakdown.elasticsearch_route_verification_work_latency_ms
                        if ready_route_breakdown is not None
                        else 0.0
                    ),
                    ready_milvus_verification_work_latency_ms=(
                        ready_route_breakdown.milvus_route_verification_work_latency_ms
                        if ready_route_breakdown is not None
                        else 0.0
                    ),
                )
            )
        return fused

    @staticmethod
    def _embed_single_query(
        provider: EmbeddingProvider,
        question: str,
    ) -> _PrewarmedQueryEmbedding:
        started = time.perf_counter()
        vectors = provider.embed([question])
        if len(vectors) != 1:
            raise ValueError("embedding provider must return exactly one query vector")
        return _PrewarmedQueryEmbedding(
            question=question,
            vector=tuple(float(value) for value in vectors[0]),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    @staticmethod
    def _shared_embeddings_from_prewarm(
        future: Future[_PrewarmedQueryEmbedding],
        question: str,
    ) -> _SharedQueryEmbeddings:
        prewarmed = future.result()
        if prewarmed.question != question:
            raise ValueError("prewarmed query embedding question does not match")
        return _SharedQueryEmbeddings(
            vectors_by_query={question: prewarmed.vector},
            latency_ms=prewarmed.latency_ms,
        )

    @staticmethod
    def _embed_route_queries(
        provider: EmbeddingProvider,
        route_queries: Mapping[str, str],
    ) -> _SharedQueryEmbeddings:
        unique_queries = tuple(dict.fromkeys(route_queries.values()))
        started = time.perf_counter()
        vectors = provider.embed(unique_queries)
        if len(vectors) != len(unique_queries):
            raise ValueError("embedding count does not match online route queries")
        return _SharedQueryEmbeddings(
            vectors_by_query={
                question: vector
                for question, vector in zip(unique_queries, vectors, strict=True)
            },
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    @staticmethod
    def _search_vector_route(
        index: MilvusVectorIndex,
        question: str,
        scope: Mapping[str, Any],
        provider: EmbeddingProvider,
        query_embedding_future: Future[_SharedQueryEmbeddings],
        vector_kwargs: Mapping[str, Any],
    ) -> list[RankedChunk]:
        shared_embeddings = query_embedding_future.result()
        try:
            query_vector = shared_embeddings.vectors_by_query[question]
        except KeyError as exc:
            raise ValueError("online route query embedding is missing") from exc
        return index.search(
            question,
            scope,
            provider,
            query_vector=query_vector,
            **dict(vector_kwargs),
        )

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
        self,
        rankings: Sequence[Sequence[RankedChunk]],
        *,
        top_k: int | None,
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
        )
        if top_k is not None:
            ordered = ordered[:top_k]
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

    @staticmethod
    def _apply_selection(
        candidates: Sequence[RankedChunk],
        selected_chunk_ids: Sequence[str],
        *,
        top_k: int,
    ) -> list[RankedChunk]:
        selected_ids = tuple(selected_chunk_ids)
        if (
            len(selected_ids) != top_k
            or len(set(selected_ids)) != len(selected_ids)
        ):
            raise ValueError("final candidate selection cardinality is invalid")
        by_id = {
            str(candidate.chunk["chunk_id"]): candidate for candidate in candidates
        }
        if not set(selected_ids).issubset(by_id):
            raise ValueError("final candidate selection expands the RRF candidates")
        selected = [
            RankedChunk(
                backend=ONLINE_RETRIEVAL_BACKEND,
                rank=rank,
                score=by_id[chunk_id].score,
                chunk=by_id[chunk_id].chunk,
            )
            for rank, chunk_id in enumerate(selected_ids, 1)
        ]
        validate_ranking(selected, expected_backend=ONLINE_RETRIEVAL_BACKEND)
        return selected
