"""Internal parse models and the frozen ChunkRecordV1 runtime model."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


ContractId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class IngestionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParsedBlock(IngestionModel):
    page_number: int = Field(ge=1)
    section_path: tuple[NonEmptyText, ...] = Field(min_length=1)
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=1)
    text: NonEmptyText

    @model_validator(mode="after")
    def source_range_is_ordered(self) -> "ParsedBlock":
        if self.source_end <= self.source_start:
            raise ValueError("source_end must be greater than source_start")
        return self


class ParsedPdf(IngestionModel):
    pdf_sha256: Sha256
    source_text_sha256: Sha256
    clean_text: str
    page_count: int = Field(ge=1)
    parse_status: Literal["PASS", "REVIEW", "FAILED"]
    warnings: tuple[ContractId, ...]
    blocks: tuple[ParsedBlock, ...]


class ChunkRecordV1(IngestionModel):
    chunk_id: ContractId
    document_id: ContractId
    version_id: ContractId
    text: NonEmptyText
    section_path: NonEmptyText
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    parent_chunk_id: ContractId | None
    previous_chunk_id: ContractId | None
    next_chunk_id: ContractId | None
    tenant_id: ContractId
    visibility: Literal["public", "tenant", "private"]
    library_scope_ids: list[ContractId]
    parse_version: ContractId
    embedding_version: ContractId
    is_active: bool

    @model_validator(mode="after")
    def ranges_and_scopes_are_valid(self) -> "ChunkRecordV1":
        if self.page_end < self.page_start:
            raise ValueError("page_end must not be smaller than page_start")
        if len(self.library_scope_ids) != len(set(self.library_scope_ids)):
            raise ValueError("library_scope_ids must contain unique values")
        return self


class IngestionResult(IngestionModel):
    document_id: ContractId
    version_id: ContractId
    pdf_sha256: Sha256
    source_text_sha256: Sha256
    parse_status: Literal["PASS", "REVIEW"]
    warnings: tuple[ContractId, ...]
    strategy: ContractId
    chunks: tuple[ChunkRecordV1, ...] = Field(min_length=1)
