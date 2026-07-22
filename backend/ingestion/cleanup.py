"""Persistent, lease-based physical cleanup for inactive index versions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from backend.ingestion.index_lifecycle import CleanupRequest, IndexBackend
from backend.storage.models import CleanupJobStatus, CleanupJobV1


class CleanupRepository(Protocol):
    def enqueue_cleanup(
        self,
        *,
        backend: str,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        max_attempts: int = 5,
    ) -> CleanupJobV1: ...

    def claim_cleanup(self, *, lease_seconds: int = 300) -> CleanupJobV1 | None: ...

    def complete_cleanup(
        self, *, cleanup_id: str, lease_token: str
    ) -> CleanupJobV1: ...

    def record_cleanup_failure(
        self,
        *,
        cleanup_id: str,
        lease_token: str,
        failure_code: str,
        retry_at: datetime,
    ) -> CleanupJobV1: ...


class VersionIndexCleaner(Protocol):
    backend: IndexBackend

    def delete_version(self, *, owner_id: str, document_version_id: str) -> bool: ...


@dataclass(frozen=True)
class CleanupExecutionResult:
    job: CleanupJobV1
    physical_object_existed: bool | None

    @property
    def succeeded(self) -> bool:
        return self.job.status is CleanupJobStatus.SUCCEEDED


class CleanupWorkerError(RuntimeError):
    """Raised when cleanup outcome cannot be durably recorded."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PersistentIndexCleanupScheduler:
    """Adapter from lifecycle cleanup requests to the PostgreSQL queue."""

    def __init__(self, repository: CleanupRepository, *, max_attempts: int = 5) -> None:
        if max_attempts < 1:
            raise ValueError("cleanup max_attempts must be positive")
        self.repository = repository
        self.max_attempts = max_attempts

    def enqueue(self, request: CleanupRequest) -> None:
        self.repository.enqueue_cleanup(
            backend=request.backend.value,
            owner_id=request.owner_id,
            document_id=request.document_id,
            document_version_id=request.document_version_id,
            max_attempts=self.max_attempts,
        )


class PersistentIndexCleanupWorker:
    """Claim due cleanup jobs and delete only identity-pinned physical versions."""

    def __init__(
        self,
        *,
        repository: CleanupRepository,
        elasticsearch: VersionIndexCleaner,
        milvus: VersionIndexCleaner,
        lease_seconds: int = 300,
        base_retry_seconds: int = 30,
        max_retry_seconds: int = 3600,
        clock=_utc_now,
    ) -> None:
        if elasticsearch.backend is not IndexBackend.ELASTICSEARCH:
            raise ValueError("elasticsearch cleaner has the wrong backend identity")
        if milvus.backend is not IndexBackend.MILVUS:
            raise ValueError("milvus cleaner has the wrong backend identity")
        if lease_seconds < 1 or base_retry_seconds < 1:
            raise ValueError("cleanup lease and retry delays must be positive")
        if max_retry_seconds < base_retry_seconds:
            raise ValueError("cleanup max retry delay must cover the base delay")
        self.repository = repository
        self.cleaners = {
            IndexBackend.ELASTICSEARCH: elasticsearch,
            IndexBackend.MILVUS: milvus,
        }
        self.lease_seconds = lease_seconds
        self.base_retry_seconds = base_retry_seconds
        self.max_retry_seconds = max_retry_seconds
        self.clock = clock

    def run_once(self) -> CleanupExecutionResult | None:
        job = self.repository.claim_cleanup(lease_seconds=self.lease_seconds)
        if job is None:
            return None
        if job.status is not CleanupJobStatus.RUNNING or job.lease_token is None:
            raise CleanupWorkerError("cleanup repository returned an unleased job")
        backend = IndexBackend(job.backend)
        cleaner = self.cleaners[backend]
        try:
            existed = cleaner.delete_version(
                owner_id=job.owner_id,
                document_version_id=job.document_version_id,
            )
        except Exception:
            failure_code = f"{backend.value.upper()}_DELETE_FAILED"
            retry_at = self.clock() + timedelta(seconds=self._retry_delay(job))
            try:
                failed = self.repository.record_cleanup_failure(
                    cleanup_id=job.cleanup_id,
                    lease_token=job.lease_token,
                    failure_code=failure_code,
                    retry_at=retry_at,
                )
            except Exception as exc:
                raise CleanupWorkerError(
                    "physical cleanup failed and retry state was not persisted"
                ) from exc
            return CleanupExecutionResult(
                job=failed,
                physical_object_existed=None,
            )

        try:
            completed = self.repository.complete_cleanup(
                cleanup_id=job.cleanup_id,
                lease_token=job.lease_token,
            )
        except Exception as exc:
            raise CleanupWorkerError(
                "physical cleanup succeeded but completion was not persisted"
            ) from exc
        return CleanupExecutionResult(
            job=completed,
            physical_object_existed=existed,
        )

    def run_batch(self, *, max_jobs: int = 100) -> tuple[CleanupExecutionResult, ...]:
        if max_jobs < 1:
            raise ValueError("cleanup max_jobs must be positive")
        results: list[CleanupExecutionResult] = []
        for _ in range(max_jobs):
            result = self.run_once()
            if result is None:
                break
            results.append(result)
        return tuple(results)

    def _retry_delay(self, job: CleanupJobV1) -> int:
        exponent = max(job.attempt_count - 1, 0)
        return min(
            self.base_retry_seconds * (2**exponent),
            self.max_retry_seconds,
        )
