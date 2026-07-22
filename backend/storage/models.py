"""Strict runtime models for the frozen PostgreSQL fact-source contract."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


ContractId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
ObjectKey = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=512,
        pattern=r"^[a-z0-9][a-z0-9._/-]*$",
    ),
]


class LifecycleStatus(StrEnum):
    REGISTERED = "REGISTERED"
    PROCESSING = "PROCESSING"
    REVIEW = "REVIEW"
    READY = "READY"
    FAILED = "FAILED"
    INACTIVE = "INACTIVE"


class IndexState(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


class IngestionJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class CleanupJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY = "RETRY"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


ALLOWED_LIFECYCLE_TRANSITIONS: dict[LifecycleStatus, frozenset[LifecycleStatus]] = {
    LifecycleStatus.REGISTERED: frozenset(
        {LifecycleStatus.PROCESSING, LifecycleStatus.INACTIVE}
    ),
    LifecycleStatus.PROCESSING: frozenset(
        {
            LifecycleStatus.REVIEW,
            LifecycleStatus.READY,
            LifecycleStatus.FAILED,
            LifecycleStatus.INACTIVE,
        }
    ),
    LifecycleStatus.REVIEW: frozenset(
        {LifecycleStatus.PROCESSING, LifecycleStatus.FAILED, LifecycleStatus.INACTIVE}
    ),
    LifecycleStatus.READY: frozenset({LifecycleStatus.INACTIVE}),
    LifecycleStatus.FAILED: frozenset(
        {LifecycleStatus.PROCESSING, LifecycleStatus.INACTIVE}
    ),
    LifecycleStatus.INACTIVE: frozenset(),
}


class StorageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_timezone(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must include a timezone")
    return value


class DocumentIdentityV1(StorageModel):
    schema_version: Literal["document_identity_v1"] = "document_identity_v1"
    paper_id: ContractId
    document_id: ContractId
    owner_id: ContractId
    source_type: Literal["uploaded", "collected"]
    mapping_version: ContractId
    source_created_time: datetime
    source_updated_time: datetime

    @field_validator("source_created_time", "source_updated_time")
    @classmethod
    def timestamps_require_timezone(cls, value: datetime, info) -> datetime:
        return _require_timezone(value, info.field_name)  # type: ignore[return-value]

    @model_validator(mode="after")
    def source_times_are_ordered(self) -> "DocumentIdentityV1":
        if self.source_updated_time < self.source_created_time:
            raise ValueError("source_updated_time must not precede source_created_time")
        return self


class IndexStatesV1(StorageModel):
    elasticsearch_chunks: IndexState = IndexState.PENDING
    milvus_vectors: IndexState = IndexState.PENDING


class DocumentVersionLifecycleV1(StorageModel):
    schema_version: Literal["document_version_lifecycle_v1"] = (
        "document_version_lifecycle_v1"
    )
    paper_id: ContractId
    document_id: ContractId
    owner_id: ContractId
    document_version_id: ContractId
    content_sha256: Sha256
    source_snapshot_sha256: Sha256
    parse_version: ContractId
    lifecycle_revision: int = Field(ge=1)
    lifecycle_status: LifecycleStatus
    parse_finish_time: datetime | None = None
    chunk_splitter_time: datetime | None = None
    chunk_create_time: datetime | None = None
    chunk_gen_time: datetime | None = None
    vector_index_time: datetime | None = None
    index_states: IndexStatesV1 = Field(default_factory=IndexStatesV1)
    delete_time: datetime | None = None
    chunk_expire_time: datetime | None = None
    last_access_time: datetime | None = None
    last_refresh_time: datetime | None = None
    failure_code: ContractId | None = None
    updated_at: datetime

    @field_validator(
        "parse_finish_time",
        "chunk_splitter_time",
        "chunk_create_time",
        "chunk_gen_time",
        "vector_index_time",
        "delete_time",
        "chunk_expire_time",
        "last_access_time",
        "last_refresh_time",
        "updated_at",
    )
    @classmethod
    def timestamps_require_timezone(
        cls, value: datetime | None, info
    ) -> datetime | None:
        return _require_timezone(value, info.field_name)

    @model_validator(mode="after")
    def lifecycle_fails_closed(self) -> "DocumentVersionLifecycleV1":
        if self.lifecycle_status is not LifecycleStatus.INACTIVE and (
            self.delete_time is not None or self.chunk_expire_time is not None
        ):
            raise ValueError("only INACTIVE versions may have delete or expiry timestamps")
        if self.lifecycle_status is LifecycleStatus.INACTIVE and (
            self.delete_time is None and self.chunk_expire_time is None
        ):
            raise ValueError("INACTIVE requires delete_time or chunk_expire_time")
        if self.lifecycle_status is LifecycleStatus.FAILED and self.failure_code is None:
            raise ValueError("FAILED requires failure_code")
        if self.lifecycle_status is LifecycleStatus.READY:
            required_times = (
                self.parse_finish_time,
                self.chunk_splitter_time,
                self.chunk_create_time,
                self.chunk_gen_time,
                self.vector_index_time,
            )
            if any(value is None for value in required_times):
                raise ValueError("READY requires all parse, chunk and vector timestamps")
            if self.index_states != IndexStatesV1(
                elasticsearch_chunks=IndexState.READY,
                milvus_vectors=IndexState.READY,
            ):
                raise ValueError("READY requires Elasticsearch and Milvus READY")
            if self.failure_code is not None:
                raise ValueError("READY must not retain a failure_code")
        return self

    @property
    def is_active(self) -> bool:
        return (
            self.lifecycle_status is LifecycleStatus.READY
            and self.delete_time is None
            and self.chunk_expire_time is None
        )


class IngestionJobV1(StorageModel):
    job_id: ContractId
    owner_id: ContractId
    idempotency_key: ContractId
    document_id: ContractId
    document_version_id: ContractId
    status: IngestionJobStatus
    attempt_count: int = Field(ge=0)
    failure_code: ContractId | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_require_timezone(cls, value: datetime, info) -> datetime:
        return _require_timezone(value, info.field_name)  # type: ignore[return-value]

    @model_validator(mode="after")
    def failed_job_requires_code(self) -> "IngestionJobV1":
        if self.status is IngestionJobStatus.FAILED and self.failure_code is None:
            raise ValueError("FAILED ingestion job requires failure_code")
        return self


class PdfObjectV1(StorageModel):
    """Immutable PDF object identity stored outside PostgreSQL payload rows."""

    owner_id: ContractId
    document_id: ContractId
    document_version_id: ContractId
    object_key: ObjectKey
    storage_backend: Literal["filesystem_v1"]
    content_sha256: Sha256
    size_bytes: int = Field(ge=1)
    media_type: Literal["application/pdf"] = "application/pdf"
    stored_at: datetime

    @field_validator("stored_at")
    @classmethod
    def stored_at_requires_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value, "stored_at")  # type: ignore[return-value]


class RuntimeSnapshotV1(StorageModel):
    """Receipt for one immutable PDF object plus its exact Chunk snapshot."""

    owner_id: ContractId
    document_id: ContractId
    document_version_id: ContractId
    pdf_object_key: ObjectKey
    pdf_sha256: Sha256
    chunk_count: int = Field(ge=1)
    chunk_snapshot_sha256: Sha256


class CleanupJobV1(StorageModel):
    cleanup_id: ContractId
    backend: Literal[
        "elasticsearch_chunks",
        "milvus_vectors",
        "runtime_snapshot",
    ]
    owner_id: ContractId
    document_id: ContractId
    document_version_id: ContractId
    status: CleanupJobStatus
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=1, le=100)
    next_attempt_at: datetime
    lease_token: ContractId | None = None
    lease_expires_at: datetime | None = None
    failure_code: ContractId | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @field_validator(
        "next_attempt_at",
        "lease_expires_at",
        "created_at",
        "updated_at",
        "completed_at",
    )
    @classmethod
    def timestamps_require_timezone(
        cls, value: datetime | None, info
    ) -> datetime | None:
        return _require_timezone(value, info.field_name)

    @model_validator(mode="after")
    def cleanup_state_is_replay_safe(self) -> "CleanupJobV1":
        is_running = self.status is CleanupJobStatus.RUNNING
        if is_running != (
            self.lease_token is not None and self.lease_expires_at is not None
        ):
            raise ValueError("RUNNING cleanup requires an exclusive lease")
        if self.status in {CleanupJobStatus.RETRY, CleanupJobStatus.FAILED}:
            if self.failure_code is None:
                raise ValueError("RETRY or FAILED cleanup requires failure_code")
        elif self.failure_code is not None:
            raise ValueError("only RETRY or FAILED cleanup may retain failure_code")
        terminal = self.status in {
            CleanupJobStatus.SUCCEEDED,
            CleanupJobStatus.FAILED,
        }
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal cleanup state must match completed_at")
        if self.attempt_count > self.max_attempts:
            raise ValueError("cleanup attempt_count exceeds max_attempts")
        if self.status is CleanupJobStatus.PENDING and self.attempt_count != 0:
            raise ValueError("PENDING cleanup must not have attempts")
        if is_running and self.attempt_count < 1:
            raise ValueError("RUNNING cleanup requires at least one attempt")
        return self
