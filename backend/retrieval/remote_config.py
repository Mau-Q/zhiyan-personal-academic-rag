"""Versioned, secret-free configuration for remote retrieval adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


RemoteName = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _validate_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("remote retrieval URL must use http or https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("remote retrieval URL must not contain credentials, query, or fragment")
    return value.rstrip("/")


class ElasticsearchRemoteConfigV1(StrictModel):
    url: str = "http://127.0.0.1:9200"
    index: RemoteName
    timeout_seconds: float = Field(default=30.0, gt=0.0)

    @field_validator("url")
    @classmethod
    def url_must_be_secret_free_http(cls, value: str) -> str:
        return _validate_http_url(value)


class MilvusRemoteConfigV1(StrictModel):
    uri: str = "http://127.0.0.1:19530"
    collection: RemoteName
    embedding_model: str = Field(default="bge-m3:latest", min_length=1, max_length=255)
    embedding_base_url: str = "http://127.0.0.1:11434"

    @field_validator("uri", "embedding_base_url")
    @classmethod
    def urls_must_be_secret_free_http(cls, value: str) -> str:
        return _validate_http_url(value)


class RemoteRrfConfigV1(StrictModel):
    top_k: int = Field(default=3, ge=1)
    candidate_k: int = Field(default=20, ge=1)
    rrf_k: int = Field(default=60, ge=1)
    vector_min_score: float = Field(default=0.5, ge=-1.0, le=1.0)

    @model_validator(mode="after")
    def candidate_pool_must_cover_output(self) -> "RemoteRrfConfigV1":
        if self.candidate_k < self.top_k:
            raise ValueError("candidate_k must be greater than or equal to top_k")
        return self


class RemoteRetrievalConfigV1(StrictModel):
    schema_version: Literal["remote_retrieval_config_v1"]
    elasticsearch: ElasticsearchRemoteConfigV1
    milvus: MilvusRemoteConfigV1
    fusion: RemoteRrfConfigV1


def load_remote_retrieval_config(path: Path) -> RemoteRetrievalConfigV1:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid remote retrieval config: {path}") from exc
    return RemoteRetrievalConfigV1.model_validate(payload)
