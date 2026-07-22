"""Replay-safe PDF preparation coordinated through the PostgreSQL fact source."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Protocol

from backend.ingestion.models import IngestionResult
from backend.ingestion.service import PARSE_VERSION, PdfIngestionError, ingest_pdf_bytes
from backend.storage.models import (
    DocumentIdentityV1,
    DocumentVersionLifecycleV1,
    IngestionJobStatus,
    IngestionJobV1,
    LifecycleStatus,
)


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class FactSourceRepository(Protocol):
    def register_document(self, **kwargs: Any) -> DocumentIdentityV1: ...
    def register_version_and_ingestion_job(
        self, **kwargs: Any
    ) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]: ...
    def transition_version(self, **kwargs: Any) -> DocumentVersionLifecycleV1: ...
    def update_ingestion_job(self, **kwargs: Any) -> IngestionJobV1: ...


@dataclass(frozen=True)
class PersistentIngestionPreparation:
    identity: DocumentIdentityV1
    version: DocumentVersionLifecycleV1
    job: IngestionJobV1
    ingestion: IngestionResult


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _start_or_resume_processing(
    repository: FactSourceRepository,
    *,
    version: DocumentVersionLifecycleV1,
) -> DocumentVersionLifecycleV1:
    if version.lifecycle_status is LifecycleStatus.PROCESSING:
        return version
    if version.lifecycle_status in {
        LifecycleStatus.REGISTERED,
        LifecycleStatus.REVIEW,
        LifecycleStatus.FAILED,
    }:
        return repository.transition_version(
            owner_id=version.owner_id,
            document_version_id=version.document_version_id,
            expected_revision=version.lifecycle_revision,
            target_status=LifecycleStatus.PROCESSING,
            updates={"failure_code": None},
        )
    raise ValueError(
        f"document version in {version.lifecycle_status.value} cannot be prepared again"
    )


def _record_failure(
    repository: FactSourceRepository,
    *,
    version: DocumentVersionLifecycleV1,
    job: IngestionJobV1,
    failure_code: str,
) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]:
    failed_version = repository.transition_version(
        owner_id=version.owner_id,
        document_version_id=version.document_version_id,
        expected_revision=version.lifecycle_revision,
        target_status=LifecycleStatus.FAILED,
        updates={"failure_code": failure_code},
    )
    failed_job = repository.update_ingestion_job(
        owner_id=job.owner_id,
        job_id=job.job_id,
        status=IngestionJobStatus.FAILED,
        failure_code=failure_code,
    )
    return failed_version, failed_job


def prepare_persistent_pdf_ingestion(
    pdf_bytes: bytes,
    *,
    repository: FactSourceRepository,
    owner_id: str,
    paper_id: str,
    source_type: str,
    source_created_time: datetime,
    source_updated_time: datetime,
    idempotency_key: str,
    strategy: str,
    library_scope_ids: list[str],
    expected_sha256: str | None = None,
    source_snapshot_sha256: str | None = None,
    allow_parse_review: bool = False,
    mapping_version: str = "document_mapping_v1",
    clock: Callable[[], datetime] = _utc_now,
) -> PersistentIngestionPreparation:
    """Prepare inactive versioned chunks; indexing and READY happen in a later gate."""

    actual_sha256 = sha256(pdf_bytes).hexdigest()
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise PdfIngestionError(
            "PDF_IDENTITY_MISMATCH",
            "PDF bytes do not match the expected SHA-256 identity.",
        )
    snapshot_sha256 = source_snapshot_sha256 or actual_sha256
    if not SHA256_PATTERN.fullmatch(snapshot_sha256):
        raise ValueError("source_snapshot_sha256 must be a lowercase SHA-256")

    identity = repository.register_document(
        owner_id=owner_id,
        paper_id=paper_id,
        source_type=source_type,
        mapping_version=mapping_version,
        source_created_time=source_created_time,
        source_updated_time=source_updated_time,
    )
    version, job = repository.register_version_and_ingestion_job(
        owner_id=owner_id,
        document_id=identity.document_id,
        content_sha256=actual_sha256,
        source_snapshot_sha256=snapshot_sha256,
        parse_version=PARSE_VERSION,
        idempotency_key=idempotency_key,
    )
    version = _start_or_resume_processing(repository, version=version)
    job = repository.update_ingestion_job(
        owner_id=owner_id,
        job_id=job.job_id,
        status=IngestionJobStatus.RUNNING,
    )

    try:
        ingestion = ingest_pdf_bytes(
            pdf_bytes,
            document_id=identity.document_id,
            tenant_id=owner_id,
            visibility="private",
            library_scope_ids=library_scope_ids,
            strategy=strategy,
            expected_sha256=actual_sha256,
            allow_parse_review=allow_parse_review,
            version_id=version.document_version_id,
            is_active=False,
        )
    except PdfIngestionError as exc:
        _record_failure(
            repository,
            version=version,
            job=job,
            failure_code=exc.code,
        )
        raise

    completed_at = clock()
    progress: Mapping[str, Any] = {
        "parse_finish_time": completed_at,
        "chunk_splitter_time": completed_at,
        "chunk_create_time": completed_at,
        "chunk_gen_time": completed_at,
        "failure_code": None,
    }
    if ingestion.parse_status == "REVIEW":
        version = repository.transition_version(
            owner_id=owner_id,
            document_version_id=version.document_version_id,
            expected_revision=version.lifecycle_revision,
            target_status=LifecycleStatus.REVIEW,
            updates=progress,
        )
        job = repository.update_ingestion_job(
            owner_id=owner_id,
            job_id=job.job_id,
            status=IngestionJobStatus.FAILED,
            failure_code="PARSE_REVIEW_REQUIRED",
        )
    else:
        version = repository.transition_version(
            owner_id=owner_id,
            document_version_id=version.document_version_id,
            expected_revision=version.lifecycle_revision,
            target_status=LifecycleStatus.PROCESSING,
            updates=progress,
        )

    return PersistentIngestionPreparation(
        identity=identity,
        version=version,
        job=job,
        ingestion=ingestion,
    )
