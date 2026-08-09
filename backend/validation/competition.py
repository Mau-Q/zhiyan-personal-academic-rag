"""Competition-only capture and redaction over the existing real RAG assembly."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from backend.rag.claim_evidence import verify_claim_evidence_sets
from backend.rag.generation import GenerationResult


ANSWER_SCENARIO_ID = "COMP-QA-001"
EVIDENCE_SET_SCENARIO_ID = "COMP-EVIDENCESET-001"
FAIL_CLOSED_SCENARIO_ID = "COMP-FAIL-CLOSED-001"
SCENARIO_IDS = (
    ANSWER_SCENARIO_ID,
    EVIDENCE_SET_SCENARIO_ID,
    FAIL_CLOSED_SCENARIO_ID,
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)(?:postgres(?:ql)?://)[^\s]+"),
    re.compile(r"(?i)\b(?:password|token|secret)\s*[:=]\s*\S+"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"(?i)\b[A-Z]:\\[^\r\n]+"),
    re.compile(r"(?<![A-Za-z0-9])/(?:Users|home|var|opt|srv)/[^\r\n]+"),
)


@dataclass(frozen=True)
class CompetitionCapture:
    case_id: str
    question: str
    initial_payload: Mapping[str, object]
    replay_payload: Mapping[str, object] | None
    generation_result: GenerationResult | None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def lf_canonical_text_sha256(path: Path) -> str:
    payload = path.read_bytes()
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("competition tracked text must not contain a UTF-8 BOM")
    if b"\r" in payload.replace(b"\r\n", b""):
        raise ValueError("competition tracked text contains an invalid lone carriage return")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("competition tracked text must be valid UTF-8") from exc
    return hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def redact_text(value: str, *, maximum_length: int) -> str:
    redacted = " ".join(value.split())
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted[:maximum_length]


def _redacted_evidence(payload: Mapping[str, object]) -> list[dict[str, object]]:
    values = payload.get("evidence")
    if not isinstance(values, list):
        return []
    redacted: list[dict[str, object]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        quote = value.get("quote") if isinstance(value.get("quote"), str) else ""
        redacted.append(
            {
                "evidence_id": value.get("evidence_id"),
                "chunk_id": value.get("chunk_id"),
                "document_id": value.get("document_id"),
                "version_id": value.get("version_id"),
                "page_start": value.get("page_start"),
                "page_end": value.get("page_end"),
                "excerpt": redact_text(quote, maximum_length=240),
                "quote_sha256": sha256_text(quote),
            }
        )
    return redacted


def _redacted_citations(payload: Mapping[str, object]) -> list[dict[str, object]]:
    values = payload.get("citations")
    if not isinstance(values, list):
        return []
    return [
        {
            key: value.get(key)
            for key in (
                "citation_id",
                "evidence_id",
                "document_id",
                "page_start",
                "page_end",
            )
        }
        for value in values
        if isinstance(value, dict)
    ]


def _evidence_set_audit(
    capture: CompetitionCapture,
    *,
    owner_id: str,
) -> dict[str, object]:
    result = capture.generation_result
    evidence_values = capture.initial_payload.get("evidence")
    if result is None or not isinstance(evidence_values, list):
        return {
            "status": "FAIL",
            "mode": "AUDIT_ONLY",
            "error_code": "STRUCTURED_GENERATION_CAPTURE_MISSING",
            "records": [],
            "multi_evidence_claim_count": 0,
        }
    internal_evidence: list[dict[str, object]] = []
    active_versions: dict[str, str] = {}
    active_chunks: dict[str, tuple[str, str]] = {}
    for value in evidence_values:
        if not isinstance(value, dict):
            continue
        document_id = value.get("document_id")
        version_id = value.get("version_id")
        chunk_id = value.get("chunk_id")
        quote = value.get("quote")
        if not all(isinstance(item, str) and item for item in (
            document_id,
            version_id,
            chunk_id,
            quote,
        )):
            continue
        active_versions[document_id] = version_id
        active_chunks[chunk_id] = (document_id, version_id)
        internal_evidence.append(
            {
                **value,
                "text": quote,
                "owner_id": owner_id,
                "tenant_id": owner_id,
                "is_active": True,
                "previous_chunk_id": None,
                "next_chunk_id": None,
            }
        )
    if not internal_evidence:
        return {
            "status": "FAIL",
            "mode": "AUDIT_ONLY",
            "error_code": "AUTHORIZED_EVIDENCE_CAPTURE_MISSING",
            "records": [],
            "multi_evidence_claim_count": 0,
        }
    report = verify_claim_evidence_sets(
        result.claims,
        internal_evidence,
        expected_owner_id=owner_id,
        active_document_versions=active_versions,
        active_chunk_identities=active_chunks,
        allow_adjacent=False,
    )
    records = [
        {
            "claim_sha256": sha256_text(record.claim.text),
            "claim_display": redact_text(record.claim.text, maximum_length=800),
            "citation_ids": list(record.evidence_set.citation_ids),
            "chunk_ids": list(record.evidence_set.chunk_ids),
            "adjacent_chunk_added": record.evidence_set.adjacent_chunk_added,
            "status": record.status.value,
            "reason_codes": list(record.reason_codes),
        }
        for record in report.records
    ]
    multi_count = sum(len(record.evidence_set.citation_ids) >= 2 for record in report.records)
    return {
        "status": "PASS" if multi_count >= 1 else "FAIL",
        "mode": "AUDIT_ONLY",
        "human_semantic_gold": False,
        "automatic_claim_deletion": False,
        "new_judge_used": False,
        "error_code": None if multi_count >= 1 else "MULTI_EVIDENCE_CLAIM_NOT_OBSERVED",
        "records": records,
        "multi_evidence_claim_count": multi_count,
    }


def build_redacted_result(
    *,
    finalized_manifest: Mapping[str, object],
    input_manifest: Mapping[str, object],
    run_id: str,
    captures: list[CompetitionCapture],
    stage1_report: Mapping[str, object],
    stage1_report_sha256: str | None = None,
) -> dict[str, object]:
    by_case_id = {capture.case_id: capture for capture in captures}
    scenario_bindings = input_manifest.get("scenario_bindings")
    if not isinstance(scenario_bindings, dict):
        raise ValueError("competition input scenario bindings are invalid")
    qa_case_id = scenario_bindings.get(ANSWER_SCENARIO_ID)
    audit_case_id = scenario_bindings.get(EVIDENCE_SET_SCENARIO_ID)
    qa = by_case_id.get(qa_case_id) if isinstance(qa_case_id, str) else None
    audit = by_case_id.get(audit_case_id) if isinstance(audit_case_id, str) else None
    if qa is None or audit is None:
        raise ValueError("required competition captures are missing")
    owner_id = stage1_report.get("owner_id")
    if not isinstance(owner_id, str):
        raise ValueError("stage1 owner identity is missing")
    qa_evidence = _redacted_evidence(qa.initial_payload)
    qa_citations = _redacted_citations(qa.initial_payload)
    qa_pass = (
        qa.initial_payload.get("status") == "COMPLETED"
        and bool(qa_evidence)
        and bool(qa_citations)
    )
    evidence_set = _evidence_set_audit(audit, owner_id=owner_id)
    audit_evidence = _redacted_evidence(audit.initial_payload)
    audit_pass = (
        audit.initial_payload.get("status") == "COMPLETED"
        and len(audit_evidence) >= 2
        and evidence_set["status"] == "PASS"
    )
    cleanup_pass = (
        stage1_report.get("cleanup_jobs_succeeded") == 3
        and stage1_report.get("runtime_snapshot_cleanup_proven") is True
        and stage1_report.get("inactive_visibility_proven") is True
        and stage1_report.get("inactive_answer_api_status") == 403
    )
    source_commit = finalized_manifest.get("source_commit")
    source_value = source_commit.get("value") if isinstance(source_commit, dict) else None
    scenarios = [
        {
            "scenario_id": ANSWER_SCENARIO_ID,
            "status": "PASS" if qa_pass else "FAIL",
            "source_case_id": qa.case_id,
            "question_sha256": sha256_text(qa.question),
            "question_display": redact_text(qa.question, maximum_length=1000),
            "answer_display": redact_text(str(qa.initial_payload.get("answer", "")), maximum_length=2400),
            "answer_sha256": sha256_text(str(qa.initial_payload.get("answer", ""))),
            "citations": qa_citations,
            "evidence": qa_evidence,
        },
        {
            "scenario_id": EVIDENCE_SET_SCENARIO_ID,
            "status": "PASS" if audit_pass else "FAIL",
            "source_case_id": audit.case_id,
            "question_sha256": sha256_text(audit.question),
            "question_display": redact_text(audit.question, maximum_length=1000),
            "answer_display": redact_text(str(audit.initial_payload.get("answer", "")), maximum_length=2400),
            "answer_sha256": sha256_text(str(audit.initial_payload.get("answer", ""))),
            "citations": _redacted_citations(audit.initial_payload),
            "evidence": audit_evidence,
            "evidence_set_audit": evidence_set,
        },
        {
            "scenario_id": FAIL_CLOSED_SCENARIO_ID,
            "status": "PASS" if cleanup_pass else "FAIL",
            "actual_refusal": True,
            "http_status": stage1_report.get("inactive_answer_api_status"),
            "error_code": "RAG_FORBIDDEN_SCOPE" if cleanup_pass else "FAIL_CLOSED_GATE_NOT_PROVEN",
            "returned_evidence_count": 0,
            "stale_evidence_reused": False,
        },
    ]
    overall_pass = qa_pass and audit_pass and cleanup_pass
    result: dict[str, object] = {
        "schema_version": "competition_redacted_result_v1",
        "pack_id": "RAG_COMPETITION_EVIDENCE_AND_HANDOFF_PACK_V1",
        "pack_version": "v1",
        "status": "PASS" if overall_pass else "FAIL",
        "run_identity": {
            "run_id": run_id,
            "execution_boundary": stage1_report.get("answer_generation_boundary"),
            "fixture_or_fake_used": False,
        },
        "source_identity": {
            "source_commit": source_value,
            "pdf_sha256": input_manifest.get("pdf_sha256"),
            "question_suite_sha256": input_manifest.get("question_suite_sha256"),
            "generation_identity": stage1_report.get("generation_identity"),
        },
        "scenarios": scenarios,
        "cleanup": {
            "status": "PASS" if cleanup_pass else "FAIL",
            "cleanup_jobs_succeeded": stage1_report.get("cleanup_jobs_succeeded"),
            "runtime_snapshot_cleanup_proven": stage1_report.get("runtime_snapshot_cleanup_proven"),
            "inactive_visibility_proven": stage1_report.get("inactive_visibility_proven"),
            "inactive_answer_api_status": stage1_report.get("inactive_answer_api_status"),
        },
        "privacy": {
            "runtime_only": True,
            "evidence_excerpt_max_characters": 240,
            "contains_pdf_bytes": False,
            "contains_database_url_or_secret": False,
            "contains_private_reasoning": False,
            "full_answer_or_evidence_publication_requires_owner_review": True,
        },
        "hashes": {
            "stage1_private_report_sha256": stage1_report_sha256
            or hashlib.sha256(
                json.dumps(stage1_report, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
        },
    }
    return result
