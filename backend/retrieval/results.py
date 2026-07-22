"""Shared ranked-candidate interface for retrieval adapters and fusion."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


JsonObject = dict[str, Any]
_BACKEND_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


@dataclass(frozen=True)
class RankedChunk:
    """One authorized retrieval candidate with backend-local rank and score."""

    backend: str
    rank: int
    score: float
    chunk: JsonObject

    def __post_init__(self) -> None:
        if not _BACKEND_PATTERN.fullmatch(self.backend):
            raise ValueError("ranked candidate backend is invalid")
        if self.rank < 1:
            raise ValueError("ranked candidate rank must be at least 1")
        if not math.isfinite(self.score):
            raise ValueError("ranked candidate score must be finite")
        for field in ("chunk_id", "document_id"):
            if not isinstance(self.chunk.get(field), str) or not self.chunk[field]:
                raise ValueError(f"ranked candidate chunk has invalid {field}")


def validate_ranking(
    ranking: Sequence[RankedChunk], *, expected_backend: str
) -> None:
    if [candidate.rank for candidate in ranking] != list(range(1, len(ranking) + 1)):
        raise ValueError("ranked candidate ranks must be contiguous and start at 1")
    chunk_ids = [str(candidate.chunk["chunk_id"]) for candidate in ranking]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("ranked candidates must have unique chunk_id values")
    if any(candidate.backend != expected_backend for candidate in ranking):
        raise ValueError("ranked candidate backend does not match ranking source")


def chunks_only(ranking: Sequence[RankedChunk]) -> list[JsonObject]:
    return [candidate.chunk for candidate in ranking]
