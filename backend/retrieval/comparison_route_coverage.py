"""Default-off final Top-3 route coverage for bilateral comparisons."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from backend.retrieval.results import RankedChunk


VARIABLE_ID = "BILATERAL_COMPARISON_ROUTE_COVERAGE_TOP3_V1"
CONFIG_SCHEMA_VERSION = "bilateral_comparison_route_coverage_top3_config_v1"
RESERVED_SWITCH = "PHASE3_COMPARISON_ROUTE_COVERAGE_ENABLED"

_CONFIG_KEYS = {
    "schema_version",
    "variable_id",
    "default_enabled",
    "failure_policy",
    "eligible_route_count",
    "final_top_k",
    "minimum_per_route",
    "comparison_markers",
}
_BOOLEAN_VALUES = {
    "0": False,
    "1": True,
    "false": False,
    "true": True,
}


@dataclass(frozen=True)
class BilateralRouteCoverageConfig:
    default_enabled: bool
    failure_policy: Literal["FALLBACK_TO_ORIGINAL_RRF_TOP3"]
    eligible_route_count: int
    final_top_k: int
    minimum_per_route: int
    comparison_markers: tuple[str, ...]


@dataclass(frozen=True)
class RouteCoverageObservation:
    status: Literal["APPLIED", "FALLBACK", "DISABLED"]
    failure_code: str | None
    route_count: int
    candidate_count: int
    selection_changed: bool
    selection_latency_ms: float


@dataclass(frozen=True)
class RouteCoveragePlan:
    status: Literal["APPLIED", "FALLBACK", "DISABLED"]
    selected_chunk_ids: tuple[str, ...]
    failure_code: str | None


def load_bilateral_route_coverage_config(
    path: Path,
) -> BilateralRouteCoverageConfig:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != _CONFIG_KEYS:
        raise ValueError("comparison route coverage config fields are invalid")
    if value["schema_version"] != CONFIG_SCHEMA_VERSION:
        raise ValueError("comparison route coverage config schema is unsupported")
    if value["variable_id"] != VARIABLE_ID:
        raise ValueError("comparison route coverage variable identity is invalid")
    if value["default_enabled"] is not False:
        raise ValueError("comparison route coverage must default to disabled")
    if value["failure_policy"] != "FALLBACK_TO_ORIGINAL_RRF_TOP3":
        raise ValueError("comparison route coverage failure policy is invalid")
    if (
        value["eligible_route_count"] != 2
        or value["final_top_k"] != 3
        or value["minimum_per_route"] != 1
    ):
        raise ValueError("comparison route coverage bounds are invalid")
    markers = value["comparison_markers"]
    if (
        not isinstance(markers, list)
        or not markers
        or any(not isinstance(marker, str) or not marker.strip() for marker in markers)
    ):
        raise ValueError("comparison route coverage markers are invalid")
    normalized_markers = tuple(marker.strip() for marker in markers)
    if len({marker.casefold() for marker in normalized_markers}) != len(
        normalized_markers
    ):
        raise ValueError("comparison route coverage markers are duplicated")
    return BilateralRouteCoverageConfig(
        default_enabled=False,
        failure_policy="FALLBACK_TO_ORIGINAL_RRF_TOP3",
        eligible_route_count=2,
        final_top_k=3,
        minimum_per_route=1,
        comparison_markers=normalized_markers,
    )


def route_coverage_switch_enabled(
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


class BilateralComparisonRouteCoverageSelector:
    """Select an authorized bilateral Top-3 without changing RRF scores."""

    def __init__(
        self,
        *,
        config: BilateralRouteCoverageConfig,
        enabled: bool = False,
        observer: Callable[[RouteCoverageObservation], None] | None = None,
    ) -> None:
        self.config = config
        self.enabled = enabled
        self.observer = observer

    def plan(
        self,
        question: str,
        candidates: Sequence[RankedChunk],
        *,
        document_ids: Sequence[str],
        top_k: int,
    ) -> RouteCoveragePlan:
        started = time.perf_counter()
        route_ids = tuple(document_ids)
        original_ids = tuple(
            str(candidate.chunk["chunk_id"]) for candidate in candidates[:top_k]
        )
        if not self.enabled:
            return self._finish(
                started=started,
                route_ids=route_ids,
                candidate_count=len(candidates),
                original_ids=original_ids,
                selected_ids=original_ids,
                status="DISABLED",
                failure_code="SWITCH_DISABLED",
            )
        if (
            len(route_ids) != self.config.eligible_route_count
            or len(set(route_ids)) != len(route_ids)
        ):
            return self._fallback(
                started,
                route_ids,
                candidates,
                original_ids,
                "ROUTE_COUNT_NOT_TWO",
            )
        if top_k != self.config.final_top_k:
            return self._fallback(
                started,
                route_ids,
                candidates,
                original_ids,
                "FINAL_TOP_K_NOT_THREE",
            )
        if not question.strip() or not self._has_comparison_marker(question):
            return self._fallback(
                started,
                route_ids,
                candidates,
                original_ids,
                "COMPARISON_NOT_PROVEN",
            )
        if len(candidates) < top_k:
            return self._fallback(
                started,
                route_ids,
                candidates,
                original_ids,
                "CANDIDATE_COUNT_INSUFFICIENT",
            )

        candidate_route_ids = {
            str(candidate.chunk["document_id"]) for candidate in candidates
        }
        if not candidate_route_ids.issubset(set(route_ids)):
            return self._fallback(
                started,
                route_ids,
                candidates,
                original_ids,
                "CANDIDATE_ROUTE_OUTSIDE_SCOPE",
            )
        first_by_route: dict[str, str] = {}
        for candidate in candidates:
            document_id = str(candidate.chunk["document_id"])
            first_by_route.setdefault(
                document_id,
                str(candidate.chunk["chunk_id"]),
            )
        if set(first_by_route) != set(route_ids):
            return self._fallback(
                started,
                route_ids,
                candidates,
                original_ids,
                "ROUTE_CANDIDATE_UNAVAILABLE",
            )

        selected = set(first_by_route.values())
        for candidate in candidates:
            if len(selected) >= top_k:
                break
            selected.add(str(candidate.chunk["chunk_id"]))
        selected_ids = tuple(
            str(candidate.chunk["chunk_id"])
            for candidate in candidates
            if str(candidate.chunk["chunk_id"]) in selected
        )
        if len(selected_ids) != top_k:
            return self._fallback(
                started,
                route_ids,
                candidates,
                original_ids,
                "SELECTION_CARDINALITY_INVALID",
            )
        return self._finish(
            started=started,
            route_ids=route_ids,
            candidate_count=len(candidates),
            original_ids=original_ids,
            selected_ids=selected_ids,
            status="APPLIED",
            failure_code=None,
        )

    def _has_comparison_marker(self, question: str) -> bool:
        folded = question.casefold()
        return any(
            marker.casefold() in folded
            for marker in self.config.comparison_markers
        )

    def _fallback(
        self,
        started: float,
        route_ids: tuple[str, ...],
        candidates: Sequence[RankedChunk],
        original_ids: tuple[str, ...],
        failure_code: str,
    ) -> RouteCoveragePlan:
        return self._finish(
            started=started,
            route_ids=route_ids,
            candidate_count=len(candidates),
            original_ids=original_ids,
            selected_ids=original_ids,
            status="FALLBACK",
            failure_code=failure_code,
        )

    def _finish(
        self,
        *,
        started: float,
        route_ids: tuple[str, ...],
        candidate_count: int,
        original_ids: tuple[str, ...],
        selected_ids: tuple[str, ...],
        status: Literal["APPLIED", "FALLBACK", "DISABLED"],
        failure_code: str | None,
    ) -> RouteCoveragePlan:
        if self.observer is not None:
            self.observer(
                RouteCoverageObservation(
                    status=status,
                    failure_code=failure_code,
                    route_count=len(route_ids),
                    candidate_count=candidate_count,
                    selection_changed=selected_ids != original_ids,
                    selection_latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
        return RouteCoveragePlan(
            status=status,
            selected_chunk_ids=selected_ids,
            failure_code=failure_code,
        )
