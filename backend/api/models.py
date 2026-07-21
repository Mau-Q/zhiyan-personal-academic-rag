"""Pydantic models aligned with the Stage 0 OpenAPI and JSON Schema contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


ContractId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
NonEmptyText = Annotated[str, StringConstraints(min_length=1)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RagAnswerRequestV1(ContractModel):
    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
    ]
    document_ids: list[ContractId]
    stream: Literal[False]

    @field_validator("document_ids")
    @classmethod
    def document_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("document_ids must contain unique values")
        return value


class EvidenceV1(ContractModel):
    evidence_id: ContractId
    chunk_id: ContractId
    document_id: ContractId
    version_id: ContractId
    section_path: NonEmptyText
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    quote: NonEmptyText


class CitationV1(ContractModel):
    citation_id: ContractId
    evidence_id: ContractId
    document_id: ContractId
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)


class RagAnswerV1(ContractModel):
    request_id: ContractId
    trace_id: ContractId
    status: Literal["COMPLETED", "NO_EVIDENCE", "DEGRADED", "FAILED"]
    answer: str
    evidence: list[EvidenceV1]
    citations: list[CitationV1]
    warnings: list[NonEmptyText]


class ErrorV1(ContractModel):
    request_id: ContractId
    code: ContractId
    message: NonEmptyText
    retryable: bool
