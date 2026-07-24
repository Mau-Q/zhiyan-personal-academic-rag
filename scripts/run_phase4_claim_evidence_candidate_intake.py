#!/usr/bin/env python3
"""Validate Member B candidate labels and measure only defensible diagnostics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from backend.rag.claim_evidence import (
    ClaimSupportStatus,
    GeneratedClaim,
    verify_claim_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = (
    ROOT / "evaluation/claim_evidence/phase4-candidate-review-intake-v1.json"
)

TAXONOMY_FIELDS = (
    "question_id",
    "split",
    "category",
    "es_passed",
    "milvus_passed",
    "primary_failure",
    "secondary_failure",
    "confidence",
    "candidate_detail_available",
    "review_status",
)
REVIEW_FIELDS = (
    "question_id",
    "claim_id",
    "chunk_id",
    "relation",
    "citation_complete",
    "confidence",
    "review_status",
)
FAILURES = frozenset(
    {
        "NONE",
        "RECALL_MISS_ES",
        "RECALL_MISS_MILVUS",
        "WRONG_DOCUMENT",
        "WRONG_PAGE",
        "PARTIAL_EVIDENCE",
        "CROSS_DOCUMENT_IMBALANCE",
        "NO_EVIDENCE_CALIBRATION",
        "SECURITY_POLICY_MISSING",
        "UNDETERMINED_NEEDS_CANDIDATE_EXPORT",
    }
)
RELATIONS = frozenset(
    {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "CONTRADICTED",
        "NOT_SUPPORTED",
        "NOT_APPLICABLE",
    }
)
CATEGORIES = frozenset({"ANSWERABLE", "NO_EVIDENCE", "FORBIDDEN"})
CONFIDENCE = frozenset({"HIGH", "MEDIUM", "LOW"})
BOOLEAN = frozenset({"true", "false"})


def _taxonomy_category(answerability: str) -> str:
    if answerability in {"ANSWERABLE", "PARTIALLY_ANSWERABLE"}:
        return "ANSWERABLE"
    if answerability in {"NO_EVIDENCE", "FORBIDDEN"}:
        return answerability
    raise CandidateIntakeError("PRIVATE_ANSWERABILITY_INVALID")


class CandidateIntakeError(ValueError):
    """Stable failure for invalid or drifting candidate-review inputs."""


def _inside_repo(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise CandidateIntakeError("ABSOLUTE_PATH_FORBIDDEN")
    resolved = (ROOT / path).resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise CandidateIntakeError("PATH_OUTSIDE_REPOSITORY") from exc
    return resolved


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_csv(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != tuple(fields):
            raise CandidateIntakeError("CSV_HEADER_INVALID")
        rows = list(reader)
    if any(None in row for row in rows):
        raise CandidateIntakeError("CSV_ROW_WIDTH_INVALID")
    return rows


def _require_unique(values: Sequence[str], code: str) -> None:
    if len(set(values)) != len(values):
        raise CandidateIntakeError(code)


def _validate_taxonomy(
    rows: Sequence[Mapping[str, str]], expected_questions: int
) -> None:
    if len(rows) != expected_questions:
        raise CandidateIntakeError("TAXONOMY_COUNT_INVALID")
    question_ids = [row["question_id"] for row in rows]
    _require_unique(question_ids, "TAXONOMY_QUESTION_DUPLICATE")
    for row in rows:
        if not row["question_id"] or row["split"] != "dev":
            raise CandidateIntakeError("TAXONOMY_ID_OR_SPLIT_INVALID")
        if row["category"] not in CATEGORIES:
            raise CandidateIntakeError("TAXONOMY_CATEGORY_INVALID")
        if (
            row["es_passed"] not in BOOLEAN
            or row["milvus_passed"] not in BOOLEAN
            or row["candidate_detail_available"] not in BOOLEAN
        ):
            raise CandidateIntakeError("TAXONOMY_BOOLEAN_INVALID")
        if row["primary_failure"] not in FAILURES:
            raise CandidateIntakeError("TAXONOMY_PRIMARY_FAILURE_INVALID")
        if row["secondary_failure"] and (
            row["secondary_failure"] not in FAILURES
            or row["secondary_failure"] == row["primary_failure"]
        ):
            raise CandidateIntakeError("TAXONOMY_SECONDARY_FAILURE_INVALID")
        if row["confidence"] not in CONFIDENCE or row["review_status"] not in {
            "REVIEWED",
            "INPUT_MISSING",
        }:
            raise CandidateIntakeError("TAXONOMY_REVIEW_METADATA_INVALID")


def _validate_reviews(
    rows: Sequence[Mapping[str, str]], expected_questions: int
) -> None:
    question_ids = [row["question_id"] for row in rows]
    if len(set(question_ids)) != expected_questions:
        raise CandidateIntakeError("REVIEW_QUESTION_COUNT_INVALID")
    for row in rows:
        if (
            not row["question_id"]
            or row["relation"] not in RELATIONS
            or row["citation_complete"] not in BOOLEAN
            or row["confidence"] not in CONFIDENCE
            or row["review_status"] not in {"REVIEWED", "INPUT_MISSING"}
        ):
            raise CandidateIntakeError("REVIEW_ROW_INVALID")
        if row["relation"] == "NOT_APPLICABLE":
            if row["claim_id"] or row["chunk_id"]:
                raise CandidateIntakeError("NOT_APPLICABLE_IDENTITIES_PRESENT")
        elif not row["claim_id"] or not row["chunk_id"]:
            raise CandidateIntakeError("REVIEW_IDENTITIES_MISSING")


def _load_private_rows(
    source: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    path = _inside_repo(str(source["path"]))
    if not path.is_file():
        raise CandidateIntakeError("PRIVATE_INPUT_MISSING")
    if _sha256(path) != source["sha256"]:
        raise CandidateIntakeError("PRIVATE_INPUT_HASH_DRIFT")
    rows: dict[str, dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(raw)
        if (
            row.get("schema_version") != source["schema_version"]
            or row.get("split") != source["split"]
        ):
            raise CandidateIntakeError("PRIVATE_INPUT_IDENTITY_INVALID")
        question_id = row.get("question_id")
        if not isinstance(question_id, str) or question_id in rows:
            raise CandidateIntakeError("PRIVATE_INPUT_QUESTION_ID_INVALID")
        rows[question_id] = row
    if len(rows) != source["question_count"]:
        raise CandidateIntakeError("PRIVATE_INPUT_COUNT_INVALID")
    return rows


def _claim_and_chunk(
    item: Mapping[str, Any], claim_id: str, chunk_id: str
) -> tuple[str, str, bool]:
    labels = item.get("final_labels")
    chunks = item.get("frozen_evidence_chunks")
    if not isinstance(labels, Mapping) or not isinstance(chunks, list):
        raise CandidateIntakeError("PRIVATE_INPUT_SHAPE_INVALID")
    claims = {
        claim["claim_id"]: claim["text"]
        for claim in labels.get("reference_claims", [])
        if isinstance(claim, Mapping)
        and isinstance(claim.get("claim_id"), str)
        and isinstance(claim.get("text"), str)
    }
    evidence = {
        chunk["chunk_id"]: chunk["text"]
        for chunk in chunks
        if isinstance(chunk, Mapping)
        and isinstance(chunk.get("chunk_id"), str)
        and isinstance(chunk.get("text"), str)
    }
    if claim_id not in claims:
        raise CandidateIntakeError("REVIEW_CLAIM_ID_NOT_IN_INPUT")
    if chunk_id not in evidence:
        raise CandidateIntakeError("REVIEW_CHUNK_ID_NOT_IN_INPUT")
    support = any(
        judgment.get("chunk_id") == chunk_id
        and claim_id in judgment.get("supports_claims", [])
        for judgment in labels.get("chunk_judgments", [])
        if isinstance(judgment, Mapping)
    )
    return claims[claim_id], evidence[chunk_id], support


def _human_positive_diagnostic(
    items: Sequence[Mapping[str, Any]],
) -> tuple[int, int]:
    total = 0
    retained = 0
    for item in items:
        labels = item["final_labels"]
        chunks = item["frozen_evidence_chunks"]
        positions = {chunk["chunk_id"]: index for index, chunk in enumerate(chunks, 1)}
        evidence = [{"quote": chunk["text"]} for chunk in chunks]
        support: dict[str, list[int]] = {
            claim["claim_id"]: [] for claim in labels["reference_claims"]
        }
        texts = {
            claim["claim_id"]: claim["text"] for claim in labels["reference_claims"]
        }
        for judgment in labels["chunk_judgments"]:
            for claim_id in judgment["supports_claims"]:
                support[claim_id].append(positions[judgment["chunk_id"]])
        for claim_id, citation_ids in support.items():
            if not citation_ids:
                raise CandidateIntakeError("HUMAN_REFERENCE_CLAIM_HAS_NO_SUPPORT")
            record = verify_claim_evidence(
                (
                    GeneratedClaim(
                        text=texts[claim_id],
                        citation_ids=tuple(sorted(set(citation_ids))),
                    ),
                ),
                evidence,
            ).records[0]
            total += 1
            retained += record.status is not ClaimSupportStatus.UNSUPPORTED
    return total, retained


def build_report(
    taxonomy: Sequence[Mapping[str, str]],
    reviews: Sequence[Mapping[str, str]],
    private_rows: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    source = policy["candidate_source"]
    _validate_taxonomy(taxonomy, source["expected_taxonomy_questions"])
    _validate_reviews(reviews, source["expected_claim_evidence_questions"])
    if set(row["question_id"] for row in taxonomy) != set(private_rows):
        raise CandidateIntakeError("TAXONOMY_PRIVATE_INPUT_SCOPE_MISMATCH")

    taxonomy_categories: Counter[str] = Counter()
    taxonomy_failures: Counter[str] = Counter()
    for row in taxonomy:
        item = private_rows[row["question_id"]]
        category = _taxonomy_category(item["final_labels"]["answerability"])
        if category != row["category"]:
            raise CandidateIntakeError("TAXONOMY_CATEGORY_MISMATCH")
        taxonomy_categories[category] += 1
        taxonomy_failures[row["primary_failure"]] += 1

    relations: Counter[str] = Counter()
    verifier_statuses: Counter[str] = Counter()
    source_alignment: Counter[str] = Counter()
    not_applicable_categories: Counter[str] = Counter()
    supported_total = 0
    supported_retained = 0
    for row in reviews:
        relation = row["relation"]
        relations[relation] += 1
        item = private_rows.get(row["question_id"])
        if item is None:
            raise CandidateIntakeError("REVIEW_QUESTION_NOT_IN_INPUT")
        category = item["final_labels"]["answerability"]
        if relation == "NOT_APPLICABLE":
            if category not in {"NO_EVIDENCE", "FORBIDDEN"}:
                raise CandidateIntakeError("NOT_APPLICABLE_CATEGORY_INVALID")
            if row["citation_complete"] != "true":
                raise CandidateIntakeError("NOT_APPLICABLE_CITATION_INVALID")
            not_applicable_categories[category] += 1
            continue
        if category not in {"ANSWERABLE", "PARTIALLY_ANSWERABLE"}:
            raise CandidateIntakeError("CLAIM_RELATION_CATEGORY_INVALID")
        claim, chunk, source_support = _claim_and_chunk(
            item, row["claim_id"], row["chunk_id"]
        )
        source_alignment[f"{relation}|source_support_{str(source_support).lower()}"] += 1
        record = verify_claim_evidence(
            (GeneratedClaim(text=claim, citation_ids=(1,)),),
            ({"quote": chunk},),
        ).records[0]
        verifier_statuses[f"{relation}|{record.status.value}"] += 1
        if relation == "SUPPORTED":
            supported_total += 1
            supported_retained += record.status is not ClaimSupportStatus.UNSUPPORTED

    human_total, human_retained = _human_positive_diagnostic(
        list(private_rows.values())
    )
    candidate_retention = supported_retained / supported_total
    human_positive_retention = human_retained / human_total
    threshold = policy["decision_policy"][
        "minimum_candidate_supported_retention_for_future_adjudication"
    ]
    return {
        "schema_version": "phase4_claim_evidence_candidate_intake_report_v1",
        "run_id": policy["run_id"],
        "candidate_status": source["status"],
        "intake": {
            "status": "PASS",
            "taxonomy_questions": len(taxonomy),
            "claim_evidence_questions": len(
                {row["question_id"] for row in reviews}
            ),
            "taxonomy_categories": dict(sorted(taxonomy_categories.items())),
            "taxonomy_primary_failures": dict(sorted(taxonomy_failures.items())),
            "claim_evidence_relations": dict(sorted(relations.items())),
            "not_applicable_categories": dict(
                sorted(not_applicable_categories.items())
            ),
            "source_alignment": dict(sorted(source_alignment.items())),
            "input_missing": sum(
                row["review_status"] == "INPUT_MISSING"
                for row in (*taxonomy, *reviews)
            ),
        },
        "diagnostics": {
            "candidate_supported_total": supported_total,
            "candidate_supported_retained": supported_retained,
            "candidate_supported_retention": round(candidate_retention, 6),
            "candidate_verifier_statuses": dict(sorted(verifier_statuses.items())),
            "human_finalized_positive_total": human_total,
            "human_finalized_positive_retained": human_retained,
            "human_finalized_positive_retention": round(
                human_positive_retention, 6
            ),
            "precision": "NOT_MEASURABLE_NO_ADJUDICATED_NEGATIVES",
            "human_agreement": "NOT_MEASURABLE_AI_ASSISTED_CANDIDATE",
        },
        "decision": {
            "candidate_supported_retention_threshold": threshold,
            "candidate_supported_retention_gate": (
                "PASS" if candidate_retention >= threshold else "FAIL"
            ),
            "default_mode": policy["decision_policy"]["safe_default"],
            "online_hard_judgment_enabled": False,
            "candidate_labels_promoted_to_truth": False,
            "reason": "HIGH_FALSE_REJECTION_RISK_AND_NO_HUMAN_ADJUDICATION",
        },
        "test": policy["private_input"]["test"],
        "acceptance": policy["private_input"]["acceptance"],
        "contains_private_text": False,
    }


def run(policy_path: Path) -> dict[str, Any]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if (
        policy.get("schema_version")
        != "phase4_claim_evidence_candidate_intake_policy_v1"
    ):
        raise CandidateIntakeError("POLICY_SCHEMA_INVALID")
    source = policy["candidate_source"]
    taxonomy_path = _inside_repo(source["failure_taxonomy_path"])
    review_path = _inside_repo(source["claim_evidence_path"])
    if _sha256(taxonomy_path) != source["failure_taxonomy_sha256"]:
        raise CandidateIntakeError("TAXONOMY_HASH_DRIFT")
    if _sha256(review_path) != source["claim_evidence_sha256"]:
        raise CandidateIntakeError("REVIEW_HASH_DRIFT")
    taxonomy = _read_csv(taxonomy_path, TAXONOMY_FIELDS)
    reviews = _read_csv(review_path, REVIEW_FIELDS)
    private_rows = _load_private_rows(policy["private_input"])
    report = build_report(taxonomy, reviews, private_rows, policy)
    report_path = _inside_repo(policy["report_path"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()
    try:
        report = run(args.policy.resolve())
    except (CandidateIntakeError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error_code": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
