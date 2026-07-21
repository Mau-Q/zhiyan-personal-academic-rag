"""Bounded text-PDF parser with page and section lineage.

Adapted from Zhiyan Paper Reading Agent under its MIT License. See
``docs/THIRD_PARTY_NOTICES.md``.
"""

from __future__ import annotations

import re
import unicodedata
from hashlib import sha256
from io import BytesIO

from pypdf import PdfReader

from backend.ingestion.models import ParsedBlock, ParsedPdf


NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?P<number>\d+(?:\.\d+)*)[.)]?\s+(?P<title>.+)$",
    re.IGNORECASE,
)
ROMAN_HEADING_PATTERN = re.compile(
    r"^(?P<number>[IVXLCDM]+)\.\s+(?P<title>.+)$",
    re.IGNORECASE,
)
NAMED_HEADING_PATTERN = re.compile(
    r"^(?:abstract|introduction|related work|methods?|methodology|experiments?|results?|"
    r"discussion|conclusions?|references)$",
    re.IGNORECASE,
)


class PdfParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _normalize_page_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        character
        for character in text
        if character in {"\n", "\t"} or unicodedata.category(character) != "Cc"
    )
    lines = [re.sub(r"[\t ]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _is_heading(text: str) -> bool:
    value = text.strip()
    if len(value) > 160 or "\n" in value:
        return False
    if NAMED_HEADING_PATTERN.fullmatch(value) is not None:
        return True
    roman_match = ROMAN_HEADING_PATTERN.fullmatch(value)
    if roman_match is not None:
        title = roman_match.group("title").strip()
        letters = [character for character in title if character.isalpha()]
        uppercase_ratio = (
            sum(character.isupper() for character in letters) / len(letters) if letters else 0
        )
        return bool(title) and uppercase_ratio >= 0.7
    match = NUMBERED_HEADING_PATTERN.fullmatch(value)
    if match is None:
        return False
    top_level = int(match.group("number").split(".", 1)[0])
    title = match.group("title").strip()
    sentence_like = re.search(
        r"\b(?:is|are|was|were|has|have|shows|denotes|contains)\b",
        title,
    )
    return (
        1 <= top_level <= 20
        and bool(title)
        and title[0].isupper()
        and sentence_like is None
    )


def _heading_level(text: str) -> int:
    match = re.match(r"^(\d+(?:\.\d+)*)", text.strip())
    return match.group(1).count(".") + 1 if match else 1


def _section_path(current: tuple[str, ...], heading: str) -> tuple[str, ...]:
    level = _heading_level(heading)
    if level <= 1:
        return (heading,)
    return (*current[: level - 1], heading)


def _text_block_spans(text: str) -> list[tuple[int, int]]:
    lines = list(re.finditer(r"[^\n]+", text))
    spans: list[tuple[int, int]] = []
    active_start: int | None = None
    active_end: int | None = None
    for index, match in enumerate(lines):
        value = match.group(0).strip()
        if not value:
            continue
        if _is_heading(value):
            if active_start is not None and active_end is not None:
                spans.append((active_start, active_end))
            spans.append((match.start(), match.end()))
            active_start = None
            active_end = None
            continue
        if active_start is None:
            active_start = match.start()
        active_end = match.end()
        next_value = lines[index + 1].group(0).strip() if index + 1 < len(lines) else ""
        paragraph_end = bool(re.search(r"[.!?。！？]\s*$", value)) and bool(
            re.match(r"[A-Z0-9\u4e00-\u9fff]", next_value)
        )
        if active_end - active_start >= 1800 or paragraph_end:
            spans.append((active_start, active_end))
            active_start = None
            active_end = None
    if active_start is not None and active_end is not None:
        spans.append((active_start, active_end))
    return spans


class PypdfTextParser:
    """Parse text-extractable PDFs without OCR, layout recovery, or network access."""

    def __init__(
        self,
        *,
        minimum_text_characters: int = 80,
        maximum_pdf_bytes: int = 50 * 1024 * 1024,
        maximum_page_count: int = 2_000,
        maximum_clean_text_bytes: int = 5 * 1024 * 1024,
    ) -> None:
        if min(
            minimum_text_characters,
            maximum_pdf_bytes,
            maximum_page_count,
            maximum_clean_text_bytes,
        ) < 1:
            raise ValueError("parser safety limits must be positive")
        self.minimum_text_characters = minimum_text_characters
        self.maximum_pdf_bytes = maximum_pdf_bytes
        self.maximum_page_count = maximum_page_count
        self.maximum_clean_text_bytes = maximum_clean_text_bytes

    def parse(self, pdf_bytes: bytes) -> ParsedPdf:
        if len(pdf_bytes) > self.maximum_pdf_bytes:
            raise PdfParseError("PDF_TOO_LARGE", "PDF exceeds the parser input limit.")
        if not pdf_bytes.startswith(b"%PDF-"):
            raise PdfParseError("PDF_SIGNATURE_INVALID", "Input is not a PDF document.")
        try:
            reader = PdfReader(BytesIO(pdf_bytes), strict=False)
            if reader.is_encrypted and reader.decrypt("") == 0:
                raise PdfParseError("PDF_ENCRYPTED", "PDF requires a password.")
            raw_pages = list(reader.pages)
        except PdfParseError:
            raise
        except Exception as exc:
            raise PdfParseError("PDF_PARSE_FAILED", "PDF could not be parsed.") from exc
        if not raw_pages:
            raise PdfParseError("PDF_HAS_NO_PAGES", "PDF has no pages.")
        if len(raw_pages) > self.maximum_page_count:
            raise PdfParseError("PDF_PAGE_LIMIT_EXCEEDED", "PDF exceeds the page limit.")

        extracted: list[str] = []
        for page in raw_pages:
            try:
                extracted.append(_normalize_page_text(page.extract_text() or ""))
            except Exception as exc:
                raise PdfParseError(
                    "PDF_TEXT_EXTRACTION_FAILED", "PDF text extraction failed."
                ) from exc

        non_empty_page_count = sum(bool(text) for text in extracted)
        total_characters = sum(len(text) for text in extracted)
        warnings: list[str] = []
        if non_empty_page_count == 0:
            parse_status = "FAILED"
            warnings.append("NO_EXTRACTABLE_TEXT")
        elif non_empty_page_count < len(extracted):
            parse_status = "REVIEW"
            warnings.append("EMPTY_TEXT_PAGE_DETECTED")
        elif total_characters < self.minimum_text_characters:
            parse_status = "REVIEW"
            warnings.append("EXTRACTED_TEXT_TOO_SHORT")
        else:
            parse_status = "PASS"

        clean_text = "\n\n".join(extracted)
        if len(clean_text.encode("utf-8")) > self.maximum_clean_text_bytes:
            raise PdfParseError(
                "PDF_CLEAN_TEXT_TOO_LARGE", "Normalized PDF text exceeds the parser limit."
            )

        page_offsets: list[int] = []
        cursor = 0
        for index, text in enumerate(extracted):
            if index:
                cursor += 2
            page_offsets.append(cursor)
            cursor += len(text)

        blocks: list[ParsedBlock] = []
        current_section = ("Document",)
        for page_number, text in enumerate(extracted, start=1):
            for local_start, local_end in _text_block_spans(text):
                block_text = text[local_start:local_end]
                if _is_heading(block_text.strip()):
                    current_section = _section_path(current_section, block_text.strip())
                blocks.append(
                    ParsedBlock(
                        page_number=page_number,
                        section_path=current_section,
                        source_start=page_offsets[page_number - 1] + local_start,
                        source_end=page_offsets[page_number - 1] + local_end,
                        text=block_text,
                    )
                )

        return ParsedPdf(
            pdf_sha256=sha256(pdf_bytes).hexdigest(),
            source_text_sha256=sha256(clean_text.encode("utf-8")).hexdigest(),
            clean_text=clean_text,
            page_count=len(extracted),
            parse_status=parse_status,
            warnings=tuple(warnings),
            blocks=tuple(blocks),
        )
