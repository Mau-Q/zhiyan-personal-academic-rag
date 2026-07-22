-- Enforce at most one PostgreSQL-visible READY version per owner/document.

CREATE UNIQUE INDEX IF NOT EXISTS rag_document_versions_one_active_per_document
    ON rag_document_versions (owner_id, document_id)
    WHERE is_active = TRUE;
