"""Deterministic Claim–Evidence checks over already-authorized Evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ClaimSupportStatus(StrEnum):
    """Conservative outcomes that do not pretend to be semantic entailment."""

    SUPPORTED = "SUPPORTED"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class GeneratedClaim:
    text: str
    citation_ids: tuple[int, ...]


@dataclass(frozen=True)
class ClaimEvidenceRecord:
    claim: GeneratedClaim
    status: ClaimSupportStatus
    reason_codes: tuple[str, ...]

    @property
    def retained(self) -> bool:
        return self.status is not ClaimSupportStatus.UNSUPPORTED


@dataclass(frozen=True)
class ClaimEvidenceReport:
    records: tuple[ClaimEvidenceRecord, ...]

    @property
    def retained_claims(self) -> tuple[GeneratedClaim, ...]:
        return tuple(record.claim for record in self.records if record.retained)

    @property
    def citation_completeness(self) -> float:
        if not self.records:
            return 0.0
        complete = sum(bool(record.claim.citation_ids) for record in self.records)
        return complete / len(self.records)

    @property
    def unsupported_claim_rate(self) -> float:
        if not self.records:
            return 0.0
        unsupported = sum(
            record.status is ClaimSupportStatus.UNSUPPORTED
            for record in self.records
        )
        return unsupported / len(self.records)

    @property
    def is_partial_answer(self) -> bool:
        return bool(self.retained_claims) and any(
            record.status is ClaimSupportStatus.UNSUPPORTED
            for record in self.records
        )


_NUMBER = re.compile(
    r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?%?",
    re.IGNORECASE,
)
_NUMBER_WITH_UNIT = re.compile(
    r"(?<![A-Za-z_])(?P<value>[-+]?\d+(?:\.\d+)?)\s*-?\s*"
    r"(?P<unit>%|％|周|星期|天|日|月|年|小时|分钟|秒|"
    r"weeks?|days?|months?|years?|hours?|minutes?|seconds?)(?![A-Za-z])",
    re.IGNORECASE,
)
_LATIN_TOKEN = re.compile(r"[A-Za-zΑ-Ωα-ω][A-Za-z0-9_Α-Ωα-ω+./-]*")
_CHINESE = re.compile(r"[\u4e00-\u9fff]")
_CLAUSE_SPLIT = re.compile(r"[。！？!?；;，,]\s*|\.(?!\d)\s+")

_ENGLISH_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "evidence",
        "of",
        "on",
        "or",
        "paper",
        "report",
        "reported",
        "reports",
        "result",
        "results",
        "study",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
    }
)
_CONFLICT_MARKERS = (
    "存在差异",
    "不一致",
    "冲突",
    "分别为",
    "different",
    "differ",
    "conflict",
    "inconsistent",
    "whereas",
    "but",
)
_INSUFFICIENT_MARKERS = (
    "证据不足",
    "无法确定",
    "未提供",
    "未提及",
    "没有说明",
    "不能判断",
    "insufficient evidence",
    "cannot determine",
    "does not identify",
    "does not report",
    "not reported",
    "not provided",
)
_CAUSAL_MARKERS = (
    "导致",
    "证明",
    "因此必然",
    "因而必然",
    "必然带来",
    "causes",
    "caused by",
    "proves",
    "must result",
)
_CAUSAL_EVIDENCE_MARKERS = _CAUSAL_MARKERS + (
    "消融",
    "对照",
    "控制变量",
    "干预",
    "ablation",
    "controlled",
    "control group",
    "intervention",
)
_UNIVERSAL_MARKERS = (
    "所有任务",
    "所有模型",
    "普遍有效",
    "始终",
    "all tasks",
    "all models",
    "universally",
    "always",
)
_COMPARATIVE_MARKERS = (
    "优于",
    "更优",
    "最佳",
    "胜过",
    "提高",
    "提升",
    "降低",
    "下降",
    "高于",
    "低于",
    "outperform",
    "superior",
    "better than",
    "best",
    "improve",
    "increase",
    "decrease",
    "higher",
    "lower",
)
_NOVELTY_MARKERS = (
    "首次",
    "首个",
    "首创",
    "唯一",
    "最全面",
    "first-ever",
    "the first",
    "the only",
    "most comprehensive",
    "state-of-the-art",
    "state of the art",
)


def verify_claim_evidence(
    claims: Sequence[GeneratedClaim],
    evidence: Sequence[Mapping[str, Any]],
) -> ClaimEvidenceReport:
    """Verify narrow deterministic support and fail closed on unproved claims."""

    records = tuple(_verify_claim(claim, evidence) for claim in claims)
    return ClaimEvidenceReport(records=records)


def _verify_claim(
    claim: GeneratedClaim,
    evidence: Sequence[Mapping[str, Any]],
) -> ClaimEvidenceRecord:
    if not isinstance(claim.text, str) or not claim.text.strip():
        return _unsupported(claim, "CLAIM_TEXT_EMPTY")
    if not claim.citation_ids:
        return _unsupported(claim, "CLAIM_CITATION_MISSING")
    if (
        any(type(position) is not int for position in claim.citation_ids)
        or tuple(sorted(set(claim.citation_ids))) != claim.citation_ids
    ):
        return _unsupported(claim, "CLAIM_CITATION_SET_INVALID")
    if any(position < 1 or position > len(evidence) for position in claim.citation_ids):
        return _unsupported(claim, "CLAIM_CITATION_OUT_OF_RANGE")

    raw_quotes = tuple(
        evidence[position - 1].get("quote")
        for position in claim.citation_ids
    )
    if any(not isinstance(quote, str) or not quote.strip() for quote in raw_quotes):
        return _unsupported(claim, "BOUND_EVIDENCE_TEXT_EMPTY")
    quotes = tuple(quote.strip() for quote in raw_quotes if isinstance(quote, str))

    claim_folded = claim.text.casefold()
    evidence_folded = "\n".join(quotes).casefold()
    conflicts = _numeric_unit_conflicts(quotes)
    discloses_conflict = _has_any(claim_folded, _CONFLICT_MARKERS)

    if conflicts:
        if not discloses_conflict:
            return _unsupported(claim, "BOUND_NUMERIC_CONFLICT_NOT_DISCLOSED")
        claim_facts = _number_unit_facts(claim.text)
        if not any(
            len(values & claim_facts.get(unit, set())) >= 2
            for unit, values in conflicts.items()
        ):
            return _unsupported(claim, "BOUND_NUMERIC_CONFLICT_VALUES_INCOMPLETE")
        support_failure = _deterministic_support_failure(
            claim.text, evidence_folded
        )
        if support_failure is not None:
            return _unsupported(claim, support_failure)
        return ClaimEvidenceRecord(
            claim=claim,
            status=ClaimSupportStatus.CONFLICTING_EVIDENCE,
            reason_codes=("BOUND_NUMERIC_CONFLICT_DISCLOSED",),
        )
    if discloses_conflict:
        return _unsupported(claim, "CONFLICT_NOT_DETERMINISTICALLY_PROVEN")

    if _is_safe_limitation(claim.text):
        return ClaimEvidenceRecord(
            claim=claim,
            status=ClaimSupportStatus.INSUFFICIENT_EVIDENCE,
            reason_codes=("SAFE_LIMITATION_WITH_BOUND_EVIDENCE",),
        )

    support_failure = _deterministic_support_failure(claim.text, evidence_folded)
    if support_failure is not None:
        return _unsupported(claim, support_failure)

    return ClaimEvidenceRecord(
        claim=claim,
        status=ClaimSupportStatus.SUPPORTED,
        reason_codes=("DETERMINISTIC_ANCHORS_AND_CORE_OVERLAP_PASS",),
    )


def _deterministic_support_failure(claim: str, evidence: str) -> str | None:
    claim_folded = claim.casefold()
    claim_numbers = {_normalize_number(value) for value in _NUMBER.findall(claim)}
    evidence_numbers = {
        _normalize_number(value) for value in _NUMBER.findall(evidence)
    }
    if not claim_numbers.issubset(evidence_numbers):
        return "NUMERIC_ANCHOR_MISSING_FROM_EVIDENCE"
    if _has_any(claim_folded, _CAUSAL_MARKERS) and not _has_any(
        evidence, _CAUSAL_EVIDENCE_MARKERS
    ):
        return "CAUSAL_RELATION_NOT_ESTABLISHED"
    if _has_any(claim_folded, _UNIVERSAL_MARKERS) and not _has_any(
        evidence, _UNIVERSAL_MARKERS
    ):
        return "UNIVERSAL_SCOPE_NOT_ESTABLISHED"
    if _has_any(claim_folded, _COMPARATIVE_MARKERS) and not _has_any(
        evidence, _COMPARATIVE_MARKERS
    ):
        return "COMPARISON_NOT_ESTABLISHED"
    if _has_any(claim_folded, _NOVELTY_MARKERS) and not _has_any(
        evidence, _NOVELTY_MARKERS
    ):
        return "NOVELTY_OR_SUPERLATIVE_NOT_ESTABLISHED"
    if not _all_claim_clauses_overlap(claim, evidence):
        return "CORE_LEXICAL_OVERLAP_NOT_ESTABLISHED"
    return None


def _unsupported(claim: GeneratedClaim, code: str) -> ClaimEvidenceRecord:
    return ClaimEvidenceRecord(
        claim=claim,
        status=ClaimSupportStatus.UNSUPPORTED,
        reason_codes=(code,),
    )


def _is_safe_limitation(text: str) -> bool:
    if _NUMBER.search(text):
        return False
    fragments = [
        fragment.strip()
        for fragment in _CLAUSE_SPLIT.split(text.casefold())
        if fragment.strip()
    ]
    return bool(fragments) and all(
        _has_any(fragment, _INSUFFICIENT_MARKERS) for fragment in fragments
    )


def _numeric_unit_conflicts(quotes: Sequence[str]) -> dict[str, set[str]]:
    by_unit: dict[str, dict[int, set[str]]] = {}
    for index, quote in enumerate(quotes):
        for unit, values in _number_unit_facts(quote).items():
            by_unit.setdefault(unit, {})[index] = values
    conflicts: dict[str, set[str]] = {}
    for unit, per_quote in by_unit.items():
        if len(per_quote) < 2:
            continue
        combined = set().union(*per_quote.values())
        if len(combined) >= 2:
            conflicts[unit] = combined
    return conflicts


def _number_unit_facts(text: str) -> dict[str, set[str]]:
    facts: dict[str, set[str]] = {}
    for match in _NUMBER_WITH_UNIT.finditer(text):
        unit = _normalize_unit(match.group("unit"))
        facts.setdefault(unit, set()).add(_normalize_number(match.group("value")))
    return facts


def _normalize_number(value: str) -> str:
    normalized = value.casefold().lstrip("+")
    if normalized.endswith("%"):
        normalized = normalized[:-1]
    try:
        return format(float(normalized), "g")
    except ValueError:
        return normalized


def _normalize_unit(value: str) -> str:
    unit = value.casefold()
    aliases = {
        "％": "%",
        "week": "weeks",
        "day": "days",
        "month": "months",
        "year": "years",
        "hour": "hours",
        "minute": "minutes",
        "second": "seconds",
    }
    return aliases.get(unit, unit)


def _core_overlap(claim: str, evidence: str) -> bool:
    claim_latin = {
        token.casefold().strip(".+/-")
        for token in _LATIN_TOKEN.findall(claim)
        if len(token.strip(".+/-")) > 1
        and token.casefold().strip(".+/-") not in _ENGLISH_STOPWORDS
    }
    evidence_latin = {
        token.casefold().strip(".+/-")
        for token in _LATIN_TOKEN.findall(evidence)
        if token.strip(".+/-")
    }
    if claim_latin and claim_latin & evidence_latin:
        return True

    claim_chinese = "".join(_CHINESE.findall(claim))
    evidence_chinese = "".join(_CHINESE.findall(evidence))
    if len(claim_chinese) >= 4:
        claim_bigrams = {
            claim_chinese[index : index + 2]
            for index in range(len(claim_chinese) - 1)
        }
        evidence_bigrams = {
            evidence_chinese[index : index + 2]
            for index in range(len(evidence_chinese) - 1)
        }
        overlap = len(claim_bigrams & evidence_bigrams) / max(1, len(claim_bigrams))
        return overlap >= 0.12
    return False


def _all_claim_clauses_overlap(claim: str, evidence: str) -> bool:
    fragments = [
        fragment.strip(" \t\n:：")
        for fragment in _CLAUSE_SPLIT.split(claim)
        if fragment.strip(" \t\n:：")
    ]
    return bool(fragments) and all(
        _core_overlap(fragment, evidence) for fragment in fragments
    )


def _has_any(value: str, markers: Sequence[str]) -> bool:
    return any(marker in value for marker in markers)
