"""Deterministic, default-off query planning for two-document comparisons."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


VARIABLE_ID = "BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1"
CONFIG_SCHEMA_VERSION = "bilateral_comparison_query_decomposition_config_v1"
RESERVED_SWITCH = "PHASE3_COMPARISON_DECOMPOSITION_ENABLED"

_CONFIG_KEYS = {
    "schema_version",
    "variable_id",
    "default_enabled",
    "failure_policy",
    "comparison_markers",
    "transition_markers",
    "document_identities",
}
_IDENTITY_KEYS = {"document_id", "aliases"}
_BOOLEAN_VALUES = {
    "0": False,
    "1": True,
    "false": False,
    "true": True,
}
_CLAUSE_BOUNDARY = re.compile(r"[。！？!?；;]+")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class DocumentQueryIdentity:
    """Stable aliases bound to one already-authorized document identity."""

    document_id: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class BilateralComparisonConfig:
    default_enabled: bool
    failure_policy: Literal["FALLBACK_TO_ORIGINAL_QUERY"]
    comparison_markers: tuple[str, ...]
    transition_markers: tuple[str, ...]
    document_identities: tuple[DocumentQueryIdentity, ...]


@dataclass(frozen=True)
class ComparisonDecompositionObservation:
    status: Literal["APPLIED", "FALLBACK", "DISABLED"]
    failure_code: str | None
    route_count: int
    decomposition_latency_ms: float


@dataclass(frozen=True)
class RouteQueryPlan:
    """Exact route-to-query mapping; no sample or candidate identity is exposed."""

    status: Literal["APPLIED", "FALLBACK", "DISABLED"]
    queries: Mapping[str, str]
    failure_code: str | None


def load_bilateral_comparison_config(path: Path) -> BilateralComparisonConfig:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != _CONFIG_KEYS:
        raise ValueError("comparison decomposition config fields are invalid")
    if value["schema_version"] != CONFIG_SCHEMA_VERSION:
        raise ValueError("comparison decomposition config schema is unsupported")
    if value["variable_id"] != VARIABLE_ID:
        raise ValueError("comparison decomposition variable identity is invalid")
    if value["default_enabled"] is not False:
        raise ValueError("comparison decomposition must default to disabled")
    if value["failure_policy"] != "FALLBACK_TO_ORIGINAL_QUERY":
        raise ValueError("comparison decomposition failure policy is invalid")

    comparison_markers = _validated_markers(
        value["comparison_markers"],
        field="comparison_markers",
    )
    transition_markers = _validated_markers(
        value["transition_markers"],
        field="transition_markers",
    )
    raw_identities = value["document_identities"]
    if not isinstance(raw_identities, list) or len(raw_identities) < 2:
        raise ValueError("comparison decomposition document identities are invalid")
    identities: list[DocumentQueryIdentity] = []
    seen_ids: set[str] = set()
    normalized_alias_owner: dict[str, str] = {}
    for raw_identity in raw_identities:
        if not isinstance(raw_identity, dict) or set(raw_identity) != _IDENTITY_KEYS:
            raise ValueError("comparison decomposition document identity fields are invalid")
        document_id = raw_identity["document_id"]
        raw_aliases = raw_identity["aliases"]
        if (
            not isinstance(document_id, str)
            or not document_id
            or document_id in seen_ids
            or not isinstance(raw_aliases, list)
            or not raw_aliases
        ):
            raise ValueError("comparison decomposition document identity is invalid")
        aliases = _validated_markers(raw_aliases, field="aliases")
        all_aliases = tuple(dict.fromkeys((document_id, *aliases)))
        for alias in all_aliases:
            normalized = alias.casefold()
            owner = normalized_alias_owner.get(normalized)
            if owner is not None and owner != document_id:
                raise ValueError("comparison decomposition aliases are ambiguous")
            normalized_alias_owner[normalized] = document_id
        identities.append(
            DocumentQueryIdentity(document_id=document_id, aliases=all_aliases)
        )
        seen_ids.add(document_id)
    return BilateralComparisonConfig(
        default_enabled=False,
        failure_policy="FALLBACK_TO_ORIGINAL_QUERY",
        comparison_markers=comparison_markers,
        transition_markers=transition_markers,
        document_identities=tuple(identities),
    )


def switch_enabled(
    environment: Mapping[str, str],
    *,
    default: bool = False,
) -> bool:
    raw_value = environment.get(RESERVED_SWITCH)
    if raw_value is None:
        return default
    normalized = raw_value.strip().casefold()
    if normalized not in _BOOLEAN_VALUES:
        raise ValueError(f"{RESERVED_SWITCH} must be true, false, 1, or 0")
    return _BOOLEAN_VALUES[normalized]


def remap_document_identities(
    config: BilateralComparisonConfig,
    document_id_map: Mapping[str, str],
) -> BilateralComparisonConfig:
    """Bind frozen source aliases to owner-scoped runtime document identities."""

    configured_ids = {
        identity.document_id for identity in config.document_identities
    }
    if (
        set(document_id_map) != configured_ids
        or any(
            not isinstance(runtime_id, str) or not runtime_id
            for runtime_id in document_id_map.values()
        )
        or len(set(document_id_map.values())) != len(document_id_map)
    ):
        raise ValueError("comparison decomposition runtime identity map is invalid")
    remapped_identities = tuple(
        DocumentQueryIdentity(
            document_id=document_id_map[identity.document_id],
            aliases=tuple(
                dict.fromkeys(
                    (
                        document_id_map[identity.document_id],
                        *identity.aliases,
                    )
                )
            ),
        )
        for identity in config.document_identities
    )
    alias_owner: dict[str, str] = {}
    for identity in remapped_identities:
        for alias in identity.aliases:
            normalized = alias.casefold()
            owner = alias_owner.get(normalized)
            if owner is not None and owner != identity.document_id:
                raise ValueError(
                    "comparison decomposition runtime identity map is ambiguous"
                )
            alias_owner[normalized] = identity.document_id
    return BilateralComparisonConfig(
        default_enabled=config.default_enabled,
        failure_policy=config.failure_policy,
        comparison_markers=config.comparison_markers,
        transition_markers=config.transition_markers,
        document_identities=remapped_identities,
    )


class BilateralComparisonQueryDecomposer:
    """Plan one document-side query per exactly two authorized routes."""

    def __init__(
        self,
        *,
        config: BilateralComparisonConfig,
        enabled: bool = False,
        observer: Callable[[ComparisonDecompositionObservation], None] | None = None,
    ) -> None:
        self.config = config
        self.enabled = enabled
        self.observer = observer
        self._identity_by_id = {
            identity.document_id: identity for identity in config.document_identities
        }

    def plan(
        self,
        question: str,
        *,
        document_ids: Sequence[str],
    ) -> RouteQueryPlan:
        started = time.perf_counter()
        route_ids = tuple(document_ids)
        if not self.enabled:
            return self._finish(
                started=started,
                route_ids=route_ids,
                status="DISABLED",
                failure_code="SWITCH_DISABLED",
                queries={document_id: question for document_id in route_ids},
            )
        if len(route_ids) != 2 or len(set(route_ids)) != 2:
            return self._fallback(
                started,
                route_ids,
                question,
                "ROUTE_COUNT_NOT_TWO",
            )
        if not question.strip():
            return self._fallback(started, route_ids, question, "QUESTION_BLANK")
        identities = tuple(
            self._identity_by_id.get(document_id) for document_id in route_ids
        )
        if any(identity is None for identity in identities):
            return self._fallback(
                started,
                route_ids,
                question,
                "DOCUMENT_IDENTITY_UNAVAILABLE",
            )
        if not _contains_marker(question, self.config.comparison_markers):
            return self._fallback(
                started,
                route_ids,
                question,
                "COMPARISON_NOT_PROVEN",
            )

        typed_identities = tuple(
            identity for identity in identities if identity is not None
        )
        queries = self._decompose(question, typed_identities)
        if queries is None or set(queries) != set(route_ids) or any(
            not query.strip() for query in queries.values()
        ):
            return self._fallback(
                started,
                route_ids,
                question,
                "BILATERAL_DECOMPOSITION_UNPROVEN",
            )
        return self._finish(
            started=started,
            route_ids=route_ids,
            status="APPLIED",
            failure_code=None,
            queries=queries,
        )

    def _decompose(
        self,
        question: str,
        identities: tuple[DocumentQueryIdentity, DocumentQueryIdentity],
    ) -> dict[str, str] | None:
        clauses = [
            clause.strip(" ，,")
            for clause in _CLAUSE_BOUNDARY.split(question)
            if clause.strip(" ，,")
        ]
        if not clauses:
            return None

        pieces: dict[str, list[str]] = {
            identity.document_id: [] for identity in identities
        }
        unanchored: list[tuple[int, str]] = []
        anchored_clause_indexes: dict[str, list[int]] = {
            identity.document_id: [] for identity in identities
        }
        for index, clause in enumerate(clauses):
            mentions = [
                identity
                for identity in identities
                if _first_alias_span(clause, identity.aliases) is not None
            ]
            if len(mentions) == 2:
                bilateral = _split_bilateral_clause(clause, identities)
                if bilateral is None:
                    return None
                for document_id, text in bilateral.items():
                    pieces[document_id].append(text)
                    anchored_clause_indexes[document_id].append(index)
            elif len(mentions) == 1:
                identity = mentions[0]
                pieces[identity.document_id].append(clause)
                anchored_clause_indexes[identity.document_id].append(index)
            else:
                unanchored.append((index, clause))

        anchored_documents = [
            document_id
            for document_id, indexes in anchored_clause_indexes.items()
            if indexes
        ]
        if len(anchored_documents) == 1:
            anchored_id = anchored_documents[0]
            other_id = next(
                identity.document_id
                for identity in identities
                if identity.document_id != anchored_id
            )
            first_anchor = min(anchored_clause_indexes[anchored_id])
            leading = [
                clause for index, clause in unanchored if index < first_anchor
            ]
            transition_anchor = _first_marker_anchor(
                question,
                self.config.transition_markers,
            )
            if (
                not leading
                or transition_anchor is None
                or transition_anchor
                >= _first_document_anchor(
                    question,
                    self._identity_by_id[anchored_id].aliases,
                )
            ):
                return None
            pieces[other_id].extend(leading)
            unanchored = [
                (index, clause)
                for index, clause in unanchored
                if index >= first_anchor
            ]
        elif len(anchored_documents) != 2:
            return None

        for _, clause in unanchored:
            for identity in identities:
                pieces[identity.document_id].append(clause)

        queries = {
            document_id: _normalize_query(" ".join(route_pieces))
            for document_id, route_pieces in pieces.items()
        }
        if any(not query for query in queries.values()):
            return None
        return queries

    def _fallback(
        self,
        started: float,
        route_ids: tuple[str, ...],
        question: str,
        failure_code: str,
    ) -> RouteQueryPlan:
        return self._finish(
            started=started,
            route_ids=route_ids,
            status="FALLBACK",
            failure_code=failure_code,
            queries={document_id: question for document_id in route_ids},
        )

    def _finish(
        self,
        *,
        started: float,
        route_ids: tuple[str, ...],
        status: Literal["APPLIED", "FALLBACK", "DISABLED"],
        failure_code: str | None,
        queries: Mapping[str, str],
    ) -> RouteQueryPlan:
        observation = ComparisonDecompositionObservation(
            status=status,
            failure_code=failure_code,
            route_count=len(route_ids),
            decomposition_latency_ms=(time.perf_counter() - started) * 1000,
        )
        if self.observer is not None:
            self.observer(observation)
        return RouteQueryPlan(
            status=status,
            queries=dict(queries),
            failure_code=failure_code,
        )


def _validated_markers(value: Any, *, field: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"comparison decomposition {field} are invalid")
    normalized = tuple(item.strip() for item in value)
    if len(set(item.casefold() for item in normalized)) != len(normalized):
        raise ValueError(f"comparison decomposition {field} are duplicated")
    return normalized


def _contains_marker(text: str, markers: Sequence[str]) -> bool:
    folded = text.casefold()
    return any(marker.casefold() in folded for marker in markers)


def _first_marker_anchor(text: str, markers: Sequence[str]) -> int | None:
    folded = text.casefold()
    anchors = [
        anchor
        for marker in markers
        if (anchor := folded.find(marker.casefold())) >= 0
    ]
    return min(anchors, default=None)


def _first_document_anchor(text: str, aliases: Sequence[str]) -> int:
    span = _first_alias_span(text, aliases)
    return len(text) if span is None else span[0]


def _first_alias_span(
    text: str,
    aliases: Sequence[str],
) -> tuple[int, int] | None:
    folded = text.casefold()
    spans = [
        (start, start + len(alias))
        for alias in aliases
        if (start := folded.find(alias.casefold())) >= 0
    ]
    return min(spans, default=None)


def _split_bilateral_clause(
    clause: str,
    identities: tuple[DocumentQueryIdentity, DocumentQueryIdentity],
) -> dict[str, str] | None:
    spans = [
        (identity, _first_alias_span(clause, identity.aliases))
        for identity in identities
    ]
    if any(span is None for _, span in spans):
        return None
    ordered = sorted(
        ((identity, span) for identity, span in spans if span is not None),
        key=lambda item: item[1][0],
    )
    (left_identity, left_span), (right_identity, right_span) = ordered
    between = clause[left_span[1] : right_span[0]]
    connector = _last_connector_span(between)
    if connector is None:
        return None
    left_end = left_span[1] + connector[0]
    right_tail_start = _shared_tail_start(clause, right_span[1])
    if right_tail_start is None:
        return None

    common_prefix = clause[: left_span[0]].strip(" ，,")
    common_tail = clause[right_tail_start:].strip(" ，,")
    left_side = clause[left_span[0] : left_end].strip(" ，,")
    right_side = clause[right_span[0] : right_tail_start].strip(" ，,")
    if not left_side or not right_side or not common_tail:
        return None
    common = " ".join(part for part in (common_prefix, common_tail) if part)
    return {
        left_identity.document_id: _normalize_query(f"{left_side} {common}"),
        right_identity.document_id: _normalize_query(f"{right_side} {common}"),
    }


def _last_connector_span(text: str) -> tuple[int, int] | None:
    matches = list(re.finditer(r"(?:与|和|以及|及|vs\.?|versus)", text, re.IGNORECASE))
    if not matches:
        return None
    match = matches[-1]
    return match.start(), match.end()


def _shared_tail_start(text: str, after: int) -> int | None:
    tail = text[after:]
    matches = [
        match
        for pattern in (
            r"在",
            r"有何",
            r"如何",
            r"分别",
            r"之间",
        )
        if (match := re.search(pattern, tail)) is not None
    ]
    if not matches:
        return None
    return after + min(match.start() for match in matches)


def _normalize_query(value: str) -> str:
    return _SPACE.sub(" ", value).strip(" ，,")
