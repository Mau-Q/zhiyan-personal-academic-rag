-- Immutable PDF object registration and Chunk snapshots for source phase 1.
-- PDF payload bytes remain in the configured object root, never in PostgreSQL.

ALTER TABLE rag_index_cleanup_jobs
    DROP CONSTRAINT IF EXISTS rag_index_cleanup_jobs_backend_check;
ALTER TABLE rag_index_cleanup_jobs
    ADD CONSTRAINT rag_index_cleanup_jobs_backend_check
    CHECK (backend IN (
        'elasticsearch_chunks', 'milvus_vectors', 'runtime_snapshot'
    ));

CREATE TABLE IF NOT EXISTS rag_pdf_objects (
    document_version_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    object_key TEXT NOT NULL UNIQUE
        CHECK (object_key ~ '^[a-z0-9][a-z0-9._/-]{0,511}$'),
    storage_backend TEXT NOT NULL CHECK (storage_backend = 'filesystem_v1'),
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    media_type TEXT NOT NULL CHECK (media_type = 'application/pdf'),
    stored_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT rag_pdf_objects_version_owner_fk
        FOREIGN KEY (document_version_id, owner_id, document_id)
        REFERENCES rag_document_versions (document_version_id, owner_id, document_id)
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id TEXT PRIMARY KEY
        CHECK (chunk_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    owner_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_version_id TEXT NOT NULL,
    chunk_ordinal INTEGER NOT NULL CHECK (chunk_ordinal >= 0),
    text TEXT NOT NULL CHECK (length(text) > 0),
    section_path TEXT NOT NULL CHECK (length(section_path) > 0),
    page_start INTEGER NOT NULL CHECK (page_start >= 1),
    page_end INTEGER NOT NULL CHECK (page_end >= page_start),
    parent_chunk_id TEXT,
    previous_chunk_id TEXT,
    next_chunk_id TEXT,
    visibility TEXT NOT NULL CHECK (visibility IN ('public', 'tenant', 'private')),
    library_scope_ids JSONB NOT NULL CHECK (jsonb_typeof(library_scope_ids) = 'array'),
    parse_version TEXT NOT NULL
        CHECK (parse_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    embedding_version TEXT NOT NULL
        CHECK (embedding_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT rag_chunks_version_owner_fk
        FOREIGN KEY (document_version_id, owner_id, document_id)
        REFERENCES rag_document_versions (document_version_id, owner_id, document_id),
    CONSTRAINT rag_chunks_version_ordinal_unique
        UNIQUE (document_version_id, chunk_ordinal)
);

CREATE INDEX IF NOT EXISTS rag_chunks_owner_version_idx
    ON rag_chunks (owner_id, document_version_id, chunk_ordinal);

CREATE OR REPLACE FUNCTION rag_reject_runtime_snapshot_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'runtime snapshot rows are immutable; create a new document version'
        USING ERRCODE = '23514';
END;
$$;

CREATE OR REPLACE FUNCTION rag_allow_only_inactive_snapshot_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM rag_document_versions
        WHERE document_version_id = OLD.document_version_id
          AND owner_id = OLD.owner_id
          AND document_id = OLD.document_id
          AND lifecycle_status = 'INACTIVE'
          AND is_active = FALSE
    ) THEN
        RAISE EXCEPTION 'runtime snapshot deletion requires an INACTIVE version'
            USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS rag_pdf_objects_immutable ON rag_pdf_objects;
CREATE TRIGGER rag_pdf_objects_immutable
BEFORE UPDATE ON rag_pdf_objects
FOR EACH ROW EXECUTE FUNCTION rag_reject_runtime_snapshot_mutation();

DROP TRIGGER IF EXISTS rag_pdf_objects_delete_guard ON rag_pdf_objects;
CREATE TRIGGER rag_pdf_objects_delete_guard
BEFORE DELETE ON rag_pdf_objects
FOR EACH ROW EXECUTE FUNCTION rag_allow_only_inactive_snapshot_delete();

DROP TRIGGER IF EXISTS rag_chunks_immutable ON rag_chunks;
CREATE TRIGGER rag_chunks_immutable
BEFORE UPDATE ON rag_chunks
FOR EACH ROW EXECUTE FUNCTION rag_reject_runtime_snapshot_mutation();

DROP TRIGGER IF EXISTS rag_chunks_delete_guard ON rag_chunks;
CREATE TRIGGER rag_chunks_delete_guard
BEFORE DELETE ON rag_chunks
FOR EACH ROW EXECUTE FUNCTION rag_allow_only_inactive_snapshot_delete();
