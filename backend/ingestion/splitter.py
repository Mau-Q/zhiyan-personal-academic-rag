"""Deterministic in-process splitter with exact source spans.

Adapted from Zhiyan Paper Reading Agent under its MIT License. See
``docs/THIRD_PARTY_NOTICES.md``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256


STRATEGIES = (
    "fixed_boundary_v1",
    "paragraph_sentence_v1",
    "section_parent_child_v1",
)
CONFIG = {
    "fixed_boundary_v1": {"chunk_size": 1024, "overlap": 200},
    "paragraph_sentence_v1": {
        "target_chars": 1024,
        "max_chars": 1280,
        "overlap_target_chars": 200,
    },
    "section_parent_child_v1": {
        "target_chars": 1024,
        "max_chars": 1280,
        "overlap_target_chars": 200,
    },
}
HEADING_RE = re.compile(
    r"(?m)^(?P<heading>(?:[1-9]\d*(?:\.[1-9]\d*)*\.|[A-Z]\.)[ \t]+[^\r\n]{2,100}|"
    r"Appendix|Acknowledg(?:e)?ments?(?:\.[^\r\n]*)?)\s*$"
)
SENTENCE_END_RE = re.compile(r"(?<=[.!?])(?:[\"')\]]*)\s+")
PARAGRAPH_BREAK_RE = re.compile(r"\n{2,}")
BOUNDARY_RE = re.compile(r"(\n\n+|(?<=[.!?;:])\s+)")
ROMAN_MAJOR_RE = re.compile(r"^(?P<number>[IVXLCDM]+)\.\s+(?P<title>.+)$")


class SplitterError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Span:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class SectionSpan(Span):
    section_id: str
    heading: str


@dataclass(frozen=True)
class RawChunk:
    text: str
    source_start: int
    source_end: int
    section_name: str | None
    parent_source_id: str | None = None


def canonical_sha256(value: object) -> str:
    content = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(content).hexdigest()


def strategy_config_hash(strategy: str) -> str:
    return canonical_sha256(CONFIG[strategy])


def _trim_span(text: str, start: int, end: int) -> Span:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return Span(start, end)


def _heading_spans(text: str) -> list[Span]:
    return [
        _trim_span(text, match.start("heading"), match.end("heading"))
        for match in HEADING_RE.finditer(text)
    ]


def _is_major_heading(value: str) -> bool:
    if re.match(r"^[1-9]\d*\.\s+", value):
        return True
    roman_match = ROMAN_MAJOR_RE.match(value)
    if roman_match is not None:
        letters = [character for character in roman_match.group("title") if character.isalpha()]
        uppercase_ratio = (
            sum(character.isupper() for character in letters) / len(letters) if letters else 0
        )
        return uppercase_ratio >= 0.7
    return bool(re.match(r"^(?:Appendix|Acknowledg)", value))


def _section_spans(text: str, *, major_only: bool = False) -> list[SectionSpan]:
    headings = _heading_spans(text)
    if major_only:
        headings = [
            span
            for span in headings
            if _is_major_heading(text[span.start : span.end])
            and not re.match(r"^[1-9]\d*\.[1-9]", text[span.start : span.end])
        ]
    unknown_id = "parent-unknown-000" if major_only else "section-unknown-000"
    if not headings:
        return [SectionSpan(0, len(text), unknown_id, "UNKNOWN")]
    sections: list[SectionSpan] = []
    if headings[0].start > 0:
        sections.append(SectionSpan(0, headings[0].start, unknown_id, "UNKNOWN"))
    prefix = "parent" if major_only else "section"
    for index, heading in enumerate(headings):
        end = headings[index + 1].start if index + 1 < len(headings) else len(text)
        sections.append(
            SectionSpan(
                heading.start,
                end,
                f"{prefix}-{index + 1:03d}",
                text[heading.start : heading.end],
            )
        )
    return sections


def _paragraph_spans(text: str, start: int, end: int) -> list[Span]:
    spans: list[Span] = []
    cursor = start
    for match in PARAGRAPH_BREAK_RE.finditer(text, start, end):
        candidate = Span(cursor, match.end())
        if text[candidate.start : candidate.end].strip():
            spans.append(candidate)
        cursor = match.end()
    candidate = Span(cursor, end)
    if text[candidate.start : candidate.end].strip():
        spans.append(candidate)
    return spans


def _sentence_spans(text: str, start: int, end: int) -> list[Span]:
    spans: list[Span] = []
    cursor = start
    for match in SENTENCE_END_RE.finditer(text, start, end):
        candidate = Span(cursor, match.end())
        if text[candidate.start : candidate.end].strip():
            spans.append(candidate)
        cursor = match.end()
    candidate = Span(cursor, end)
    if text[candidate.start : candidate.end].strip():
        spans.append(candidate)
    return spans


def _atomic_spans(text: str, section: SectionSpan, max_chars: int) -> list[Span]:
    units: list[Span] = []
    for paragraph in _paragraph_spans(text, section.start, section.end):
        if paragraph.length <= max_chars:
            units.append(paragraph)
            continue
        for sentence in _sentence_spans(text, paragraph.start, paragraph.end):
            if sentence.length <= max_chars:
                units.append(sentence)
                continue
            cursor = sentence.start
            while cursor < sentence.end:
                boundary = min(cursor + max_chars, sentence.end)
                units.append(Span(cursor, boundary))
                cursor = boundary
    if units:
        units[0] = Span(section.start, units[0].end)
        units[-1] = Span(units[-1].start, section.end)
    return units


def _group_units(
    units: list[Span],
    target_chars: int,
    max_chars: int,
    overlap_target_chars: int,
) -> list[Span]:
    chunks: list[Span] = []
    index = 0
    while index < len(units):
        start = units[index].start
        stop = index + 1
        while stop < len(units) and units[stop].end - start <= target_chars:
            stop += 1
        if stop < len(units) and units[stop].end - start <= max_chars:
            current_distance = abs(units[stop - 1].end - start - target_chars)
            next_distance = abs(units[stop].end - start - target_chars)
            if next_distance <= current_distance:
                stop += 1
        end = units[stop - 1].end
        chunks.append(Span(start, end))
        if stop >= len(units):
            break
        if units[stop].length + overlap_target_chars > max_chars:
            index = stop
            continue
        overlap_start = stop - 1
        while overlap_start > index and end - units[overlap_start].start < overlap_target_chars:
            overlap_start -= 1
        index = max(index + 1, overlap_start)
    return chunks


def _split_structural(text: str, *, parent_ids: bool, **config: int) -> list[RawChunk]:
    chunks: list[RawChunk] = []
    sections = _section_spans(text, major_only=parent_ids)
    for section in sections:
        units = _atomic_spans(text, section, config["max_chars"])
        for span in _group_units(
            units,
            config["target_chars"],
            config["max_chars"],
            config["overlap_target_chars"],
        ):
            chunk_text = text[span.start : span.end]
            if chunk_text.strip():
                chunks.append(
                    RawChunk(
                        text=chunk_text,
                        source_start=span.start,
                        source_end=span.end,
                        section_name=None if section.heading == "UNKNOWN" else section.heading,
                        parent_source_id=section.section_id if parent_ids else None,
                    )
                )
    return chunks


def _split_units(text: str) -> list[str]:
    parts = BOUNDARY_RE.split(text.strip())
    units: list[str] = []
    current = ""
    for part in parts:
        if not part:
            continue
        current += part
        if BOUNDARY_RE.fullmatch(part):
            if current.strip():
                units.append(current.strip())
            current = ""
    if current.strip():
        units.append(current.strip())
    return units


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    chunks: list[str] = []
    current = ""
    for unit in _split_units(text):
        if len(unit) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            start = 0
            while start < len(unit):
                end = min(start + chunk_size, len(unit))
                chunks.append(unit[start:end].strip())
                if end >= len(unit):
                    break
                start = end - overlap
            continue
        next_text = f"{current} {unit}".strip() if current else unit
        if len(next_text) <= chunk_size:
            current = next_text
            continue
        if current:
            chunks.append(current.strip())
        tail = current[-overlap:].strip() if overlap and current else ""
        current = f"{tail} {unit}".strip() if tail else unit
    if current:
        chunks.append(current.strip())
    return chunks


def _split_fixed(text: str, *, chunk_size: int, overlap: int) -> list[RawChunk]:
    sections = _section_spans(text)
    chunks: list[RawChunk] = []
    lower_bound = 0
    for chunk in _chunk_text(text, chunk_size, overlap):
        exact = text.find(chunk, lower_bound)
        if exact < 0:
            tokens = [re.escape(token) for token in re.split(r"\s+", chunk.strip()) if token]
            match = re.compile(r"\s+".join(tokens)).search(text, lower_bound) if tokens else None
            if match is None:
                raise SplitterError(
                    "SPLITTER_SOURCE_SPAN_INVALID",
                    "Fixed-boundary chunk could not be mapped to source text.",
                )
            start, end = match.span()
        else:
            start, end = exact, exact + len(chunk)
        first = next(section for section in sections if section.start <= start < section.end)
        last_offset = max(start, end - 1)
        last = next(
            section for section in sections if section.start <= last_offset < section.end
        )
        section_name = (
            first.heading
            if first.section_id == last.section_id
            else f"{first.heading} -> {last.heading}"
        )
        chunks.append(
            RawChunk(
                text=text[start:end],
                source_start=start,
                source_end=end,
                section_name=None if section_name == "UNKNOWN" else section_name,
            )
        )
        lower_bound = start if len(chunk) <= overlap else max(start + 1, end - overlap)
    return chunks


def split_text(text: str, strategy: str) -> list[RawChunk]:
    if strategy not in STRATEGIES:
        raise SplitterError(
            "UNSUPPORTED_SPLITTER_STRATEGY",
            f"Strategy must be one of: {', '.join(STRATEGIES)}.",
        )
    if not text.strip():
        raise SplitterError("EMPTY_SOURCE_TEXT", "Source text must not be empty.")
    config = CONFIG[strategy]
    if strategy == "fixed_boundary_v1":
        chunks = _split_fixed(text, **config)
    else:
        chunks = _split_structural(
            text,
            parent_ids=strategy == "section_parent_child_v1",
            **config,
        )
    if not chunks:
        raise SplitterError("SPLITTER_EMPTY_RESULT", "Splitter produced no chunks.")
    for chunk in chunks:
        if text[chunk.source_start : chunk.source_end] != chunk.text:
            raise SplitterError(
                "SPLITTER_SOURCE_SPAN_INVALID",
                "Splitter chunk does not match its exact source span.",
            )
    return chunks
