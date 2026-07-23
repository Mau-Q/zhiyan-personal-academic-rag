"""Fixed Cross-Encoder reranking over frozen retrieval candidates."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from backend.evaluation.retrieval_metrics import RetrievalRankingResultV1


CONFIG_KEYS = {
    "schema_version",
    "run_id",
    "candidate_backend",
    "candidate_top_k",
    "output_top_k",
    "evaluation_splits",
    "metric_k_values",
    "model",
    "decision_policy",
}
MODEL_KEYS = {
    "provider",
    "model_id",
    "revision",
    "max_length",
    "batch_size",
    "device",
    "trust_remote_code",
    "input_template",
}
DECISION_KEYS = {
    "primary_split",
    "baseline_backend",
    "minimum_relative_ndcg_at_10_gain",
    "minimum_precision_at_5_delta",
    "critical_question_types",
    "maximum_critical_ndcg_at_10_regression",
}


class CrossEncoderScorer(Protocol):
    def score(self, pairs: Sequence[tuple[str, str]]) -> list[float]: ...

    def token_lengths(self, pairs: Sequence[tuple[str, str]]) -> list[int]: ...


@dataclass(frozen=True)
class FixedCrossEncoderConfig:
    run_id: str
    candidate_backend: str
    candidate_top_k: int
    output_top_k: int
    evaluation_splits: tuple[str, ...]
    metric_k_values: tuple[int, ...]
    model: Mapping[str, Any]
    decision_policy: Mapping[str, Any]


@dataclass(frozen=True)
class RerankObservation:
    result: RetrievalRankingResultV1
    reranker_latency_ms: float
    pair_count: int
    truncated_pair_count: int
    maximum_pair_tokens: int


def load_config(path: Path) -> FixedCrossEncoderConfig:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != CONFIG_KEYS:
        raise ValueError("fixed Cross-Encoder config fields are invalid")
    if value["schema_version"] != "fixed_cross_encoder_config_v1":
        raise ValueError("unsupported fixed Cross-Encoder config")
    model = value["model"]
    decision = value["decision_policy"]
    if not isinstance(model, dict) or set(model) != MODEL_KEYS:
        raise ValueError("fixed Cross-Encoder model fields are invalid")
    if not isinstance(decision, dict) or set(decision) != DECISION_KEYS:
        raise ValueError("fixed Cross-Encoder decision fields are invalid")
    if model["provider"] != "sentence_transformers_cross_encoder":
        raise ValueError("unsupported fixed Cross-Encoder provider")
    if model["input_template"] != "question_title_section_text_v1":
        raise ValueError("unsupported fixed Cross-Encoder input template")
    if model["trust_remote_code"] is not False:
        raise ValueError("fixed Cross-Encoder must not trust remote code")
    for field in ("model_id", "revision", "device"):
        if not isinstance(model[field], str) or not model[field]:
            raise ValueError(f"fixed Cross-Encoder model {field} is invalid")
    if not isinstance(model["max_length"], int) or model["max_length"] < 32:
        raise ValueError("fixed Cross-Encoder max_length is invalid")
    if not isinstance(model["batch_size"], int) or model["batch_size"] < 1:
        raise ValueError("fixed Cross-Encoder batch_size is invalid")
    for field in ("run_id", "candidate_backend"):
        if not isinstance(value[field], str) or not value[field]:
            raise ValueError(f"fixed Cross-Encoder {field} is invalid")
    metric_k_values = value["metric_k_values"]
    if (
        not isinstance(metric_k_values, list)
        or not metric_k_values
        or any(not isinstance(item, int) or item < 1 for item in metric_k_values)
        or metric_k_values != sorted(set(metric_k_values))
    ):
        raise ValueError("fixed Cross-Encoder metric K values are invalid")
    if not isinstance(value["candidate_top_k"], int) or value["candidate_top_k"] < 10:
        raise ValueError("fixed Cross-Encoder candidate_top_k is invalid")
    if (
        not isinstance(value["output_top_k"], int)
        or value["output_top_k"] < max(metric_k_values)
        or value["output_top_k"] > value["candidate_top_k"]
    ):
        raise ValueError("fixed Cross-Encoder output_top_k is invalid")
    evaluation_splits = value["evaluation_splits"]
    if (
        not isinstance(evaluation_splits, list)
        or not evaluation_splits
        or any(split not in {"dev", "test"} for split in evaluation_splits)
        or len(set(evaluation_splits)) != len(evaluation_splits)
    ):
        raise ValueError("fixed Cross-Encoder evaluation splits are invalid")
    if decision["primary_split"] not in {"dev", "test"}:
        raise ValueError("fixed Cross-Encoder primary split must be dev or test")
    if decision["primary_split"] not in evaluation_splits:
        raise ValueError("fixed Cross-Encoder primary split is not evaluated")
    if decision["baseline_backend"] != value["candidate_backend"]:
        raise ValueError("fixed Cross-Encoder baseline backend is inconsistent")
    for field in (
        "minimum_relative_ndcg_at_10_gain",
        "minimum_precision_at_5_delta",
        "maximum_critical_ndcg_at_10_regression",
    ):
        if not isinstance(decision[field], (int, float)) or not math.isfinite(
            decision[field]
        ):
            raise ValueError(f"fixed Cross-Encoder decision {field} is invalid")
    critical_types = decision["critical_question_types"]
    if (
        not isinstance(critical_types, list)
        or not critical_types
        or any(not isinstance(item, str) or not item for item in critical_types)
        or len(set(critical_types)) != len(critical_types)
    ):
        raise ValueError("fixed Cross-Encoder critical question types are invalid")
    return FixedCrossEncoderConfig(
        run_id=value["run_id"],
        candidate_backend=value["candidate_backend"],
        candidate_top_k=value["candidate_top_k"],
        output_top_k=value["output_top_k"],
        evaluation_splits=tuple(evaluation_splits),
        metric_k_values=tuple(metric_k_values),
        model=dict(model),
        decision_policy=dict(decision),
    )


def load_document_titles(path: Path) -> dict[str, str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    documents = value.get("documents") if isinstance(value, dict) else None
    if not isinstance(documents, list):
        raise ValueError("document catalog has no documents")
    titles: dict[str, str] = {}
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("document catalog entry is invalid")
        arxiv_id = document.get("arxiv_id")
        title = document.get("title")
        if not isinstance(arxiv_id, str) or not arxiv_id:
            raise ValueError("document catalog arxiv_id is invalid")
        if not isinstance(title, str) or not title:
            raise ValueError("document catalog title is invalid")
        document_id = f"doc_arxiv_{arxiv_id.replace('.', '_')}"
        if document_id in titles:
            raise ValueError("document catalog contains duplicate document identity")
        titles[document_id] = title
    return titles


def build_passage(
    chunk: Mapping[str, Any],
    document_titles: Mapping[str, str],
) -> str:
    document_id = chunk.get("document_id")
    section_path = chunk.get("section_path")
    text = chunk.get("text")
    if not isinstance(document_id, str) or document_id not in document_titles:
        raise ValueError("reranker Chunk has no frozen document title")
    if not isinstance(section_path, str) or not section_path:
        raise ValueError("reranker Chunk section_path is invalid")
    if not isinstance(text, str) or not text:
        raise ValueError("reranker Chunk text is invalid")
    return (
        f"Title: {document_titles[document_id]}\n"
        f"Section: {section_path}\n"
        f"{text}"
    )


def rerank_result(
    *,
    source: RetrievalRankingResultV1,
    question: str,
    chunks_by_id: Mapping[str, Mapping[str, Any]],
    document_titles: Mapping[str, str],
    config: FixedCrossEncoderConfig,
    scorer: CrossEncoderScorer,
) -> RerankObservation:
    if source.backend != config.candidate_backend:
        raise ValueError("reranker source backend does not match frozen config")
    if source.decision != "EVIDENCE_FOUND":
        result = source.model_copy(
            update={
                "run_id": config.run_id,
                "backend": "fixed_cross_encoder",
                "top_k": config.output_top_k,
                "latency_ms": source.latency_ms,
            }
        )
        return RerankObservation(
            result=result,
            reranker_latency_ms=0.0,
            pair_count=0,
            truncated_pair_count=0,
            maximum_pair_tokens=0,
        )

    candidates = source.candidates[: config.candidate_top_k]
    pairs: list[tuple[str, str]] = []
    for candidate in candidates:
        chunk = chunks_by_id.get(candidate.chunk_id)
        if chunk is None:
            raise ValueError(f"reranker candidate Chunk is missing: {candidate.chunk_id}")
        if chunk.get("document_id") != candidate.document_id:
            raise ValueError("reranker candidate document identity drift")
        pairs.append((question, build_passage(chunk, document_titles)))

    token_lengths = scorer.token_lengths(pairs)
    if len(token_lengths) != len(pairs) or any(
        not isinstance(length, int) or length < 1 for length in token_lengths
    ):
        raise ValueError("reranker tokenizer returned invalid lengths")
    started = time.perf_counter()
    scores = scorer.score(pairs)
    reranker_latency_ms = (time.perf_counter() - started) * 1000
    if len(scores) != len(candidates) or any(not math.isfinite(score) for score in scores):
        raise ValueError("reranker returned invalid scores")

    ranked = sorted(
        zip(candidates, scores, strict=True),
        key=lambda value: (-value[1], value[0].rank),
    )[: config.output_top_k]
    result = RetrievalRankingResultV1.model_validate(
        {
            "schema_version": "retrieval_ranking_result_v1",
            "run_id": config.run_id,
            "dataset_version": source.dataset_version,
            "question_id": source.question_id,
            "backend": "fixed_cross_encoder",
            "top_k": config.output_top_k,
            "decision": source.decision,
            "latency_ms": source.latency_ms + reranker_latency_ms,
            "candidates": [
                {
                    "rank": rank,
                    "chunk_id": candidate.chunk_id,
                    "document_id": candidate.document_id,
                    "score": float(score),
                }
                for rank, (candidate, score) in enumerate(ranked, 1)
            ],
        }
    )
    max_length = int(config.model["max_length"])
    return RerankObservation(
        result=result,
        reranker_latency_ms=reranker_latency_ms,
        pair_count=len(pairs),
        truncated_pair_count=sum(length > max_length for length in token_lengths),
        maximum_pair_tokens=max(token_lengths, default=0),
    )


def directory_sha256(path: Path) -> str:
    files = sorted(
        (
            (item.relative_to(path).as_posix(), item)
            for item in path.rglob("*")
            if item.is_file()
        ),
        key=lambda value: value[0],
    )
    if not files:
        raise ValueError("model snapshot is empty")
    digest = sha256()
    for relative_path, file_path in files:
        relative = relative_path.encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        file_hasher = sha256()
        with file_path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                file_hasher.update(block)
        file_digest = file_hasher.digest()
        digest.update(file_digest)
    return digest.hexdigest()


def _relative_gain(candidate: float, baseline: float) -> float:
    if baseline == 0:
        return math.inf if candidate > 0 else 0.0
    return (candidate - baseline) / baseline


def build_decision(
    *,
    metrics_report: Mapping[str, Any],
    config: FixedCrossEncoderConfig,
) -> dict[str, Any]:
    policy = config.decision_policy
    baseline_label = str(policy["baseline_backend"])
    reranker_label = "fixed_cross_encoder"
    runs = metrics_report.get("runs")
    if not isinstance(runs, dict):
        raise ValueError("reranker metrics report has no runs")
    baseline = runs.get(baseline_label)
    reranker = runs.get(reranker_label)
    if not isinstance(baseline, dict) or not isinstance(reranker, dict):
        raise ValueError("reranker metrics report is missing compared runs")
    baseline_metrics = baseline.get("metrics")
    reranker_metrics = reranker.get("metrics")
    if not isinstance(baseline_metrics, dict) or not isinstance(reranker_metrics, dict):
        raise ValueError("reranker metrics report has invalid metric objects")
    baseline_ndcg = float(baseline_metrics["ndcg@10"])
    reranker_ndcg = float(reranker_metrics["ndcg@10"])
    baseline_precision = float(baseline_metrics["precision@5"])
    reranker_precision = float(reranker_metrics["precision@5"])
    relative_ndcg_gain = _relative_gain(reranker_ndcg, baseline_ndcg)
    precision_delta = reranker_precision - baseline_precision

    critical_results: dict[str, Any] = {}
    baseline_types = baseline.get("by_question_type")
    reranker_types = reranker.get("by_question_type")
    if not isinstance(baseline_types, dict) or not isinstance(reranker_types, dict):
        raise ValueError("reranker metrics report has invalid question-type metrics")
    maximum_regression = float(policy["maximum_critical_ndcg_at_10_regression"])
    critical_pass = True
    for question_type in policy["critical_question_types"]:
        baseline_entry = baseline_types.get(question_type)
        reranker_entry = reranker_types.get(question_type)
        if not isinstance(baseline_entry, dict) or not isinstance(reranker_entry, dict):
            raise ValueError(f"reranker metrics are missing critical type: {question_type}")
        delta = float(reranker_entry["ndcg@10"]) - float(baseline_entry["ndcg@10"])
        passed = delta >= -maximum_regression
        critical_pass = critical_pass and passed
        critical_results[question_type] = {
            "eligible_count": reranker_entry["eligible_count"],
            "ndcg_at_10_delta": round(delta, 6),
            "passed": passed,
        }

    ndcg_pass = relative_ndcg_gain >= float(
        policy["minimum_relative_ndcg_at_10_gain"]
    )
    precision_pass = precision_delta >= float(policy["minimum_precision_at_5_delta"])
    retain = ndcg_pass and precision_pass and critical_pass
    return {
        "schema_version": "fixed_cross_encoder_decision_v1",
        "primary_split": policy["primary_split"],
        "baseline_backend": baseline_label,
        "candidate_backend": reranker_label,
        "quality": {
            "baseline_ndcg_at_10": baseline_ndcg,
            "reranker_ndcg_at_10": reranker_ndcg,
            "relative_ndcg_at_10_gain": round(relative_ndcg_gain, 6),
            "minimum_relative_ndcg_at_10_gain": policy[
                "minimum_relative_ndcg_at_10_gain"
            ],
            "ndcg_gate_passed": ndcg_pass,
            "baseline_precision_at_5": baseline_precision,
            "reranker_precision_at_5": reranker_precision,
            "precision_at_5_delta": round(precision_delta, 6),
            "minimum_precision_at_5_delta": policy["minimum_precision_at_5_delta"],
            "precision_gate_passed": precision_pass,
            "critical_question_types": critical_results,
            "critical_gate_passed": critical_pass,
        },
        "decision": (
            "RETAIN_FIXED_CROSS_ENCODER_PENDING_TARGET_HARDWARE_P95"
            if retain
            else "FALLBACK_TO_LOCAL_RRF"
        ),
        "default_online_route_changed": False,
        "boundary": "LOCAL_ENGINEERING_EVALUATION_NOT_PRODUCTION_ACCEPTANCE",
    }
