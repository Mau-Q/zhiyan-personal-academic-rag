from __future__ import annotations

import unittest
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from backend.ingestion.persistent import prepare_persistent_pdf_ingestion
from backend.ingestion.service import PdfIngestionError
from backend.storage.models import (
    ALLOWED_LIFECYCLE_TRANSITIONS,
    DocumentIdentityV1,
    DocumentVersionLifecycleV1,
    IndexStatesV1,
    IngestionJobStatus,
    IngestionJobV1,
    LifecycleStatus,
)
from tests.ingestion.pdf_fixture import synthetic_text_pdf


NOW = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)
GOOD_PDF = synthetic_text_pdf(
    [
        "1. Introduction\n"
        "This versioned document has deterministic evidence and source lineage. " * 12,
        "2. Method\n"
        "The method preserves owner scope, PDF pages, and stable chunk identifiers. " * 12,
    ]
)


class InMemoryFactSource:
    def __init__(self) -> None:
        self.identities: dict[tuple[str, str], DocumentIdentityV1] = {}
        self.versions: dict[
            tuple[str, str, str, str, str], DocumentVersionLifecycleV1
        ] = {}
        self.jobs: dict[tuple[str, str], IngestionJobV1] = {}
        self.calls: list[str] = []
        self.next_id = 1

    def _id(self, prefix: str) -> str:
        value = f"{prefix}_{self.next_id:03d}"
        self.next_id += 1
        return value

    def register_document(self, **kwargs: Any) -> DocumentIdentityV1:
        self.calls.append("register_document")
        key = (kwargs["owner_id"], kwargs["paper_id"])
        existing = self.identities.get(key)
        if existing is not None:
            if existing.source_type != kwargs["source_type"]:
                raise ValueError("immutable source_type conflict")
            return existing
        identity = DocumentIdentityV1(
            paper_id=kwargs["paper_id"],
            document_id=self._id("doc"),
            owner_id=kwargs["owner_id"],
            source_type=kwargs["source_type"],
            mapping_version=kwargs["mapping_version"],
            source_created_time=kwargs["source_created_time"],
            source_updated_time=kwargs["source_updated_time"],
        )
        self.identities[key] = identity
        return identity

    def register_version(self, **kwargs: Any) -> DocumentVersionLifecycleV1:
        self.calls.append("register_version")
        identity = next(
            (
                item
                for item in self.identities.values()
                if item.owner_id == kwargs["owner_id"]
                and item.document_id == kwargs["document_id"]
            ),
            None,
        )
        if identity is None:
            raise ValueError("owner-scoped document missing")
        key = (
            kwargs["owner_id"],
            kwargs["document_id"],
            kwargs["content_sha256"],
            kwargs["source_snapshot_sha256"],
            kwargs["parse_version"],
        )
        existing = self.versions.get(key)
        if existing is not None:
            return existing
        version = DocumentVersionLifecycleV1(
            paper_id=identity.paper_id,
            document_id=identity.document_id,
            owner_id=identity.owner_id,
            document_version_id=self._id("document_version"),
            content_sha256=kwargs["content_sha256"],
            source_snapshot_sha256=kwargs["source_snapshot_sha256"],
            parse_version=kwargs["parse_version"],
            lifecycle_revision=1,
            lifecycle_status=LifecycleStatus.REGISTERED,
            updated_at=NOW,
        )
        self.versions[key] = version
        return version

    def _version_key(
        self, *, owner_id: str, document_version_id: str
    ) -> tuple[str, str, str, str, str]:
        return next(
            key
            for key, value in self.versions.items()
            if value.owner_id == owner_id
            and value.document_version_id == document_version_id
        )

    def register_ingestion_job(self, **kwargs: Any) -> IngestionJobV1:
        self.calls.append("register_ingestion_job")
        key = (kwargs["owner_id"], kwargs["idempotency_key"])
        existing = self.jobs.get(key)
        if existing is not None:
            if existing.document_version_id != kwargs["document_version_id"]:
                raise ValueError("idempotency key changed version")
            return existing
        job = IngestionJobV1(
            job_id=self._id("ingestion_job"),
            owner_id=kwargs["owner_id"],
            idempotency_key=kwargs["idempotency_key"],
            document_id=kwargs["document_id"],
            document_version_id=kwargs["document_version_id"],
            status=IngestionJobStatus.PENDING,
            attempt_count=0,
            created_at=NOW,
            updated_at=NOW,
        )
        self.jobs[key] = job
        return job

    def register_version_and_ingestion_job(
        self, **kwargs: Any
    ) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]:
        self.calls.append("register_version_and_ingestion_job")
        job_key = (kwargs["owner_id"], kwargs["idempotency_key"])
        existing_job = self.jobs.get(job_key)
        if existing_job is not None:
            existing_version = next(
                version
                for version in self.versions.values()
                if version.document_version_id == existing_job.document_version_id
            )
            if (
                existing_job.document_id != kwargs["document_id"]
                or existing_version.content_sha256 != kwargs["content_sha256"]
                or existing_version.source_snapshot_sha256
                != kwargs["source_snapshot_sha256"]
                or existing_version.parse_version != kwargs["parse_version"]
            ):
                raise ValueError("idempotency key changed immutable source identity")
            return existing_version, existing_job
        version = self.register_version(**kwargs)
        job = self.register_ingestion_job(
            owner_id=kwargs["owner_id"],
            document_id=kwargs["document_id"],
            document_version_id=version.document_version_id,
            idempotency_key=kwargs["idempotency_key"],
        )
        return version, job

    def transition_version(self, **kwargs: Any) -> DocumentVersionLifecycleV1:
        self.calls.append("transition_version")
        key = self._version_key(
            owner_id=kwargs["owner_id"],
            document_version_id=kwargs["document_version_id"],
        )
        current = self.versions[key]
        if current.lifecycle_revision != kwargs["expected_revision"]:
            raise ValueError("stale revision")
        target = kwargs["target_status"]
        updates = dict(kwargs.get("updates") or {})
        is_progress = (
            current.lifecycle_status is LifecycleStatus.PROCESSING
            and target is LifecycleStatus.PROCESSING
            and bool(updates)
        )
        if (
            target not in ALLOWED_LIFECYCLE_TRANSITIONS[current.lifecycle_status]
            and not is_progress
        ):
            raise ValueError("invalid lifecycle transition")
        if "index_states" in updates:
            updates["index_states"] = IndexStatesV1.model_validate(
                updates["index_states"]
            )
        updated = DocumentVersionLifecycleV1.model_validate(
            {
                **current.model_dump(),
                **updates,
                "lifecycle_revision": current.lifecycle_revision + 1,
                "lifecycle_status": target,
                "updated_at": NOW,
            }
        )
        self.versions[key] = updated
        return updated

    def update_ingestion_job(self, **kwargs: Any) -> IngestionJobV1:
        self.calls.append("update_ingestion_job")
        key = next(
            key
            for key, value in self.jobs.items()
            if value.owner_id == kwargs["owner_id"] and value.job_id == kwargs["job_id"]
        )
        current = self.jobs[key]
        status = kwargs["status"]
        updated = IngestionJobV1.model_validate(
            {
                **current.model_dump(),
                "status": status,
                "attempt_count": current.attempt_count
                + (1 if status is IngestionJobStatus.RUNNING else 0),
                "failure_code": kwargs.get("failure_code"),
                "updated_at": NOW,
            }
        )
        self.jobs[key] = updated
        return updated


def prepare(repository: InMemoryFactSource, pdf_bytes: bytes = GOOD_PDF, **overrides):
    arguments = {
        "repository": repository,
        "owner_id": "owner_001",
        "paper_id": "paper_001",
        "source_type": "uploaded",
        "source_created_time": NOW,
        "source_updated_time": NOW,
        "idempotency_key": "upload_001",
        "strategy": "fixed_boundary_v1",
        "library_scope_ids": ["personal_library_001"],
        "clock": lambda: NOW,
    }
    arguments.update(overrides)
    return prepare_persistent_pdf_ingestion(pdf_bytes, **arguments)


class PersistentIngestionTests(unittest.TestCase):
    def test_success_is_versioned_owner_scoped_and_not_online_ready(self):
        repository = InMemoryFactSource()
        result = prepare(repository)

        self.assertEqual(result.identity.owner_id, "owner_001")
        self.assertEqual(result.version.lifecycle_status, LifecycleStatus.PROCESSING)
        self.assertFalse(result.version.is_active)
        self.assertIsNone(result.version.vector_index_time)
        self.assertEqual(result.job.status, IngestionJobStatus.RUNNING)
        self.assertEqual(result.job.attempt_count, 1)
        for chunk in result.ingestion.chunks:
            self.assertEqual(chunk.version_id, result.version.document_version_id)
            self.assertEqual(chunk.tenant_id, "owner_001")
            self.assertFalse(chunk.is_active)

    def test_replay_reuses_mapping_version_job_and_chunk_ids(self):
        repository = InMemoryFactSource()
        first = prepare(repository)
        second = prepare(repository)

        self.assertEqual(first.identity.document_id, second.identity.document_id)
        self.assertEqual(
            first.version.document_version_id,
            second.version.document_version_id,
        )
        self.assertEqual(first.job.job_id, second.job.job_id)
        self.assertEqual(second.job.attempt_count, 2)
        self.assertEqual(
            [chunk.chunk_id for chunk in first.ingestion.chunks],
            [chunk.chunk_id for chunk in second.ingestion.chunks],
        )
        self.assertEqual(len(repository.identities), 1)
        self.assertEqual(len(repository.versions), 1)
        self.assertEqual(len(repository.jobs), 1)

    def test_pdf_identity_mismatch_precedes_all_persistent_mutation(self):
        repository = InMemoryFactSource()
        with self.assertRaises(PdfIngestionError) as captured:
            prepare(repository, expected_sha256="0" * 64)

        self.assertEqual(captured.exception.code, "PDF_IDENTITY_MISMATCH")
        self.assertFalse(repository.calls)

    def test_idempotency_key_cannot_be_reused_for_different_pdf(self):
        repository = InMemoryFactSource()
        prepare(repository)
        changed_pdf = synthetic_text_pdf(
            ["1. Changed\nThis is a different persistent source snapshot. " * 12]
        )

        with self.assertRaisesRegex(ValueError, "idempotency key changed"):
            prepare(repository, changed_pdf)
        self.assertEqual(len(repository.versions), 1)
        self.assertEqual(len(repository.jobs), 1)

    def test_parse_failure_is_persisted_and_same_request_can_retry(self):
        repository = InMemoryFactSource()
        invalid_pdf = synthetic_text_pdf([""])

        for expected_attempt in (1, 2):
            with self.assertRaises(PdfIngestionError) as captured:
                prepare(repository, invalid_pdf)
            self.assertEqual(captured.exception.code, "PARSE_QUALITY_GATE_BLOCKED")
            version = next(iter(repository.versions.values()))
            job = next(iter(repository.jobs.values()))
            self.assertEqual(version.lifecycle_status, LifecycleStatus.FAILED)
            self.assertEqual(version.failure_code, "PARSE_QUALITY_GATE_BLOCKED")
            self.assertEqual(job.status, IngestionJobStatus.FAILED)
            self.assertEqual(job.attempt_count, expected_attempt)

    def test_parse_review_stops_before_indexes_and_requires_review(self):
        repository = InMemoryFactSource()
        result = prepare(
            repository,
            synthetic_text_pdf(["Short text"]),
            allow_parse_review=True,
        )

        self.assertEqual(result.ingestion.parse_status, "REVIEW")
        self.assertEqual(result.version.lifecycle_status, LifecycleStatus.REVIEW)
        self.assertFalse(result.version.is_active)
        self.assertEqual(result.job.status, IngestionJobStatus.FAILED)
        self.assertEqual(result.job.failure_code, "PARSE_REVIEW_REQUIRED")

    def test_same_paper_for_different_owners_has_distinct_identity(self):
        repository = InMemoryFactSource()
        first = prepare(repository)
        second = prepare(
            repository,
            owner_id="owner_002",
            idempotency_key="upload_001",
            library_scope_ids=["personal_library_002"],
        )

        self.assertNotEqual(first.identity.document_id, second.identity.document_id)
        self.assertNotEqual(
            first.version.document_version_id,
            second.version.document_version_id,
        )
        self.assertEqual(len(repository.identities), 2)


if __name__ == "__main__":
    unittest.main()
