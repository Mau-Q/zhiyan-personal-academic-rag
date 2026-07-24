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


class EvidenceSetStatus(StrEnum):
    """Evidence-set outcomes for audit-only multi-evidence verification."""

    SUPPORTED_BY_EVIDENCE_SET = "SUPPORTED_BY_EVIDENCE_SET"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


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


@dataclass(frozen=True)
class EvidenceSet:
    """Deterministic set of request-local Evidence positions for one Claim."""

    citation_ids: tuple[int, ...]
    chunk_ids: tuple[str, ...]
    adjacent_chunk_added: bool = False


@dataclass(frozen=True)
class EvidenceSetRecord:
    claim: GeneratedClaim
    evidence_set: EvidenceSet
    status: EvidenceSetStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceSetReport:
    records: tuple[EvidenceSetRecord, ...]

    @property
    def has_conflict(self) -> bool:
        return any(
            record.status is EvidenceSetStatus.CONFLICTING_EVIDENCE
            for record in self.records
        )

    @property
    def is_partial_answer(self) -> bool:
        statuses = {record.status for record in self.records}
        return bool(statuses) and (
            EvidenceSetStatus.PARTIALLY_SUPPORTED in statuses
            or (
                EvidenceSetStatus.SUPPORTED_BY_EVIDENCE_SET in statuses
                and EvidenceSetStatus.INSUFFICIENT_EVIDENCE in statuses
            )
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
_CONTRACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

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
_QUALIFIER_MARKER_GROUPS = (
    ("至少", "at least"),
    ("至多", "最多", "不超过", "at most", "no more than"),
    ("仅", "只在", "only"),
    ("分别", "respectively"),
    ("条件下", "under"),
)


def verify_claim_evidence(
    claims: Sequence[GeneratedClaim],
    evidence: Sequence[Mapping[str, Any]],
) -> ClaimEvidenceReport:
    """Verify narrow deterministic support and fail closed on unproved claims."""

    records = tuple(_verify_claim(claim, evidence) for claim in claims)
    return ClaimEvidenceReport(records=records)


def verify_claim_evidence_sets(
    claims: Sequence[GeneratedClaim],
    evidence: Sequence[Mapping[str, Any]],
    *,
    expected_owner_id: str,
    active_document_versions: Mapping[str, str],
    active_chunk_identities: Mapping[str, tuple[str, str]],
    allow_adjacent: bool = True,
) -> EvidenceSetReport:
    """Build and audit deterministic multi-Evidence sets without retrieval changes.

    ``evidence`` is the already-authorized request-local candidate sequence.  It may
    contain more items than a Claim cites so that one existing adjacent item can be
    added when, and only when, it upgrades deterministic support.  No retrieval
    score is read or changed.
    """

    if not _valid_contract_id(expected_owner_id):
        raise ValueError("expected_owner_id must be a contract ID")
    if not active_document_versions or any(
        not _valid_contract_id(document_id)
        or not _valid_contract_id(version_id)
        for document_id, version_id in active_document_versions.items()
    ):
        raise ValueError("active_document_versions must contain contract IDs")
    if not active_chunk_identities or any(
        not _valid_contract_id(chunk_id)
        or not isinstance(identity, tuple)
        or len(identity) != 2
        or not _valid_contract_id(identity[0])
        or not _valid_contract_id(identity[1])
        for chunk_id, identity in active_chunk_identities.items()
    ):
        raise ValueError("active_chunk_identities must contain exact contract IDs")
    records = tuple(
        _verify_claim_evidence_set(
            claim,
            evidence,
            expected_owner_id=expected_owner_id,
            active_document_versions=active_document_versions,
            active_chunk_identities=active_chunk_identities,
            allow_adjacent=allow_adjacent,
        )
        for claim in claims
    )
    return EvidenceSetReport(records=records)


def _verify_claim_evidence_set(
    claim: GeneratedClaim,
    evidence: Sequence[Mapping[str, Any]],
    *,
    expected_owner_id: str,
    active_document_versions: Mapping[str, str],
    active_chunk_identities: Mapping[str, tuple[str, str]],
    allow_adjacent: bool,
) -> EvidenceSetRecord:
    citation_failure = _claim_citation_failure(claim, evidence)
    if citation_failure is not None:
        return _insufficient_evidence_set(claim, (), evidence, citation_failure)

    citation_ids = claim.citation_ids
    identity_failure = _evidence_identity_failure(
        citation_ids,
        evidence,
        expected_owner_id=expected_owner_id,
        active_document_versions=active_document_versions,
        active_chunk_identities=active_chunk_identities,
    )
    if identity_failure is not None:
        return _insufficient_evidence_set(
            claim, citation_ids, evidence, identity_failure
        )

    base = _classify_evidence_set(claim, citation_ids, evidence)
    if (
        not allow_adjacent
        or base.status
        in {
            EvidenceSetStatus.SUPPORTED_BY_EVIDENCE_SET,
            EvidenceSetStatus.CONFLICTING_EVIDENCE,
        }
    ):
        return base

    for adjacent_position in _valid_adjacent_positions(
        citation_ids,
        evidence,
        expected_owner_id=expected_owner_id,
        active_document_versions=active_document_versions,
        active_chunk_identities=active_chunk_identities,
    ):
        expanded_ids = tuple(sorted((*citation_ids, adjacent_position)))
        expanded = _classify_evidence_set(claim, expanded_ids, evidence)
        if expanded.status in {
            EvidenceSetStatus.SUPPORTED_BY_EVIDENCE_SET,
            EvidenceSetStatus.CONFLICTING_EVIDENCE,
        }:
            return EvidenceSetRecord(
                claim=claim,
                evidence_set=EvidenceSet(
                    citation_ids=expanded.evidence_set.citation_ids,
                    chunk_ids=expanded.evidence_set.chunk_ids,
                    adjacent_chunk_added=True,
                ),
                status=expanded.status,
                reason_codes=(
                    *expanded.reason_codes,
                    "SAME_DOCUMENT_VERSION_ADJACENT_EVIDENCE_ADDED",
                    "RETRIEVAL_SCORE_UNCHANGED",
                ),
            )
    return base


def _classify_evidence_set(
    claim: GeneratedClaim,
    citation_ids: tuple[int, ...],
    evidence: Sequence[Mapping[str, Any]],
) -> EvidenceSetRecord:
    quotes = tuple(_evidence_text(evidence[position - 1]) for position in citation_ids)
    evidence_folded = "\n".join(quotes).casefold()
    evidence_set = _make_evidence_set(citation_ids, evidence)
    conflicts = _numeric_unit_conflicts(quotes)
    discloses_conflict = _has_any(claim.text.casefold(), _CONFLICT_MARKERS)

    if conflicts:
        reason = (
            "BOUND_NUMERIC_CONFLICT_DISCLOSED"
            if discloses_conflict
            else "BOUND_NUMERIC_CONFLICT_NOT_DISCLOSED"
        )
        return EvidenceSetRecord(
            claim=claim,
            evidence_set=evidence_set,
            status=EvidenceSetStatus.CONFLICTING_EVIDENCE,
            reason_codes=(reason,),
        )
    if discloses_conflict:
        return EvidenceSetRecord(
            claim=claim,
            evidence_set=evidence_set,
            status=EvidenceSetStatus.INSUFFICIENT_EVIDENCE,
            reason_codes=("CONFLICT_NOT_DETERMINISTICALLY_PROVEN",),
        )
    if _is_safe_limitation(claim.text):
        return EvidenceSetRecord(
            claim=claim,
            evidence_set=evidence_set,
            status=EvidenceSetStatus.INSUFFICIENT_EVIDENCE,
            reason_codes=("SAFE_LIMITATION_WITH_BOUND_EVIDENCE",),
        )

    support_failure = _deterministic_support_failure(claim.text, evidence_folded)
    if support_failure is None:
        return EvidenceSetRecord(
            claim=claim,
            evidence_set=evidence_set,
            status=EvidenceSetStatus.SUPPORTED_BY_EVIDENCE_SET,
            reason_codes=("DETERMINISTIC_EVIDENCE_SET_PASS",),
        )

    fragments = _claim_fragments(claim.text)
    supported_fragments = sum(
        _deterministic_support_failure(fragment, evidence_folded) is None
        for fragment in fragments
    )
    status = (
        EvidenceSetStatus.PARTIALLY_SUPPORTED
        if 0 < supported_fragments < len(fragments)
        else EvidenceSetStatus.INSUFFICIENT_EVIDENCE
    )
    return EvidenceSetRecord(
        claim=claim,
        evidence_set=evidence_set,
        status=status,
        reason_codes=(support_failure,),
    )


def _claim_citation_failure(
    claim: GeneratedClaim,
    evidence: Sequence[Mapping[str, Any]],
) -> str | None:
    if not isinstance(claim.text, str) or not claim.text.strip():
        return "CLAIM_TEXT_EMPTY"
    if not claim.citation_ids:
        return "CLAIM_CITATION_MISSING"
    if (
        any(type(position) is not int for position in claim.citation_ids)
        or tuple(sorted(set(claim.citation_ids))) != claim.citation_ids
    ):
        return "CLAIM_CITATION_SET_INVALID"
    if any(position < 1 or position > len(evidence) for position in claim.citation_ids):
        return "CLAIM_CITATION_OUT_OF_RANGE"
    return None


def _evidence_identity_failure(
    citation_ids: Sequence[int],
    evidence: Sequence[Mapping[str, Any]],
    *,
    expected_owner_id: str,
    active_document_versions: Mapping[str, str],
    active_chunk_identities: Mapping[str, tuple[str, str]],
) -> str | None:
    seen_chunks: set[str] = set()
    version_by_document: dict[str, str] = {}
    for position in citation_ids:
        item = evidence[position - 1]
        chunk_id = item.get("chunk_id")
        document_id = item.get("document_id")
        version_id = item.get("version_id")
        owner_id = _evidence_owner_id(item)
        if not all(
            _valid_contract_id(value)
            for value in (chunk_id, document_id, version_id, owner_id)
        ):
            return "EVIDENCE_IDENTITY_INVALID"
        if owner_id != expected_owner_id:
            return "EVIDENCE_OWNER_MISMATCH"
        if item.get("is_active") is not True:
            return "EVIDENCE_VERSION_NOT_ACTIVE"
        if chunk_id in seen_chunks:
            return "EVIDENCE_CHUNK_ID_DUPLICATE"
        seen_chunks.add(chunk_id)
        existing_version = version_by_document.setdefault(document_id, version_id)
        if existing_version != version_id:
            return "EVIDENCE_SET_CROSS_VERSION"
        if active_document_versions.get(document_id) != version_id:
            return "EVIDENCE_VERSION_NOT_CURRENT"
        if active_chunk_identities.get(chunk_id) != (document_id, version_id):
            return "EVIDENCE_CHUNK_IDENTITY_NOT_CURRENT"
        if not _evidence_text(item):
            return "BOUND_EVIDENCE_TEXT_EMPTY"
    return None


def _valid_adjacent_positions(
    citation_ids: tuple[int, ...],
    evidence: Sequence[Mapping[str, Any]],
    *,
    expected_owner_id: str,
    active_document_versions: Mapping[str, str],
    active_chunk_identities: Mapping[str, tuple[str, str]],
) -> tuple[int, ...]:
    candidates: list[int] = []
    cited = set(citation_ids)
    for position, candidate in enumerate(evidence, start=1):
        if position in cited:
            continue
        if (
            _evidence_identity_failure(
                (position,),
                evidence,
                expected_owner_id=expected_owner_id,
                active_document_versions=active_document_versions,
                active_chunk_identities=active_chunk_identities,
            )
            is not None
        ):
            continue
        for bound_position in citation_ids:
            bound = evidence[bound_position - 1]
            if (
                candidate.get("document_id") == bound.get("document_id")
                and candidate.get("version_id") == bound.get("version_id")
                and _are_reciprocal_neighbors(bound, candidate)
            ):
                candidates.append(position)
                break
    return tuple(candidates)


def _are_reciprocal_neighbors(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    left_id = left.get("chunk_id")
    right_id = right.get("chunk_id")
    return (
        left.get("next_chunk_id") == right_id
        and right.get("previous_chunk_id") == left_id
    ) or (
        left.get("previous_chunk_id") == right_id
        and right.get("next_chunk_id") == left_id
    )


def _make_evidence_set(
    citation_ids: tuple[int, ...],
    evidence: Sequence[Mapping[str, Any]],
) -> EvidenceSet:
    return EvidenceSet(
        citation_ids=citation_ids,
        chunk_ids=tuple(
            str(evidence[position - 1].get("chunk_id", ""))
            for position in citation_ids
        ),
    )


def _insufficient_evidence_set(
    claim: GeneratedClaim,
    citation_ids: tuple[int, ...],
    evidence: Sequence[Mapping[str, Any]],
    reason: str,
) -> EvidenceSetRecord:
    safe_ids = tuple(
        position
        for position in citation_ids
        if 1 <= position <= len(evidence)
    )
    return EvidenceSetRecord(
        claim=claim,
        evidence_set=_make_evidence_set(safe_ids, evidence),
        status=EvidenceSetStatus.INSUFFICIENT_EVIDENCE,
        reason_codes=(reason,),
    )


def _evidence_owner_id(item: Mapping[str, Any]) -> Any:
    owner_id = item.get("owner_id")
    tenant_id = item.get("tenant_id")
    if owner_id is not None and tenant_id is not None and owner_id != tenant_id:
        return None
    return owner_id if owner_id is not None else tenant_id


def _evidence_text(item: Mapping[str, Any]) -> str:
    value = item.get("quote")
    if value is None:
        value = item.get("text")
    return value.strip() if isinstance(value, str) else ""


def _valid_contract_id(value: Any) -> bool:
    return isinstance(value, str) and _CONTRACT_ID.fullmatch(value) is not None


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
    claim_unit_facts = _number_unit_facts(claim)
    evidence_unit_facts = _number_unit_facts(evidence)
    if any(
        not values.issubset(evidence_unit_facts.get(unit, set()))
        for unit, values in claim_unit_facts.items()
    ):
        return "NUMERIC_UNIT_NOT_ESTABLISHED"
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
    if _has_any(claim_folded, _COMPARATIVE_MARKERS) and not _comparison_objects_overlap(
        claim, evidence
    ):
        return "COMPARISON_OBJECTS_NOT_ESTABLISHED"
    if _has_any(claim_folded, _NOVELTY_MARKERS) and not _has_any(
        evidence, _NOVELTY_MARKERS
    ):
        return "NOVELTY_OR_SUPERLATIVE_NOT_ESTABLISHED"
    if any(
        _has_any(claim_folded, marker_group)
        and not _has_any(evidence, marker_group)
        for marker_group in _QUALIFIER_MARKER_GROUPS
    ):
        return "QUALIFYING_CONDITION_NOT_ESTABLISHED"
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
    fragments = _claim_fragments(claim)
    return bool(fragments) and all(
        _core_overlap(fragment, evidence) for fragment in fragments
    )


def _claim_fragments(claim: str) -> tuple[str, ...]:
    return tuple(
        fragment.strip(" \t\n:：")
        for fragment in _CLAUSE_SPLIT.split(claim)
        if fragment.strip(" \t\n:：")
    )


def _comparison_objects_overlap(claim: str, evidence: str) -> bool:
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
    if claim_latin and len(claim_latin & evidence_latin) >= 2:
        return True
    claim_chinese = "".join(_CHINESE.findall(claim))
    evidence_chinese = "".join(_CHINESE.findall(evidence))
    claim_bigrams = {
        claim_chinese[index : index + 2]
        for index in range(max(0, len(claim_chinese) - 1))
    }
    evidence_bigrams = {
        evidence_chinese[index : index + 2]
        for index in range(max(0, len(evidence_chinese) - 1))
    }
    return len(claim_bigrams & evidence_bigrams) >= 2


def _has_any(value: str, markers: Sequence[str]) -> bool:
    return any(marker in value for marker in markers)
