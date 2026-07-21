"""Compute deterministic retrieval metrics over finalized formal evaluation labels."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from backend.evaluation.formal_corpus import EvaluationItemV1, load_manifest_and_items


Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RankedCandidateV1(StrictModel):
    rank: int = Field(ge=1)
    chunk_id: Identifier
    document_id: Identifier
    score: float | None = Field(default=None, allow_inf_nan=False)


class RetrievalRankingResultV1(StrictModel):
    schema_version: Literal["retrieval_ranking_result_v1"]
    run_id: Identifier
    dataset_version: Identifier
    question_id: Identifier
    backend: Identifier
    top_k: int = Field(ge=1)
    decision: Literal["EVIDENCE_FOUND", "NO_EVIDENCE", "FORBIDDEN"]
    latency_ms: float = Field(ge=0.0, allow_inf_nan=False)
    candidates: list[RankedCandidateV1]

    @model_validator(mode="after")
    def ranks_and_candidates_must_be_consistent(self) -> "RetrievalRankingResultV1":
        ranks = [candidate.rank for candidate in self.candidates]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("candidate ranks must be contiguous and start at 1")
        chunk_ids = [candidate.chunk_id for candidate in self.candidates]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("ranking candidates must have unique chunk_id values")
        if len(self.candidates) > self.top_k:
            raise ValueError("candidate count cannot exceed top_k")
        if self.decision == "EVIDENCE_FOUND" and not self.candidates:
            raise ValueError("EVIDENCE_FOUND results require at least one candidate")
        if self.decision != "EVIDENCE_FOUND" and self.candidates:
            raise ValueError("NO_EVIDENCE and FORBIDDEN results cannot expose candidates")
        return self


def load_ranking_results(path: Path) -> list[RetrievalRankingResultV1]:
    results: list[RetrievalRankingResultV1] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            results.append(RetrievalRankingResultV1.model_validate(json.loads(raw_line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"invalid ranking result at {path}:{line_number}: {exc}") from exc
    if not results:
        raise ValueError(f"ranking result file is empty: {path}")
    return results


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _ranking_scores(
    item: EvaluationItemV1,
    result: RetrievalRankingResultV1,
    k: int,
) -> dict[str, float]:
    relevance = {judgment.chunk_id: judgment.relevance for judgment in item.chunk_judgments}
    relevant_ids = {chunk_id for chunk_id, grade in relevance.items() if grade >= 2}
    top = result.candidates[:k]
    hits = [candidate for candidate in top if candidate.chunk_id in relevant_ids]
    recall = len(hits) / len(relevant_ids)
    precision = len(hits) / k
    reciprocal_rank = next(
        (1.0 / candidate.rank for candidate in top if candidate.chunk_id in relevant_ids),
        0.0,
    )
    dcg = sum(
        (2 ** relevance.get(candidate.chunk_id, 0) - 1) / math.log2(candidate.rank + 1)
        for candidate in top
    )
    ideal_grades = sorted(relevance.values(), reverse=True)[:k]
    ideal_dcg = sum(
        (2**grade - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(ideal_grades, 1)
    )
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    return {"recall": recall, "precision": precision, "mrr": reciprocal_rank, "ndcg": ndcg}


def _aggregate_backend(
    items: list[EvaluationItemV1],
    results: list[RetrievalRankingResultV1],
    k_values: list[int],
) -> dict[str, Any]:
    by_question = {result.question_id: result for result in results}
    expected_ids = {item.question_id for item in items}
    if set(by_question) != expected_ids or len(results) != len(by_question):
        missing = sorted(expected_ids - set(by_question))
        extra = sorted(set(by_question) - expected_ids)
        raise ValueError(f"ranking coverage mismatch; missing={missing}, extra={extra}")
    if len({result.run_id for result in results}) != 1:
        raise ValueError("ranking results must belong to exactly one run_id")
    if any(result.top_k < max(k_values) for result in results):
        raise ValueError("every ranking result top_k must cover the largest requested K")

    answerable_states = {"ANSWERABLE", "PARTIALLY_ANSWERABLE", "CONFLICTING_EVIDENCE"}
    eligible = [item for item in items if item.answerability in answerable_states]
    metric_values: dict[int, dict[str, list[float]]] = {
        k: defaultdict(list) for k in k_values
    }
    for item in eligible:
        result = by_question[item.question_id]
        for k in k_values:
            for metric, value in _ranking_scores(item, result, k).items():
                metric_values[k][metric].append(value)

    predicted_no_evidence = [
        item for item in items if by_question[item.question_id].decision == "NO_EVIDENCE"
    ]
    no_evidence_items = [item for item in items if item.answerability == "NO_EVIDENCE"]
    forbidden_items = [item for item in items if item.answerability == "FORBIDDEN"]
    wrong_refusals = [
        item
        for item in eligible
        if by_question[item.question_id].decision != "EVIDENCE_FOUND"
    ]
    latency = [by_question[item.question_id].latency_ms for item in items]
    metrics: dict[str, Any] = {}
    for k in k_values:
        for metric in ("recall", "precision", "mrr", "ndcg"):
            metrics[f"{metric}@{k}"] = _round(_mean(metric_values[k][metric]))
    metrics.update(
        {
            "no_answer_detection_recall": _round(
                sum(
                    by_question[item.question_id].decision == "NO_EVIDENCE"
                    for item in no_evidence_items
                )
                / len(no_evidence_items)
            )
            if no_evidence_items
            else None,
            "refusal_precision": _round(
                sum(item.answerability == "NO_EVIDENCE" for item in predicted_no_evidence)
                / len(predicted_no_evidence)
            )
            if predicted_no_evidence
            else None,
            "answerable_wrong_refusal_rate": _round(len(wrong_refusals) / len(eligible))
            if eligible
            else None,
            "forbidden_block_rate": _round(
                sum(
                    by_question[item.question_id].decision == "FORBIDDEN"
                    for item in forbidden_items
                )
                / len(forbidden_items)
            )
            if forbidden_items
            else None,
            "latency_ms_p50": _round(_percentile(latency, 0.50)),
            "latency_ms_p95": _round(_percentile(latency, 0.95)),
        }
    )

    by_type: dict[str, Any] = {}
    for question_type in sorted({value for item in items for value in item.question_types}):
        selected = [item for item in eligible if question_type in item.question_types]
        scores = [
            _ranking_scores(item, by_question[item.question_id], max(k_values))
            for item in selected
        ]
        by_type[question_type] = {
            "eligible_count": len(selected),
            f"recall@{max(k_values)}": _round(_mean([score["recall"] for score in scores])),
            f"ndcg@{max(k_values)}": _round(_mean([score["ndcg"] for score in scores])),
        }
    return {
        "case_count": len(items),
        "answerable_metric_count": len(eligible),
        "metrics": metrics,
        "by_question_type": by_type,
    }


def build_metrics_report(
    manifest_path: Path,
    run_paths: dict[str, Path],
    *,
    split: str,
    k_values: list[int],
) -> dict[str, Any]:
    manifest, all_items, _ = load_manifest_and_items(manifest_path)
    items = [item for item in all_items if item.split == split]
    if not items:
        raise ValueError(f"evaluation split has no items: {split}")
    run_reports: dict[str, Any] = {}
    for label, path in sorted(run_paths.items()):
        results = load_ranking_results(path)
        selected_ids = {item.question_id for item in items}
        selected = [result for result in results if result.question_id in selected_ids]
        if any(result.dataset_version != manifest.dataset_version for result in selected):
            raise ValueError("ranking dataset_version does not match manifest")
        if any(result.backend != label for result in selected):
            raise ValueError(f"ranking backend does not match --run label: {label}")
        run_reports[label] = _aggregate_backend(items, selected, k_values)

    comparisons: dict[str, Any] = {}
    labels = sorted(run_reports)
    for candidate in labels:
        comparisons[candidate] = {}
        for baseline in labels:
            if candidate == baseline:
                continue
            deltas: dict[str, float] = {}
            for metric, candidate_value in run_reports[candidate]["metrics"].items():
                baseline_value = run_reports[baseline]["metrics"].get(metric)
                if isinstance(candidate_value, (int, float)) and isinstance(
                    baseline_value, (int, float)
                ):
                    deltas[metric] = round(candidate_value - baseline_value, 6)
            comparisons[candidate][f"vs_{baseline}"] = deltas
    return {
        "schema_version": "formal_retrieval_metrics_report_v1",
        "dataset_id": manifest.dataset_id,
        "dataset_version": manifest.dataset_version,
        "split": split,
        "k_values": k_values,
        "runs": run_reports,
        "comparisons": comparisons,
        "interpretation_boundary": (
            "Retrieval-only metrics; no generation, production ANN, or acceptance sign-off"
        ),
    }


def _parse_run(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--run must use backend=path")
    label, raw_path = value.split("=", 1)
    if not label or not raw_path:
        raise argparse.ArgumentTypeError("--run must use backend=path")
    return label, Path(raw_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute formal retrieval ranking metrics")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run", action="append", type=_parse_run, required=True)
    parser.add_argument(
        "--split",
        choices=("dev", "test", "acceptance", "online_hard_cases"),
        required=True,
    )
    parser.add_argument("--k", default="3,5,10,20,50")
    parser.add_argument("--allow-acceptance", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.split == "acceptance" and not args.allow_acceptance:
        print("acceptance split requires --allow-acceptance", file=sys.stderr)
        return 2
    try:
        k_values = sorted({int(value) for value in args.k.split(",")})
        if not k_values or min(k_values) < 1:
            raise ValueError("K values must be positive")
        run_paths = dict(args.run)
        if len(run_paths) != len(args.run):
            raise ValueError("--run backend labels must be unique")
        report = build_metrics_report(
            args.manifest,
            run_paths,
            split=args.split,
            k_values=k_values,
        )
    except (OSError, ValueError) as exc:
        print(f"retrieval metrics error: {exc}", file=sys.stderr)
        return 2
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(f"retrieval metrics report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
