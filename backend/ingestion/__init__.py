"""Local PDF ingestion for frozen Stage 0 contracts."""

from .service import PdfIngestionError, ingest_pdf_bytes

__all__ = ["PdfIngestionError", "ingest_pdf_bytes"]
