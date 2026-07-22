from __future__ import annotations

import tomllib
import unittest
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.storage.migrate import (
    MigrationDriftError,
    apply_fact_source_migration,
    migration_sha256,
)
from backend.storage.models import (
    DocumentIdentityV1,
    DocumentVersionLifecycleV1,
    IndexState,
    IndexStatesV1,
    IngestionJobStatus,
    LifecycleStatus,
)
from backend.storage.postgres import (
    ConcurrentLifecycleUpdateError,
    IdentityConflictError,
    LifecycleTransitionError,
    PostgresFactRepository,
)


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


class ScriptedCursor:
    def __init__(self, connection: "ScriptedConnection") -> None:
        self.connection = connection
        self.current_result = None
        self.closed = False

    def execute(self, query: str, params: object | None = None) -> None:
        self.connection.executions.append((query, params))
        if not self.connection.results:
            raise AssertionError(f"unexpected SQL execution: {query[:80]}")
        result = self.connection.results.popleft()
        if isinstance(result, BaseException):
            raise result
        self.current_result = result

    def fetchone(self):
        return self.current_result

    def close(self) -> None:
        self.closed = True


class ScriptedConnection:
    def __init__(self, *results: object) -> None:
        self.results = deque(results)
        self.executions: list[tuple[str, object | None]] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.cursors: list[ScriptedCursor] = []

    def cursor(self) -> ScriptedCursor:
        cursor = ScriptedCursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


def identity_row(**updates: Any) -> dict[str, Any]:
    row = {
        "paper_id": "paper_001",
        "document_id": "doc_existing",
        "owner_id": "owner_001",
        "source_type": "uploaded",
        "mapping_version": "document_mapping_v1",
        "source_created_time": NOW,
        "source_updated_time": NOW,
    }
    row.update(updates)
    return row


def version_row(**updates: Any) -> dict[str, Any]:
    row = {
        "paper_id": "paper_001",
        "document_id": "doc_existing",
        "owner_id": "owner_001",
        "document_version_id": "document_version_existing",
        "content_sha256": "a" * 64,
        "source_snapshot_sha256": "b" * 64,
        "parse_version": "pypdf_text_v1",
        "lifecycle_revision": 1,
        "lifecycle_status": "REGISTERED",
        "parse_finish_time": None,
        "chunk_splitter_time": None,
        "chunk_create_time": None,
        "chunk_gen_time": None,
        "vector_index_time": None,
        "elasticsearch_state": "PENDING",
        "milvus_state": "PENDING",
        "delete_time": None,
        "chunk_expire_time": None,
        "last_access_time": None,
        "last_refresh_time": None,
        "failure_code": None,
        "updated_at": NOW,
        "is_active": False,
    }
    row.update(updates)
    return row


def job_row(**updates: Any) -> dict[str, Any]:
    row = {
        "job_id": "ingestion_job_existing",
        "owner_id": "owner_001",
        "idempotency_key": "upload_request_001",
        "document_id": "doc_existing",
        "document_version_id": "document_version_existing",
        "status": "PENDING",
        "attempt_count": 0,
        "failure_code": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(updates)
    return row


class StorageModelTests(unittest.TestCase):
    def test_identity_requires_timezone_and_ordered_source_times(self):
        with self.assertRaises(ValidationError):
            DocumentIdentityV1.model_validate(
                {
                    **identity_row(),
                    "schema_version": "document_identity_v1",
                    "source_created_time": NOW.replace(tzinfo=None),
                }
            )
        with self.assertRaises(ValidationError):
            DocumentIdentityV1(
                **identity_row(source_updated_time=NOW.replace(year=2025)),
                schema_version="document_identity_v1",
            )

    def test_ready_and_inactive_states_fail_closed(self):
        base = version_row()
        base["schema_version"] = "document_version_lifecycle_v1"
        base["index_states"] = {
            "elasticsearch_chunks": base.pop("elasticsearch_state"),
            "milvus_vectors": base.pop("milvus_state"),
        }
        base.pop("is_active")

        with self.assertRaises(ValidationError):
            DocumentVersionLifecycleV1.model_validate(
                {**base, "lifecycle_status": "READY"}
            )
        with self.assertRaises(ValidationError):
            DocumentVersionLifecycleV1.model_validate(
                {**base, "lifecycle_status": "INACTIVE"}
            )


class PostgreSQLMigrationTests(unittest.TestCase):
    def test_migration_is_declared_as_package_data(self):
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = pyproject["tool"]["setuptools"]["package-data"]
        self.assertIn("migrations/*.sql", package_data["backend.storage"])

    def test_migration_contains_database_level_truth_and_failure_guards(self):
        sql = (
            ROOT / "backend/storage/migrations/0001_fact_source.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("UNIQUE (owner_id, paper_id)", sql)
        self.assertIn("document identity fields are immutable", sql)
        self.assertIn("GENERATED ALWAYS AS", sql)
        self.assertIn("elasticsearch_state = 'READY'", sql)
        self.assertIn("milvus_state = 'READY'", sql)
        self.assertIn("invalid lifecycle transition", sql)
        self.assertIn("OLD.lifecycle_status = 'PROCESSING'", sql)
        self.assertIn("UNIQUE (owner_id, idempotency_key)", sql)

    def test_migration_is_idempotent_and_detects_checksum_drift(self):
        first = ScriptedConnection(None, None, None, None)
        self.assertTrue(apply_fact_source_migration(first))
        self.assertEqual(first.commit_count, 1)
        self.assertEqual(first.rollback_count, 0)
        self.assertTrue(all(cursor.closed for cursor in first.cursors))

        unchanged = ScriptedConnection(None, {"sha256": migration_sha256()})
        self.assertFalse(apply_fact_source_migration(unchanged))
        self.assertEqual(unchanged.commit_count, 1)

        drifted = ScriptedConnection(None, {"sha256": "0" * 64})
        with self.assertRaises(MigrationDriftError):
            apply_fact_source_migration(drifted)
        self.assertEqual(drifted.rollback_count, 1)


class PostgresFactRepositoryTests(unittest.TestCase):
    def repository(self, connection: ScriptedConnection) -> PostgresFactRepository:
        return PostgresFactRepository(
            connection,
            id_factory=lambda prefix: f"{prefix}_candidate",
            clock=lambda: NOW,
        )

    def test_owner_paper_registration_is_idempotent(self):
        connection = ScriptedConnection(identity_row(), identity_row())
        repository = self.repository(connection)
        arguments = {
            "owner_id": "owner_001",
            "paper_id": "paper_001",
            "source_type": "uploaded",
            "mapping_version": "document_mapping_v1",
            "source_created_time": NOW,
            "source_updated_time": NOW,
        }

        first = repository.register_document(**arguments)
        second = repository.register_document(**arguments)

        self.assertEqual(first.document_id, "doc_existing")
        self.assertEqual(second, first)
        self.assertEqual(connection.commit_count, 2)
        query = connection.executions[0][0]
        self.assertIn("ON CONFLICT (owner_id, paper_id)", query)

    def test_conflicting_immutable_source_type_rolls_back(self):
        connection = ScriptedConnection(identity_row(source_type="collected"))
        with self.assertRaises(IdentityConflictError):
            self.repository(connection).register_document(
                owner_id="owner_001",
                paper_id="paper_001",
                source_type="uploaded",
                mapping_version="document_mapping_v1",
                source_created_time=NOW,
                source_updated_time=NOW,
            )
        self.assertEqual(connection.commit_count, 0)
        self.assertEqual(connection.rollback_count, 1)

    def test_content_version_registration_is_replay_safe_and_owner_scoped(self):
        connection = ScriptedConnection(version_row(), version_row())
        repository = self.repository(connection)
        arguments = {
            "owner_id": "owner_001",
            "document_id": "doc_existing",
            "content_sha256": "a" * 64,
            "source_snapshot_sha256": "b" * 64,
            "parse_version": "pypdf_text_v1",
        }

        first = repository.register_version(**arguments)
        second = repository.register_version(**arguments)

        self.assertEqual(first.document_version_id, "document_version_existing")
        self.assertEqual(second, first)
        query = connection.executions[0][0]
        self.assertIn("ON CONFLICT", query)
        self.assertIn("DO NOTHING", query)
        self.assertIn("d.owner_id = %(owner_id)s", query)

    def test_version_registration_rechecks_after_concurrent_conflict(self):
        connection = ScriptedConnection(None, version_row())
        result = self.repository(connection).register_version(
            owner_id="owner_001",
            document_id="doc_existing",
            content_sha256="a" * 64,
            source_snapshot_sha256="b" * 64,
            parse_version="pypdf_text_v1",
        )

        self.assertEqual(result.document_version_id, "document_version_existing")
        self.assertIn("get_idempotent_document_version_v1", connection.executions[1][0])

    def test_ingestion_idempotency_key_cannot_change_version(self):
        connection = ScriptedConnection(
            job_row(document_version_id="document_version_other")
        )
        with self.assertRaises(IdentityConflictError):
            self.repository(connection).register_ingestion_job(
                owner_id="owner_001",
                document_id="doc_existing",
                document_version_id="document_version_existing",
                idempotency_key="upload_request_001",
            )
        self.assertEqual(connection.rollback_count, 1)

    def test_version_and_job_registration_commit_atomically(self):
        success = ScriptedConnection(version_row(), job_row())
        version, job = self.repository(success).register_version_and_ingestion_job(
            owner_id="owner_001",
            document_id="doc_existing",
            content_sha256="a" * 64,
            source_snapshot_sha256="b" * 64,
            parse_version="pypdf_text_v1",
            idempotency_key="upload_request_001",
        )

        self.assertEqual(version.document_version_id, job.document_version_id)
        self.assertEqual(success.commit_count, 1)

        conflict = ScriptedConnection(
            version_row(),
            job_row(document_version_id="document_version_other"),
        )
        with self.assertRaises(IdentityConflictError):
            self.repository(conflict).register_version_and_ingestion_job(
                owner_id="owner_001",
                document_id="doc_existing",
                content_sha256="a" * 64,
                source_snapshot_sha256="b" * 64,
                parse_version="pypdf_text_v1",
                idempotency_key="upload_request_001",
            )
        self.assertEqual(conflict.commit_count, 0)
        self.assertGreaterEqual(conflict.rollback_count, 1)

    def test_ready_transition_requires_both_indexes_and_all_lineage_times(self):
        processing = version_row(lifecycle_status="PROCESSING")
        ready = version_row(
            lifecycle_revision=2,
            lifecycle_status="READY",
            parse_finish_time=NOW,
            chunk_splitter_time=NOW,
            chunk_create_time=NOW,
            chunk_gen_time=NOW,
            vector_index_time=NOW,
            elasticsearch_state="READY",
            milvus_state="READY",
            is_active=True,
        )
        connection = ScriptedConnection(processing, ready)
        result = self.repository(connection).transition_version(
            owner_id="owner_001",
            document_version_id="document_version_existing",
            expected_revision=1,
            target_status=LifecycleStatus.READY,
            updates={
                "parse_finish_time": NOW,
                "chunk_splitter_time": NOW,
                "chunk_create_time": NOW,
                "chunk_gen_time": NOW,
                "vector_index_time": NOW,
                "index_states": {
                    "elasticsearch_chunks": IndexState.READY,
                    "milvus_vectors": IndexState.READY,
                },
            },
        )

        self.assertTrue(result.is_active)
        self.assertEqual(result.lifecycle_revision, 2)
        update_query = connection.executions[1][0]
        self.assertIn("lifecycle_revision = %(expected_revision)s", update_query)

    def test_ready_transition_with_one_pending_index_rolls_back_before_update(self):
        connection = ScriptedConnection(version_row(lifecycle_status="PROCESSING"))
        with self.assertRaises(ValidationError):
            self.repository(connection).transition_version(
                owner_id="owner_001",
                document_version_id="document_version_existing",
                expected_revision=1,
                target_status=LifecycleStatus.READY,
                updates={
                    "parse_finish_time": NOW,
                    "chunk_splitter_time": NOW,
                    "chunk_create_time": NOW,
                    "chunk_gen_time": NOW,
                    "vector_index_time": NOW,
                    "index_states": {
                        "elasticsearch_chunks": "READY",
                        "milvus_vectors": "PENDING",
                    },
                },
            )
        self.assertEqual(len(connection.executions), 1)
        self.assertEqual(connection.rollback_count, 1)

    def test_processing_progress_records_lineage_without_becoming_active(self):
        processing = version_row(lifecycle_status="PROCESSING")
        progressed = version_row(
            lifecycle_revision=2,
            lifecycle_status="PROCESSING",
            parse_finish_time=NOW,
            chunk_splitter_time=NOW,
            chunk_create_time=NOW,
            chunk_gen_time=NOW,
        )
        connection = ScriptedConnection(processing, progressed)
        result = self.repository(connection).transition_version(
            owner_id="owner_001",
            document_version_id="document_version_existing",
            expected_revision=1,
            target_status=LifecycleStatus.PROCESSING,
            updates={
                "parse_finish_time": NOW,
                "chunk_splitter_time": NOW,
                "chunk_create_time": NOW,
                "chunk_gen_time": NOW,
            },
        )

        self.assertEqual(result.lifecycle_status, LifecycleStatus.PROCESSING)
        self.assertFalse(result.is_active)
        self.assertIsNone(result.vector_index_time)

    def test_index_failure_and_success_finalize_version_and_job_atomically(self):
        processing = version_row(
            lifecycle_status="PROCESSING",
            parse_finish_time=NOW,
            chunk_splitter_time=NOW,
            chunk_create_time=NOW,
            chunk_gen_time=NOW,
        )
        failed = version_row(
            lifecycle_revision=2,
            lifecycle_status="PROCESSING",
            parse_finish_time=NOW,
            chunk_splitter_time=NOW,
            chunk_create_time=NOW,
            chunk_gen_time=NOW,
            elasticsearch_state="READY",
            milvus_state="FAILED",
            failure_code="MILVUS_VECTORS_STAGE_FAILED",
        )
        failed_job = job_row(
            status="FAILED",
            failure_code="MILVUS_VECTORS_STAGE_FAILED",
        )
        failure_connection = ScriptedConnection(processing, failed, failed_job)

        failed_version, failed_result_job = self.repository(
            failure_connection
        ).record_indexing_failure(
            owner_id="owner_001",
            document_version_id="document_version_existing",
            expected_revision=1,
            index_states=IndexStatesV1(
                elasticsearch_chunks=IndexState.READY,
                milvus_vectors=IndexState.FAILED,
            ),
            job_id="ingestion_job_existing",
            failure_code="MILVUS_VECTORS_STAGE_FAILED",
        )

        self.assertEqual(failed_version.failure_code, "MILVUS_VECTORS_STAGE_FAILED")
        self.assertEqual(failed_result_job.status, IngestionJobStatus.FAILED)
        self.assertEqual(failure_connection.commit_count, 1)

        ready = version_row(
            lifecycle_revision=2,
            lifecycle_status="READY",
            parse_finish_time=NOW,
            chunk_splitter_time=NOW,
            chunk_create_time=NOW,
            chunk_gen_time=NOW,
            vector_index_time=NOW,
            elasticsearch_state="READY",
            milvus_state="READY",
            is_active=True,
        )
        succeeded_job = job_row(status="SUCCEEDED")
        success_connection = ScriptedConnection(processing, ready, succeeded_job)

        ready_version, ready_job = self.repository(
            success_connection
        ).finalize_indexing_success(
            owner_id="owner_001",
            document_version_id="document_version_existing",
            expected_revision=1,
            index_states=IndexStatesV1(
                elasticsearch_chunks=IndexState.READY,
                milvus_vectors=IndexState.READY,
            ),
            vector_index_time=NOW,
            job_id="ingestion_job_existing",
        )

        self.assertTrue(ready_version.is_active)
        self.assertEqual(ready_job.status, IngestionJobStatus.SUCCEEDED)
        self.assertEqual(success_connection.commit_count, 1)

        mismatched_job = job_row(
            status="SUCCEEDED",
            document_version_id="document_version_other",
        )
        mismatch_connection = ScriptedConnection(processing, ready, mismatched_job)
        with self.assertRaisesRegex(IdentityConflictError, "not bound"):
            self.repository(mismatch_connection).finalize_indexing_success(
                owner_id="owner_001",
                document_version_id="document_version_existing",
                expected_revision=1,
                index_states=IndexStatesV1(
                    elasticsearch_chunks=IndexState.READY,
                    milvus_vectors=IndexState.READY,
                ),
                vector_index_time=NOW,
                job_id="ingestion_job_other",
            )
        self.assertEqual(mismatch_connection.commit_count, 0)
        self.assertGreaterEqual(mismatch_connection.rollback_count, 1)

    def test_index_finalization_rolls_back_when_job_update_fails(self):
        processing = version_row(
            lifecycle_status="PROCESSING",
            parse_finish_time=NOW,
            chunk_splitter_time=NOW,
            chunk_create_time=NOW,
            chunk_gen_time=NOW,
        )
        ready = version_row(
            lifecycle_revision=2,
            lifecycle_status="READY",
            parse_finish_time=NOW,
            chunk_splitter_time=NOW,
            chunk_create_time=NOW,
            chunk_gen_time=NOW,
            vector_index_time=NOW,
            elasticsearch_state="READY",
            milvus_state="READY",
            is_active=True,
        )
        connection = ScriptedConnection(
            processing,
            ready,
            RuntimeError("simulated job update failure"),
        )

        with self.assertRaisesRegex(RuntimeError, "job update"):
            self.repository(connection).finalize_indexing_success(
                owner_id="owner_001",
                document_version_id="document_version_existing",
                expected_revision=1,
                index_states=IndexStatesV1(
                    elasticsearch_chunks=IndexState.READY,
                    milvus_vectors=IndexState.READY,
                ),
                vector_index_time=NOW,
                job_id="ingestion_job_existing",
            )

        self.assertEqual(connection.commit_count, 0)
        self.assertGreaterEqual(connection.rollback_count, 1)

    def test_invalid_or_stale_transition_fails_closed(self):
        invalid = ScriptedConnection(version_row())
        with self.assertRaises(LifecycleTransitionError):
            self.repository(invalid).transition_version(
                owner_id="owner_001",
                document_version_id="document_version_existing",
                expected_revision=1,
                target_status=LifecycleStatus.READY,
            )

        stale = ScriptedConnection(version_row(lifecycle_revision=2))
        with self.assertRaises(ConcurrentLifecycleUpdateError):
            self.repository(stale).transition_version(
                owner_id="owner_001",
                document_version_id="document_version_existing",
                expected_revision=1,
                target_status=LifecycleStatus.PROCESSING,
            )

    def test_online_lookup_always_filters_owner_and_active_state(self):
        connection = ScriptedConnection(None)
        result = self.repository(connection).get_online_version(
            owner_id="owner_001",
            document_version_id="document_version_existing",
        )

        self.assertIsNone(result)
        query, params = connection.executions[0]
        self.assertIn("owner_id = %(owner_id)s", query)
        self.assertIn("is_active = TRUE", query)
        self.assertEqual(params["owner_id"], "owner_001")

    def test_failed_ingestion_job_requires_stable_error_code(self):
        connection = ScriptedConnection()
        with self.assertRaises(ValueError):
            self.repository(connection).update_ingestion_job(
                owner_id="owner_001",
                job_id="ingestion_job_existing",
                status=IngestionJobStatus.FAILED,
            )
        self.assertFalse(connection.executions)


if __name__ == "__main__":
    unittest.main()
