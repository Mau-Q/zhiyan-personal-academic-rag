from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.storage.models import (
    DocumentVersionLifecycleV1,
    IndexState,
    IndexStatesV1,
    LifecycleStatus,
)
from backend.validation.stage1 import (
    Stage1ReconciliationError,
    reconcile_ready_scope,
)


NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def ready_version(
    document_id: str = "doc_001",
    document_version_id: str = "version_001",
) -> DocumentVersionLifecycleV1:
    return DocumentVersionLifecycleV1(
        paper_id="paper_001",
        document_id=document_id,
        owner_id="owner_001",
        document_version_id=document_version_id,
        content_sha256="a" * 64,
        source_snapshot_sha256="b" * 64,
        parse_version="pypdf_text_v1",
        lifecycle_revision=4,
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


class FakeReadyRepository:
    def __init__(self, versions: tuple[DocumentVersionLifecycleV1, ...]) -> None:
        self.versions = versions

    def resolve_online_versions(self, *, owner_id: str, document_ids=()):
        return tuple(
            version
            for version in self.versions
            if version.owner_id == owner_id
            and (not document_ids or version.document_id in document_ids)
        )


class FakeRouteInspector:
    def __init__(self, route_prefix: str, *, fail: bool = False) -> None:
        self.route_prefix = route_prefix
        self.fail = fail

    def verify_online_version(
        self, *, owner_id: str, document_id: str, document_version_id: str
    ) -> str:
        del owner_id, document_id
        if self.fail:
            raise RuntimeError("simulated route drift")
        return f"{self.route_prefix}{document_version_id}"


class Stage1ReconciliationTests(unittest.TestCase):
    def test_exact_ready_scope_produces_sanitized_report(self):
        report = reconcile_ready_scope(
            repository=FakeReadyRepository((ready_version(),)),
            elasticsearch=FakeRouteInspector("es--"),
            milvus=FakeRouteInspector("milvus_"),
            owner_id="owner_001",
            document_ids=["doc_001"],
        )

        payload = report.model_dump()
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["requested_document_ids"], ("doc_001",))
        self.assertEqual(report.versions[0].elasticsearch_index, "es--version_001")
        self.assertEqual(report.versions[0].milvus_collection, "milvus_version_001")
        self.assertNotIn("text", payload)
        self.assertNotIn("database_url", payload)

    def test_missing_ready_version_fails_closed(self):
        with self.assertRaisesRegex(
            Stage1ReconciliationError, "does not match the requested"
        ):
            reconcile_ready_scope(
                repository=FakeReadyRepository(()),
                elasticsearch=FakeRouteInspector("es--"),
                milvus=FakeRouteInspector("milvus_"),
                owner_id="owner_001",
                document_ids=["doc_001"],
            )

    def test_one_physical_route_drift_fails_whole_report(self):
        with self.assertRaisesRegex(Stage1ReconciliationError, "physical route"):
            reconcile_ready_scope(
                repository=FakeReadyRepository((ready_version(),)),
                elasticsearch=FakeRouteInspector("es--"),
                milvus=FakeRouteInspector("milvus_", fail=True),
                owner_id="owner_001",
                document_ids=["doc_001"],
            )

    def test_scope_must_be_nonempty_unique_and_contract_safe(self):
        repository = FakeReadyRepository((ready_version(),))
        for document_ids in ([], ["doc_001", "doc_001"], ["bad id"]):
            with self.subTest(document_ids=document_ids):
                with self.assertRaisesRegex(Stage1ReconciliationError, "identity"):
                    reconcile_ready_scope(
                        repository=repository,
                        elasticsearch=FakeRouteInspector("es--"),
                        milvus=FakeRouteInspector("milvus_"),
                        owner_id="owner_001",
                        document_ids=document_ids,
                    )


if __name__ == "__main__":
    unittest.main()
