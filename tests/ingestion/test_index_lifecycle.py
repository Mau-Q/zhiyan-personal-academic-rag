from __future__ import annotations

import unittest
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from backend.ingestion.index_lifecycle import (
    CleanupRequest,
    InactivationCleanupPendingError,
    InactivationReason,
    IndexBackend,
    IndexLifecycleError,
    IndexWriteReceipt,
    inactivate_and_schedule_cleanup,
    publish_prepared_indexes,
)
from backend.ingestion.models import ChunkRecordV1, IngestionResult
from backend.ingestion.persistent import PersistentIngestionPreparation
from backend.retrieval.sqlite_fts import chunks_fingerprint
from backend.storage.models import (
    ALLOWED_LIFECYCLE_TRANSITIONS,
    DocumentIdentityV1,
    DocumentVersionLifecycleV1,
    IndexState,
    IndexStatesV1,
    IngestionJobStatus,
    IngestionJobV1,
    LifecycleStatus,
)


NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(
        self,
        version: DocumentVersionLifecycleV1,
        job: IngestionJobV1,
        events: list[str],
    ) -> None:
        self.version = version
        self.job = job
        self.events = events
        self.fail_finalize = False

    def _replace_version(
        self,
        *,
        target_status: LifecycleStatus,
        expected_revision: int,
        updates: Mapping[str, Any],
    ) -> DocumentVersionLifecycleV1:
        if expected_revision != self.version.lifecycle_revision:
            raise ValueError("stale lifecycle revision")
        is_progress = (
            self.version.lifecycle_status is LifecycleStatus.PROCESSING
            and target_status is LifecycleStatus.PROCESSING
            and bool(updates)
        )
        if (
            target_status not in ALLOWED_LIFECYCLE_TRANSITIONS[self.version.lifecycle_status]
            and not is_progress
        ):
            raise ValueError("invalid lifecycle transition")
        payload = {
            **self.version.model_dump(),
            **dict(updates),
            "lifecycle_revision": self.version.lifecycle_revision + 1,
            "lifecycle_status": target_status,
            "updated_at": NOW,
        }
        self.version = DocumentVersionLifecycleV1.model_validate(payload)
        return self.version

    def transition_version(self, **kwargs: Any) -> DocumentVersionLifecycleV1:
        target = kwargs["target_status"]
        event = (
            "repository:inactive"
            if target is LifecycleStatus.INACTIVE
            else "repository:progress"
        )
        self.events.append(event)
        return self._replace_version(
            target_status=target,
            expected_revision=kwargs["expected_revision"],
            updates=kwargs.get("updates") or {},
        )

    def record_indexing_failure(
        self, **kwargs: Any
    ) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]:
        self.events.append(f"repository:failure:{kwargs['failure_code']}")
        self._replace_version(
            target_status=LifecycleStatus.PROCESSING,
            expected_revision=kwargs["expected_revision"],
            updates={
                "index_states": kwargs["index_states"],
                "failure_code": kwargs["failure_code"],
            },
        )
        self.job = IngestionJobV1.model_validate(
            {
                **self.job.model_dump(),
                "status": IngestionJobStatus.FAILED,
                "failure_code": kwargs["failure_code"],
                "updated_at": NOW,
            }
        )
        return self.version, self.job

    def finalize_indexing_success(
        self, **kwargs: Any
    ) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]:
        self.events.append("repository:ready")
        if self.fail_finalize:
            self.fail_finalize = False
            raise RuntimeError("simulated finalization failure")
        self._replace_version(
            target_status=LifecycleStatus.READY,
            expected_revision=kwargs["expected_revision"],
            updates={
                "index_states": kwargs["index_states"],
                "vector_index_time": kwargs["vector_index_time"],
                "failure_code": None,
            },
        )
        self.job = IngestionJobV1.model_validate(
            {
                **self.job.model_dump(),
                "status": IngestionJobStatus.SUCCEEDED,
                "failure_code": None,
                "updated_at": NOW,
            }
        )
        return self.version, self.job

    def resume(self) -> None:
        self.job = IngestionJobV1.model_validate(
            {
                **self.job.model_dump(),
                "status": IngestionJobStatus.RUNNING,
                "failure_code": None,
                "attempt_count": self.job.attempt_count + 1,
                "updated_at": NOW,
            }
        )


class FakeWriter:
    def __init__(self, backend: IndexBackend, events: list[str]) -> None:
        self.backend = backend
        self.events = events
        self.fail_stage = False
        self.fail_activate = False
        self.fail_deactivate = False
        self.stage_count = 0

    @property
    def label(self) -> str:
        return "es" if self.backend is IndexBackend.ELASTICSEARCH else "milvus"

    def ensure_staged(
        self,
        *,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        chunks: Sequence[Mapping[str, Any]],
    ) -> IndexWriteReceipt:
        del document_id
        self.events.append(f"{self.label}:stage")
        self.stage_count += 1
        if self.fail_stage:
            raise RuntimeError("simulated stage failure")
        self.assert_inactive(chunks)
        return IndexWriteReceipt(
            backend=self.backend,
            owner_id=owner_id,
            document_version_id=document_version_id,
            chunk_count=len(chunks),
            source_chunks_sha256=chunks_fingerprint(chunks),
        )

    def assert_inactive(self, chunks: Sequence[Mapping[str, Any]]) -> None:
        if not all(chunk["is_active"] is False for chunk in chunks):
            raise AssertionError("writer received an active staged chunk")

    def activate_version(self, *, owner_id: str, document_version_id: str) -> None:
        del owner_id, document_version_id
        self.events.append(f"{self.label}:activate")
        if self.fail_activate:
            raise RuntimeError("simulated activation failure")

    def deactivate_version(self, *, owner_id: str, document_version_id: str) -> None:
        del owner_id, document_version_id
        self.events.append(f"{self.label}:deactivate")
        if self.fail_deactivate:
            raise RuntimeError("simulated deactivation failure")


class FakeVisibility:
    def __init__(self, events: list[str], *, fail: bool = False) -> None:
        self.events = events
        self.fail = fail

    def invalidate_version(self, **kwargs: Any) -> None:
        del kwargs
        self.events.append("visibility:invalidate")
        if self.fail:
            raise RuntimeError("simulated visibility invalidation failure")


class FakeCleanup:
    def __init__(
        self,
        events: list[str],
        *,
        fail_backend: IndexBackend | None = None,
    ) -> None:
        self.events = events
        self.fail_backend = fail_backend
        self.requests: list[CleanupRequest] = []

    def enqueue(self, request: CleanupRequest) -> None:
        label = "es" if request.backend is IndexBackend.ELASTICSEARCH else "milvus"
        self.events.append(f"cleanup:{label}")
        if request.backend is self.fail_backend:
            raise RuntimeError("simulated cleanup enqueue failure")
        self.requests.append(request)


def make_preparation(events: list[str]):
    identity = DocumentIdentityV1(
        paper_id="paper_001",
        document_id="doc_001",
        owner_id="owner_001",
        source_type="uploaded",
        mapping_version="document_mapping_v1",
        source_created_time=NOW,
        source_updated_time=NOW,
    )
    version = DocumentVersionLifecycleV1(
        paper_id="paper_001",
        document_id="doc_001",
        owner_id="owner_001",
        document_version_id="version_001",
        content_sha256="a" * 64,
        source_snapshot_sha256="b" * 64,
        parse_version="pypdf_text_v1",
        lifecycle_revision=2,
        lifecycle_status=LifecycleStatus.PROCESSING,
        parse_finish_time=NOW,
        chunk_splitter_time=NOW,
        chunk_create_time=NOW,
        chunk_gen_time=NOW,
        updated_at=NOW,
    )
    job = IngestionJobV1(
        job_id="job_001",
        owner_id="owner_001",
        idempotency_key="upload_001",
        document_id="doc_001",
        document_version_id="version_001",
        status=IngestionJobStatus.RUNNING,
        attempt_count=1,
        created_at=NOW,
        updated_at=NOW,
    )
    chunks = tuple(
        ChunkRecordV1(
            chunk_id=f"chunk_{position:03d}",
            document_id="doc_001",
            version_id="version_001",
            text=f"Evidence chunk {position}",
            section_path="Method",
            page_start=position,
            page_end=position,
            parent_chunk_id=None,
            previous_chunk_id=None,
            next_chunk_id=None,
            tenant_id="owner_001",
            visibility="private",
            library_scope_ids=["library_001"],
            parse_version="pypdf_text_v1",
            embedding_version="bge_m3_v1",
            is_active=False,
        )
        for position in (1, 2)
    )
    ingestion = IngestionResult(
        document_id="doc_001",
        version_id="version_001",
        pdf_sha256="a" * 64,
        source_text_sha256="c" * 64,
        parse_status="PASS",
        warnings=(),
        strategy="fixed_boundary_v1",
        chunks=chunks,
    )
    repository = FakeRepository(version, job, events)
    preparation = PersistentIngestionPreparation(identity, version, job, ingestion)
    return repository, preparation


class IndexLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[str] = []
        self.repository, self.preparation = make_preparation(self.events)
        self.elasticsearch = FakeWriter(IndexBackend.ELASTICSEARCH, self.events)
        self.milvus = FakeWriter(IndexBackend.MILVUS, self.events)

    def publish(self):
        return publish_prepared_indexes(
            self.preparation,
            repository=self.repository,
            elasticsearch=self.elasticsearch,
            milvus=self.milvus,
            clock=lambda: NOW,
        )

    def test_success_activates_both_before_atomic_ready_and_job_success(self):
        result = self.publish()

        self.assertEqual(result.version.lifecycle_status, LifecycleStatus.READY)
        self.assertTrue(result.version.is_active)
        self.assertEqual(result.job.status, IngestionJobStatus.SUCCEEDED)
        self.assertEqual(
            result.version.index_states,
            IndexStatesV1(
                elasticsearch_chunks=IndexState.READY,
                milvus_vectors=IndexState.READY,
            ),
        )
        self.assertLess(
            self.events.index("milvus:activate"),
            self.events.index("repository:ready"),
        )

    def test_elasticsearch_stage_failure_is_persisted_before_milvus_runs(self):
        self.elasticsearch.fail_stage = True

        with self.assertRaises(IndexLifecycleError) as captured:
            self.publish()

        self.assertEqual(captured.exception.code, "ELASTICSEARCH_CHUNKS_STAGE_FAILED")
        self.assertEqual(
            self.repository.version.index_states.elasticsearch_chunks,
            IndexState.FAILED,
        )
        self.assertEqual(self.repository.job.status, IngestionJobStatus.FAILED)
        self.assertNotIn("milvus:stage", self.events)

    def test_milvus_stage_failure_preserves_es_and_replay_can_finish(self):
        self.milvus.fail_stage = True
        with self.assertRaises(IndexLifecycleError):
            self.publish()

        self.assertEqual(
            self.repository.version.index_states,
            IndexStatesV1(
                elasticsearch_chunks=IndexState.READY,
                milvus_vectors=IndexState.FAILED,
            ),
        )
        self.repository.resume()
        self.milvus.fail_stage = False
        self.preparation = PersistentIngestionPreparation(
            self.preparation.identity,
            self.repository.version,
            self.repository.job,
            self.preparation.ingestion,
        )

        result = self.publish()

        self.assertEqual(result.version.lifecycle_status, LifecycleStatus.READY)
        self.assertEqual(self.elasticsearch.stage_count, 2)
        self.assertEqual(self.milvus.stage_count, 2)

    def test_activation_failure_deactivates_both_and_never_enters_ready(self):
        self.milvus.fail_activate = True

        with self.assertRaises(IndexLifecycleError) as captured:
            self.publish()

        self.assertEqual(captured.exception.code, "MILVUS_VECTORS_ACTIVATION_FAILED")
        self.assertIn("es:deactivate", self.events)
        self.assertIn("milvus:deactivate", self.events)
        self.assertEqual(
            self.repository.version.lifecycle_status,
            LifecycleStatus.PROCESSING,
        )
        self.assertFalse(self.repository.version.is_active)

    def test_finalization_failure_compensates_and_records_replayable_failure(self):
        self.repository.fail_finalize = True

        with self.assertRaises(IndexLifecycleError) as captured:
            self.publish()

        self.assertEqual(captured.exception.code, "INDEX_FINALIZATION_FAILED")
        self.assertIn("es:deactivate", self.events)
        self.assertIn("milvus:deactivate", self.events)
        self.assertEqual(self.repository.job.status, IngestionJobStatus.FAILED)
        self.assertFalse(self.repository.version.is_active)

    def test_inactivation_commits_truth_before_visibility_and_cleanup(self):
        published = self.publish()
        self.events.clear()
        cleanup = FakeCleanup(self.events)

        result = inactivate_and_schedule_cleanup(
            published.version,
            reason=InactivationReason.REVOKE,
            repository=self.repository,
            visibility=FakeVisibility(self.events),
            cleanup=cleanup,
            elasticsearch=self.elasticsearch,
            milvus=self.milvus,
            clock=lambda: NOW,
        )

        self.assertEqual(result.version.lifecycle_status, LifecycleStatus.INACTIVE)
        self.assertFalse(result.version.is_active)
        self.assertEqual(self.events[0], "repository:inactive")
        self.assertEqual(self.events[1], "visibility:invalidate")
        self.assertEqual(len(result.cleanup_requests), 2)

    def test_downstream_cleanup_failure_never_reactivates_fact_source(self):
        published = self.publish()
        self.events.clear()
        self.elasticsearch.fail_deactivate = True
        cleanup = FakeCleanup(self.events, fail_backend=IndexBackend.MILVUS)

        with self.assertRaises(InactivationCleanupPendingError) as captured:
            inactivate_and_schedule_cleanup(
                published.version,
                reason=InactivationReason.DELETE,
                repository=self.repository,
                visibility=FakeVisibility(self.events, fail=True),
                cleanup=cleanup,
                elasticsearch=self.elasticsearch,
                milvus=self.milvus,
                clock=lambda: NOW,
            )

        result = captured.exception.result
        self.assertEqual(result.version.lifecycle_status, LifecycleStatus.INACTIVE)
        self.assertFalse(result.version.is_active)
        self.assertEqual(self.events[0], "repository:inactive")
        self.assertIn("query_visibility:invalidate", result.failures)
        self.assertIn("elasticsearch_chunks:deactivate", result.failures)
        self.assertIn("milvus_vectors:enqueue_cleanup", result.failures)


if __name__ == "__main__":
    unittest.main()
