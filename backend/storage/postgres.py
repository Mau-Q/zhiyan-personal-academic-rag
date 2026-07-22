"""PostgreSQL adapter for owner-scoped document identity and lifecycle truth."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from backend.storage.models import (
    ALLOWED_LIFECYCLE_TRANSITIONS,
    CleanupJobStatus,
    CleanupJobV1,
    DocumentIdentityV1,
    DocumentVersionLifecycleV1,
    IndexStatesV1,
    IngestionJobStatus,
    IngestionJobV1,
    LifecycleStatus,
)


JsonObject = dict[str, Any]
MIGRATIONS_DIR = Path(__file__).with_name("migrations")
MIGRATION_PATHS = {
    "0001_fact_source": MIGRATIONS_DIR / "0001_fact_source.sql",
    "0002_cleanup_queue": MIGRATIONS_DIR / "0002_cleanup_queue.sql",
    "0003_online_ready_visibility": MIGRATIONS_DIR / "0003_online_ready_visibility.sql",
}
MIGRATION_PATH = MIGRATION_PATHS["0001_fact_source"]
LIFECYCLE_MUTABLE_FIELDS = frozenset(
    {
        "parse_finish_time",
        "chunk_splitter_time",
        "chunk_create_time",
        "chunk_gen_time",
        "vector_index_time",
        "index_states",
        "delete_time",
        "chunk_expire_time",
        "last_access_time",
        "last_refresh_time",
        "failure_code",
    }
)
_CONTRACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class Cursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> Any: ...
    def fetchone(self) -> Mapping[str, Any] | None: ...
    def fetchall(self) -> Sequence[Mapping[str, Any]]: ...
    def close(self) -> None: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class PostgresFactSourceError(RuntimeError):
    """Base error for fact-source operations that must fail closed."""


class IdentityConflictError(PostgresFactSourceError):
    """Raised when an idempotent request conflicts with immutable identity."""


class ConcurrentLifecycleUpdateError(PostgresFactSourceError):
    """Raised when lifecycle revision compare-and-swap detects stale state."""


class LifecycleTransitionError(PostgresFactSourceError):
    """Raised before SQL when a transition violates the frozen state machine."""


def connect_postgres(database_url: str) -> Connection:
    """Connect lazily so base installs do not require the optional driver."""

    if not database_url.startswith("postgresql://"):
        raise ValueError("DATABASE_URL must use postgresql:// without logging credentials")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise PostgresFactSourceError(
            'psycopg is required; install the optional dependency with pip install -e ".[postgres]"'
        ) from exc
    return cast(Connection, psycopg.connect(database_url, row_factory=dict_row))


def _default_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _identity_from_row(row: Mapping[str, Any]) -> DocumentIdentityV1:
    return DocumentIdentityV1.model_validate(
        {"schema_version": "document_identity_v1", **dict(row)}
    )


def _version_from_row(row: Mapping[str, Any]) -> DocumentVersionLifecycleV1:
    payload = dict(row)
    payload["schema_version"] = "document_version_lifecycle_v1"
    payload["index_states"] = {
        "elasticsearch_chunks": payload.pop("elasticsearch_state"),
        "milvus_vectors": payload.pop("milvus_state"),
    }
    payload.pop("is_active", None)
    return DocumentVersionLifecycleV1.model_validate(payload)


def _job_from_row(row: Mapping[str, Any]) -> IngestionJobV1:
    return IngestionJobV1.model_validate(dict(row))


def _cleanup_from_row(row: Mapping[str, Any]) -> CleanupJobV1:
    return CleanupJobV1.model_validate(dict(row))


class PostgresFactRepository:
    """Small transactional repository; PostgreSQL remains the only business truth."""

    def __init__(
        self,
        connection: Connection,
        *,
        id_factory: Callable[[str], str] = _default_id,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.connection = connection
        self.id_factory = id_factory
        self.clock = clock

    def _execute_one(
        self, query: str, params: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            cursor.close()

    def _execute_no_result(self, query: str, params: Mapping[str, Any]) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, params)
        finally:
            cursor.close()

    def _execute_all(
        self, query: str, params: Mapping[str, Any]
    ) -> tuple[Mapping[str, Any], ...]:
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, params)
            return tuple(cursor.fetchall())
        finally:
            cursor.close()

    def _commit(self) -> None:
        self.connection.commit()

    def _rollback(self) -> None:
        self.connection.rollback()

    def register_document(
        self,
        *,
        owner_id: str,
        paper_id: str,
        source_type: str,
        mapping_version: str,
        source_created_time: datetime,
        source_updated_time: datetime,
    ) -> DocumentIdentityV1:
        """Create or idempotently return one owner-scoped paper mapping."""

        candidate = DocumentIdentityV1(
            paper_id=paper_id,
            document_id=self.id_factory("doc"),
            owner_id=owner_id,
            source_type=source_type,
            mapping_version=mapping_version,
            source_created_time=source_created_time,
            source_updated_time=source_updated_time,
        )
        try:
            row = self._execute_one(
                """-- register_document_v1
                INSERT INTO rag_documents (
                    owner_id, paper_id, document_id, source_type, mapping_version,
                    source_created_time, source_updated_time
                ) VALUES (
                    %(owner_id)s, %(paper_id)s, %(document_id)s, %(source_type)s,
                    %(mapping_version)s, %(source_created_time)s, %(source_updated_time)s
                )
                ON CONFLICT (owner_id, paper_id) DO UPDATE SET
                    mapping_version = EXCLUDED.mapping_version,
                    source_updated_time = GREATEST(
                        rag_documents.source_updated_time, EXCLUDED.source_updated_time
                    ),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING paper_id, document_id, owner_id, source_type, mapping_version,
                          source_created_time, source_updated_time
                """,
                candidate.model_dump(exclude={"schema_version"}),
            )
            if row is None:
                raise PostgresFactSourceError("document registration returned no row")
            identity = _identity_from_row(row)
            if identity.source_type != candidate.source_type:
                raise IdentityConflictError(
                    "owner/paper mapping already exists with a different immutable source_type"
                )
            self._commit()
            return identity
        except Exception:
            self._rollback()
            raise

    def register_version(
        self,
        *,
        owner_id: str,
        document_id: str,
        content_sha256: str,
        source_snapshot_sha256: str,
        parse_version: str,
    ) -> DocumentVersionLifecycleV1:
        return self._register_version(
            owner_id=owner_id,
            document_id=document_id,
            content_sha256=content_sha256,
            source_snapshot_sha256=source_snapshot_sha256,
            parse_version=parse_version,
            commit_transaction=True,
        )

    def _register_version(
        self,
        *,
        owner_id: str,
        document_id: str,
        content_sha256: str,
        source_snapshot_sha256: str,
        parse_version: str,
        commit_transaction: bool,
    ) -> DocumentVersionLifecycleV1:
        """Create one immutable content version, idempotent for the same source identity."""

        now = self.clock()
        params = {
            "owner_id": owner_id,
            "document_id": document_id,
            "document_version_id": self.id_factory("document_version"),
            "content_sha256": content_sha256,
            "source_snapshot_sha256": source_snapshot_sha256,
            "parse_version": parse_version,
            "updated_at": now,
        }
        try:
            row = self._execute_one(
                """-- register_document_version_v1
                WITH inserted AS (
                    INSERT INTO rag_document_versions (
                        owner_id, paper_id, document_id, document_version_id,
                        content_sha256, source_snapshot_sha256, parse_version,
                        lifecycle_status, updated_at
                    )
                    SELECT d.owner_id, d.paper_id, d.document_id,
                           %(document_version_id)s, %(content_sha256)s,
                           %(source_snapshot_sha256)s, %(parse_version)s,
                           'REGISTERED', %(updated_at)s
                    FROM rag_documents AS d
                    WHERE d.owner_id = %(owner_id)s
                      AND d.document_id = %(document_id)s
                    ON CONFLICT (
                        document_id, content_sha256, source_snapshot_sha256, parse_version
                    ) DO NOTHING
                    RETURNING *
                )
                SELECT paper_id, document_id, owner_id, document_version_id,
                       content_sha256, source_snapshot_sha256, parse_version,
                       lifecycle_revision, lifecycle_status, parse_finish_time,
                       chunk_splitter_time, chunk_create_time, chunk_gen_time,
                       vector_index_time, elasticsearch_state, milvus_state,
                       delete_time, chunk_expire_time, last_access_time,
                       last_refresh_time, failure_code, updated_at, is_active
                FROM inserted
                UNION ALL
                SELECT v.paper_id, v.document_id, v.owner_id, v.document_version_id,
                       v.content_sha256, v.source_snapshot_sha256, v.parse_version,
                       v.lifecycle_revision, v.lifecycle_status, v.parse_finish_time,
                       v.chunk_splitter_time, v.chunk_create_time, v.chunk_gen_time,
                       v.vector_index_time, v.elasticsearch_state, v.milvus_state,
                       v.delete_time, v.chunk_expire_time, v.last_access_time,
                       v.last_refresh_time, v.failure_code, v.updated_at, v.is_active
                FROM rag_document_versions AS v
                WHERE v.owner_id = %(owner_id)s
                  AND v.document_id = %(document_id)s
                  AND v.content_sha256 = %(content_sha256)s
                  AND v.source_snapshot_sha256 = %(source_snapshot_sha256)s
                  AND v.parse_version = %(parse_version)s
                LIMIT 1
                """,
                params,
            )
            if row is None:
                # A concurrent INSERT may win after this statement snapshot was taken.
                # Re-read in a new statement before classifying the owner/document as absent.
                row = self._execute_one(
                    """-- get_idempotent_document_version_v1
                    SELECT paper_id, document_id, owner_id, document_version_id,
                           content_sha256, source_snapshot_sha256, parse_version,
                           lifecycle_revision, lifecycle_status, parse_finish_time,
                           chunk_splitter_time, chunk_create_time, chunk_gen_time,
                           vector_index_time, elasticsearch_state, milvus_state,
                           delete_time, chunk_expire_time, last_access_time,
                           last_refresh_time, failure_code, updated_at, is_active
                    FROM rag_document_versions
                    WHERE owner_id = %(owner_id)s
                      AND document_id = %(document_id)s
                      AND content_sha256 = %(content_sha256)s
                      AND source_snapshot_sha256 = %(source_snapshot_sha256)s
                      AND parse_version = %(parse_version)s
                    """,
                    params,
                )
            if row is None:
                raise IdentityConflictError(
                    "document does not exist in the authenticated owner scope"
                )
            version = _version_from_row(row)
            if commit_transaction:
                self._commit()
            return version
        except Exception:
            self._rollback()
            raise

    def register_ingestion_job(
        self,
        *,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        idempotency_key: str,
    ) -> IngestionJobV1:
        return self._register_ingestion_job(
            owner_id=owner_id,
            document_id=document_id,
            document_version_id=document_version_id,
            idempotency_key=idempotency_key,
            commit_transaction=True,
        )

    def _register_ingestion_job(
        self,
        *,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        idempotency_key: str,
        commit_transaction: bool,
    ) -> IngestionJobV1:
        """Persist one replay-safe ingestion job per owner and idempotency key."""

        now = self.clock()
        params = {
            "job_id": self.id_factory("ingestion_job"),
            "owner_id": owner_id,
            "document_id": document_id,
            "document_version_id": document_version_id,
            "idempotency_key": idempotency_key,
            "created_at": now,
            "updated_at": now,
        }
        try:
            row = self._execute_one(
                """-- register_ingestion_job_v1
                INSERT INTO rag_ingestion_jobs (
                    job_id, owner_id, idempotency_key, document_id,
                    document_version_id, status, created_at, updated_at
                ) VALUES (
                    %(job_id)s, %(owner_id)s, %(idempotency_key)s, %(document_id)s,
                    %(document_version_id)s, 'PENDING', %(created_at)s, %(updated_at)s
                )
                ON CONFLICT (owner_id, idempotency_key) DO UPDATE SET
                    updated_at = rag_ingestion_jobs.updated_at
                RETURNING job_id, owner_id, idempotency_key, document_id,
                          document_version_id, status, attempt_count,
                          failure_code, created_at, updated_at
                """,
                params,
            )
            if row is None:
                raise PostgresFactSourceError("ingestion job registration returned no row")
            job = _job_from_row(row)
            if (
                job.document_id != document_id
                or job.document_version_id != document_version_id
            ):
                raise IdentityConflictError(
                    "idempotency key is already bound to a different document version"
                )
            if commit_transaction:
                self._commit()
            return job
        except Exception:
            self._rollback()
            raise

    def register_version_and_ingestion_job(
        self,
        *,
        owner_id: str,
        document_id: str,
        content_sha256: str,
        source_snapshot_sha256: str,
        parse_version: str,
        idempotency_key: str,
    ) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]:
        """Atomically bind one idempotency key to one immutable content version."""

        try:
            version = self._register_version(
                owner_id=owner_id,
                document_id=document_id,
                content_sha256=content_sha256,
                source_snapshot_sha256=source_snapshot_sha256,
                parse_version=parse_version,
                commit_transaction=False,
            )
            job = self._register_ingestion_job(
                owner_id=owner_id,
                document_id=document_id,
                document_version_id=version.document_version_id,
                idempotency_key=idempotency_key,
                commit_transaction=False,
            )
            self._commit()
            return version, job
        except Exception:
            self._rollback()
            raise

    def transition_version(
        self,
        *,
        owner_id: str,
        document_version_id: str,
        expected_revision: int,
        target_status: LifecycleStatus,
        updates: Mapping[str, Any] | None = None,
    ) -> DocumentVersionLifecycleV1:
        return self._transition_version(
            owner_id=owner_id,
            document_version_id=document_version_id,
            expected_revision=expected_revision,
            target_status=target_status,
            updates=updates,
            commit_transaction=True,
        )

    def _transition_version(
        self,
        *,
        owner_id: str,
        document_version_id: str,
        expected_revision: int,
        target_status: LifecycleStatus,
        updates: Mapping[str, Any] | None,
        commit_transaction: bool,
    ) -> DocumentVersionLifecycleV1:
        """Compare-and-swap a lifecycle state after validating the frozen transition graph."""

        patch = dict(updates or {})
        unknown = set(patch) - LIFECYCLE_MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"unsupported lifecycle update fields: {sorted(unknown)}")
        try:
            current_row = self._execute_one(
                """-- lock_document_version_v1
                SELECT paper_id, document_id, owner_id, document_version_id,
                       content_sha256, source_snapshot_sha256, parse_version,
                       lifecycle_revision, lifecycle_status, parse_finish_time,
                       chunk_splitter_time, chunk_create_time, chunk_gen_time,
                       vector_index_time, elasticsearch_state, milvus_state,
                       delete_time, chunk_expire_time, last_access_time,
                       last_refresh_time, failure_code, updated_at, is_active
                FROM rag_document_versions
                WHERE owner_id = %(owner_id)s
                  AND document_version_id = %(document_version_id)s
                FOR UPDATE
                """,
                {
                    "owner_id": owner_id,
                    "document_version_id": document_version_id,
                },
            )
            if current_row is None:
                raise IdentityConflictError(
                    "document version does not exist in the authenticated owner scope"
                )
            current = _version_from_row(current_row)
            if current.lifecycle_revision != expected_revision:
                raise ConcurrentLifecycleUpdateError(
                    "document lifecycle revision changed before update"
                )
            is_processing_progress = (
                current.lifecycle_status is LifecycleStatus.PROCESSING
                and target_status is LifecycleStatus.PROCESSING
                and bool(patch)
            )
            if (
                target_status
                not in ALLOWED_LIFECYCLE_TRANSITIONS[current.lifecycle_status]
                and not is_processing_progress
            ):
                raise LifecycleTransitionError(
                    "transition "
                    f"{current.lifecycle_status.value} -> {target_status.value} "
                    "is not allowed"
                )
            if "index_states" in patch:
                patch["index_states"] = IndexStatesV1.model_validate(patch["index_states"])
            candidate = DocumentVersionLifecycleV1.model_validate(
                {
                    **current.model_dump(),
                    **patch,
                    "lifecycle_revision": current.lifecycle_revision + 1,
                    "lifecycle_status": target_status,
                    "updated_at": self.clock(),
                }
            )
            params = candidate.model_dump(exclude={"schema_version", "index_states"})
            params.update(
                {
                    "expected_revision": expected_revision,
                    "elasticsearch_state": candidate.index_states.elasticsearch_chunks,
                    "milvus_state": candidate.index_states.milvus_vectors,
                }
            )
            updated_row = self._execute_one(
                """-- update_document_version_lifecycle_v1
                UPDATE rag_document_versions SET
                    lifecycle_revision = %(lifecycle_revision)s,
                    lifecycle_status = %(lifecycle_status)s,
                    parse_finish_time = %(parse_finish_time)s,
                    chunk_splitter_time = %(chunk_splitter_time)s,
                    chunk_create_time = %(chunk_create_time)s,
                    chunk_gen_time = %(chunk_gen_time)s,
                    vector_index_time = %(vector_index_time)s,
                    elasticsearch_state = %(elasticsearch_state)s,
                    milvus_state = %(milvus_state)s,
                    delete_time = %(delete_time)s,
                    chunk_expire_time = %(chunk_expire_time)s,
                    last_access_time = %(last_access_time)s,
                    last_refresh_time = %(last_refresh_time)s,
                    failure_code = %(failure_code)s,
                    updated_at = %(updated_at)s
                WHERE owner_id = %(owner_id)s
                  AND document_version_id = %(document_version_id)s
                  AND lifecycle_revision = %(expected_revision)s
                RETURNING paper_id, document_id, owner_id, document_version_id,
                          content_sha256, source_snapshot_sha256, parse_version,
                          lifecycle_revision, lifecycle_status, parse_finish_time,
                          chunk_splitter_time, chunk_create_time, chunk_gen_time,
                          vector_index_time, elasticsearch_state, milvus_state,
                          delete_time, chunk_expire_time, last_access_time,
                          last_refresh_time, failure_code, updated_at, is_active
                """,
                params,
            )
            if updated_row is None:
                raise ConcurrentLifecycleUpdateError(
                    "document lifecycle revision changed during update"
                )
            updated = _version_from_row(updated_row)
            if commit_transaction:
                self._commit()
            return updated
        except Exception:
            self._rollback()
            raise

    def get_online_version(
        self, *, owner_id: str, document_version_id: str
    ) -> DocumentVersionLifecycleV1 | None:
        """Return only an active version inside the authenticated owner scope."""

        try:
            row = self._execute_one(
                """-- get_online_document_version_v1
                SELECT paper_id, document_id, owner_id, document_version_id,
                       content_sha256, source_snapshot_sha256, parse_version,
                       lifecycle_revision, lifecycle_status, parse_finish_time,
                       chunk_splitter_time, chunk_create_time, chunk_gen_time,
                       vector_index_time, elasticsearch_state, milvus_state,
                       delete_time, chunk_expire_time, last_access_time,
                       last_refresh_time, failure_code, updated_at, is_active
                FROM rag_document_versions
                WHERE owner_id = %(owner_id)s
                  AND document_version_id = %(document_version_id)s
                  AND is_active = TRUE
                """,
                {
                    "owner_id": owner_id,
                    "document_version_id": document_version_id,
                },
            )
            self._commit()
            return None if row is None else _version_from_row(row)
        except Exception:
            self._rollback()
            raise

    def resolve_online_versions(
        self, *, owner_id: str, document_ids: Sequence[str] = ()
    ) -> tuple[DocumentVersionLifecycleV1, ...]:
        """Resolve only PostgreSQL-READY versions inside one authenticated owner."""

        requested = tuple(document_ids)
        if len(requested) > 1000:
            raise ValueError("online document scope exceeds the phase-1 limit")
        if len(requested) != len(set(requested)):
            raise ValueError("online document scope contains duplicates")
        if not _CONTRACT_ID_PATTERN.fullmatch(owner_id) or any(
            not _CONTRACT_ID_PATTERN.fullmatch(document_id)
            for document_id in requested
        ):
            raise ValueError("online owner or document identity is invalid")
        try:
            rows = self._execute_all(
                """-- resolve_online_document_versions_v1
                SELECT paper_id, document_id, owner_id, document_version_id,
                       content_sha256, source_snapshot_sha256, parse_version,
                       lifecycle_revision, lifecycle_status, parse_finish_time,
                       chunk_splitter_time, chunk_create_time, chunk_gen_time,
                       vector_index_time, elasticsearch_state, milvus_state,
                       delete_time, chunk_expire_time, last_access_time,
                       last_refresh_time, failure_code, updated_at, is_active
                FROM rag_document_versions
                WHERE owner_id = %(owner_id)s
                  AND lifecycle_status = 'READY'
                  AND is_active = TRUE
                  AND delete_time IS NULL
                  AND chunk_expire_time IS NULL
                  AND elasticsearch_state = 'READY'
                  AND milvus_state = 'READY'
                  AND (
                      cardinality(%(document_ids)s::text[]) = 0
                      OR document_id = ANY(%(document_ids)s::text[])
                  )
                ORDER BY document_id, document_version_id
                """,
                {"owner_id": owner_id, "document_ids": list(requested)},
            )
            versions = tuple(_version_from_row(row) for row in rows)
            document_keys = [version.document_id for version in versions]
            if len(document_keys) != len(set(document_keys)):
                raise PostgresFactSourceError(
                    "multiple active versions violate online visibility truth"
                )
            self._commit()
            return versions
        except Exception:
            self._rollback()
            raise

    def update_ingestion_job(
        self,
        *,
        owner_id: str,
        job_id: str,
        status: IngestionJobStatus,
        failure_code: str | None = None,
    ) -> IngestionJobV1:
        return self._update_ingestion_job(
            owner_id=owner_id,
            job_id=job_id,
            status=status,
            failure_code=failure_code,
            commit_transaction=True,
        )

    def _update_ingestion_job(
        self,
        *,
        owner_id: str,
        job_id: str,
        status: IngestionJobStatus,
        failure_code: str | None,
        commit_transaction: bool,
    ) -> IngestionJobV1:
        """Persist replay attempts and stable job failure state."""

        if status is IngestionJobStatus.FAILED and failure_code is None:
            raise ValueError("FAILED ingestion job requires failure_code")
        if status is not IngestionJobStatus.FAILED and failure_code is not None:
            raise ValueError("only FAILED ingestion jobs may retain failure_code")
        try:
            row = self._execute_one(
                """-- update_ingestion_job_v1
                UPDATE rag_ingestion_jobs SET
                    status = %(status)s,
                    attempt_count = attempt_count +
                        CASE WHEN %(status)s = 'RUNNING' THEN 1 ELSE 0 END,
                    failure_code = %(failure_code)s,
                    updated_at = %(updated_at)s
                WHERE owner_id = %(owner_id)s AND job_id = %(job_id)s
                RETURNING job_id, owner_id, idempotency_key, document_id,
                          document_version_id, status, attempt_count,
                          failure_code, created_at, updated_at
                """,
                {
                    "owner_id": owner_id,
                    "job_id": job_id,
                    "status": status,
                    "failure_code": failure_code,
                    "updated_at": self.clock(),
                },
            )
            if row is None:
                raise IdentityConflictError(
                    "ingestion job does not exist in the authenticated owner scope"
                )
            job = _job_from_row(row)
            if commit_transaction:
                self._commit()
            return job
        except Exception:
            self._rollback()
            raise

    def record_indexing_failure(
        self,
        *,
        owner_id: str,
        document_version_id: str,
        expected_revision: int,
        index_states: IndexStatesV1 | Mapping[str, Any],
        job_id: str,
        failure_code: str,
    ) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]:
        """Atomically persist a replayable indexing failure and its stable job code."""

        try:
            version = self._transition_version(
                owner_id=owner_id,
                document_version_id=document_version_id,
                expected_revision=expected_revision,
                target_status=LifecycleStatus.PROCESSING,
                updates={
                    "index_states": index_states,
                    "failure_code": failure_code,
                },
                commit_transaction=False,
            )
            job = self._update_ingestion_job(
                owner_id=owner_id,
                job_id=job_id,
                status=IngestionJobStatus.FAILED,
                failure_code=failure_code,
                commit_transaction=False,
            )
            if job.document_version_id != version.document_version_id:
                raise IdentityConflictError(
                    "ingestion job is not bound to the indexed document version"
                )
            self._commit()
            return version, job
        except Exception:
            self._rollback()
            raise

    def finalize_indexing_success(
        self,
        *,
        owner_id: str,
        document_version_id: str,
        expected_revision: int,
        index_states: IndexStatesV1 | Mapping[str, Any],
        vector_index_time: datetime,
        job_id: str,
    ) -> tuple[DocumentVersionLifecycleV1, IngestionJobV1]:
        """Atomically make a dual-indexed version READY and complete its job."""

        try:
            version = self._transition_version(
                owner_id=owner_id,
                document_version_id=document_version_id,
                expected_revision=expected_revision,
                target_status=LifecycleStatus.READY,
                updates={
                    "index_states": index_states,
                    "vector_index_time": vector_index_time,
                    "failure_code": None,
                },
                commit_transaction=False,
            )
            job = self._update_ingestion_job(
                owner_id=owner_id,
                job_id=job_id,
                status=IngestionJobStatus.SUCCEEDED,
                failure_code=None,
                commit_transaction=False,
            )
            if job.document_version_id != version.document_version_id:
                raise IdentityConflictError(
                    "ingestion job is not bound to the indexed document version"
                )
            self._commit()
            return version, job
        except Exception:
            self._rollback()
            raise

    def enqueue_cleanup(
        self,
        *,
        backend: str,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        max_attempts: int = 5,
    ) -> CleanupJobV1:
        """Idempotently persist cleanup only for an already-INACTIVE version."""

        now = self.clock()
        candidate = CleanupJobV1(
            cleanup_id=self.id_factory("cleanup"),
            backend=backend,
            owner_id=owner_id,
            document_id=document_id,
            document_version_id=document_version_id,
            status=CleanupJobStatus.PENDING,
            attempt_count=0,
            max_attempts=max_attempts,
            next_attempt_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            row = self._execute_one(
                """-- enqueue_index_cleanup_v1
                INSERT INTO rag_index_cleanup_jobs (
                    cleanup_id, backend, owner_id, document_id,
                    document_version_id, status, attempt_count, max_attempts,
                    next_attempt_at, created_at, updated_at
                )
                SELECT %(cleanup_id)s, %(backend)s, v.owner_id, v.document_id,
                       v.document_version_id, 'PENDING', 0, %(max_attempts)s,
                       %(next_attempt_at)s, %(created_at)s, %(updated_at)s
                FROM rag_document_versions AS v
                WHERE v.owner_id = %(owner_id)s
                  AND v.document_id = %(document_id)s
                  AND v.document_version_id = %(document_version_id)s
                  AND v.lifecycle_status = 'INACTIVE'
                ON CONFLICT (backend, owner_id, document_id, document_version_id)
                DO UPDATE SET updated_at = rag_index_cleanup_jobs.updated_at
                RETURNING cleanup_id, backend, owner_id, document_id,
                          document_version_id, status, attempt_count, max_attempts,
                          next_attempt_at, lease_token, lease_expires_at,
                          failure_code, created_at, updated_at, completed_at
                """,
                candidate.model_dump(),
            )
            if row is None:
                raise IdentityConflictError(
                    "cleanup requires an INACTIVE version in the authenticated owner scope"
                )
            job = _cleanup_from_row(row)
            if (
                job.backend != candidate.backend
                or job.owner_id != candidate.owner_id
                or job.document_id != candidate.document_id
                or job.document_version_id != candidate.document_version_id
                or job.max_attempts != candidate.max_attempts
            ):
                raise IdentityConflictError(
                    "cleanup identity or retry policy does not match the request"
                )
            self._commit()
            return job
        except Exception:
            self._rollback()
            raise

    def claim_cleanup(self, *, lease_seconds: int = 300) -> CleanupJobV1 | None:
        """Recover expired leases and claim one due cleanup with SKIP LOCKED."""

        if lease_seconds < 1:
            raise ValueError("cleanup lease_seconds must be positive")
        now = self.clock()
        try:
            self._execute_no_result(
                """-- recover_expired_index_cleanup_leases_v1
                UPDATE rag_index_cleanup_jobs SET
                    status = CASE
                        WHEN attempt_count >= max_attempts THEN 'FAILED'
                        ELSE 'RETRY'
                    END,
                    next_attempt_at = %(now)s,
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    failure_code = 'CLEANUP_LEASE_EXPIRED',
                    updated_at = %(now)s,
                    completed_at = CASE
                        WHEN attempt_count >= max_attempts THEN %(now)s
                        ELSE NULL
                    END
                WHERE status = 'RUNNING'
                  AND lease_expires_at <= %(now)s
                """,
                {"now": now},
            )
            row = self._execute_one(
                """-- claim_due_index_cleanup_v1
                WITH candidate AS (
                    SELECT cleanup_id
                    FROM rag_index_cleanup_jobs
                    WHERE status IN ('PENDING', 'RETRY')
                      AND next_attempt_at <= %(now)s
                    ORDER BY next_attempt_at, created_at, cleanup_id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE rag_index_cleanup_jobs AS jobs SET
                    status = 'RUNNING',
                    attempt_count = jobs.attempt_count + 1,
                    lease_token = %(lease_token)s,
                    lease_expires_at = %(lease_expires_at)s,
                    failure_code = NULL,
                    updated_at = %(now)s,
                    completed_at = NULL
                FROM candidate
                WHERE jobs.cleanup_id = candidate.cleanup_id
                RETURNING jobs.cleanup_id, jobs.backend, jobs.owner_id,
                          jobs.document_id, jobs.document_version_id, jobs.status,
                          jobs.attempt_count, jobs.max_attempts, jobs.next_attempt_at,
                          jobs.lease_token, jobs.lease_expires_at, jobs.failure_code,
                          jobs.created_at, jobs.updated_at, jobs.completed_at
                """,
                {
                    "now": now,
                    "lease_token": self.id_factory("cleanup_lease"),
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                },
            )
            self._commit()
            return None if row is None else _cleanup_from_row(row)
        except Exception:
            self._rollback()
            raise

    def complete_cleanup(
        self, *, cleanup_id: str, lease_token: str
    ) -> CleanupJobV1:
        """Complete only the exact currently leased cleanup attempt."""

        now = self.clock()
        try:
            row = self._execute_one(
                """-- complete_index_cleanup_v1
                UPDATE rag_index_cleanup_jobs SET
                    status = 'SUCCEEDED',
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    failure_code = NULL,
                    updated_at = %(now)s,
                    completed_at = %(now)s
                WHERE cleanup_id = %(cleanup_id)s
                  AND status = 'RUNNING'
                  AND lease_token = %(lease_token)s
                RETURNING cleanup_id, backend, owner_id, document_id,
                          document_version_id, status, attempt_count, max_attempts,
                          next_attempt_at, lease_token, lease_expires_at,
                          failure_code, created_at, updated_at, completed_at
                """,
                {
                    "cleanup_id": cleanup_id,
                    "lease_token": lease_token,
                    "now": now,
                },
            )
            if row is None:
                raise IdentityConflictError("cleanup lease is stale or does not exist")
            job = _cleanup_from_row(row)
            self._commit()
            return job
        except Exception:
            self._rollback()
            raise

    def record_cleanup_failure(
        self,
        *,
        cleanup_id: str,
        lease_token: str,
        failure_code: str,
        retry_at: datetime,
    ) -> CleanupJobV1:
        """Persist retry or terminal failure without exposing raw exception text."""

        if not _CONTRACT_ID_PATTERN.fullmatch(failure_code):
            raise ValueError("cleanup failure_code must be a stable contract ID")
        if retry_at.tzinfo is None or retry_at.utcoffset() is None:
            raise ValueError("cleanup retry_at must include a timezone")
        now = self.clock()
        try:
            row = self._execute_one(
                """-- record_index_cleanup_failure_v1
                UPDATE rag_index_cleanup_jobs SET
                    status = CASE
                        WHEN attempt_count >= max_attempts THEN 'FAILED'
                        ELSE 'RETRY'
                    END,
                    next_attempt_at = %(retry_at)s,
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    failure_code = %(failure_code)s,
                    updated_at = %(now)s,
                    completed_at = CASE
                        WHEN attempt_count >= max_attempts THEN %(now)s
                        ELSE NULL
                    END
                WHERE cleanup_id = %(cleanup_id)s
                  AND status = 'RUNNING'
                  AND lease_token = %(lease_token)s
                RETURNING cleanup_id, backend, owner_id, document_id,
                          document_version_id, status, attempt_count, max_attempts,
                          next_attempt_at, lease_token, lease_expires_at,
                          failure_code, created_at, updated_at, completed_at
                """,
                {
                    "cleanup_id": cleanup_id,
                    "lease_token": lease_token,
                    "failure_code": failure_code,
                    "retry_at": retry_at,
                    "now": now,
                },
            )
            if row is None:
                raise IdentityConflictError("cleanup lease is stale or does not exist")
            job = _cleanup_from_row(row)
            self._commit()
            return job
        except Exception:
            self._rollback()
            raise
