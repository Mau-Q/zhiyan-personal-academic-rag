-- Repair the PDF object-key check without rewriting applied migration 0004.
-- PostgreSQL regular-expression bounds reject repetition counts above 255.

ALTER TABLE rag_pdf_objects
    DROP CONSTRAINT IF EXISTS rag_pdf_objects_object_key_check;

ALTER TABLE rag_pdf_objects
    ADD CONSTRAINT rag_pdf_objects_object_key_check
    CHECK (
        length(object_key) BETWEEN 1 AND 512
        AND object_key ~ '^[a-z0-9][a-z0-9._/-]*$'
    );
