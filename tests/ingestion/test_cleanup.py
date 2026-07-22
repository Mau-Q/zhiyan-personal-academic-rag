from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.ingestion.cleanup import (
    CleanupWorkerError,
    PersistentIndexCleanupScheduler,
    PersistentIndexCleanupWorker,
)
from backend.ingestion.index_lifecycle import CleanupRequest, IndexBackend
from backend.storage.models import CleanupJobStatus, CleanupJobV1


NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def cleanup_job(
    *,
    backend: IndexBackend = IndexBackend.ELASTICSEARCH,
    status: CleanupJobStatus = CleanupJobStatus.PENDING,
    attempt_count: int = 0,
    max_attempts: int = 3,
    failure_code: str | None = None,
    completed_at: datetime | None = None,
) -> CleanupJobV1:
    running = status is CleanupJobStatus.RUNNING
    return CleanupJobV1(
        cleanup_id=f"cleanup_{backend.value}",
        backend=backend.value,
        owner_id="owner_001",
        document_id="document_001",
        document_version_id="document_version_001",
        status=status,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        next_attempt_at=NOW,
        lease_token="cleanup_lease_001" if running else None,
        lease_expires_at=NOW + timedelta(minutes=5) if running else None,
        failure_code=failure_code,
        created_at=NOW,
        updated_at=NOW,
        completed_at=completed_at,
    )


class FakeCleanupRepository:
    def __init__(self, claimed: list[CleanupJobV1] | None = None) -> None:
        self.claimed = list(claimed or [])
        self.enqueued: list[dict[str, Any]] = []
        self.completed: list[str] = []
        self.failures: list[dict[str, Any]] = []
        self.fail_completion = False
        self.fail_failure_recording = False

    def enqueue_cleanup(self, **kwargs: Any) -> CleanupJobV1:
        self.enqueued.append(dict(kwargs))
        return cleanup_job(backend=IndexBackend(kwargs["backend"]))

    def claim_cleanup(self, *, lease_seconds: int = 300) -> CleanupJobV1 | None:
        del lease_seconds
        return None if not self.claimed else self.claimed.pop(0)

    def complete_cleanup(
        self, *, cleanup_id: str, lease_token: str
    ) -> CleanupJobV1:
        if self.fail_completion:
            raise RuntimeError("simulated completion failure")
        self.completed.append(f"{cleanup_id}:{lease_token}")
        source = self._source(cleanup_id)
        return CleanupJobV1.model_validate(
            {
                **source.model_dump(),
                "status": CleanupJobStatus.SUCCEEDED,
                "lease_token": None,
                "lease_expires_at": None,
                "completed_at": NOW,
                "updated_at": NOW,
            }
        )

    def record_cleanup_failure(self, **kwargs: Any) -> CleanupJobV1:
        if self.fail_failure_recording:
            raise RuntimeError("simulated failure recording error")
        self.failures.append(dict(kwargs))
        source = self._source(kwargs["cleanup_id"])
        terminal = source.attempt_count >= source.max_attempts
        return CleanupJobV1.model_validate(
            {
                **source.model_dump(),
                "status": (
                    CleanupJobStatus.FAILED if terminal else CleanupJobStatus.RETRY
                ),
                "next_attempt_at": kwargs["retry_at"],
                "lease_token": None,
                "lease_expires_at": None,
                "failure_code": kwargs["failure_code"],
                "updated_at": NOW,
                "completed_at": NOW if terminal else None,
            }
        )

    def _source(self, cleanup_id: str) -> CleanupJobV1:
        for job in self._all_claimed:
            if job.cleanup_id == cleanup_id:
                return job
        raise AssertionError(f"unknown cleanup job: {cleanup_id}")

    @property
    def _all_claimed(self) -> list[CleanupJobV1]:
        return getattr(self, "history", [])

    def remember_claims(self, jobs: list[CleanupJobV1]) -> None:
        self.history = list(jobs)


class FakeCleaner:
    def __init__(self, backend: IndexBackend, *, fail: bool = False) -> None:
        self.backend = backend
        self.fail = fail
        self.calls: list[tuple[str, str]] = []
        self.existed = True

    def delete_version(self, *, owner_id: str, document_version_id: str) -> bool:
        self.calls.append((owner_id, document_version_id))
        if self.fail:
            raise RuntimeError("raw backend failure must not be persisted")
        return self.existed


class PersistentCleanupTests(unittest.TestCase):
    def worker(
        self,
        repository: FakeCleanupRepository,
        *,
        elasticsearch: FakeCleaner | None = None,
        milvus: FakeCleaner | None = None,
    ) -> PersistentIndexCleanupWorker:
        return PersistentIndexCleanupWorker(
            repository=repository,
            elasticsearch=elasticsearch or FakeCleaner(IndexBackend.ELASTICSEARCH),
            milvus=milvus or FakeCleaner(IndexBackend.MILVUS),
            base_retry_seconds=30,
            max_retry_seconds=120,
            clock=lambda: NOW,
        )

    def test_scheduler_persists_exact_backend_and_version_identity(self):
        repository = FakeCleanupRepository()
        scheduler = PersistentIndexCleanupScheduler(repository, max_attempts=7)

        scheduler.enqueue(
            CleanupRequest(
                backend=IndexBackend.MILVUS,
                owner_id="owner_001",
                document_id="document_001",
                document_version_id="document_version_001",
            )
        )

        self.assertEqual(
            repository.enqueued,
            [
                {
                    "backend": "milvus_vectors",
                    "owner_id": "owner_001",
                    "document_id": "document_001",
                    "document_version_id": "document_version_001",
                    "max_attempts": 7,
                }
            ],
        )

    def test_successful_delete_completes_exact_lease(self):
        claimed = cleanup_job(status=CleanupJobStatus.RUNNING, attempt_count=1)
        repository = FakeCleanupRepository([claimed])
        repository.remember_claims([claimed])
        elasticsearch = FakeCleaner(IndexBackend.ELASTICSEARCH)

        result = self.worker(repository, elasticsearch=elasticsearch).run_once()

        self.assertIsNotNone(result)
        self.assertTrue(result.succeeded)
        self.assertTrue(result.physical_object_existed)
        self.assertEqual(
            elasticsearch.calls,
            [("owner_001", "document_version_001")],
        )
        self.assertEqual(
            repository.completed,
            [f"{claimed.cleanup_id}:{claimed.lease_token}"],
        )

    def test_already_missing_physical_object_is_idempotent_success(self):
        claimed = cleanup_job(
            backend=IndexBackend.MILVUS,
            status=CleanupJobStatus.RUNNING,
            attempt_count=1,
        )
        repository = FakeCleanupRepository([claimed])
        repository.remember_claims([claimed])
        milvus = FakeCleaner(IndexBackend.MILVUS)
        milvus.existed = False

        result = self.worker(repository, milvus=milvus).run_once()

        self.assertTrue(result.succeeded)
        self.assertFalse(result.physical_object_existed)

    def test_delete_failure_records_stable_retry_with_bounded_backoff(self):
        claimed = cleanup_job(
            status=CleanupJobStatus.RUNNING,
            attempt_count=3,
            max_attempts=5,
        )
        repository = FakeCleanupRepository([claimed])
        repository.remember_claims([claimed])
        elasticsearch = FakeCleaner(IndexBackend.ELASTICSEARCH, fail=True)

        result = self.worker(repository, elasticsearch=elasticsearch).run_once()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.job.status, CleanupJobStatus.RETRY)
        failure = repository.failures[0]
        self.assertEqual(
            failure["failure_code"],
            "ELASTICSEARCH_CHUNKS_DELETE_FAILED",
        )
        self.assertEqual(failure["retry_at"], NOW + timedelta(seconds=120))
        self.assertNotIn("raw backend", str(failure))

    def test_last_delete_failure_becomes_terminal_without_reactivation(self):
        claimed = cleanup_job(
            backend=IndexBackend.MILVUS,
            status=CleanupJobStatus.RUNNING,
            attempt_count=3,
            max_attempts=3,
        )
        repository = FakeCleanupRepository([claimed])
        repository.remember_claims([claimed])
        milvus = FakeCleaner(IndexBackend.MILVUS, fail=True)

        result = self.worker(repository, milvus=milvus).run_once()

        self.assertEqual(result.job.status, CleanupJobStatus.FAILED)
        self.assertIsNotNone(result.job.completed_at)
        self.assertEqual(result.physical_object_existed, None)

    def test_unpersisted_outcome_raises_for_lease_recovery(self):
        success = cleanup_job(status=CleanupJobStatus.RUNNING, attempt_count=1)
        success_repository = FakeCleanupRepository([success])
        success_repository.remember_claims([success])
        success_repository.fail_completion = True
        with self.assertRaisesRegex(CleanupWorkerError, "completion was not persisted"):
            self.worker(success_repository).run_once()

        failed = cleanup_job(status=CleanupJobStatus.RUNNING, attempt_count=1)
        failed_repository = FakeCleanupRepository([failed])
        failed_repository.remember_claims([failed])
        failed_repository.fail_failure_recording = True
        with self.assertRaisesRegex(CleanupWorkerError, "retry state was not persisted"):
            self.worker(
                failed_repository,
                elasticsearch=FakeCleaner(IndexBackend.ELASTICSEARCH, fail=True),
            ).run_once()

    def test_batch_stops_when_no_due_jobs_remain(self):
        first = cleanup_job(status=CleanupJobStatus.RUNNING, attempt_count=1)
        second = cleanup_job(
            backend=IndexBackend.MILVUS,
            status=CleanupJobStatus.RUNNING,
            attempt_count=1,
        )
        repository = FakeCleanupRepository([first, second])
        repository.remember_claims([first, second])

        results = self.worker(repository).run_batch(max_jobs=5)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.succeeded for result in results))


if __name__ == "__main__":
    unittest.main()
