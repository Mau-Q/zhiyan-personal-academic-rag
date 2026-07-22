"""Version-scoped Elasticsearch writer for hidden lifecycle-managed indexes."""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any, Protocol

from backend.ingestion.index_lifecycle import IndexBackend, IndexWriteReceipt
from backend.retrieval.elasticsearch import (
    INDEX_CONFIGURATION,
    ElasticsearchIndexNotReadyError,
    JsonObject,
    _json_body,
    _mapping,
    _validate_chunks,
    _validate_index_name,
)
from backend.retrieval.sqlite_fts import chunks_fingerprint


VERSION_WRITER_SCHEMA = "elasticsearch_version_writer_v1"
MAX_INDEX_NAME_BYTES = 255
_CONTRACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_EXPECTED_PROPERTY_TYPES = {
    "chunk_id": "keyword",
    "document_id": "keyword",
    "version_id": "keyword",
    "text": "text",
    "section_path": "text",
    "tenant_id": "keyword",
    "visibility": "keyword",
    "library_scope_ids": "keyword",
    "is_active": "boolean",
}


class ElasticsearchVersionTransport(Protocol):
    def index_exists(self, index_name: str) -> bool: ...

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
    ) -> JsonObject: ...


def _identity_digest(owner_id: str, document_version_id: str) -> str:
    payload = f"{owner_id}\0{document_version_id}".encode("utf-8")
    return sha256(payload).hexdigest()[:24]


class ElasticsearchVersionIndexWriter:
    """Write one owner/version to a deterministic physical index with no online alias."""

    backend = IndexBackend.ELASTICSEARCH

    def __init__(
        self,
        *,
        index_prefix: str,
        transport: ElasticsearchVersionTransport,
    ) -> None:
        self.index_prefix = _validate_index_name(index_prefix)
        candidate = f"{self.index_prefix}--v-{'0' * 24}"
        if len(candidate.encode("utf-8")) > MAX_INDEX_NAME_BYTES:
            raise ValueError("Elasticsearch version index prefix is too long")
        self.transport = transport

    def physical_index_name(self, *, owner_id: str, document_version_id: str) -> str:
        self._validate_identity(owner_id=owner_id, document_version_id=document_version_id)
        return f"{self.index_prefix}--v-{_identity_digest(owner_id, document_version_id)}"

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
        index_name = self.physical_index_name(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        if not self.transport.index_exists(index_name):
            mapping = _mapping(chunk_list)
            mapping["settings"]["index.hidden"] = True
            mapping["mappings"]["_meta"].update(
                {
                    "version_writer_schema": VERSION_WRITER_SCHEMA,
                    "owner_id": owner_id,
                    "document_id": document_id,
                    "document_version_id": document_version_id,
                    "online_entrypoint": "HIDDEN_PHYSICAL_INDEX",
                }
            )
            try:
                self.transport.request(
                    "PUT",
                    self._path(index_name),
                    body=_json_body(mapping),
                )
            except ElasticsearchIndexNotReadyError:
                if not self.transport.index_exists(index_name):
                    raise

        metadata = self._inspect_identity(
            index_name=index_name,
            owner_id=owner_id,
            document_id=document_id,
            document_version_id=document_version_id,
            source_sha256=source_sha256,
            expected_count=len(chunk_list),
        )
        current_count = self._verify_owned_count(
            index_name=index_name,
            owner_id=owner_id,
            document_id=document_id,
            document_version_id=document_version_id,
            expected_count=len(chunk_list),
            allow_incomplete=True,
        )
        if current_count < len(chunk_list):
            self._verify_source_payloads(
                index_name=index_name,
                chunks=chunk_list,
                allow_missing=True,
            )
            self._bulk_index(index_name=index_name, chunks=chunk_list)
            self._verify_owned_count(
                index_name=index_name,
                owner_id=owner_id,
                document_id=document_id,
                document_version_id=document_version_id,
                expected_count=len(chunk_list),
                allow_incomplete=False,
            )
        self._verify_source_payloads(index_name=index_name, chunks=chunk_list)
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
        index_name = self.physical_index_name(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        if not self.transport.index_exists(index_name):
            return
        self._set_active(
            owner_id=owner_id,
            document_version_id=document_version_id,
            is_active=False,
        )

    def delete_version(self, *, owner_id: str, document_version_id: str) -> bool:
        index_name = self.physical_index_name(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        if not self.transport.index_exists(index_name):
            return False
        self._inspect_identity(
            index_name=index_name,
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        result = self.transport.request("DELETE", self._path(index_name))
        if result.get("acknowledged") is not True:
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index deletion was not acknowledged"
            )
        if self.transport.index_exists(index_name):
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index still exists after deletion"
            )
        return True

    def _set_active(
        self,
        *,
        owner_id: str,
        document_version_id: str,
        is_active: bool,
    ) -> None:
        index_name = self.physical_index_name(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        if not self.transport.index_exists(index_name):
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index does not exist"
            )
        metadata = self._inspect_identity(
            index_name=index_name,
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        expected_count = int(metadata["chunk_count"])
        payload = {
            "query": self._identity_query(
                owner_id=owner_id,
                document_version_id=document_version_id,
            ),
            "script": {
                "lang": "painless",
                "source": "ctx._source.is_active = params.is_active",
                "params": {"is_active": is_active},
            },
        }
        response = self.transport.request(
            "POST",
            f"{self._path(index_name)}/_update_by_query?refresh=true",
            body=_json_body(payload),
        )
        if response.get("failures") not in (None, []):
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version activation update failed"
            )
        matching = self._count(
            index_name=index_name,
            query={
                "bool": {
                    "filter": [
                        self._identity_query(
                            owner_id=owner_id,
                            document_version_id=document_version_id,
                        ),
                        {"term": {"is_active": is_active}},
                    ]
                }
            },
        )
        if matching != expected_count:
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version active-state count does not match metadata"
            )

    def _inspect_identity(
        self,
        *,
        index_name: str,
        owner_id: str,
        document_version_id: str,
        document_id: str | None = None,
        source_sha256: str | None = None,
        expected_count: int | None = None,
    ) -> dict[str, str]:
        mapping = self.transport.request("GET", f"{self._path(index_name)}/_mapping")
        payload = mapping.get(index_name)
        mappings = payload.get("mappings") if isinstance(payload, dict) else None
        metadata = mappings.get("_meta") if isinstance(mappings, dict) else None
        if not isinstance(metadata, dict):
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index metadata is missing"
            )
        settings_response = self.transport.request(
            "GET",
            f"{self._path(index_name)}/_settings/index.hidden",
        )
        settings_payload = settings_response.get(index_name)
        settings = (
            settings_payload.get("settings")
            if isinstance(settings_payload, dict)
            else None
        )
        index_settings = settings.get("index") if isinstance(settings, dict) else None
        hidden = index_settings.get("hidden") if isinstance(index_settings, dict) else None
        if hidden not in (True, "true"):
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index hidden setting drift"
            )
        normalized = {str(key): str(value) for key, value in metadata.items()}
        expected = {
            **INDEX_CONFIGURATION,
            "version_writer_schema": VERSION_WRITER_SCHEMA,
            "owner_id": owner_id,
            "document_version_id": document_version_id,
            "online_entrypoint": "HIDDEN_PHYSICAL_INDEX",
        }
        if document_id is not None:
            expected["document_id"] = document_id
        if source_sha256 is not None:
            expected["source_chunks_sha256"] = source_sha256
        if expected_count is not None:
            expected["chunk_count"] = str(expected_count)
        for key, value in expected.items():
            if normalized.get(key) != value:
                raise ElasticsearchIndexNotReadyError(
                    f"Elasticsearch version index {key} identity drift"
                )
        properties = mappings.get("properties")
        if mappings.get("dynamic") != "strict" or not isinstance(properties, dict):
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index strict mapping drift"
            )
        for field, expected_type in _EXPECTED_PROPERTY_TYPES.items():
            definition = properties.get(field)
            if not isinstance(definition, dict) or definition.get("type") != expected_type:
                raise ElasticsearchIndexNotReadyError(
                    f"Elasticsearch version index {field} mapping drift"
                )
        try:
            count = int(normalized["chunk_count"])
        except (KeyError, ValueError) as exc:
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index chunk_count is invalid"
            ) from exc
        source_identity = normalized.get("source_chunks_sha256", "")
        if count < 1 or not re.fullmatch(r"[a-f0-9]{64}", source_identity):
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index source identity is invalid"
            )
        return normalized

    def _verify_owned_count(
        self,
        *,
        index_name: str,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        expected_count: int,
        allow_incomplete: bool,
    ) -> int:
        total = self._count(index_name=index_name)
        owned = self._count(
            index_name=index_name,
            query={
                "bool": {
                    "filter": [
                        {"term": {"tenant_id": owner_id}},
                        {"term": {"document_id": document_id}},
                        {"term": {"version_id": document_version_id}},
                    ]
                }
            },
        )
        if total != owned or total > expected_count:
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index contains foreign or excess chunks"
            )
        if not allow_incomplete and total != expected_count:
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index chunk count does not match metadata"
            )
        return total

    def _bulk_index(
        self, *, index_name: str, chunks: Sequence[Mapping[str, Any]]
    ) -> None:
        lines: list[str] = []
        for chunk in chunks:
            lines.append(
                json.dumps(
                    {"index": {"_index": index_name, "_id": chunk["chunk_id"]}},
                    separators=(",", ":"),
                )
            )
            lines.append(json.dumps(chunk, ensure_ascii=False, separators=(",", ":")))
        response = self.transport.request(
            "POST",
            "/_bulk",
            body=("\n".join(lines) + "\n").encode("utf-8"),
            content_type="application/x-ndjson",
        )
        if response.get("errors") is not False:
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version bulk indexing failed"
            )
        self.transport.request("POST", f"{self._path(index_name)}/_refresh")

    def _verify_source_payloads(
        self,
        *,
        index_name: str,
        chunks: Sequence[Mapping[str, Any]],
        allow_missing: bool = False,
    ) -> None:
        expected = {str(chunk["chunk_id"]): dict(chunk) for chunk in chunks}
        response = self.transport.request(
            "POST",
            f"{self._path(index_name)}/_mget",
            body=_json_body({"ids": list(expected)}),
        )
        documents = response.get("docs")
        if not isinstance(documents, list) or len(documents) != len(expected):
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index source payload coverage drift"
            )
        seen: set[str] = set()
        for document in documents:
            source = document.get("_source") if isinstance(document, dict) else None
            chunk_id = document.get("_id") if isinstance(document, dict) else None
            found = document.get("found") if isinstance(document, dict) else None
            if (
                not isinstance(chunk_id, str)
                or chunk_id in seen
                or chunk_id not in expected
            ):
                raise ElasticsearchIndexNotReadyError(
                    "Elasticsearch version index source payload identity drift"
                )
            seen.add(chunk_id)
            if found is False and allow_missing:
                continue
            if found is not True or not isinstance(source, dict):
                raise ElasticsearchIndexNotReadyError(
                    "Elasticsearch version index source payload identity drift"
                )
            normalized = dict(source)
            if not isinstance(normalized.get("is_active"), bool):
                raise ElasticsearchIndexNotReadyError(
                    "Elasticsearch version index active state is invalid"
                )
            normalized["is_active"] = False
            if normalized != expected[chunk_id]:
                raise ElasticsearchIndexNotReadyError(
                    "Elasticsearch version index source payload drift"
                )

    def _count(self, *, index_name: str, query: Mapping[str, Any] | None = None) -> int:
        response = self.transport.request(
            "GET" if query is None else "POST",
            f"{self._path(index_name)}/_count",
            body=None if query is None else _json_body({"query": query}),
        )
        count = response.get("count")
        if not isinstance(count, int) or count < 0:
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch version index returned an invalid count"
            )
        return count

    @staticmethod
    def _identity_query(*, owner_id: str, document_version_id: str) -> dict[str, Any]:
        return {
            "bool": {
                "filter": [
                    {"term": {"tenant_id": owner_id}},
                    {"term": {"version_id": document_version_id}},
                ]
            }
        }

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
        ElasticsearchVersionIndexWriter._validate_identity(
            owner_id=owner_id,
            document_version_id=document_version_id,
        )
        if not _CONTRACT_ID_PATTERN.fullmatch(document_id) or not chunks:
            raise ValueError("document_id must be valid and chunks must not be empty")
        _validate_chunks(chunks)
        for chunk in chunks:
            if (
                chunk["tenant_id"] != owner_id
                or chunk["document_id"] != document_id
                or chunk["version_id"] != document_version_id
                or chunk["is_active"] is not False
            ):
                raise ValueError(
                    "Elasticsearch staged chunks must match identity and remain inactive"
                )

    @staticmethod
    def _path(index_name: str) -> str:
        return f"/{urllib.parse.quote(index_name, safe='-_.')}"
