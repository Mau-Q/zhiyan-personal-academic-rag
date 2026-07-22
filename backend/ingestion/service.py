"""Adapt local PDF parse output to the frozen ChunkRecordV1 contract."""

from __future__ import annotations

from hashlib import sha256

from pydantic import ValidationError

from backend.ingestion.models import ChunkRecordV1, IngestionResult, ParsedBlock
from backend.ingestion.parser import PdfParseError, PypdfTextParser
from backend.ingestion.splitter import (
    RawChunk,
    SplitterError,
    canonical_sha256,
    split_text,
    strategy_config_hash,
)


PARSE_VERSION = "pypdf_text_v1"
DEFAULT_EMBEDDING_VERSION = "not_embedded_v1"


class PdfIngestionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _source_blocks_for_chunk(
    blocks: tuple[ParsedBlock, ...], chunk: RawChunk
) -> list[ParsedBlock]:
    return [
        block
        for block in blocks
        if block.source_start < chunk.source_end and block.source_end > chunk.source_start
    ]


def _section_path(blocks: list[ParsedBlock], fallback: str | None) -> str:
    paths: list[tuple[str, ...]] = []
    for block in blocks:
        if block.section_path not in paths:
            paths.append(block.section_path)
    if not paths:
        return fallback or "Document"
    first = " > ".join(paths[0])
    if len(paths) == 1:
        return first
    last = " > ".join(paths[-1])
    return f"{first} -> {last}"


def _parent_chunk_id(
    *,
    document_id: str,
    version_id: str,
    strategy: str,
    parent_source_id: str | None,
) -> str | None:
    if parent_source_id is None:
        return None
    identity = {
        "document_id": document_id,
        "version_id": version_id,
        "strategy": strategy,
        "parent_source_id": parent_source_id,
    }
    return f"parent_{canonical_sha256(identity)[:24]}"


def ingest_pdf_bytes(
    pdf_bytes: bytes,
    *,
    document_id: str,
    tenant_id: str,
    visibility: str,
    library_scope_ids: list[str],
    strategy: str,
    expected_sha256: str | None = None,
    allow_parse_review: bool = False,
    embedding_version: str = DEFAULT_EMBEDDING_VERSION,
    version_id: str | None = None,
    is_active: bool = True,
    parser: PypdfTextParser | None = None,
) -> IngestionResult:
    """Create deterministic ChunkRecordV1 objects without network or remote services."""

    actual_pdf_sha256 = sha256(pdf_bytes).hexdigest()
    if expected_sha256 is not None and actual_pdf_sha256 != expected_sha256:
        raise PdfIngestionError(
            "PDF_IDENTITY_MISMATCH",
            "PDF bytes do not match the expected SHA-256 identity.",
        )
    try:
        parsed = (parser or PypdfTextParser()).parse(pdf_bytes)
    except PdfParseError as exc:
        raise PdfIngestionError(exc.code, str(exc)) from exc
    if parsed.parse_status == "FAILED":
        raise PdfIngestionError(
            "PARSE_QUALITY_GATE_BLOCKED",
            "PDF has no usable text; OCR is outside the current stage.",
        )
    if parsed.parse_status == "REVIEW" and not allow_parse_review:
        raise PdfIngestionError(
            "PARSE_QUALITY_GATE_BLOCKED",
            "PDF parse quality requires explicit review approval.",
        )
    if not parsed.blocks:
        raise PdfIngestionError(
            "PARSED_DOCUMENT_LINEAGE_INVALID",
            "Parsed text has no page and section lineage blocks.",
        )
    for block in parsed.blocks:
        if parsed.clean_text[block.source_start : block.source_end] != block.text:
            raise PdfIngestionError(
                "PARSED_DOCUMENT_LINEAGE_INVALID",
                "A parsed block does not match its exact source span.",
            )

    try:
        raw_chunks = split_text(parsed.clean_text, strategy)
    except SplitterError as exc:
        raise PdfIngestionError(exc.code, str(exc)) from exc

    resolved_version_id = version_id or f"version_{parsed.pdf_sha256[:24]}"
    config_hash = strategy_config_hash(strategy)
    chunk_ids: list[str] = []
    chunk_blocks: list[list[ParsedBlock]] = []
    for index, chunk in enumerate(raw_chunks):
        blocks = _source_blocks_for_chunk(parsed.blocks, chunk)
        if not blocks:
            raise PdfIngestionError(
                "SPLITTER_OBJECT_LINEAGE_MISSING",
                "A chunk cannot be traced to a PDF page and section.",
            )
        chunk_blocks.append(blocks)
        identity = {
            "document_id": document_id,
            "version_id": resolved_version_id,
            "strategy": strategy,
            "config_hash": config_hash,
            "source_text_sha256": parsed.source_text_sha256,
            "chunk_index": index,
            "source_start": chunk.source_start,
            "source_end": chunk.source_end,
            "content_sha256": sha256(chunk.text.encode("utf-8")).hexdigest(),
        }
        chunk_ids.append(f"chunk_{canonical_sha256(identity)[:24]}")

    records: list[ChunkRecordV1] = []
    try:
        for index, (chunk, blocks) in enumerate(zip(raw_chunks, chunk_blocks, strict=True)):
            page_numbers = [block.page_number for block in blocks]
            records.append(
                ChunkRecordV1(
                    chunk_id=chunk_ids[index],
                    document_id=document_id,
                    version_id=resolved_version_id,
                    text=chunk.text,
                    section_path=_section_path(blocks, chunk.section_name),
                    page_start=min(page_numbers),
                    page_end=max(page_numbers),
                    parent_chunk_id=_parent_chunk_id(
                        document_id=document_id,
                        version_id=resolved_version_id,
                        strategy=strategy,
                        parent_source_id=chunk.parent_source_id,
                    ),
                    previous_chunk_id=chunk_ids[index - 1] if index else None,
                    next_chunk_id=chunk_ids[index + 1] if index + 1 < len(chunk_ids) else None,
                    tenant_id=tenant_id,
                    visibility=visibility,
                    library_scope_ids=library_scope_ids,
                    parse_version=PARSE_VERSION,
                    embedding_version=embedding_version,
                    is_active=is_active,
                )
            )
        return IngestionResult(
            document_id=document_id,
            version_id=resolved_version_id,
            pdf_sha256=parsed.pdf_sha256,
            source_text_sha256=parsed.source_text_sha256,
            parse_status=parsed.parse_status,
            warnings=parsed.warnings,
            strategy=strategy,
            chunks=tuple(records),
        )
    except ValidationError as exc:
        raise PdfIngestionError(
            "CHUNK_RECORD_CONTRACT_INVALID",
            "Ingestion configuration or output violates ChunkRecordV1.",
        ) from exc
