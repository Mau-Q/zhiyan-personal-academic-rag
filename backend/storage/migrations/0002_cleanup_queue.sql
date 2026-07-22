-- Persistent, lease-based physical index cleanup queue for source phase 1.

CREATE TABLE IF NOT EXISTS rag_index_cleanup_jobs (
    cleanup_id TEXT PRIMARY KEY
        CHECK (cleanup_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    backend TEXT NOT NULL
        CHECK (backend IN ('elasticsearch_chunks', 'milvus_vectors')),
    owner_id TEXT NOT NULL
        CHECK (owner_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    document_id TEXT NOT NULL
        CHECK (document_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    document_version_id TEXT NOT NULL
        CHECK (document_version_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'RETRY', 'SUCCEEDED', 'FAILED')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 100),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_token TEXT
        CHECK (lease_token IS NULL OR lease_token ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    lease_expires_at TIMESTAMPTZ,
    failure_code TEXT
        CHECK (failure_code IS NULL OR failure_code ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    CONSTRAINT rag_index_cleanup_jobs_version_owner_fk
        FOREIGN KEY (document_version_id, owner_id, document_id)
        REFERENCES rag_document_versions (document_version_id, owner_id, document_id),
    CONSTRAINT rag_index_cleanup_jobs_identity_unique
        UNIQUE (backend, owner_id, document_id, document_version_id),
    CONSTRAINT rag_index_cleanup_jobs_lease_state
        CHECK (
            (status = 'RUNNING') =
            (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
        ),
    CONSTRAINT rag_index_cleanup_jobs_failure_state
        CHECK (
            (status IN ('RETRY', 'FAILED')) = (failure_code IS NOT NULL)
        ),
    CONSTRAINT rag_index_cleanup_jobs_terminal_state
        CHECK (
            (status IN ('SUCCEEDED', 'FAILED')) = (completed_at IS NOT NULL)
        ),
    CONSTRAINT rag_index_cleanup_jobs_attempt_limit
        CHECK (attempt_count <= max_attempts),
    CONSTRAINT rag_index_cleanup_jobs_pending_attempts
        CHECK (status <> 'PENDING' OR attempt_count = 0)
);

CREATE INDEX IF NOT EXISTS rag_index_cleanup_jobs_due_idx
    ON rag_index_cleanup_jobs (status, next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX IF NOT EXISTS rag_index_cleanup_jobs_expired_lease_idx
    ON rag_index_cleanup_jobs (lease_expires_at)
    WHERE status = 'RUNNING';
