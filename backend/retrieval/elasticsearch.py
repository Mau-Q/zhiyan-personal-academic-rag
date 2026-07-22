"""Remote Elasticsearch BM25 adapter for authorized ChunkRecordV1 retrieval."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from backend.retrieval.fixture import is_chunk_authorized, load_chunks, load_scope
from backend.retrieval.results import RankedChunk, chunks_only, validate_ranking
from backend.retrieval.sqlite_fts import chunks_fingerprint


JsonObject = dict[str, Any]
INDEX_SCHEMA_VERSION = "elasticsearch_bm25_index_v1"
RETRIEVAL_BACKEND = "elasticsearch_bm25"
INDEX_CONFIGURATION = {
    "schema_version": INDEX_SCHEMA_VERSION,
    "retrieval_backend": RETRIEVAL_BACKEND,
    "text_analyzer": "standard",
    "query_mode": "multi_match_or",
    "section_path_boost": "2.0",
}
_INDEX_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class ElasticsearchIndexNotReadyError(ValueError):
    """Raised when Elasticsearch cannot prove a matching usable index."""


class ElasticsearchTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
    ) -> JsonObject: ...


class UrllibElasticsearchTransport:
    """Small dependency-free JSON transport for a loopback Elasticsearch node."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:9200",
        timeout_seconds: float = 30.0,
    ):
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("Elasticsearch base_url must use http or https")
        if timeout_seconds <= 0:
            raise ValueError("Elasticsearch timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
    ) -> JsonObject:
        headers = {"Content-Type": content_type} if body is not None else {}
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except (OSError, urllib.error.URLError) as exc:
            raise ElasticsearchIndexNotReadyError(
                f"Elasticsearch request failed for {path}: {exc}"
            ) from exc
        if not raw:
            return {}
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ElasticsearchIndexNotReadyError(
                f"Elasticsearch returned invalid JSON for {path}"
            ) from exc
        if not isinstance(decoded, dict):
            raise ElasticsearchIndexNotReadyError(
                f"Elasticsearch returned a non-object response for {path}"
            )
        return decoded


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _validate_index_name(index_name: str) -> str:
    if not _INDEX_NAME_PATTERN.fullmatch(index_name):
        raise ValueError("Elasticsearch index name must be lowercase and URL-safe")
    return index_name


def _validate_chunks(chunks: Sequence[Mapping[str, Any]]) -> None:
    seen: set[str] = set()
    for position, chunk in enumerate(chunks):
        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError(f"chunk at position {position} has no valid chunk_id")
        if chunk_id in seen:
            raise ValueError(f"duplicate chunk_id: {chunk_id}")
        seen.add(chunk_id)
        required_strings = (
            "document_id",
            "version_id",
            "text",
            "section_path",
            "tenant_id",
            "visibility",
            "parse_version",
            "embedding_version",
        )
        if not all(isinstance(chunk.get(field), str) and chunk[field] for field in required_strings):
            raise ValueError(f"chunk {chunk_id} is missing required string fields")
        if not isinstance(chunk.get("library_scope_ids"), list) or not all(
            isinstance(value, str) and value for value in chunk["library_scope_ids"]
        ):
            raise ValueError(f"chunk {chunk_id} has invalid library_scope_ids")
        if not isinstance(chunk.get("is_active"), bool):
            raise ValueError(f"chunk {chunk_id} has invalid is_active")
        if (
            not isinstance(chunk.get("page_start"), int)
            or not isinstance(chunk.get("page_end"), int)
            or chunk["page_start"] < 1
            or chunk["page_start"] > chunk["page_end"]
        ):
            raise ValueError(f"chunk {chunk_id} has an invalid page range")


def _mapping(chunks: Sequence[Mapping[str, Any]]) -> JsonObject:
    metadata = {
        **INDEX_CONFIGURATION,
        "source_chunks_sha256": chunks_fingerprint(chunks),
        "chunk_count": str(len(chunks)),
    }
    return {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "_meta": metadata,
            "dynamic": "strict",
            "properties": {
                "chunk_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "version_id": {"type": "keyword"},
                "text": {"type": "text", "analyzer": "standard"},
                "section_path": {"type": "text", "analyzer": "standard"},
                "page_start": {"type": "integer"},
                "page_end": {"type": "integer"},
                "parent_chunk_id": {"type": "keyword"},
                "previous_chunk_id": {"type": "keyword"},
                "next_chunk_id": {"type": "keyword"},
                "tenant_id": {"type": "keyword"},
                "visibility": {"type": "keyword"},
                "library_scope_ids": {"type": "keyword"},
                "parse_version": {"type": "keyword"},
                "embedding_version": {"type": "keyword"},
                "is_active": {"type": "boolean"},
            },
        },
    }


def _string_list(scope: Mapping[str, Any], field: str) -> list[str] | None:
    value = scope.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return None
    return sorted(set(value))


def _authorization_filter(scope: Mapping[str, Any]) -> JsonObject:
    user_id = scope.get("user_id")
    tenant_id = scope.get("tenant_id")
    acl_version = scope.get("acl_version")
    include_public = scope.get("include_public")
    document_ids = _string_list(scope, "document_ids")
    library_ids = _string_list(scope, "library_ids")
    folder_ids = _string_list(scope, "folder_ids")
    if (
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
    ):
        return {"bool": {"must_not": [{"match_all": {}}]}}

    selectors: list[JsonObject] = []
    if document_ids:
        selectors.append({"terms": {"document_id": document_ids}})
    if library_ids:
        selectors.append({"terms": {"library_scope_ids": library_ids}})
    selection = {"bool": {"should": selectors, "minimum_should_match": 1}}
    has_resolvable_selector = bool(selectors)
    has_any_selector = has_resolvable_selector or bool(folder_ids)

    visibility_rules: list[JsonObject] = []
    if include_public and (not has_any_selector or has_resolvable_selector):
        public_rule: list[JsonObject] = [{"term": {"visibility": "public"}}]
        if has_any_selector:
            public_rule.append(selection)
        visibility_rules.append({"bool": {"filter": public_rule}})

    tenant_rule: list[JsonObject] = [
        {"term": {"visibility": "tenant"}},
        {"term": {"tenant_id": tenant_id}},
    ]
    if has_any_selector:
        if has_resolvable_selector:
            tenant_rule.append(selection)
        else:
            tenant_rule.append({"bool": {"must_not": [{"match_all": {}}]}})
    visibility_rules.append({"bool": {"filter": tenant_rule}})

    if has_resolvable_selector:
        visibility_rules.append(
            {
                "bool": {
                    "filter": [
                        {"term": {"visibility": "private"}},
                        {"term": {"tenant_id": tenant_id}},
                        selection,
                    ]
                }
            }
        )

    return {
        "bool": {
            "filter": [{"term": {"is_active": True}}],
            "should": visibility_rules,
            "minimum_should_match": 1,
        }
    }


class ElasticsearchBm25Index:
    """Build, verify, and query one identity-pinned Elasticsearch index."""

    def __init__(self, index_name: str, transport: ElasticsearchTransport):
        self.index_name = _validate_index_name(index_name)
        self.transport = transport
        self.path = f"/{urllib.parse.quote(self.index_name, safe='-_.')}"

    def build(self, chunks: Iterable[Mapping[str, Any]]) -> dict[str, str]:
        chunk_list = [dict(chunk) for chunk in chunks]
        if not chunk_list:
            raise ValueError("cannot build an empty Elasticsearch index")
        _validate_chunks(chunk_list)
        self.transport.request("PUT", self.path, body=_json_body(_mapping(chunk_list)))

        lines: list[str] = []
        for chunk in chunk_list:
            lines.append(
                json.dumps(
                    {"index": {"_index": self.index_name, "_id": chunk["chunk_id"]}},
                    separators=(",", ":"),
                )
            )
            lines.append(json.dumps(chunk, ensure_ascii=False, separators=(",", ":")))
        bulk_body = ("\n".join(lines) + "\n").encode("utf-8")
        bulk = self.transport.request(
            "POST", "/_bulk", body=bulk_body, content_type="application/x-ndjson"
        )
        if bulk.get("errors") is not False:
            raise ElasticsearchIndexNotReadyError("Elasticsearch bulk indexing failed")
        self.transport.request("POST", f"{self.path}/_refresh")
        return self.verify_source(chunk_list)

    def inspect(self) -> dict[str, str]:
        mapping = self.transport.request("GET", f"{self.path}/_mapping")
        index_payload = mapping.get(self.index_name)
        if not isinstance(index_payload, dict):
            raise ElasticsearchIndexNotReadyError("Elasticsearch index mapping is missing")
        mappings = index_payload.get("mappings")
        metadata = mappings.get("_meta") if isinstance(mappings, dict) else None
        if not isinstance(metadata, dict):
            raise ElasticsearchIndexNotReadyError("Elasticsearch index metadata is missing")
        normalized = {str(key): str(value) for key, value in metadata.items()}
        for key, expected in INDEX_CONFIGURATION.items():
            if normalized.get(key) != expected:
                raise ElasticsearchIndexNotReadyError(
                    f"Elasticsearch index {key} metadata is invalid"
                )
        return normalized

    def verify_source(self, chunks: Sequence[Mapping[str, Any]]) -> dict[str, str]:
        metadata = self.inspect()
        if metadata.get("source_chunks_sha256") != chunks_fingerprint(chunks):
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch index source fingerprint does not match chunks"
            )
        count = self.transport.request("GET", f"{self.path}/_count").get("count")
        if count != len(chunks) or metadata.get("chunk_count") != str(len(chunks)):
            raise ElasticsearchIndexNotReadyError(
                "Elasticsearch index chunk count does not match chunks"
            )
        return metadata

    def search(
        self,
        question: str,
        scope: Mapping[str, Any],
        *,
        top_k: int = 3,
        expected_chunks: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[RankedChunk]:
        if not question.strip():
            raise ValueError("question must not be blank")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if expected_chunks is not None:
            self.verify_source(expected_chunks)
        payload = {
            "size": top_k,
            "track_total_hits": False,
            "sort": ["_score", {"chunk_id": "asc"}],
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": question,
                                "fields": ["section_path^2", "text"],
                                "operator": "or",
                            }
                        }
                    ],
                    "filter": [_authorization_filter(scope)],
                }
            },
        }
        response = self.transport.request(
            "POST", f"{self.path}/_search", body=_json_body(payload)
        )
        hits = response.get("hits")
        hit_list = hits.get("hits") if isinstance(hits, dict) else None
        if not isinstance(hit_list, list):
            raise ElasticsearchIndexNotReadyError("Elasticsearch search response is invalid")
        scored: list[tuple[float, JsonObject]] = []
        for hit in hit_list:
            source = hit.get("_source") if isinstance(hit, dict) else None
            score = hit.get("_score") if isinstance(hit, dict) else None
            if not isinstance(source, dict) or not isinstance(score, (int, float)):
                raise ElasticsearchIndexNotReadyError(
                    "Elasticsearch search hit violates ranked candidate interface"
                )
            numeric_score = float(score)
            if not math.isfinite(numeric_score):
                raise ElasticsearchIndexNotReadyError(
                    "Elasticsearch search score must be finite"
                )
            if is_chunk_authorized(source, scope):
                scored.append((numeric_score, dict(source)))
        scored.sort(key=lambda item: (-item[0], str(item[1]["chunk_id"])))
        ranking = [
            RankedChunk(
                backend=RETRIEVAL_BACKEND,
                rank=rank,
                score=score,
                chunk=chunk,
            )
            for rank, (score, chunk) in enumerate(scored[:top_k], 1)
        ]
        validate_ranking(ranking, expected_backend=RETRIEVAL_BACKEND)
        return ranking

    def retrieve(
        self,
        question: str,
        scope: Mapping[str, Any],
        *,
        top_k: int = 3,
        expected_chunks: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[JsonObject]:
        return chunks_only(
            self.search(
                question,
                scope,
                top_k=top_k,
                expected_chunks=expected_chunks,
            )
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or query an Elasticsearch BM25 index")
    parser.add_argument("--url", default="http://127.0.0.1:9200")
    parser.add_argument("--index", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--chunks", required=True, type=Path)
    inspect = subparsers.add_parser("inspect")
    query = subparsers.add_parser("query")
    query.add_argument("--chunks", required=True, type=Path)
    query.add_argument("--scope", required=True, type=Path)
    query.add_argument("--question", required=True)
    query.add_argument("--top-k", type=int, default=3)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    index = ElasticsearchBm25Index(
        args.index, UrllibElasticsearchTransport(base_url=args.url)
    )
    try:
        if args.command == "build":
            payload: Any = index.build(load_chunks(args.chunks))
        elif args.command == "inspect":
            payload = index.inspect()
        else:
            chunks = load_chunks(args.chunks)
            payload = {
                "results": index.retrieve(
                    args.question,
                    load_scope(args.scope),
                    top_k=args.top_k,
                    expected_chunks=chunks,
                )
            }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Elasticsearch input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
