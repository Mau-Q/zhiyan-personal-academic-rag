"""Version-scoped Milvus writer for detached lifecycle-managed collections."""

from __future__ import annotations

import json
import math
import re
import struct
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

from backend.ingestion.index_lifecycle import IndexBackend, IndexWriteReceipt
from backend.retrieval.embedding import EmbeddingProvider
from backend.retrieval.milvus import (
    COLLECTION_SCHEMA_VERSION,
    EXPECTED_FIELDS,
    HNSW_EF_CONSTRUCTION,
    HNSW_M,
    HNSW_SEARCH_EF,
    INDEX_TYPE,
    METRIC_TYPE,
    PASSAGE_TEMPLATE,
    QUERY_TEMPLATE,
    RETRIEVAL_BACKEND,
    VECTOR_NORMALIZATION,
    JsonObject,
    MilvusIndexNotReadyError,
    MilvusTransport,
    _COLLECTION_NAME_PATTERN,
    _description,
    _metadata,
    _normalize,
    _parse_description,
    _passage_text,
    _validate_chunks,
)
from backend.retrieval.sqlite_fts import chunks_fingerprint


VERSION_WRITER_SCHEMA = "milvus_version_writer_v1"
ONLINE_ENTRYPOINT = "DETACHED_VERSION_COLLECTION"
MAX_COLLECTION_NAME_LENGTH = 255
MAX_VERSION_ROWS = 16_000
_CONTRACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _identity_digest(owner_id: str, document_version_id: str) -> str:
    payload = f"{owner_id}\0{document_version_id}".encode("utf-8")
    return sha256(payload).hexdigest()[:24]


def _float32_vector(vector: Sequence[float]) -> list[float]:
    normalized = _normalize(vector)
    return [struct.unpack("!f", struct.pack("!f", value))[0] for value in normalized]


def _embeddings_fingerprint(vectors: Mapping[str, Sequence[float]]) -> str:
    canonical: list[list[Any]] = []
    for chunk_id in sorted(vectors):
        vector = [float(value) for value in vectors[chunk_id]]
        if not vector or not all(math.isfinite(value) for value in vector):
            raise MilvusIndexNotReadyError("Milvus version embedding is invalid")
        canonical.append([chunk_id, vector])
    payload = json.dumps(canonical, separators=(",", ":")).encode("utf-8")
    return sha256(payload).hexdigest()


class MilvusVersionIndexWriter:
    """Write one owner/version to a deterministic collection outside online routing."""

    backend = IndexBackend.MILVUS

    def __init__(
        self,
        *,
        collection_prefix: str,
        transport: MilvusTransport,
        provider: EmbeddingProvider,
    ) -> None:
        if not _COLLECTION_NAME_PATTERN.fullmatch(collection_prefix):
            raise ValueError("Milvus version collection prefix is invalid")
        candidate = f"{collection_prefix}_v_{'0' * 24}"
        if len(candidate) > MAX_COLLECTION_NAME_LENGTH:
            raise ValueError("Milvus version collection prefix is too long")
        self.collection_prefix = collection_prefix
        self.transport = transport
        self.provider = provider

    def physical_collection_name(
        self, *, owner_id: str, document_version_id: str
    ) -> str:
        self._validate_identity(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        digest = _identity_digest(owner_id, document_version_id)
        return f"{self.collection_prefix}_v_{digest}"

    def ensure_staged(
        self,
        *,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        chunks: Sequence[Mapping[str, Any]],
    ) -> IndexWriteReceipt:
        chunk_list = [dict(chunk) for chunk in chunks]
        self._validate_stage(
            owner_id=owner_id,
            document_id=document_id,
            document_version_id=document_version_id,
            chunks=chunk_list,
        )
        source_sha256 = chunks_fingerprint(chunk_list)
        collection_name = self.physical_collection_name(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )

        if not self.transport.has_collection(collection_name):
            vectors = self._embed_chunks(chunk_list)
            dimension = len(next(iter(vectors.values())))
            metadata = _metadata(chunk_list, self.provider, dimension)
            metadata.update(
                {
                    "version_writer_schema": VERSION_WRITER_SCHEMA,
                    "owner_id": owner_id,
                    "document_id": document_id,
                    "document_version_id": document_version_id,
                    "online_entrypoint": ONLINE_ENTRYPOINT,
                    "embeddings_sha256": _embeddings_fingerprint(vectors),
                }
            )
            self.transport.create_collection(
                collection_name,
                dimension=dimension,
                description=_description(metadata),
            )
            self._upsert_rows(
                collection_name=collection_name,
                chunks=chunk_list,
                vectors=vectors,
            )

        metadata = self._inspect_identity(
            collection_name=collection_name,
            owner_id=owner_id,
            document_id=document_id,
            document_version_id=document_version_id,
            source_sha256=source_sha256,
            expected_count=len(chunk_list),
            verify_provider=True,
        )
        rows = self._query_rows(collection_name)
        seen = self._verify_expected_rows(
            rows=rows,
            chunks=chunk_list,
            metadata=metadata,
            allow_missing=True,
        )
        missing = [chunk for chunk in chunk_list if chunk["chunk_id"] not in seen]
        if missing:
            vectors = self._embed_chunks(chunk_list)
            if _embeddings_fingerprint(vectors) != metadata["embeddings_sha256"]:
                raise MilvusIndexNotReadyError(
                    "Milvus version embedding identity drift"
                )
            self._verify_expected_rows(
                rows=rows,
                chunks=chunk_list,
                metadata=metadata,
                allow_missing=True,
                expected_vectors=vectors,
            )
            self._upsert_rows(
                collection_name=collection_name,
                chunks=missing,
                vectors=vectors,
            )
            rows = self._query_rows(collection_name)
        self._verify_expected_rows(
            rows=rows,
            chunks=chunk_list,
            metadata=metadata,
            allow_missing=False,
        )
        return IndexWriteReceipt(
            backend=self.backend,
            owner_id=owner_id,
            document_version_id=document_version_id,
            chunk_count=int(metadata["chunk_count"]),
            source_chunks_sha256=metadata["source_chunks_sha256"],
        )

    def activate_version(self, *, owner_id: str, document_version_id: str) -> None:
        self._set_active(
            owner_id=owner_id,
            document_version_id=document_version_id,
            is_active=True,
        )

    def deactivate_version(self, *, owner_id: str, document_version_id: str) -> None:
        collection_name = self.physical_collection_name(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        if not self.transport.has_collection(collection_name):
            return
        self._set_active(
            owner_id=owner_id,
            document_version_id=document_version_id,
            is_active=False,
            allow_incomplete=True,
        )

    def delete_version(self, *, owner_id: str, document_version_id: str) -> bool:
        collection_name = self.physical_collection_name(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        if not self.transport.has_collection(collection_name):
            return False
        self._inspect_identity(
            collection_name=collection_name,
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        self.transport.drop_collection(collection_name)
        if self.transport.has_collection(collection_name):
            raise MilvusIndexNotReadyError(
                "Milvus version collection still exists after deletion"
            )
        return True

    def _set_active(
        self,
        *,
        owner_id: str,
        document_version_id: str,
        is_active: bool,
        allow_incomplete: bool = False,
    ) -> None:
        collection_name = self.physical_collection_name(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        if not self.transport.has_collection(collection_name):
            raise MilvusIndexNotReadyError("Milvus version collection does not exist")
        metadata = self._inspect_identity(
            collection_name=collection_name,
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        rows = self._query_rows(collection_name)
        self._verify_lifecycle_rows(
            rows=rows,
            metadata=metadata,
            allow_incomplete=allow_incomplete,
        )
        updated: list[JsonObject] = []
        for row in rows:
            candidate = dict(row)
            payload = dict(candidate["payload"])
            candidate["is_active"] = is_active
            payload["is_active"] = is_active
            candidate["payload"] = payload
            updated.append(candidate)
        if updated:
            result = self.transport.upsert(collection_name, updated)
            if result.get("upsert_count") not in (None, len(updated)):
                raise MilvusIndexNotReadyError(
                    "Milvus version active-state upsert count is invalid"
                )
            self._flush_and_load(collection_name)
        verified = self._query_rows(collection_name)
        self._verify_lifecycle_rows(
            rows=verified,
            metadata=metadata,
            allow_incomplete=allow_incomplete,
            expected_active=is_active,
        )

    def _inspect_identity(
        self,
        *,
        collection_name: str,
        owner_id: str,
        document_version_id: str,
        document_id: str | None = None,
        source_sha256: str | None = None,
        expected_count: int | None = None,
        verify_provider: bool = False,
    ) -> dict[str, str]:
        description = self.transport.describe_collection(collection_name)
        metadata = _parse_description(description.get("description"))
        expected = {
            "schema_version": COLLECTION_SCHEMA_VERSION,
            "retrieval_backend": RETRIEVAL_BACKEND,
            "passage_template": PASSAGE_TEMPLATE,
            "query_template": QUERY_TEMPLATE,
            "vector_normalization": VECTOR_NORMALIZATION,
            "input_truncation": "provider_enabled_v1",
            "metric_type": METRIC_TYPE,
            "index_type": INDEX_TYPE,
            "hnsw_m": str(HNSW_M),
            "hnsw_ef_construction": str(HNSW_EF_CONSTRUCTION),
            "hnsw_search_ef": str(HNSW_SEARCH_EF),
            "version_writer_schema": VERSION_WRITER_SCHEMA,
            "owner_id": owner_id,
            "document_version_id": document_version_id,
            "online_entrypoint": ONLINE_ENTRYPOINT,
        }
        if document_id is not None:
            expected["document_id"] = document_id
        if source_sha256 is not None:
            expected["source_chunks_sha256"] = source_sha256
        if expected_count is not None:
            expected["chunk_count"] = str(expected_count)
        if verify_provider:
            identity = self.provider.identity()
            expected.update(
                {
                    "embedding_provider": identity.provider,
                    "embedding_model": identity.model,
                    "embedding_model_digest": identity.digest,
                }
            )
        for key, value in expected.items():
            if metadata.get(key) != value:
                raise MilvusIndexNotReadyError(
                    f"Milvus version collection {key} identity drift"
                )
        fields = description.get("fields")
        field_names = {
            field.get("name") for field in fields if isinstance(field, Mapping)
        } if isinstance(fields, list) else set()
        if field_names != EXPECTED_FIELDS:
            raise MilvusIndexNotReadyError("Milvus version collection schema drift")
        try:
            count = int(metadata["chunk_count"])
            dimension = int(metadata["embedding_dimension"])
        except (KeyError, ValueError) as exc:
            raise MilvusIndexNotReadyError(
                "Milvus version collection count or dimension is invalid"
            ) from exc
        if count < 1 or count > MAX_VERSION_ROWS or dimension < 1:
            raise MilvusIndexNotReadyError(
                "Milvus version collection count or dimension is invalid"
            )
        if not _CONTRACT_ID_PATTERN.fullmatch(metadata.get("document_id", "")):
            raise MilvusIndexNotReadyError(
                "Milvus version collection document_id is invalid"
            )
        for key in (
            "embedding_provider",
            "embedding_model",
            "embedding_model_digest",
        ):
            if not metadata.get(key):
                raise MilvusIndexNotReadyError(
                    f"Milvus version collection {key} is missing"
                )
        for key in ("source_chunks_sha256", "embeddings_sha256"):
            if not re.fullmatch(r"[a-f0-9]{64}", metadata.get(key, "")):
                raise MilvusIndexNotReadyError(
                    f"Milvus version collection {key} is invalid"
                )
        return metadata

    def _embed_chunks(
        self, chunks: Sequence[Mapping[str, Any]]
    ) -> dict[str, list[float]]:
        vectors = self.provider.embed([_passage_text(chunk) for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("embedding count does not match chunk count")
        normalized = [_float32_vector(vector) for vector in vectors]
        dimensions = {len(vector) for vector in normalized}
        if len(dimensions) != 1:
            raise ValueError("embedding dimensions are inconsistent")
        return {
            str(chunk["chunk_id"]): vector
            for chunk, vector in zip(chunks, normalized, strict=True)
        }

    def _upsert_rows(
        self,
        *,
        collection_name: str,
        chunks: Sequence[Mapping[str, Any]],
        vectors: Mapping[str, Sequence[float]],
    ) -> None:
        rows = [self._row(chunk=chunk, vector=vectors[str(chunk["chunk_id"])]) for chunk in chunks]
        result = self.transport.upsert(collection_name, rows)
        if result.get("upsert_count") not in (None, len(rows)):
            raise MilvusIndexNotReadyError("Milvus version upsert count is invalid")
        self._flush_and_load(collection_name)

    def _query_rows(self, collection_name: str) -> list[dict[str, Any]]:
        rows = self.transport.query(
            collection_name,
            filter_expression="",
            output_fields=sorted(EXPECTED_FIELDS),
            limit=MAX_VERSION_ROWS,
        )
        if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
            raise MilvusIndexNotReadyError("Milvus version query response is invalid")
        return [dict(row) for row in rows]

    def _verify_expected_rows(
        self,
        *,
        rows: Sequence[Mapping[str, Any]],
        chunks: Sequence[Mapping[str, Any]],
        metadata: Mapping[str, str],
        allow_missing: bool,
        expected_vectors: Mapping[str, Sequence[float]] | None = None,
    ) -> set[str]:
        expected = {str(chunk["chunk_id"]): dict(chunk) for chunk in chunks}
        seen: set[str] = set()
        actual_vectors: dict[str, Sequence[float]] = {}
        for row in rows:
            chunk_id, vector, payload = self._validated_row(
                row=row,
                metadata=metadata,
            )
            if chunk_id in seen or chunk_id not in expected:
                raise MilvusIndexNotReadyError(
                    "Milvus version collection contains foreign or duplicate rows"
                )
            seen.add(chunk_id)
            normalized_payload = dict(payload)
            normalized_payload["is_active"] = False
            if normalized_payload != expected[chunk_id]:
                raise MilvusIndexNotReadyError("Milvus version payload drift")
            if expected_vectors is not None and list(vector) != list(expected_vectors[chunk_id]):
                raise MilvusIndexNotReadyError("Milvus version embedding drift")
            actual_vectors[chunk_id] = vector
        if len(rows) > len(expected) or (not allow_missing and seen != set(expected)):
            raise MilvusIndexNotReadyError(
                "Milvus version collection row count does not match metadata"
            )
        if not allow_missing:
            fingerprint = _embeddings_fingerprint(actual_vectors)
            if fingerprint != metadata["embeddings_sha256"]:
                raise MilvusIndexNotReadyError("Milvus version embedding identity drift")
        return seen

    def _verify_lifecycle_rows(
        self,
        *,
        rows: Sequence[Mapping[str, Any]],
        metadata: Mapping[str, str],
        allow_incomplete: bool,
        expected_active: bool | None = None,
    ) -> None:
        expected_count = int(metadata["chunk_count"])
        if len(rows) > expected_count or (not allow_incomplete and len(rows) != expected_count):
            raise MilvusIndexNotReadyError(
                "Milvus version collection row count does not match metadata"
            )
        seen: set[str] = set()
        vectors: dict[str, Sequence[float]] = {}
        for row in rows:
            chunk_id, vector, payload = self._validated_row(row=row, metadata=metadata)
            if chunk_id in seen:
                raise MilvusIndexNotReadyError(
                    "Milvus version collection contains duplicate rows"
                )
            seen.add(chunk_id)
            if expected_active is not None and payload["is_active"] is not expected_active:
                raise MilvusIndexNotReadyError(
                    "Milvus version active-state verification failed"
                )
            vectors[chunk_id] = vector
        embeddings_match = (
            _embeddings_fingerprint(vectors) == metadata["embeddings_sha256"]
        )
        if not allow_incomplete and not embeddings_match:
            raise MilvusIndexNotReadyError("Milvus version embedding identity drift")

    @staticmethod
    def _validated_row(
        *, row: Mapping[str, Any], metadata: Mapping[str, str]
    ) -> tuple[str, list[float], dict[str, Any]]:
        if set(row) != EXPECTED_FIELDS:
            raise MilvusIndexNotReadyError("Milvus version row schema drift")
        chunk_id = row.get("chunk_id")
        payload = row.get("payload")
        vector = row.get("embedding")
        if (
            not isinstance(chunk_id, str)
            or not isinstance(payload, dict)
            or not isinstance(vector, list)
            or len(vector) != int(metadata["embedding_dimension"])
            or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector)
        ):
            raise MilvusIndexNotReadyError("Milvus version row payload is invalid")
        if (
            payload.get("chunk_id") != chunk_id
            or payload.get("tenant_id") != metadata["owner_id"]
            or payload.get("document_id") != metadata["document_id"]
            or payload.get("version_id") != metadata["document_version_id"]
            or row.get("document_id") != payload.get("document_id")
            or row.get("tenant_id") != payload.get("tenant_id")
            or row.get("visibility") != payload.get("visibility")
            or row.get("library_scope_ids") != payload.get("library_scope_ids")
            or not isinstance(row.get("is_active"), bool)
            or row.get("is_active") is not payload.get("is_active")
        ):
            raise MilvusIndexNotReadyError("Milvus version row identity drift")
        return chunk_id, [float(value) for value in vector], dict(payload)

    @staticmethod
    def _row(*, chunk: Mapping[str, Any], vector: Sequence[float]) -> JsonObject:
        return {
            "chunk_id": chunk["chunk_id"],
            "embedding": list(vector),
            "document_id": chunk["document_id"],
            "tenant_id": chunk["tenant_id"],
            "visibility": chunk["visibility"],
            "library_scope_ids": list(chunk["library_scope_ids"]),
            "is_active": chunk["is_active"],
            "payload": dict(chunk),
        }

    def _flush_and_load(self, collection_name: str) -> None:
        self.transport.flush(collection_name)
        self.transport.load_collection(collection_name)

    @staticmethod
    def _validate_identity(*, owner_id: str, document_version_id: str) -> None:
        if not _CONTRACT_ID_PATTERN.fullmatch(owner_id) or not _CONTRACT_ID_PATTERN.fullmatch(
            document_version_id
        ):
            raise ValueError("owner_id and document_version_id must be valid contract IDs")

    @staticmethod
    def _validate_stage(
        *,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        chunks: Sequence[Mapping[str, Any]],
    ) -> None:
        MilvusVersionIndexWriter._validate_identity(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        if (
            not _CONTRACT_ID_PATTERN.fullmatch(document_id)
            or not chunks
            or len(chunks) > MAX_VERSION_ROWS
        ):
            raise ValueError("document_id and Milvus version chunk count are invalid")
        _validate_chunks(chunks)
        for chunk in chunks:
            if (
                not _CONTRACT_ID_PATTERN.fullmatch(str(chunk["chunk_id"]))
                or chunk["tenant_id"] != owner_id
                or chunk["document_id"] != document_id
                or chunk.get("version_id") != document_version_id
                or chunk["is_active"] is not False
            ):
                raise ValueError(
                    "Milvus staged chunks must match identity and remain inactive"
                )
