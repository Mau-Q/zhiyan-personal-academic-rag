-- PostgreSQL 18+ minimal fact source for source phase 1.
-- This migration contains no credentials, extensions, runtime data or remote host assumptions.

CREATE TABLE IF NOT EXISTS rag_schema_migrations (
    migration_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rag_documents (
    document_id TEXT PRIMARY KEY CHECK (document_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    owner_id TEXT NOT NULL CHECK (owner_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    paper_id TEXT NOT NULL CHECK (paper_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    source_type TEXT NOT NULL CHECK (source_type IN ('uploaded', 'collected')),
    mapping_version TEXT NOT NULL
        CHECK (mapping_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    source_created_time TIMESTAMPTZ NOT NULL,
    source_updated_time TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT rag_documents_owner_paper_unique UNIQUE (owner_id, paper_id),
    CONSTRAINT rag_documents_identity_tuple_unique UNIQUE (document_id, owner_id, paper_id),
    CONSTRAINT rag_documents_source_time_order
        CHECK (source_updated_time >= source_created_time)
);

CREATE OR REPLACE FUNCTION rag_reject_document_identity_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.owner_id IS DISTINCT FROM OLD.owner_id
       OR NEW.paper_id IS DISTINCT FROM OLD.paper_id
       OR NEW.document_id IS DISTINCT FROM OLD.document_id
       OR NEW.source_type IS DISTINCT FROM OLD.source_type THEN
        RAISE EXCEPTION 'document identity fields are immutable'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS rag_documents_identity_immutable ON rag_documents;
CREATE TRIGGER rag_documents_identity_immutable
BEFORE UPDATE ON rag_documents
FOR EACH ROW EXECUTE FUNCTION rag_reject_document_identity_mutation();

CREATE TABLE IF NOT EXISTS rag_document_versions (
    document_version_id TEXT PRIMARY KEY
        CHECK (document_version_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    document_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
    source_snapshot_sha256 TEXT NOT NULL
        CHECK (source_snapshot_sha256 ~ '^[a-f0-9]{64}$'),
    parse_version TEXT NOT NULL
        CHECK (parse_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    lifecycle_revision INTEGER NOT NULL DEFAULT 1 CHECK (lifecycle_revision >= 1),
    lifecycle_status TEXT NOT NULL DEFAULT 'REGISTERED'
        CHECK (lifecycle_status IN (
            'REGISTERED', 'PROCESSING', 'REVIEW', 'READY', 'FAILED', 'INACTIVE'
        )),
    parse_finish_time TIMESTAMPTZ,
    chunk_splitter_time TIMESTAMPTZ,
    chunk_create_time TIMESTAMPTZ,
    chunk_gen_time TIMESTAMPTZ,
    vector_index_time TIMESTAMPTZ,
    elasticsearch_state TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (elasticsearch_state IN ('PENDING', 'READY', 'FAILED')),
    milvus_state TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (milvus_state IN ('PENDING', 'READY', 'FAILED')),
    delete_time TIMESTAMPTZ,
    chunk_expire_time TIMESTAMPTZ,
    last_access_time TIMESTAMPTZ,
    last_refresh_time TIMESTAMPTZ,
    failure_code TEXT
        CHECK (failure_code IS NULL OR failure_code ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN GENERATED ALWAYS AS (
        lifecycle_status = 'READY'
        AND delete_time IS NULL
        AND chunk_expire_time IS NULL
    ) STORED,
    CONSTRAINT rag_document_versions_document_owner_fk
        FOREIGN KEY (document_id, owner_id, paper_id)
        REFERENCES rag_documents (document_id, owner_id, paper_id),
    CONSTRAINT rag_document_versions_source_identity_unique
        UNIQUE (document_id, content_sha256, source_snapshot_sha256, parse_version),
    CONSTRAINT rag_document_versions_owner_lookup_unique
        UNIQUE (document_version_id, owner_id, document_id),
    CONSTRAINT rag_document_versions_delete_state
        CHECK (
            (lifecycle_status = 'INACTIVE'
             AND (delete_time IS NOT NULL OR chunk_expire_time IS NOT NULL))
            OR
            (lifecycle_status <> 'INACTIVE'
             AND delete_time IS NULL AND chunk_expire_time IS NULL)
        ),
    CONSTRAINT rag_document_versions_failure_state
        CHECK (lifecycle_status <> 'FAILED' OR failure_code IS NOT NULL),
    CONSTRAINT rag_document_versions_ready_state
        CHECK (
            lifecycle_status <> 'READY'
            OR (
                parse_finish_time IS NOT NULL
                AND chunk_splitter_time IS NOT NULL
                AND chunk_create_time IS NOT NULL
                AND chunk_gen_time IS NOT NULL
                AND vector_index_time IS NOT NULL
                AND elasticsearch_state = 'READY'
                AND milvus_state = 'READY'
                AND failure_code IS NULL
            )
        )
);

CREATE INDEX IF NOT EXISTS rag_document_versions_owner_active_idx
    ON rag_document_versions (owner_id, document_id, is_active);

CREATE OR REPLACE FUNCTION rag_enforce_document_version_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    transition_allowed BOOLEAN;
BEGIN
    IF NEW.document_version_id IS DISTINCT FROM OLD.document_version_id
       OR NEW.document_id IS DISTINCT FROM OLD.document_id
       OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
       OR NEW.paper_id IS DISTINCT FROM OLD.paper_id
       OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
       OR NEW.source_snapshot_sha256 IS DISTINCT FROM OLD.source_snapshot_sha256
       OR NEW.parse_version IS DISTINCT FROM OLD.parse_version THEN
        RAISE EXCEPTION 'document version identity fields are immutable'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.lifecycle_revision <> OLD.lifecycle_revision + 1 THEN
        RAISE EXCEPTION 'lifecycle_revision must increase by exactly one'
            USING ERRCODE = '40001';
    END IF;

    IF NEW.lifecycle_status = OLD.lifecycle_status THEN
        -- PROCESSING progress revisions record parse/chunk/index milestones without
        -- pretending that a lifecycle transition occurred.
        transition_allowed := OLD.lifecycle_status = 'PROCESSING';
    ELSE
        transition_allowed := CASE OLD.lifecycle_status
            WHEN 'REGISTERED' THEN NEW.lifecycle_status IN ('PROCESSING', 'INACTIVE')
            WHEN 'PROCESSING' THEN NEW.lifecycle_status IN (
                'REVIEW', 'READY', 'FAILED', 'INACTIVE'
            )
            WHEN 'REVIEW' THEN NEW.lifecycle_status IN ('PROCESSING', 'FAILED', 'INACTIVE')
            WHEN 'READY' THEN NEW.lifecycle_status = 'INACTIVE'
            WHEN 'FAILED' THEN NEW.lifecycle_status IN ('PROCESSING', 'INACTIVE')
            WHEN 'INACTIVE' THEN FALSE
            ELSE FALSE
        END;
    END IF;
    IF NOT transition_allowed THEN
        RAISE EXCEPTION 'invalid lifecycle transition: % -> %',
            OLD.lifecycle_status, NEW.lifecycle_status
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS rag_document_versions_transition_guard ON rag_document_versions;
CREATE TRIGGER rag_document_versions_transition_guard
BEFORE UPDATE ON rag_document_versions
FOR EACH ROW EXECUTE FUNCTION rag_enforce_document_version_transition();

CREATE TABLE IF NOT EXISTS rag_ingestion_jobs (
    job_id TEXT PRIMARY KEY CHECK (job_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    owner_id TEXT NOT NULL CHECK (owner_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    idempotency_key TEXT NOT NULL
        CHECK (idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    document_id TEXT NOT NULL,
    document_version_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    failure_code TEXT
        CHECK (failure_code IS NULL OR failure_code ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT rag_ingestion_jobs_owner_key_unique UNIQUE (owner_id, idempotency_key),
    CONSTRAINT rag_ingestion_jobs_version_owner_fk
        FOREIGN KEY (document_version_id, owner_id, document_id)
        REFERENCES rag_document_versions (document_version_id, owner_id, document_id),
    CONSTRAINT rag_ingestion_jobs_failure_state
        CHECK ((status = 'FAILED') = (failure_code IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS rag_ingestion_jobs_owner_status_idx
    ON rag_ingestion_jobs (owner_id, status, updated_at);
