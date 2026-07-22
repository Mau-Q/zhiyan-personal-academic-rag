from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend.retrieval.online import (
    OnlineScopeForbiddenError,
    OnlineVersionRoute,
    OnlineVersionRrfRetriever,
    OnlineVisibilityUnavailableError,
    PostgresReadyRouteResolver,
)
from backend.retrieval.results import RankedChunk
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
        del question, scope
        self.transport.expected[self.index_name] = kwargs["expected_chunks"]
        return self.transport.rankings[self.index_name]


class FakeMilvusIndex:
    def __init__(self, collection_name, transport):
        self.collection_name = collection_name
        self.transport = transport

    def search(self, question, scope, provider, **kwargs):
        del question, scope, provider
        self.transport.expected[self.collection_name] = kwargs["expected_chunks"]
        return self.transport.rankings[self.collection_name]


class RankingTransport:
    def __init__(self, rankings):
        self.rankings = rankings
        self.expected = {}


class OnlineVersionRrfRetrieverTests(unittest.TestCase):
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
                [first, second],
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
                    [expected],
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
                    [expected],
                    owner_id=OWNER_ID,
                    document_ids=["document_001"],
                )


if __name__ == "__main__":
    unittest.main()
