"""Contracts and fail-closed validation for the formal retrieval evaluation corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)


Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
DatasetSplit = Literal["dev", "test", "acceptance", "online_hard_cases"]
QuestionType = Literal[
    "exact_lookup",
    "single_document_fact",
    "single_document_explanation",
    "cross_document_semantic",
    "comparison",
    "multi_hop",
    "teaching_explanation",
    "standards_freshness",
    "no_answer_evidence_insufficient",
    "adversarial_security",
]
Answerability = Literal[
    "ANSWERABLE",
    "PARTIALLY_ANSWERABLE",
    "NO_EVIDENCE",
    "CONFLICTING_EVIDENCE",
    "FORBIDDEN",
]
AnnotationStatus = Literal[
    "DRAFT",
    "GPT_ASSISTED",
    "DOUBLE_ANNOTATED",
    "ADJUDICATED",
    "EXPERT_REVIEWED",
]
ENGINEERING_TARGET_ITEMS = 500
ENGINEERING_HUMAN_AUDIT_MIN_RATIO = 0.10


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationTurnV1(StrictModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ExpectedFiltersV1(StrictModel):
    document_ids: list[Identifier] = Field(default_factory=list)
    year_gte: int | None = Field(default=None, ge=1000, le=9999)
    year_lte: int | None = Field(default=None, ge=1000, le=9999)

    @field_validator("document_ids")
    @classmethod
    def document_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("document_ids must contain unique values")
        return value

    @model_validator(mode="after")
    def year_range_must_be_ordered(self) -> "ExpectedFiltersV1":
        if self.year_gte is not None and self.year_lte is not None:
            if self.year_gte > self.year_lte:
                raise ValueError("year_gte must be <= year_lte")
        return self


class ChunkJudgmentV1(StrictModel):
    chunk_id: Identifier
    document_id: Identifier
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    relevance: int = Field(ge=0, le=3)
    supports_claims: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_chunk_judgment(self) -> "ChunkJudgmentV1":
        if self.page_start > self.page_end:
            raise ValueError("page_start must be <= page_end")
        if len(self.supports_claims) != len(set(self.supports_claims)):
            raise ValueError("supports_claims must contain unique values")
        return self


class ReferenceClaimV1(StrictModel):
    claim_id: Identifier
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    required: bool


class EvaluationItemV1(StrictModel):
    schema_version: Literal["retrieval_evaluation_item_v1"]
    dataset_version: Identifier
    question_id: Identifier
    split: DatasetSplit
    leakage_group_id: Identifier
    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
    ]
    conversation_history: list[ConversationTurnV1] = Field(default_factory=list)
    authorized_scope_ids: list[Identifier]
    question_types: list[QuestionType] = Field(min_length=1)
    language: Literal["zh", "en", "mixed"]
    query_form: Literal["short", "long", "typo", "abbreviation", "multi_turn"]
    expected_route: Identifier
    expected_filters: ExpectedFiltersV1
    answerability: Answerability
    chunk_judgments: list[ChunkJudgmentV1]
    reference_claims: list[ReferenceClaimV1]
    acceptable_answer_points: list[str]
    must_not_claim: list[str]
    expected_citations: list[Identifier]
    freshness_cutoff: str | None
    difficulty: Literal["easy", "medium", "hard"]
    annotation_status: AnnotationStatus
    annotation_record_ids: list[Identifier]
    final_annotation_id: Identifier | None
    agreement_score: float | None = Field(default=None, ge=0.0, le=1.0)
    blind_holdout: bool

    @field_validator(
        "authorized_scope_ids",
        "question_types",
        "expected_citations",
        "annotation_record_ids",
    )
    @classmethod
    def lists_must_be_unique(cls, value: list[Any]) -> list[Any]:
        if len(value) != len(set(value)):
            raise ValueError("list values must be unique")
        return value

    @field_validator("freshness_cutoff")
    @classmethod
    def freshness_cutoff_must_be_iso_date(cls, value: str | None) -> str | None:
        if value is not None:
            datetime.strptime(value, "%Y-%m-%d")
        return value

    @model_validator(mode="after")
    def validate_item_semantics(self) -> "EvaluationItemV1":
        claim_ids = [claim.claim_id for claim in self.reference_claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("reference claim ids must be unique")
        chunk_ids = [judgment.chunk_id for judgment in self.chunk_judgments]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk judgment ids must be unique")
        known_claims = set(claim_ids)
        for judgment in self.chunk_judgments:
            if not set(judgment.supports_claims).issubset(known_claims):
                raise ValueError("chunk judgment references an unknown claim")
        supporting_chunks = {
            judgment.chunk_id for judgment in self.chunk_judgments if judgment.relevance >= 2
        }
        if not set(self.expected_citations).issubset(supporting_chunks):
            raise ValueError("expected_citations must reference relevance >= 2 chunks")
        needs_support = self.answerability in {
            "ANSWERABLE",
            "PARTIALLY_ANSWERABLE",
            "CONFLICTING_EVIDENCE",
        }
        if needs_support and not supporting_chunks:
            raise ValueError("answerable items require at least one relevance >= 2 chunk")
        if self.answerability in {"NO_EVIDENCE", "FORBIDDEN"} and supporting_chunks:
            raise ValueError("NO_EVIDENCE and FORBIDDEN items cannot have supporting chunks")
        if self.split == "acceptance" and not self.blind_holdout:
            raise ValueError("acceptance items must be blind_holdout")
        minimum_records = {
            "DRAFT": 0,
            "GPT_ASSISTED": 1,
            "DOUBLE_ANNOTATED": 2,
            "ADJUDICATED": 3,
            "EXPERT_REVIEWED": 3,
        }[self.annotation_status]
        if len(self.annotation_record_ids) < minimum_records:
            raise ValueError("annotation status has too few annotation records")
        if self.annotation_status in {"DRAFT", "GPT_ASSISTED", "DOUBLE_ANNOTATED"}:
            if self.final_annotation_id is not None:
                raise ValueError(
                    "DRAFT, GPT_ASSISTED, and DOUBLE_ANNOTATED items cannot have "
                    "final_annotation_id"
                )
        if self.annotation_status in {"ADJUDICATED", "EXPERT_REVIEWED"}:
            if self.final_annotation_id not in self.annotation_record_ids:
                raise ValueError("final_annotation_id must reference an annotation record")
        return self


class AnnotationRecordV1(StrictModel):
    schema_version: Literal["retrieval_annotation_record_v1"]
    annotation_id: Identifier
    dataset_version: Identifier
    question_id: Identifier
    role: Literal["ANNOTATOR", "ADJUDICATOR", "EXPERT_REVIEWER"]
    annotator_id: Identifier
    actor_type: Literal["HUMAN", "GPT", "FIXTURE"] = "FIXTURE"
    model_identity: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
    ] | None = None
    prompt_version: Identifier | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, allow_inf_nan=False)
    submitted_at: datetime
    answerability: Answerability
    expected_route: Identifier
    chunk_judgments: list[ChunkJudgmentV1]
    notes: Annotated[str, StringConstraints(max_length=4000)]
    based_on_annotation_ids: list[Identifier]

    @field_validator("based_on_annotation_ids")
    @classmethod
    def based_on_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("based_on_annotation_ids must contain unique values")
        return value

    @field_validator("submitted_at")
    @classmethod
    def submitted_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("submitted_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_role_lineage(self) -> "AnnotationRecordV1":
        model_fields = (self.model_identity, self.prompt_version, self.temperature)
        if self.actor_type == "GPT" and any(value is None for value in model_fields):
            raise ValueError(
                "GPT annotations require model_identity, prompt_version, and temperature"
            )
        if self.actor_type != "GPT" and any(value is not None for value in model_fields):
            raise ValueError("only GPT annotations may declare model execution fields")
        if self.actor_type == "GPT" and self.role != "ANNOTATOR":
            raise ValueError("GPT may assist annotation but cannot arbitrate or expert-review")
        if self.role == "ANNOTATOR" and self.based_on_annotation_ids:
            raise ValueError("independent annotators cannot depend on prior annotations")
        if self.role == "ADJUDICATOR" and len(self.based_on_annotation_ids) < 2:
            raise ValueError("adjudicator must reference two independent annotations")
        if self.role == "EXPERT_REVIEWER" and not self.based_on_annotation_ids:
            raise ValueError("expert reviewer must reference prior review lineage")
        return self


def _reviewer_identity(record: AnnotationRecordV1) -> tuple[str, str]:
    if record.actor_type == "GPT":
        return record.actor_type, record.model_identity or ""
    return record.actor_type, record.annotator_id


def _record_matches_item(record: AnnotationRecordV1, item: EvaluationItemV1) -> bool:
    return (
        record.answerability == item.answerability
        and record.expected_route == item.expected_route
        and record.chunk_judgments == item.chunk_judgments
    )


class SourceSnapshotV1(StrictModel):
    corpus_id: Identifier
    corpus_sha256: Sha256
    chunk_snapshot_sha256: Sha256
    created_at: datetime


class SplitPolicyV1(StrictModel):
    dev_ratio: float = Field(ge=0.0, le=1.0)
    test_ratio: float = Field(ge=0.0, le=1.0)
    acceptance_ratio: float = Field(ge=0.0, le=1.0)
    ratio_tolerance: float = Field(ge=0.0, le=0.1)
    acceptance_blind: Literal[True]
    online_hard_cases_separate: Literal[True]

    @model_validator(mode="after")
    def primary_split_ratios_must_sum_to_one(self) -> "SplitPolicyV1":
        total = self.dev_ratio + self.test_ratio + self.acceptance_ratio
        if abs(total - 1.0) > 1e-9:
            raise ValueError("dev/test/acceptance ratios must sum to 1")
        return self


class StratumTargetV1(StrictModel):
    question_type: QuestionType
    min_ratio: float = Field(ge=0.0, le=1.0)
    max_ratio: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def ratio_range_must_be_ordered(self) -> "StratumTargetV1":
        if self.min_ratio > self.max_ratio:
            raise ValueError("min_ratio must be <= max_ratio")
        return self


class QualityGatesV1(StrictModel):
    minimum_independent_annotators: int = Field(ge=2)
    relevance_scale: Literal["0_3"]
    expert_review_question_types: list[QuestionType]
    expert_review_difficulties: list[Literal["easy", "medium", "hard"]]


class EvaluationManifestV1(StrictModel):
    schema_version: Literal["retrieval_evaluation_manifest_v1"]
    dataset_id: Identifier
    dataset_version: Identifier
    status: Literal["DESIGN_READY", "DATA_COLLECTION", "ANNOTATION", "LOCKED", "RETIRED"]
    target_size: int = Field(ge=200, le=500)
    source_snapshot: SourceSnapshotV1
    items_path: str
    items_sha256: Sha256
    annotation_records_path: str | None
    annotation_records_sha256: Sha256 | None
    split_policy: SplitPolicyV1
    stratification_targets: list[StratumTargetV1]
    quality_gates: QualityGatesV1

    @field_validator("items_path", "annotation_records_path")
    @classmethod
    def paths_must_be_relative(cls, value: str | None) -> str | None:
        if value is not None and (Path(value).is_absolute() or ".." in Path(value).parts):
            raise ValueError("evaluation artifact paths must stay relative to the manifest")
        return value

    @model_validator(mode="after")
    def annotation_path_and_hash_must_pair(self) -> "EvaluationManifestV1":
        if (self.annotation_records_path is None) != (self.annotation_records_sha256 is None):
            raise ValueError("annotation path and hash must both be set or both be null")
        target_types = [target.question_type for target in self.stratification_targets]
        if len(target_types) != len(set(target_types)):
            raise ValueError("stratification target types must be unique")
        return self


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_jsonl(path: Path, model: type[BaseModel]) -> list[Any]:
    records: list[Any] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            records.append(model.model_validate(json.loads(raw_line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"invalid record at {path}:{line_number}: {exc}") from exc
    return records


def load_manifest_and_items(
    manifest_path: Path,
) -> tuple[EvaluationManifestV1, list[EvaluationItemV1], list[AnnotationRecordV1]]:
    try:
        manifest = EvaluationManifestV1.model_validate(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid evaluation manifest: {exc}") from exc
    base = manifest_path.parent
    items_path = base / manifest.items_path
    if sha256_file(items_path) != manifest.items_sha256:
        raise ValueError("evaluation items SHA-256 does not match manifest")
    items = _load_jsonl(items_path, EvaluationItemV1)
    annotations: list[AnnotationRecordV1] = []
    if manifest.annotation_records_path is not None:
        annotations_path = base / manifest.annotation_records_path
        if sha256_file(annotations_path) != manifest.annotation_records_sha256:
            raise ValueError("annotation records SHA-256 does not match manifest")
        annotations = _load_jsonl(annotations_path, AnnotationRecordV1)
    return manifest, items, annotations


def validate_corpus(manifest_path: Path) -> dict[str, Any]:
    manifest, items, annotations = load_manifest_and_items(manifest_path)
    blockers: list[str] = []
    question_ids = [item.question_id for item in items]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("evaluation question_id values must be unique")
    question_id_set = set(question_ids)
    if any(item.dataset_version != manifest.dataset_version for item in items):
        raise ValueError("evaluation item dataset_version does not match manifest")

    leakage_splits: dict[str, set[str]] = defaultdict(set)
    low_risk_dev_test_count = 0
    low_risk_dev_test_human_reviewed = 0
    for item in items:
        leakage_splits[item.leakage_group_id].add(item.split)
    leaking = sorted(group for group, splits in leakage_splits.items() if len(splits) > 1)
    if leaking:
        raise ValueError(f"leakage groups span multiple splits: {','.join(leaking)}")

    split_counts = Counter(item.split for item in items)
    primary_items = [item for item in items if item.split != "online_hard_cases"]
    type_counts = Counter(
        question_type for item in primary_items for question_type in item.question_types
    )
    primary_count = len(primary_items)
    if primary_count < manifest.target_size:
        blockers.append(
            f"primary_item_count {primary_count} is below target_size {manifest.target_size}"
        )
    if manifest.status == "LOCKED" and primary_count != manifest.target_size:
        blockers.append("LOCKED corpus must contain exactly target_size primary items")

    if primary_count:
        for split, target in (
            ("dev", manifest.split_policy.dev_ratio),
            ("test", manifest.split_policy.test_ratio),
            ("acceptance", manifest.split_policy.acceptance_ratio),
        ):
            observed = split_counts[split] / primary_count
            if abs(observed - target) > manifest.split_policy.ratio_tolerance:
                blockers.append(f"{split} split ratio {observed:.4f} is outside tolerance")
    for target in manifest.stratification_targets:
        observed = type_counts[target.question_type] / primary_count if primary_count else 0.0
        if not target.min_ratio <= observed <= target.max_ratio:
            blockers.append(
                f"{target.question_type} ratio {observed:.4f} is outside "
                f"[{target.min_ratio:.4f}, {target.max_ratio:.4f}]"
            )

    annotation_by_id = {record.annotation_id: record for record in annotations}
    if len(annotation_by_id) != len(annotations):
        raise ValueError("annotation_id values must be unique")
    referenced_annotation_ids = {
        annotation_id for item in items for annotation_id in item.annotation_record_ids
    }
    orphan_annotation_ids = sorted(set(annotation_by_id) - referenced_annotation_ids)
    if orphan_annotation_ids:
        raise ValueError(
            "annotation records are not referenced by an evaluation item: "
            + ",".join(orphan_annotation_ids)
        )
    for record in annotations:
        if record.question_id not in question_id_set:
            raise ValueError("annotation record references an unknown question_id")
        if record.dataset_version != manifest.dataset_version:
            raise ValueError("annotation record dataset_version does not match manifest")
        parents = []
        for parent_id in record.based_on_annotation_ids:
            parent = annotation_by_id.get(parent_id)
            if parent is None:
                raise ValueError(f"annotation references missing parent: {parent_id}")
            if parent.question_id != record.question_id:
                raise ValueError("annotation lineage crosses question_id")
            parents.append(parent)
        if record.role == "ADJUDICATOR":
            if any(parent.role != "ANNOTATOR" for parent in parents):
                raise ValueError("adjudicator parents must be independent annotations")
            if len({_reviewer_identity(parent) for parent in parents}) < 2:
                raise ValueError("adjudicator parents must have independent reviewers")
        if record.role == "EXPERT_REVIEWER":
            direct_consensus = (
                len(parents) >= 2
                and all(parent.role == "ANNOTATOR" for parent in parents)
                and len({_reviewer_identity(parent) for parent in parents}) >= 2
            )
            adjudicated_conflict = (
                len(parents) == 1 and parents[0].role == "ADJUDICATOR"
            )
            if not (direct_consensus or adjudicated_conflict):
                raise ValueError(
                    "expert reviewer must reference independent annotations or adjudication"
                )
    for item in items:
        records = []
        for annotation_id in item.annotation_record_ids:
            record = annotation_by_id.get(annotation_id)
            if record is None:
                blockers.append(f"{item.question_id} references missing annotation {annotation_id}")
                continue
            if record.question_id != item.question_id:
                raise ValueError("annotation record question_id does not match item")
            if record.dataset_version != manifest.dataset_version:
                raise ValueError("annotation record dataset_version does not match manifest")
            records.append(record)
        independent_records = [record for record in records if record.role == "ANNOTATOR"]
        independent = {_reviewer_identity(record) for record in independent_records}
        if len(independent) < manifest.quality_gates.minimum_independent_annotators:
            blockers.append(f"{item.question_id} lacks two independent reviewers")
        independent_humans = {
            record.annotator_id
            for record in independent_records
            if record.actor_type == "HUMAN"
        }
        if len(independent_humans) < manifest.quality_gates.minimum_independent_annotators:
            blockers.append(
                f"{item.question_id} formal corpus requires two human annotators"
            )
        if item.annotation_status == "DRAFT":
            blockers.append(f"{item.question_id} is still draft")
        if item.annotation_status == "GPT_ASSISTED":
            blockers.append(
                f"{item.question_id} formal corpus requires double-human status"
            )
            gpt_records = [
                record for record in independent_records if record.actor_type == "GPT"
            ]
            if not gpt_records:
                blockers.append(f"{item.question_id} GPT_ASSISTED item lacks GPT annotation")
            if any(
                not _record_matches_item(record, item) for record in independent_records
            ):
                blockers.append(
                    f"{item.question_id} GPT-assisted labels require conflict review"
                )
        if item.agreement_score is None and item.annotation_status != "GPT_ASSISTED":
            blockers.append(f"{item.question_id} lacks agreement_score")
        elif item.agreement_score is not None and item.agreement_score < 1.0:
            if item.annotation_status not in {"ADJUDICATED", "EXPERT_REVIEWED"}:
                blockers.append(f"{item.question_id} has conflict requiring adjudication")
        elif item.annotation_status == "DOUBLE_ANNOTATED":
            if any(
                not _record_matches_item(record, item) for record in independent_records
            ):
                blockers.append(
                    f"{item.question_id} consensus labels do not match independent reviews"
                )
        needs_expert = (
            item.difficulty in manifest.quality_gates.expert_review_difficulties
            or bool(
                set(item.question_types)
                & set(manifest.quality_gates.expert_review_question_types)
            )
        )
        if needs_expert and item.annotation_status != "EXPERT_REVIEWED":
            blockers.append(f"{item.question_id} requires expert review")
        needs_human = item.split == "acceptance"
        if needs_human and not any(record.actor_type == "HUMAN" for record in records):
            blockers.append(f"{item.question_id} requires human review")
        is_low_risk_dev_test = (
            item.split in {"dev", "test"}
            and item.difficulty != "hard"
            and not needs_expert
        )
        if is_low_risk_dev_test:
            low_risk_dev_test_count += 1
            if any(record.actor_type == "HUMAN" for record in records):
                low_risk_dev_test_human_reviewed += 1
        if item.final_annotation_id is not None:
            final_record = annotation_by_id.get(item.final_annotation_id)
            if final_record is None:
                blockers.append(f"{item.question_id} final annotation is missing")
            else:
                expected_role = (
                    "EXPERT_REVIEWER"
                    if item.annotation_status == "EXPERT_REVIEWED"
                    else "ADJUDICATOR"
                )
                if final_record.role != expected_role:
                    blockers.append(f"{item.question_id} final annotation role is invalid")
                if final_record.actor_type != "HUMAN":
                    blockers.append(
                        f"{item.question_id} final arbitration or expert review must be human"
                    )
                if not _record_matches_item(final_record, item):
                    blockers.append(f"{item.question_id} final labels do not match annotation")

    engineering_blockers = [
        blocker
        for blocker in blockers
        if not blocker.startswith("primary_item_count ")
        and not blocker.startswith("LOCKED corpus ")
        and "formal corpus requires two human annotators" not in blocker
        and "formal corpus requires double-human status" not in blocker
        and "lacks two independent reviewers" not in blocker
    ]
    if primary_count != ENGINEERING_TARGET_ITEMS:
        engineering_blockers.append(
            f"primary_item_count {primary_count} does not equal GPT-assisted target "
            f"{ENGINEERING_TARGET_ITEMS}"
        )
    audit_ratio = (
        low_risk_dev_test_human_reviewed / low_risk_dev_test_count
        if low_risk_dev_test_count
        else 0.0
    )
    if audit_ratio < ENGINEERING_HUMAN_AUDIT_MIN_RATIO:
        engineering_blockers.append(
            f"low-risk dev/test human audit ratio {audit_ratio:.4f} is below "
            f"{ENGINEERING_HUMAN_AUDIT_MIN_RATIO:.4f}"
        )
    lock_ready = not blockers
    engineering_ready = not engineering_blockers
    return {
        "schema_version": "retrieval_evaluation_validation_report_v1",
        "dataset_id": manifest.dataset_id,
        "dataset_version": manifest.dataset_version,
        "status": manifest.status,
        "target_size": manifest.target_size,
        "item_count": len(items),
        "primary_item_count": primary_count,
        "online_hard_case_count": split_counts["online_hard_cases"],
        "engineering_target_size": ENGINEERING_TARGET_ITEMS,
        "low_risk_dev_test_count": low_risk_dev_test_count,
        "low_risk_dev_test_human_reviewed": low_risk_dev_test_human_reviewed,
        "low_risk_dev_test_human_audit_ratio": round(audit_ratio, 6),
        "engineering_ready": engineering_ready,
        "engineering_blockers": engineering_blockers,
        "annotation_record_count": len(annotations),
        "split_counts": dict(sorted(split_counts.items())),
        "question_type_counts": dict(sorted(type_counts.items())),
        "leakage_group_count": len(leakage_splits),
        "lock_ready": lock_ready,
        "blockers": blockers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a formal retrieval evaluation corpus")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-lock-ready", action="store_true")
    parser.add_argument("--require-engineering-ready", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = validate_corpus(args.manifest)
    except (OSError, ValueError) as exc:
        print(f"formal evaluation corpus error: {exc}", file=sys.stderr)
        return 2
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(
            f"formal corpus report={args.output}; "
            f"engineering_ready={report['engineering_ready']}; "
            f"lock_ready={report['lock_ready']}"
        )
    if args.require_engineering_ready and not report["engineering_ready"]:
        return 1
    if (args.require_lock_ready or report["status"] == "LOCKED") and not report["lock_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
