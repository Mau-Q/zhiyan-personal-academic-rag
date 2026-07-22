"""Remote Milvus dense-vector adapter with pinned identity and ACL filtering."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from backend.retrieval.embedding import EmbeddingProvider, OllamaEmbeddingProvider
from backend.retrieval.fixture import is_chunk_authorized, load_chunks, load_scope
from backend.retrieval.sqlite_fts import chunks_fingerprint


JsonObject = dict[str, Any]
COLLECTION_SCHEMA_VERSION = "milvus_vector_collection_v1"
RETRIEVAL_BACKEND = "milvus_dense_bge_m3"
DESCRIPTION_PREFIX = "zhiyan-milvus-v1:"
PASSAGE_TEMPLATE = "section_path_newline_text_v1"
QUERY_TEMPLATE = "raw_question_v1"
VECTOR_NORMALIZATION = "l2_float32_v1"
DEFAULT_VECTOR_MIN_SCORE = 0.5
INDEX_TYPE = "HNSW"
METRIC_TYPE = "COSINE"
HNSW_M = 16
HNSW_EF_CONSTRUCTION = 200
HNSW_SEARCH_EF = 64
EXPECTED_FIELDS = {
    "chunk_id",
    "embedding",
    "document_id",
    "tenant_id",
    "visibility",
    "library_scope_ids",
    "is_active",
    "payload",
}
_COLLECTION_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,254}$")


class MilvusIndexNotReadyError(ValueError):
    """Raised when Milvus cannot prove a matching usable collection."""


class MilvusTransport(Protocol):
    def has_collection(self, collection_name: str) -> bool: ...
    def create_collection(
        self, collection_name: str, *, dimension: int, description: str
    ) -> None: ...
    def insert(self, collection_name: str, data: list[JsonObject]) -> Mapping[str, Any]: ...
    def flush(self, collection_name: str) -> None: ...
    def load_collection(self, collection_name: str) -> None: ...
    def describe_collection(self, collection_name: str) -> Mapping[str, Any]: ...
    def get_collection_stats(self, collection_name: str) -> Mapping[str, Any]: ...
    def search(
        self,
        collection_name: str,
        *,
        vector: Sequence[float],
        filter_expression: str,
        limit: int,
    ) -> list[list[Mapping[str, Any]]]: ...


class PymilvusTransport:
    """Lazy PyMilvus wrapper so the base project does not require the SDK."""

    def __init__(self, *, uri: str = "http://127.0.0.1:19530"):
        try:
            from pymilvus import DataType, MilvusClient
        except ImportError as exc:
            raise MilvusIndexNotReadyError(
                "PyMilvus is required; install the optional dependency "
                'with pip install -e ".[milvus]"'
            ) from exc
        self.client = MilvusClient(uri=uri, token=os.getenv("MILVUS_TOKEN"))
        self.data_type = DataType

    def has_collection(self, collection_name: str) -> bool:
        return bool(self.client.has_collection(collection_name=collection_name))

    def create_collection(
        self, collection_name: str, *, dimension: int, description: str
    ) -> None:
        schema = self.client.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
            description=description,
        )
        schema.add_field(
            field_name="chunk_id", datatype=self.data_type.VARCHAR, is_primary=True, max_length=128
        )
        schema.add_field(
            field_name="embedding", datatype=self.data_type.FLOAT_VECTOR, dim=dimension
        )
        for field_name in ("document_id", "tenant_id", "visibility"):
            schema.add_field(
                field_name=field_name, datatype=self.data_type.VARCHAR, max_length=256
            )
        schema.add_field(
            field_name="library_scope_ids",
            datatype=self.data_type.ARRAY,
            element_type=self.data_type.VARCHAR,
            max_capacity=64,
            max_length=256,
        )
        schema.add_field(field_name="is_active", datatype=self.data_type.BOOL)
        schema.add_field(field_name="payload", datatype=self.data_type.JSON)
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_name="embedding_hnsw",
            index_type=INDEX_TYPE,
            metric_type=METRIC_TYPE,
            params={"M": HNSW_M, "efConstruction": HNSW_EF_CONSTRUCTION},
        )
        self.client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
            consistency_level="Strong",
            num_shards=1,
        )

    def insert(self, collection_name: str, data: list[JsonObject]) -> Mapping[str, Any]:
        return self.client.insert(collection_name=collection_name, data=data)

    def flush(self, collection_name: str) -> None:
        self.client.flush(collection_name=collection_name)

    def load_collection(self, collection_name: str) -> None:
        self.client.load_collection(collection_name=collection_name)

    def describe_collection(self, collection_name: str) -> Mapping[str, Any]:
        return self.client.describe_collection(collection_name=collection_name)

    def get_collection_stats(self, collection_name: str) -> Mapping[str, Any]:
        return self.client.get_collection_stats(collection_name=collection_name)

    def search(
        self,
        collection_name: str,
        *,
        vector: Sequence[float],
        filter_expression: str,
        limit: int,
    ) -> list[list[Mapping[str, Any]]]:
        return self.client.search(
            collection_name=collection_name,
            data=[list(vector)],
            anns_field="embedding",
            filter=filter_expression,
            limit=limit,
            output_fields=["payload"],
            search_params={"metric_type": METRIC_TYPE, "params": {"ef": HNSW_SEARCH_EF}},
        )


def _normalize(vector: Sequence[float]) -> list[float]:
    converted = [float(value) for value in vector]
    if not converted or not all(math.isfinite(value) for value in converted):
        raise ValueError("embedding vector must be non-empty and finite")
    norm = math.sqrt(math.fsum(value * value for value in converted))
    if norm <= 0:
        raise ValueError("embedding vector norm must be positive")
    return [value / norm for value in converted]


def _passage_text(chunk: Mapping[str, Any]) -> str:
    return f"{chunk['section_path']}\n{chunk['text']}"


def _validate_chunks(chunks: Sequence[Mapping[str, Any]]) -> None:
    if not chunks:
        raise ValueError("cannot build an empty Milvus collection")
    ids: set[str] = set()
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id or chunk_id in ids:
            raise ValueError("Milvus chunks require unique non-empty chunk_id values")
        ids.add(chunk_id)
        for field in ("document_id", "tenant_id", "visibility", "section_path", "text"):
            if not isinstance(chunk.get(field), str) or not chunk[field]:
                raise ValueError(f"chunk {chunk_id} has invalid {field}")
        if not isinstance(chunk.get("library_scope_ids"), list) or not all(
            isinstance(value, str) and value for value in chunk["library_scope_ids"]
        ):
            raise ValueError(f"chunk {chunk_id} has invalid library_scope_ids")
        if not isinstance(chunk.get("is_active"), bool):
            raise ValueError(f"chunk {chunk_id} has invalid is_active")


def _metadata(
    chunks: Sequence[Mapping[str, Any]], provider: EmbeddingProvider, dim: int
) -> JsonObject:
    identity = provider.identity()
    return {
        "schema_version": COLLECTION_SCHEMA_VERSION,
        "retrieval_backend": RETRIEVAL_BACKEND,
        "source_chunks_sha256": chunks_fingerprint(chunks),
        "chunk_count": str(len(chunks)),
        "embedding_provider": identity.provider,
        "embedding_model": identity.model,
        "embedding_model_digest": identity.digest,
        "embedding_dimension": str(dim),
        "passage_template": PASSAGE_TEMPLATE,
        "query_template": QUERY_TEMPLATE,
        "vector_normalization": VECTOR_NORMALIZATION,
        "input_truncation": "provider_enabled_v1",
        "metric_type": METRIC_TYPE,
        "index_type": INDEX_TYPE,
        "hnsw_m": str(HNSW_M),
        "hnsw_ef_construction": str(HNSW_EF_CONSTRUCTION),
        "hnsw_search_ef": str(HNSW_SEARCH_EF),
    }


def _description(metadata: Mapping[str, Any]) -> str:
    return DESCRIPTION_PREFIX + json.dumps(metadata, sort_keys=True, separators=(",", ":"))


def _parse_description(value: Any) -> dict[str, str]:
    if not isinstance(value, str) or not value.startswith(DESCRIPTION_PREFIX):
        raise MilvusIndexNotReadyError("Milvus collection identity description is missing")
    try:
        payload = json.loads(value[len(DESCRIPTION_PREFIX) :])
    except json.JSONDecodeError as exc:
        raise MilvusIndexNotReadyError("Milvus collection identity description is invalid") from exc
    if not isinstance(payload, dict):
        raise MilvusIndexNotReadyError("Milvus collection identity must be an object")
    return {str(key): str(value) for key, value in payload.items()}


def _string_list(scope: Mapping[str, Any], field: str) -> list[str] | None:
    value = scope.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return None
    return sorted(set(value))


def _quoted_list(values: Sequence[str]) -> str:
    return "[" + ",".join(json.dumps(value) for value in values) + "]"


def _authorization_filter(scope: Mapping[str, Any]) -> str:
    user_id = scope.get("user_id")
    tenant_id = scope.get("tenant_id")
    acl_version = scope.get("acl_version")
    include_public = scope.get("include_public")
    document_ids = _string_list(scope, "document_ids")
    library_ids = _string_list(scope, "library_ids")
    folder_ids = _string_list(scope, "folder_ids")
    invalid = (
        not isinstance(user_id, str)
        or not user_id
        or not isinstance(tenant_id, str)
        or not tenant_id
        or not isinstance(acl_version, str)
        or not acl_version
        or not isinstance(include_public, bool)
        or document_ids is None
        or library_ids is None
        or folder_ids is None
    )
    if invalid:
        return "is_active == true and is_active == false"
    selectors: list[str] = []
    if document_ids:
        selectors.append(f"document_id in {_quoted_list(document_ids)}")
    if library_ids:
        selectors.append(f"array_contains_any(library_scope_ids, {_quoted_list(library_ids)})")
    if folder_ids and not selectors:
        return "is_active == true and is_active == false"
    selector = "(" + " or ".join(selectors) + ")" if selectors else ""
    visibility: list[str] = []
    if include_public:
        visibility.append(f'(visibility == "public"{f" and {selector}" if selector else ""})')
    tenant = json.dumps(tenant_id)
    tenant_selector = f" and {selector}" if selector else ""
    visibility.append(
        f'(visibility == "tenant" and tenant_id == {tenant}{tenant_selector})'
    )
    if selector:
        visibility.append(
            f'(visibility == "private" and tenant_id == {tenant} and {selector})'
        )
    return "is_active == true and (" + " or ".join(visibility) + ")"


class MilvusVectorIndex:
    def __init__(self, collection_name: str, transport: MilvusTransport):
        if not _COLLECTION_NAME_PATTERN.fullmatch(collection_name):
            raise ValueError("Milvus collection_name is invalid")
        self.collection_name = collection_name
        self.transport = transport

    def build(
        self, chunks: Iterable[Mapping[str, Any]], provider: EmbeddingProvider
    ) -> dict[str, str]:
        chunk_list = [dict(chunk) for chunk in chunks]
        _validate_chunks(chunk_list)
        if self.transport.has_collection(self.collection_name):
            raise MilvusIndexNotReadyError(
                "Milvus collection already exists; use a new versioned name"
            )
        vectors = provider.embed([_passage_text(chunk) for chunk in chunk_list])
        if len(vectors) != len(chunk_list):
            raise ValueError("embedding count does not match chunk count")
        normalized = [_normalize(vector) for vector in vectors]
        dimensions = {len(vector) for vector in normalized}
        if len(dimensions) != 1:
            raise ValueError("embedding dimensions are inconsistent")
        dimension = dimensions.pop()
        metadata = _metadata(chunk_list, provider, dimension)
        self.transport.create_collection(
            self.collection_name, dimension=dimension, description=_description(metadata)
        )
        rows = [
            {
                "chunk_id": chunk["chunk_id"],
                "embedding": vector,
                "document_id": chunk["document_id"],
                "tenant_id": chunk["tenant_id"],
                "visibility": chunk["visibility"],
                "library_scope_ids": chunk["library_scope_ids"],
                "is_active": chunk["is_active"],
                "payload": chunk,
            }
            for chunk, vector in zip(chunk_list, normalized, strict=True)
        ]
        result = self.transport.insert(self.collection_name, rows)
        if result.get("insert_count") not in (None, len(rows)):
            raise MilvusIndexNotReadyError("Milvus insert count does not match chunks")
        self.transport.flush(self.collection_name)
        self.transport.load_collection(self.collection_name)
        return self.verify_source(chunk_list)

    def inspect(self) -> dict[str, str]:
        if not self.transport.has_collection(self.collection_name):
            raise MilvusIndexNotReadyError("Milvus collection does not exist")
        description = self.transport.describe_collection(self.collection_name)
        metadata = _parse_description(description.get("description"))
        expected = {
            "schema_version": COLLECTION_SCHEMA_VERSION,
            "retrieval_backend": RETRIEVAL_BACKEND,
            "passage_template": PASSAGE_TEMPLATE,
            "query_template": QUERY_TEMPLATE,
            "vector_normalization": VECTOR_NORMALIZATION,
            "metric_type": METRIC_TYPE,
            "index_type": INDEX_TYPE,
            "hnsw_m": str(HNSW_M),
            "hnsw_ef_construction": str(HNSW_EF_CONSTRUCTION),
            "hnsw_search_ef": str(HNSW_SEARCH_EF),
        }
        for key, value in expected.items():
            if metadata.get(key) != value:
                raise MilvusIndexNotReadyError(f"Milvus collection {key} is invalid")
        fields = description.get("fields")
        if not isinstance(fields, list) or {
            field.get("name") for field in fields if isinstance(field, dict)
        } != EXPECTED_FIELDS:
            raise MilvusIndexNotReadyError("Milvus collection schema fields are invalid")
        try:
            count = int(self.transport.get_collection_stats(self.collection_name)["row_count"])
            dimension = int(metadata["embedding_dimension"])
            expected_count = int(metadata["chunk_count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MilvusIndexNotReadyError(
                "Milvus collection count or dimension is invalid"
            ) from exc
        if dimension < 1 or count != expected_count:
            raise MilvusIndexNotReadyError("Milvus collection row count does not match metadata")
        for key in (
            "source_chunks_sha256",
            "embedding_provider",
            "embedding_model",
            "embedding_model_digest",
        ):
            if not metadata.get(key):
                raise MilvusIndexNotReadyError(f"Milvus collection {key} is missing")
        return metadata

    def verify_source(self, chunks: Sequence[Mapping[str, Any]]) -> dict[str, str]:
        metadata = self.inspect()
        if metadata["source_chunks_sha256"] != chunks_fingerprint(chunks):
            raise MilvusIndexNotReadyError(
                "Milvus collection source fingerprint does not match chunks"
            )
        if metadata["chunk_count"] != str(len(chunks)):
            raise MilvusIndexNotReadyError("Milvus collection chunk count does not match chunks")
        return metadata

    def verify_provider(self, provider: EmbeddingProvider) -> dict[str, str]:
        metadata = self.inspect()
        identity = provider.identity()
        if (identity.provider, identity.model, identity.digest) != (
            metadata["embedding_provider"],
            metadata["embedding_model"],
            metadata["embedding_model_digest"],
        ):
            raise MilvusIndexNotReadyError(
                "Milvus collection embedding model identity does not match"
            )
        return metadata

    def retrieve(
        self,
        question: str,
        scope: Mapping[str, Any],
        provider: EmbeddingProvider,
        *,
        top_k: int = 3,
        min_score: float = DEFAULT_VECTOR_MIN_SCORE,
        expected_chunks: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[JsonObject]:
        if not question.strip():
            raise ValueError("question must not be blank")
        if top_k < 1 or not -1.0 <= min_score <= 1.0:
            raise ValueError("top_k or min_score is invalid")
        metadata = self.verify_provider(provider)
        if expected_chunks is not None:
            self.verify_source(expected_chunks)
        vector = _normalize(provider.embed([question])[0])
        if len(vector) != int(metadata["embedding_dimension"]):
            raise MilvusIndexNotReadyError("Milvus query embedding dimension does not match")
        hits = self.transport.search(
            self.collection_name,
            vector=vector,
            filter_expression=_authorization_filter(scope),
            limit=top_k,
        )
        first = hits[0] if isinstance(hits, list) and hits else []
        results: list[tuple[float, JsonObject]] = []
        for hit in first:
            entity = hit.get("entity") if isinstance(hit, Mapping) else None
            payload = entity.get("payload") if isinstance(entity, Mapping) else None
            score = hit.get("distance") if isinstance(hit, Mapping) else None
            if isinstance(payload, dict) and isinstance(score, (int, float)):
                if float(score) >= min_score and is_chunk_authorized(payload, scope):
                    results.append((float(score), dict(payload)))
        results.sort(key=lambda item: (-item[0], item[1]["chunk_id"]))
        return [chunk for _, chunk in results[:top_k]]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or query a Milvus vector collection")
    parser.add_argument("--uri", default="http://127.0.0.1:19530")
    parser.add_argument("--collection", required=True)
    parser.add_argument("--model", default="bge-m3:latest")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--chunks", required=True, type=Path)
    subparsers.add_parser("inspect")
    query = subparsers.add_parser("query")
    query.add_argument("--chunks", required=True, type=Path)
    query.add_argument("--scope", required=True, type=Path)
    query.add_argument("--question", required=True)
    query.add_argument("--top-k", type=int, default=3)
    query.add_argument("--min-score", type=float, default=DEFAULT_VECTOR_MIN_SCORE)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        provider = OllamaEmbeddingProvider(model=args.model, base_url=args.base_url)
        index = MilvusVectorIndex(args.collection, PymilvusTransport(uri=args.uri))
        if args.command == "build":
            payload: Any = index.build(load_chunks(args.chunks), provider)
        elif args.command == "inspect":
            payload = index.inspect()
        else:
            chunks = load_chunks(args.chunks)
            payload = {"results": index.retrieve(
                args.question, load_scope(args.scope), provider, top_k=args.top_k,
                min_score=args.min_score, expected_chunks=chunks,
            )}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Milvus input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
