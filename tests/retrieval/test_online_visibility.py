from __future__ import annotations

import threading
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend.retrieval.comparison_decomposition import RouteQueryPlan
from backend.retrieval.comparison_route_coverage import RouteCoveragePlan
from backend.retrieval.online import (
    OnlineRetrievalLatencyBreakdown,
    OnlineScopeForbiddenError,
    OnlineVersionRoute,
    OnlineVersionRrfRetriever,
    OnlineVisibilityUnavailableError,
    PostgresReadyRouteResolver,
)
from backend.retrieval.elasticsearch import ElasticsearchSearchLatencyBreakdown
from backend.retrieval.milvus import MilvusSearchLatencyBreakdown
from backend.retrieval.results import RankedChunk
from backend.ingestion.models import ChunkRecordV1
from backend.storage.models import (
    DocumentVersionLifecycleV1,
    IndexState,
    IndexStatesV1,
    LifecycleStatus,
)
from tests.retrieval.fake_embedding import FakeEmbeddingProvider


NOW = datetime(2026, 7, 22, 16, 0, tzinfo=timezone.utc)
OWNER_ID = "owner_001"


def ready_version(
    document_id: str = "document_001",
    version_id: str = "document_version_001",
) -> DocumentVersionLifecycleV1:
    return DocumentVersionLifecycleV1(
        paper_id=f"paper_{document_id}",
        document_id=document_id,
        owner_id=OWNER_ID,
        document_version_id=version_id,
        content_sha256="a" * 64,
        source_snapshot_sha256="b" * 64,
        parse_version="pypdf_text_v1",
        lifecycle_revision=3,
        lifecycle_status=LifecycleStatus.READY,
        parse_finish_time=NOW,
        chunk_splitter_time=NOW,
        chunk_create_time=NOW,
        chunk_gen_time=NOW,
        vector_index_time=NOW,
        index_states=IndexStatesV1(
            elasticsearch_chunks=IndexState.READY,
            milvus_vectors=IndexState.READY,
        ),
        updated_at=NOW,
    )


def chunk(document_id: str, version_id: str, position: int) -> dict[str, object]:
    return {
        "chunk_id": f"chunk_{document_id}_{position}",
        "document_id": document_id,
        "version_id": version_id,
        "text": f"Evidence {document_id} {position}",
        "section_path": "Method",
        "page_start": position,
        "page_end": position,
        "parent_chunk_id": None,
        "previous_chunk_id": None,
        "next_chunk_id": None,
        "tenant_id": OWNER_ID,
        "visibility": "private",
        "library_scope_ids": [],
        "parse_version": "pypdf_text_v1",
        "embedding_version": "bge_m3_v1",
        "is_active": True,
    }


class FakeReadyRepository:
    def __init__(self, versions):
        self.versions = tuple(versions)
        self.calls = []

    def resolve_online_versions(self, **kwargs):
        self.calls.append(kwargs)
        return self.versions


class FakeRouteInspector:
    def __init__(self, prefix: str, *, fail: bool = False):
        self.prefix = prefix
        self.fail = fail
        self.calls = []

    def verify_online_version(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("simulated route failure")
        return f"{self.prefix}_{kwargs['document_version_id']}"


class ReadyRouteResolverTests(unittest.TestCase):
    def test_resolves_exact_requested_ready_routes(self):
        repository = FakeReadyRepository(
            [ready_version("document_002", "version_002")]
        )
        elasticsearch = FakeRouteInspector("es")
        milvus = FakeRouteInspector("milvus")
        resolver = PostgresReadyRouteResolver(
            repository=repository,
            elasticsearch=elasticsearch,
            milvus=milvus,
        )

        routes = resolver.resolve(
            owner_id=OWNER_ID,
            document_ids=["document_002"],
        )

        self.assertEqual(routes[0].elasticsearch_index, "es_version_002")
        self.assertEqual(routes[0].milvus_collection, "milvus_version_002")
        self.assertEqual(repository.calls[0]["owner_id"], OWNER_ID)

    def test_missing_requested_document_is_forbidden_without_existence_leak(self):
        resolver = PostgresReadyRouteResolver(
            repository=FakeReadyRepository([]),
            elasticsearch=FakeRouteInspector("es"),
            milvus=FakeRouteInspector("milvus"),
        )

        with self.assertRaises(OnlineScopeForbiddenError):
            resolver.resolve(owner_id=OWNER_ID, document_ids=["document_missing"])

    def test_repository_or_physical_route_failure_is_unavailable(self):
        class FailingRepository:
            def resolve_online_versions(self, **kwargs):
                raise RuntimeError(f"database unavailable: {kwargs}")

        repository_failure = PostgresReadyRouteResolver(
            repository=FailingRepository(),
            elasticsearch=FakeRouteInspector("es"),
            milvus=FakeRouteInspector("milvus"),
        )
        with self.assertRaises(OnlineVisibilityUnavailableError):
            repository_failure.resolve(owner_id=OWNER_ID, document_ids=[])

        route_failure = PostgresReadyRouteResolver(
            repository=FakeReadyRepository([ready_version()]),
            elasticsearch=FakeRouteInspector("es", fail=True),
            milvus=FakeRouteInspector("milvus"),
        )
        with self.assertRaises(OnlineVisibilityUnavailableError):
            route_failure.resolve(owner_id=OWNER_ID, document_ids=[])


class StaticResolver:
    def __init__(self, routes):
        self.routes = tuple(routes)

    def resolve(self, **kwargs):
        del kwargs
        return self.routes

    def revalidate(self, routes, **kwargs):
        del kwargs
        if tuple(routes) != self.routes:
            raise AssertionError("route snapshot changed unexpectedly")


class FakeElasticsearchIndex:
    def __init__(self, index_name, transport):
        self.index_name = index_name
        self.transport = transport

    def search(self, question, scope, **kwargs):
        del scope
        timing_sink = kwargs.pop("timing_sink", None)
        self.transport.questions[self.index_name] = question
        self.transport.expected[self.index_name] = kwargs["expected_chunks"]
        self.transport.source_fingerprints[self.index_name] = kwargs[
            "source_fingerprint_chunks"
        ]
        ranking = self.transport.rankings[self.index_name]
        if timing_sink is not None:
            timing_sink(
                ElasticsearchSearchLatencyBreakdown(
                    validation_latency_ms=0.1,
                    query_latency_ms=0.2,
                    total_latency_ms=0.3,
                )
            )
        return ranking


class FakeMilvusIndex:
    def __init__(self, collection_name, transport):
        self.collection_name = collection_name
        self.transport = transport

    def search(self, question, scope, provider, **kwargs):
        del scope, provider
        timing_sink = kwargs.pop("timing_sink", None)
        self.transport.questions[self.collection_name] = question
        self.transport.expected[self.collection_name] = kwargs["expected_chunks"]
        self.transport.source_fingerprints[self.collection_name] = kwargs[
            "source_fingerprint_chunks"
        ]
        ranking = self.transport.rankings[self.collection_name]
        if timing_sink is not None:
            timing_sink(
                MilvusSearchLatencyBreakdown(
                    validation_latency_ms=0.4,
                    query_embedding_latency_ms=0.5,
                    ann_search_latency_ms=0.6,
                    total_latency_ms=1.5,
                )
            )
        return ranking


class RankingTransport:
    def __init__(self, rankings):
        self.rankings = rankings
        self.expected = {}
        self.source_fingerprints = {}
        self.questions = {}


class FakeChunkSnapshots:
    def __init__(self, chunks):
        self.chunks = tuple(ChunkRecordV1.model_validate(item) for item in chunks)
        self.calls = []

    def load_online_chunks(self, **kwargs):
        self.calls.append(kwargs)
        return self.chunks


class OnlineVersionRrfRetrieverTests(unittest.TestCase):
    def test_applied_final_selector_reorders_only_existing_rrf_candidates(self):
        alpha_route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_alpha",
            document_version_id="version_alpha",
            elasticsearch_index="es_version_alpha",
            milvus_collection="milvus_version_alpha",
        )
        beta_route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_beta",
            document_version_id="version_beta",
            elasticsearch_index="es_version_beta",
            milvus_collection="milvus_version_beta",
        )
        alpha_1 = chunk("document_alpha", "version_alpha", 1)
        alpha_2 = chunk("document_alpha", "version_alpha", 2)
        alpha_3 = chunk("document_alpha", "version_alpha", 3)
        beta_1 = chunk("document_beta", "version_beta", 1)
        elasticsearch = RankingTransport(
            {
                "es_version_alpha": [
                    RankedChunk("es", 1, 4.0, alpha_1),
                    RankedChunk("es", 2, 3.0, alpha_2),
                    RankedChunk("es", 3, 2.5, alpha_3),
                ],
                "es_version_beta": [RankedChunk("es", 1, 2.0, beta_1)],
            }
        )
        milvus = RankingTransport(
            {
                "milvus_version_alpha": [
                    RankedChunk("milvus", 1, 0.9, alpha_1),
                    RankedChunk("milvus", 2, 0.8, alpha_2),
                    RankedChunk("milvus", 3, 0.7, alpha_3),
                ],
                "milvus_version_beta": [],
            }
        )

        class StaticSelector:
            def plan(self, question, candidates, *, document_ids, top_k):
                self.seen = (
                    question,
                    tuple(document_ids),
                    tuple(item.chunk["chunk_id"] for item in candidates),
                    top_k,
                )
                return RouteCoveragePlan(
                    status="APPLIED",
                    selected_chunk_ids=(
                        alpha_1["chunk_id"],
                        alpha_2["chunk_id"],
                        beta_1["chunk_id"],
                    ),
                    failure_code=None,
                )

        selector = StaticSelector()
        retriever = OnlineVersionRrfRetriever(
            resolver=StaticResolver([alpha_route, beta_route]),
            elasticsearch_transport=elasticsearch,
            milvus_transport=milvus,
            embedding_provider=FakeEmbeddingProvider(),
            chunk_snapshots=FakeChunkSnapshots(
                [alpha_1, alpha_2, alpha_3, beta_1]
            ),
            final_candidate_selector=selector,
        )

        with patch(
            "backend.retrieval.online.ElasticsearchBm25Index",
            FakeElasticsearchIndex,
        ), patch("backend.retrieval.online.MilvusVectorIndex", FakeMilvusIndex):
            results = retriever.retrieve(
                "比较两篇论文",
                {"user_id": OWNER_ID, "tenant_id": OWNER_ID},
                owner_id=OWNER_ID,
                document_ids=["document_alpha", "document_beta"],
                top_k=3,
            )

        self.assertEqual(
            [item["chunk_id"] for item in results],
            [alpha_1["chunk_id"], alpha_2["chunk_id"], beta_1["chunk_id"]],
        )
        self.assertEqual(selector.seen[0], "比较两篇论文")
        self.assertEqual(selector.seen[1], ("document_alpha", "document_beta"))
        self.assertEqual(
            selector.seen[2][:3],
            (
                alpha_1["chunk_id"],
                alpha_2["chunk_id"],
                alpha_3["chunk_id"],
            ),
        )
        self.assertEqual(retriever.candidate_k, 20)
        self.assertEqual(retriever.rrf_k, 60)

    def test_applied_route_query_plan_changes_only_route_query_text(self):
        first_route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_001",
            document_version_id="version_001",
            elasticsearch_index="es_version_001",
            milvus_collection="milvus_version_001",
        )
        second_route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_002",
            document_version_id="version_002",
            elasticsearch_index="es_version_002",
            milvus_collection="milvus_version_002",
        )
        first = chunk("document_001", "version_001", 1)
        second = chunk("document_002", "version_002", 1)
        elasticsearch = RankingTransport(
            {
                "es_version_001": [RankedChunk("es", 1, 4.0, first)],
                "es_version_002": [RankedChunk("es", 1, 3.0, second)],
            }
        )
        milvus = RankingTransport(
            {
                "milvus_version_001": [],
                "milvus_version_002": [],
            }
        )

        class StaticPlanner:
            calls = []

            def plan(self, question, *, document_ids):
                self.calls.append((question, tuple(document_ids)))
                return RouteQueryPlan(
                    status="APPLIED",
                    queries={
                        "document_001": "first-side query",
                        "document_002": "second-side query",
                    },
                    failure_code=None,
                )

        planner = StaticPlanner()
        retriever = OnlineVersionRrfRetriever(
            resolver=StaticResolver([first_route, second_route]),
            elasticsearch_transport=elasticsearch,
            milvus_transport=milvus,
            embedding_provider=FakeEmbeddingProvider(),
            chunk_snapshots=FakeChunkSnapshots([first, second]),
            route_query_planner=planner,
        )

        with patch(
            "backend.retrieval.online.ElasticsearchBm25Index",
            FakeElasticsearchIndex,
        ), patch("backend.retrieval.online.MilvusVectorIndex", FakeMilvusIndex):
            retriever.retrieve(
                "original comparison",
                {"user_id": OWNER_ID, "tenant_id": OWNER_ID},
                owner_id=OWNER_ID,
                document_ids=["document_001", "document_002"],
                top_k=2,
            )

        self.assertEqual(
            planner.calls,
            [
                (
                    "original comparison",
                    ("document_001", "document_002"),
                )
            ],
        )
        self.assertEqual(
            elasticsearch.questions,
            {
                "es_version_001": "first-side query",
                "es_version_002": "second-side query",
            },
        )
        self.assertEqual(
            milvus.questions,
            {
                "milvus_version_001": "first-side query",
                "milvus_version_002": "second-side query",
            },
        )
        self.assertEqual(retriever.candidate_k, 20)
        self.assertEqual(retriever.rrf_k, 60)

    def test_invalid_or_failed_route_query_plan_falls_back_to_original_query(self):
        route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_001",
            document_version_id="version_001",
            elasticsearch_index="es_version_001",
            milvus_collection="milvus_version_001",
        )
        expected = chunk("document_001", "version_001", 1)
        elasticsearch = RankingTransport(
            {"es_version_001": [RankedChunk("es", 1, 1.0, expected)]}
        )
        milvus = RankingTransport({"milvus_version_001": []})

        class FailingPlanner:
            def plan(self, question, *, document_ids):
                del question, document_ids
                raise RuntimeError("simulated decomposition failure")

        retriever = OnlineVersionRrfRetriever(
            resolver=StaticResolver([route]),
            elasticsearch_transport=elasticsearch,
            milvus_transport=milvus,
            embedding_provider=FakeEmbeddingProvider(),
            chunk_snapshots=FakeChunkSnapshots([expected]),
            route_query_planner=FailingPlanner(),
        )

        with patch(
            "backend.retrieval.online.ElasticsearchBm25Index",
            FakeElasticsearchIndex,
        ), patch("backend.retrieval.online.MilvusVectorIndex", FakeMilvusIndex):
            retriever.retrieve(
                "original question",
                {"user_id": OWNER_ID, "tenant_id": OWNER_ID},
                owner_id=OWNER_ID,
                document_ids=["document_001"],
            )

        self.assertEqual(
            elasticsearch.questions["es_version_001"],
            "original question",
        )
        self.assertEqual(
            milvus.questions["milvus_version_001"],
            "original question",
        )

    def test_persisted_snapshot_must_match_exact_ready_route_versions(self):
        route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_001",
            document_version_id="version_001",
            elasticsearch_index="es_version_001",
            milvus_collection="milvus_version_001",
        )
        retriever = OnlineVersionRrfRetriever(
            resolver=StaticResolver([route]),
            elasticsearch_transport=RankingTransport({}),
            milvus_transport=RankingTransport({}),
            embedding_provider=FakeEmbeddingProvider(),
            chunk_snapshots=FakeChunkSnapshots(
                [
                    chunk("document_001", "version_001", 1),
                    chunk("document_002", "version_extra", 1),
                ]
            ),
        )

        with self.assertRaisesRegex(
            OnlineVisibilityUnavailableError,
            "does not match READY routes",
        ):
            retriever.retrieve(
                "question",
                {"user_id": OWNER_ID, "tenant_id": OWNER_ID},
                owner_id=OWNER_ID,
                document_ids=["document_001"],
            )

    def test_fuses_multiple_ready_version_routes_without_static_index_names(self):
        first_route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_001",
            document_version_id="version_001",
            elasticsearch_index="es_version_001",
            milvus_collection="milvus_version_001",
        )
        second_route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_002",
            document_version_id="version_002",
            elasticsearch_index="es_version_002",
            milvus_collection="milvus_version_002",
        )
        first = chunk("document_001", "version_001", 1)
        second = chunk("document_002", "version_002", 1)
        elasticsearch = RankingTransport(
            {
                "es_version_001": [RankedChunk("es", 1, 4.0, first)],
                "es_version_002": [RankedChunk("es", 1, 3.0, second)],
            }
        )
        milvus = RankingTransport(
            {
                "milvus_version_001": [RankedChunk("milvus", 1, 0.9, first)],
                "milvus_version_002": [],
            }
        )
        retriever = OnlineVersionRrfRetriever(
            resolver=StaticResolver([first_route, second_route]),
            elasticsearch_transport=elasticsearch,
            milvus_transport=milvus,
            embedding_provider=FakeEmbeddingProvider(),
            chunk_snapshots=FakeChunkSnapshots([first, second]),
        )
        scope = {
            "user_id": OWNER_ID,
            "tenant_id": OWNER_ID,
            "acl_version": "acl_v1",
            "include_public": False,
            "document_ids": [],
            "library_ids": [],
            "folder_ids": [],
        }

        with patch(
            "backend.retrieval.online.ElasticsearchBm25Index",
            FakeElasticsearchIndex,
        ), patch("backend.retrieval.online.MilvusVectorIndex", FakeMilvusIndex):
            results = retriever.retrieve(
                "question",
                scope,
                owner_id=OWNER_ID,
                document_ids=[],
                top_k=2,
            )

        self.assertEqual(
            [item["chunk_id"] for item in results],
            [first["chunk_id"], second["chunk_id"]],
        )
        self.assertEqual(
            [item["document_id"] for item in elasticsearch.expected["es_version_001"]],
            ["document_001"],
        )
        self.assertTrue(
            all(
                item["is_active"] is False
                for item in elasticsearch.source_fingerprints["es_version_001"]
            )
        )
        self.assertTrue(
            all(
                item["is_active"] is False
                for item in milvus.source_fingerprints["milvus_version_001"]
            )
        )

    def test_elasticsearch_and_milvus_searches_overlap_per_ready_route(self):
        route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_001",
            document_version_id="version_001",
            elasticsearch_index="es_version_001",
            milvus_collection="milvus_version_001",
        )
        expected = chunk("document_001", "version_001", 1)
        elasticsearch = RankingTransport(
            {"es_version_001": [RankedChunk("es", 1, 1.0, expected)]}
        )
        milvus = RankingTransport(
            {"milvus_version_001": [RankedChunk("milvus", 1, 0.9, expected)]}
        )
        rendezvous = threading.Barrier(2, timeout=2.0)

        class ConcurrentElasticsearchIndex(FakeElasticsearchIndex):
            def search(self, question, scope, **kwargs):
                rendezvous.wait()
                return super().search(question, scope, **kwargs)

        class ConcurrentMilvusIndex(FakeMilvusIndex):
            def search(self, question, scope, provider, **kwargs):
                rendezvous.wait()
                return super().search(question, scope, provider, **kwargs)

        retriever = OnlineVersionRrfRetriever(
            resolver=StaticResolver([route]),
            elasticsearch_transport=elasticsearch,
            milvus_transport=milvus,
            embedding_provider=FakeEmbeddingProvider(),
            chunk_snapshots=FakeChunkSnapshots([expected]),
        )

        with patch(
            "backend.retrieval.online.ElasticsearchBm25Index",
            ConcurrentElasticsearchIndex,
        ), patch(
            "backend.retrieval.online.MilvusVectorIndex",
            ConcurrentMilvusIndex,
        ):
            results = retriever.retrieve(
                "question",
                {"user_id": OWNER_ID, "tenant_id": OWNER_ID},
                owner_id=OWNER_ID,
                document_ids=["document_001"],
            )

        self.assertEqual([item["chunk_id"] for item in results], [expected["chunk_id"]])

    def test_latency_observer_receives_sanitized_stage_breakdown(self):
        route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_001",
            document_version_id="version_001",
            elasticsearch_index="es_version_001",
            milvus_collection="milvus_version_001",
        )
        expected = chunk("document_001", "version_001", 1)
        observations: list[OnlineRetrievalLatencyBreakdown] = []
        retriever = OnlineVersionRrfRetriever(
            resolver=StaticResolver([route]),
            elasticsearch_transport=RankingTransport(
                {"es_version_001": [RankedChunk("es", 1, 1.0, expected)]}
            ),
            milvus_transport=RankingTransport(
                {"milvus_version_001": [RankedChunk("milvus", 1, 0.9, expected)]}
            ),
            embedding_provider=FakeEmbeddingProvider(),
            chunk_snapshots=FakeChunkSnapshots([expected]),
            latency_observer=observations.append,
        )

        with patch(
            "backend.retrieval.online.ElasticsearchBm25Index",
            FakeElasticsearchIndex,
        ), patch("backend.retrieval.online.MilvusVectorIndex", FakeMilvusIndex):
            retriever.retrieve(
                "question",
                {"user_id": OWNER_ID, "tenant_id": OWNER_ID},
                owner_id=OWNER_ID,
                document_ids=["document_001"],
            )

        self.assertEqual(len(observations), 1)
        observation = observations[0]
        self.assertEqual(observation.route_count, 1)
        self.assertEqual(observation.elasticsearch_total_work_latency_ms, 0.3)
        self.assertEqual(observation.query_embedding_work_latency_ms, 0.5)
        self.assertEqual(observation.milvus_ann_search_work_latency_ms, 0.6)
        self.assertGreaterEqual(observation.backend_parallel_wall_latency_ms, 0)
        self.assertGreaterEqual(observation.total_latency_ms, 0)

    def test_parallel_backend_failure_still_fails_closed(self):
        route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_001",
            document_version_id="version_001",
            elasticsearch_index="es_version_001",
            milvus_collection="milvus_version_001",
        )
        expected = chunk("document_001", "version_001", 1)
        elasticsearch = RankingTransport({"es_version_001": []})
        milvus = RankingTransport({"milvus_version_001": []})

        class FailingElasticsearchIndex(FakeElasticsearchIndex):
            def search(self, question, scope, **kwargs):
                del question, scope, kwargs
                raise RuntimeError("simulated Elasticsearch failure")

        retriever = OnlineVersionRrfRetriever(
            resolver=StaticResolver([route]),
            elasticsearch_transport=elasticsearch,
            milvus_transport=milvus,
            embedding_provider=FakeEmbeddingProvider(),
            chunk_snapshots=FakeChunkSnapshots([expected]),
        )

        with patch(
            "backend.retrieval.online.ElasticsearchBm25Index",
            FailingElasticsearchIndex,
        ), patch("backend.retrieval.online.MilvusVectorIndex", FakeMilvusIndex):
            with self.assertRaisesRegex(
                OnlineVisibilityUnavailableError,
                "failed closed",
            ):
                retriever.retrieve(
                    "question",
                    {"user_id": OWNER_ID, "tenant_id": OWNER_ID},
                    owner_id=OWNER_ID,
                    document_ids=["document_001"],
                )

    def test_candidate_identity_drift_fails_closed(self):
        route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_001",
            document_version_id="version_001",
            elasticsearch_index="es_version_001",
            milvus_collection="milvus_version_001",
        )
        expected = chunk("document_001", "version_001", 1)
        drifted = {**expected, "tenant_id": "owner_other"}
        elasticsearch = RankingTransport(
            {"es_version_001": [RankedChunk("es", 1, 1.0, drifted)]}
        )
        milvus = RankingTransport({"milvus_version_001": []})
        retriever = OnlineVersionRrfRetriever(
            resolver=StaticResolver([route]),
            elasticsearch_transport=elasticsearch,
            milvus_transport=milvus,
            embedding_provider=FakeEmbeddingProvider(),
            chunk_snapshots=FakeChunkSnapshots([expected]),
        )
        scope = {"user_id": OWNER_ID, "tenant_id": OWNER_ID}

        with patch(
            "backend.retrieval.online.ElasticsearchBm25Index",
            FakeElasticsearchIndex,
        ), patch("backend.retrieval.online.MilvusVectorIndex", FakeMilvusIndex):
            with self.assertRaises(OnlineVisibilityUnavailableError):
                retriever.retrieve(
                    "question",
                    scope,
                    owner_id=OWNER_ID,
                    document_ids=["document_001"],
                )

    def test_postgres_invalidation_during_retrieval_fails_closed(self):
        route = OnlineVersionRoute(
            owner_id=OWNER_ID,
            document_id="document_001",
            document_version_id="version_001",
            elasticsearch_index="es_version_001",
            milvus_collection="milvus_version_001",
        )

        class InvalidatedResolver(StaticResolver):
            def revalidate(self, routes, **kwargs):
                del routes, kwargs
                raise OnlineVisibilityUnavailableError("version became inactive")

        expected = chunk("document_001", "version_001", 1)
        elasticsearch = RankingTransport(
            {"es_version_001": [RankedChunk("es", 1, 1.0, expected)]}
        )
        milvus = RankingTransport({"milvus_version_001": []})
        retriever = OnlineVersionRrfRetriever(
            resolver=InvalidatedResolver([route]),
            elasticsearch_transport=elasticsearch,
            milvus_transport=milvus,
            embedding_provider=FakeEmbeddingProvider(),
            chunk_snapshots=FakeChunkSnapshots([expected]),
        )
        scope = {"user_id": OWNER_ID, "tenant_id": OWNER_ID}

        with patch(
            "backend.retrieval.online.ElasticsearchBm25Index",
            FakeElasticsearchIndex,
        ), patch("backend.retrieval.online.MilvusVectorIndex", FakeMilvusIndex):
            with self.assertRaisesRegex(
                OnlineVisibilityUnavailableError,
                "became inactive",
            ):
                retriever.retrieve(
                    "question",
                    scope,
                    owner_id=OWNER_ID,
                    document_ids=["document_001"],
                )


if __name__ == "__main__":
    unittest.main()
