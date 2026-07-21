"""Fail-closed deterministic retrieval over the checked-in ChunkRecordV1 fixture."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


JsonObject = dict[str, Any]

_TOKEN_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "before",
    "does",
    "for",
    "how",
    "in",
    "is",
    "of",
    "the",
    "to",
    "what",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_chunks(path: Path) -> list[JsonObject]:
    """Load a list of ChunkRecordV1-like objects from JSON."""

    payload = _load_json(path)
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError("chunk fixture must be a JSON array of objects")
    return payload


def load_scope(path: Path) -> JsonObject:
    """Load one AuthorizedScopeV1-like object from JSON."""

    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("authorized scope fixture must be a JSON object")
    return payload


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str) and item}


def _has_required_chunk_fields(chunk: Mapping[str, Any]) -> bool:
    string_fields = (
        "chunk_id",
        "document_id",
        "version_id",
        "text",
        "section_path",
        "tenant_id",
        "visibility",
    )
    return (
        all(isinstance(chunk.get(field), str) and chunk.get(field) for field in string_fields)
        and isinstance(chunk.get("page_start"), int)
        and isinstance(chunk.get("page_end"), int)
        and isinstance(chunk.get("library_scope_ids"), list)
    )


def _has_required_scope_fields(scope: Mapping[str, Any]) -> bool:
    return (
        all(
            isinstance(scope.get(field), str) and scope.get(field)
            for field in ("user_id", "tenant_id", "acl_version")
        )
        and all(
            isinstance(scope.get(field), list)
            for field in ("library_ids", "folder_ids", "document_ids")
        )
        and isinstance(scope.get("include_public"), bool)
    )


def _matches_selected_scope(chunk: Mapping[str, Any], scope: Mapping[str, Any]) -> bool:
    document_ids = _string_set(scope.get("document_ids"))
    library_ids = _string_set(scope.get("library_ids"))
    folder_ids = _string_set(scope.get("folder_ids"))
    chunk_libraries = _string_set(chunk.get("library_scope_ids"))

    selected_by_document = chunk.get("document_id") in document_ids
    selected_by_library = bool(chunk_libraries & library_ids)

    if document_ids or library_ids:
        return selected_by_document or selected_by_library
    if folder_ids:
        # ChunkRecordV1 has no folder field. The real authorization layer must
        # expand folders to document IDs before this consumer sees the scope.
        return False
    return False


def is_chunk_authorized(chunk: Mapping[str, Any], scope: Mapping[str, Any]) -> bool:
    """Apply AuthorizedScopeV1 to one chunk without widening the scope."""

    if (
        not _has_required_chunk_fields(chunk)
        or not _has_required_scope_fields(scope)
        or chunk.get("is_active") is not True
    ):
        return False

    visibility = chunk.get("visibility")
    same_tenant = chunk.get("tenant_id") == scope["tenant_id"]
    selected = _matches_selected_scope(chunk, scope)
    has_selectors = bool(
        _string_set(scope.get("document_ids"))
        or _string_set(scope.get("library_ids"))
        or _string_set(scope.get("folder_ids"))
    )

    if visibility == "public":
        return scope.get("include_public") is True and (not has_selectors or selected)
    if visibility == "tenant":
        return same_tenant and (not has_selectors or selected)
    if visibility == "private":
        return same_tenant and selected
    return False


def filter_authorized_chunks(
    chunks: Iterable[Mapping[str, Any]], scope: Mapping[str, Any]
) -> list[JsonObject]:
    """Return copies of active chunks inside the server-calculated scope."""

    return [dict(chunk) for chunk in chunks if is_chunk_authorized(chunk, scope)]


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in (match.group(0).lower() for match in _TOKEN_PATTERN.finditer(value))
        if token not in _STOP_WORDS
    }


def retrieve_chunks(
    question: str,
    chunks: Iterable[Mapping[str, Any]],
    scope: Mapping[str, Any],
    *,
    top_k: int = 3,
) -> list[JsonObject]:
    """Retrieve authorized chunks by deterministic lexical token overlap."""

    if not question.strip():
        raise ValueError("question must not be blank")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    query_tokens = _tokens(question)
    if not query_tokens:
        return []

    scored: list[tuple[int, str, JsonObject]] = []
    for chunk in filter_authorized_chunks(chunks, scope):
        searchable = f"{chunk.get('section_path', '')} {chunk.get('text', '')}"
        score = len(query_tokens & _tokens(searchable))
        if score > 0:
            scored.append((score, str(chunk.get("chunk_id", "")), chunk))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [chunk for _, _, chunk in scored[:top_k]]
