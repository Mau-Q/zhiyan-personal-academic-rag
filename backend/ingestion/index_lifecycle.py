"""Fail-closed coordination for versioned Elasticsearch and Milvus writes."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol

from backend.ingestion.persistent import PersistentIngestionPreparation
from backend.retrieval.sqlite_fts import chunks_fingerprint
from backend.storage.models import (
    DocumentVersionLifecycleV1,
    IndexState,
    IndexStatesV1,
    IngestionJobStatus,
    IngestionJobV1,
    LifecycleStatus,
)


class IndexBackend(StrEnum):
    ELASTICSEARCH = "elasticsearch_chunks"
    MILVUS = "milvus_vectors"


class InactivationReason(StrEnum):
    DELETE = "DELETE"
    REVOKE = "REVOKE"
    EXPIRE = "EXPIRE"


@dataclass(frozen=True)
class IndexWriteReceipt:
    backend: IndexBackend
    owner_id: str
    document_version_id: str
    chunk_count: int
    source_chunks_sha256: str


@dataclass(frozen=True)
class CleanupRequest:
    backend: IndexBackend
    owner_id: str
    document_id: str
    document_version_id: str


@dataclass(frozen=True)
class IndexPublicationResult:
    version: DocumentVersionLifecycleV1
    job: IngestionJobV1
    receipts: tuple[IndexWriteReceipt, IndexWriteReceipt]


@dataclass(frozen=True)
class InactivationResult:
    version: DocumentVersionLifecycleV1
    reason: InactivationReason
    visibility_invalidated: bool
    deactivated_backends: tuple[IndexBackend, ...]
    cleanup_requests: tuple[CleanupRequest, ...]
    failures: tuple[str, ...]


class IndexLifecycleError(RuntimeError):
    def __init__(self, code: str, message: str, *, compensation_failures: Sequence[str] = ()):
        super().__init__(message)
        self.code = code
        self.compensation_failures = tuple(compensation_failures)


class InactivationCleanupPendingError(RuntimeError):
    def __init__(self, result: InactivationResult):
        super().__init__("fact source is INACTIVE but downstream invalidation remains pending")
        self.result = result


class IndexLifecycleRepository(Protocol):
    def transition_version(self, **kwargs: Any) -> DocumentVersionLifecycleV1: ...
    def record_indexing_failure(
        self, **kwargs: Any
    ) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]: ...
    def finalize_indexing_success(
        self, **kwargs: Any
    ) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]: ...


class VersionIndexWriter(Protocol):
    backend: IndexBackend

    def ensure_staged(
        self,
        *,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        chunks: Sequence[Mapping[str, Any]],
    ) -> IndexWriteReceipt: ...

    def activate_version(self, *, owner_id: str, document_version_id: str) -> None: ...
    def deactivate_version(self, *, owner_id: str, document_version_id: str) -> None: ...


class QueryVisibilityInvalidator(Protocol):
    def invalidate_version(
        self, *, owner_id: str, document_id: str, document_version_id: str
    ) -> None: ...


class IndexCleanupScheduler(Protocol):
    def enqueue(self, request: CleanupRequest) -> None: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _updated_states(
    current: IndexStatesV1, backend: IndexBackend, state: IndexState
) -> IndexStatesV1:
    payload = current.model_dump()
    payload[backend.value] = state
    return IndexStatesV1.model_validate(payload)


def _validated_writers(
    elasticsearch: VersionIndexWriter,
    milvus: VersionIndexWriter,
) -> tuple[VersionIndexWriter, VersionIndexWriter]:
    if elasticsearch.backend is not IndexBackend.ELASTICSEARCH:
        raise ValueError("elasticsearch writer has the wrong backend identity")
    if milvus.backend is not IndexBackend.MILVUS:
        raise ValueError("milvus writer has the wrong backend identity")
    return elasticsearch, milvus


def _validate_preparation(
    preparation: PersistentIngestionPreparation,
) -> tuple[list[dict[str, Any]], str]:
    version = preparation.version
    job = preparation.job
    if version.lifecycle_status is not LifecycleStatus.PROCESSING:
        raise ValueError("index publication requires a PROCESSING document version")
    if job.status is not IngestionJobStatus.RUNNING:
        raise ValueError("index publication requires a RUNNING ingestion job")
    if (
        job.owner_id != version.owner_id
        or job.document_id != version.document_id
        or job.document_version_id != version.document_version_id
    ):
        raise ValueError("ingestion job identity does not match the document version")
    if preparation.ingestion.parse_status != "PASS":
        raise ValueError("only PASS ingestion output may enter dual-index publication")

    chunks = [chunk.model_dump() for chunk in preparation.ingestion.chunks]
    if not chunks:
        raise ValueError("index publication requires at least one chunk")
    for chunk in chunks:
        if (
            chunk["tenant_id"] != version.owner_id
            or chunk["document_id"] != version.document_id
            or chunk["version_id"] != version.document_version_id
            or chunk["is_active"] is not False
        ):
            raise ValueError(
                "staged chunks must match owner/document/version and remain inactive"
            )
    return chunks, chunks_fingerprint(chunks)


def _verify_receipt(
    receipt: IndexWriteReceipt,
    *,
    writer: VersionIndexWriter,
    version: DocumentVersionLifecycleV1,
    expected_count: int,
    expected_sha256: str,
) -> None:
    if receipt.backend is not writer.backend:
        raise ValueError("index writer returned a receipt for the wrong backend")
    if (
        receipt.owner_id != version.owner_id
        or receipt.document_version_id != version.document_version_id
        or receipt.chunk_count != expected_count
        or receipt.source_chunks_sha256 != expected_sha256
    ):
        raise ValueError("index writer receipt does not match the staged version identity")


def _compensate_deactivation(
    writers: Sequence[VersionIndexWriter],
    *,
    owner_id: str,
    document_version_id: str,
) -> tuple[str, ...]:
    failures: list[str] = []
    for writer in writers:
        try:
            writer.deactivate_version(
                owner_id=owner_id,
                document_version_id=document_version_id,
            )
        except Exception:
            failures.append(f"{writer.backend.value}:deactivate")
    return tuple(failures)


def _record_failure(
    repository: IndexLifecycleRepository,
    *,
    version: DocumentVersionLifecycleV1,
    job: IngestionJobV1,
    backend: IndexBackend,
    code: str,
) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]:
    states = _updated_states(version.index_states, backend, IndexState.FAILED)
    return repository.record_indexing_failure(
        owner_id=version.owner_id,
        document_version_id=version.document_version_id,
        expected_revision=version.lifecycle_revision,
        index_states=states,
        job_id=job.job_id,
        failure_code=code,
    )


def publish_prepared_indexes(
    preparation: PersistentIngestionPreparation,
    *,
    repository: IndexLifecycleRepository,
    elasticsearch: VersionIndexWriter,
    milvus: VersionIndexWriter,
    clock: Callable[[], datetime] = _utc_now,
) -> IndexPublicationResult:
    """Stage both indexes, activate them behind PostgreSQL, then atomically enter READY.

    Concrete writers must keep their staged/activated version outside online retrieval
    until PostgreSQL exposes that exact owner/version as READY.
    """

    writers = _validated_writers(elasticsearch, milvus)
    chunks, source_sha256 = _validate_preparation(preparation)
    version = preparation.version
    job = preparation.job
    receipts: list[IndexWriteReceipt] = []

    for writer in writers:
        try:
            receipt = writer.ensure_staged(
                owner_id=version.owner_id,
                document_id=version.document_id,
                document_version_id=version.document_version_id,
                chunks=chunks,
            )
            _verify_receipt(
                receipt,
                writer=writer,
                version=version,
                expected_count=len(chunks),
                expected_sha256=source_sha256,
            )
        except Exception as exc:
            code = f"{writer.backend.value.upper()}_STAGE_FAILED"
            try:
                version, job = _record_failure(
                    repository,
                    version=version,
                    job=job,
                    backend=writer.backend,
                    code=code,
                )
            except Exception as record_exc:
                raise IndexLifecycleError(
                    code,
                    "dual-index staging failed and fact-source failure recording failed",
                    compensation_failures=("fact_source:record_failure",),
                ) from record_exc
            raise IndexLifecycleError(code, "dual-index staging failed") from exc
        states = _updated_states(version.index_states, writer.backend, IndexState.READY)
        version = repository.transition_version(
            owner_id=version.owner_id,
            document_version_id=version.document_version_id,
            expected_revision=version.lifecycle_revision,
            target_status=LifecycleStatus.PROCESSING,
            updates={"index_states": states, "failure_code": None},
        )
        receipts.append(receipt)

    for writer in writers:
        try:
            writer.activate_version(
                owner_id=version.owner_id,
                document_version_id=version.document_version_id,
            )
        except Exception as exc:
            compensation = _compensate_deactivation(
                writers,
                owner_id=version.owner_id,
                document_version_id=version.document_version_id,
            )
            code = f"{writer.backend.value.upper()}_ACTIVATION_FAILED"
            try:
                version, job = _record_failure(
                    repository,
                    version=version,
                    job=job,
                    backend=writer.backend,
                    code=code,
                )
            except Exception as record_exc:
                raise IndexLifecycleError(
                    code,
                    "activation failed and fact-source failure recording failed",
                    compensation_failures=(*compensation, "fact_source:record_failure"),
                ) from record_exc
            raise IndexLifecycleError(
                code,
                "dual-index activation failed",
                compensation_failures=compensation,
            ) from exc

    try:
        version, job = repository.finalize_indexing_success(
            owner_id=version.owner_id,
            document_version_id=version.document_version_id,
            expected_revision=version.lifecycle_revision,
            index_states=IndexStatesV1(
                elasticsearch_chunks=IndexState.READY,
                milvus_vectors=IndexState.READY,
            ),
            vector_index_time=clock(),
            job_id=job.job_id,
        )
    except Exception as exc:
        compensation = _compensate_deactivation(
            writers,
            owner_id=version.owner_id,
            document_version_id=version.document_version_id,
        )
        code = "INDEX_FINALIZATION_FAILED"
        try:
            _record_failure(
                repository,
                version=version,
                job=job,
                backend=IndexBackend.ELASTICSEARCH,
                code=code,
            )
        except Exception:
            compensation = (*compensation, "fact_source:record_failure")
        raise IndexLifecycleError(
            code,
            "atomic index finalization failed",
            compensation_failures=compensation,
        ) from exc

    return IndexPublicationResult(
        version=version,
        job=job,
        receipts=(receipts[0], receipts[1]),
    )


def inactivate_and_schedule_cleanup(
    version: DocumentVersionLifecycleV1,
    *,
    reason: InactivationReason,
    repository: IndexLifecycleRepository,
    visibility: QueryVisibilityInvalidator,
    cleanup: IndexCleanupScheduler,
    elasticsearch: VersionIndexWriter,
    milvus: VersionIndexWriter,
    clock: Callable[[], datetime] = _utc_now,
) -> InactivationResult:
    """Commit INACTIVE first, invalidate visibility, then enqueue physical cleanup."""

    writers = _validated_writers(elasticsearch, milvus)
    if version.lifecycle_status is not LifecycleStatus.INACTIVE:
        timestamp_field = (
            "chunk_expire_time" if reason is InactivationReason.EXPIRE else "delete_time"
        )
        version = repository.transition_version(
            owner_id=version.owner_id,
            document_version_id=version.document_version_id,
            expected_revision=version.lifecycle_revision,
            target_status=LifecycleStatus.INACTIVE,
            updates={timestamp_field: clock()},
        )

    failures: list[str] = []
    visibility_invalidated = False
    try:
        visibility.invalidate_version(
            owner_id=version.owner_id,
            document_id=version.document_id,
            document_version_id=version.document_version_id,
        )
        visibility_invalidated = True
    except Exception:
        failures.append("query_visibility:invalidate")

    deactivated: list[IndexBackend] = []
    requests: list[CleanupRequest] = []
    for writer in writers:
        try:
            writer.deactivate_version(
                owner_id=version.owner_id,
                document_version_id=version.document_version_id,
            )
            deactivated.append(writer.backend)
        except Exception:
            failures.append(f"{writer.backend.value}:deactivate")
        request = CleanupRequest(
            backend=writer.backend,
            owner_id=version.owner_id,
            document_id=version.document_id,
            document_version_id=version.document_version_id,
        )
        try:
            cleanup.enqueue(request)
            requests.append(request)
        except Exception:
            failures.append(f"{writer.backend.value}:enqueue_cleanup")

    result = InactivationResult(
        version=version,
        reason=reason,
        visibility_invalidated=visibility_invalidated,
        deactivated_backends=tuple(deactivated),
        cleanup_requests=tuple(requests),
        failures=tuple(failures),
    )
    if failures:
        raise InactivationCleanupPendingError(result)
    return result
