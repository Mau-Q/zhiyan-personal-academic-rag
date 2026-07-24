"""Offline multilingual NLI candidate evaluation without online RAG coupling."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, MutableSequence, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol


class NliCandidateError(ValueError):
    """Stable failure for invalid NLI configuration or scorer output."""


class NliLabel(StrEnum):
    ENTAILMENT = "entailment"
    NEUTRAL = "neutral"
    CONTRADICTION = "contradiction"


@dataclass(frozen=True)
class NliCandidateConfig:
    run_id: str
    model: Mapping[str, Any]
    inputs: Mapping[str, Any]
    benchmark: Mapping[str, Any]
    decision_policy: Mapping[str, Any]
    scope: Mapping[str, Any]


@dataclass(frozen=True)
class NliPair:
    key: str
    premise: str
    hypothesis: str
    question_id: str = ""
    claim_id: str = ""
    chunk_id: str = ""


@dataclass(frozen=True)
class PositiveClaimGroup:
    pair_keys: tuple[str, ...]


@dataclass(frozen=True)
class NliObservation:
    pair_key: str
    label: NliLabel
    probabilities: tuple[float, float, float]
    token_length: int


class NliScorer(Protocol):
    def score(self, pairs: Sequence[tuple[str, str]]) -> Sequence[Sequence[float]]: ...

    def token_lengths(self, pairs: Sequence[tuple[str, str]]) -> Sequence[int]: ...


_TOP_LEVEL_KEYS = {
    "schema_version",
    "run_id",
    "model",
    "inputs",
    "benchmark",
    "decision_policy",
    "scope",
}
_MODEL_KEYS = {
    "provider",
    "model_id",
    "revision",
    "snapshot_sha256",
    "allowed_files",
    "max_length",
    "batch_size",
    "label_mapping",
    "input_template",
    "trust_remote_code",
    "mac_execution",
    "remote_device",
    "remote_dtype",
}
_INPUT_KEYS = {
    "candidate_review_path",
    "candidate_review_sha256",
    "private_package_sha256",
    "private_input_member",
    "private_input_sha256",
    "private_input_schema_version",
    "question_count",
    "split",
    "candidate_relation_counts",
}
_BENCHMARK_KEYS = {
    "pair_count",
    "repetitions",
    "warmup_repetitions",
    "latency_scope",
}
_DECISION_KEYS = {
    "minimum_candidate_supported_retention",
    "minimum_human_finalized_positive_retention",
    "pass_decision",
    "fail_decision",
    "candidate_pass_enables_online_enforcement",
}
_SCOPE_KEYS = {
    "competition_rag_core",
    "knowledge_base_integration",
    "frontend",
    "demo",
    "test",
    "acceptance",
    "online_enforcement",
}


def load_nli_candidate_config(path: Path) -> NliCandidateConfig:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != _TOP_LEVEL_KEYS:
        raise NliCandidateError("NLI_CONFIG_FIELDS_INVALID")
    if value["schema_version"] != "phase4_multilingual_nli_candidate_config_v1":
        raise NliCandidateError("NLI_CONFIG_SCHEMA_INVALID")
    if value["run_id"] != "phase4-multilingual-nli-rtx4090-v1":
        raise NliCandidateError("NLI_CONFIG_RUN_ID_INVALID")
    for field, expected in (
        ("model", _MODEL_KEYS),
        ("inputs", _INPUT_KEYS),
        ("benchmark", _BENCHMARK_KEYS),
        ("decision_policy", _DECISION_KEYS),
        ("scope", _SCOPE_KEYS),
    ):
        if not isinstance(value[field], dict) or set(value[field]) != expected:
            raise NliCandidateError(f"NLI_CONFIG_{field.upper()}_INVALID")

    model = value["model"]
    if (
        model["provider"] != "sentence_transformers_cross_encoder"
        or model["model_id"]
        != "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
        or model["revision"] != "b5113eb38ab63efdd7f280f8c144ea8b13f978ce"
        or model["snapshot_sha256"]
        != "7e973b42bf69d9475c065d4deb04745659badf94ce054fd1de0f9cc1caeeafd5"
        or model["input_template"] != "evidence_premise_claim_hypothesis_v1"
        or model["trust_remote_code"] is not False
        or model["mac_execution"] != "FAKE_SCORER_ONLY"
        or model["remote_device"] != "cuda"
        or model["remote_dtype"] != "float16"
        or model["label_mapping"]
        != ["entailment", "neutral", "contradiction"]
    ):
        raise NliCandidateError("NLI_MODEL_BOUNDARY_INVALID")
    for field in ("model_id", "revision", "snapshot_sha256"):
        if not isinstance(model[field], str) or not model[field]:
            raise NliCandidateError(f"NLI_MODEL_{field.upper()}_INVALID")
    allowed_files = model["allowed_files"]
    if (
        not isinstance(allowed_files, list)
        or not allowed_files
        or any(
            not isinstance(item, str)
            or not item
            or Path(item).is_absolute()
            or ".." in Path(item).parts
            for item in allowed_files
        )
        or allowed_files != sorted(set(allowed_files))
        or "model.safetensors" not in allowed_files
        or "pytorch_model.bin" in allowed_files
    ):
        raise NliCandidateError("NLI_MODEL_ALLOWED_FILES_INVALID")
    if (
        type(model["max_length"]) is not int
        or model["max_length"] != 512
        or type(model["batch_size"]) is not int
        or model["batch_size"] < 1
    ):
        raise NliCandidateError("NLI_MODEL_BATCH_OR_LENGTH_INVALID")

    inputs = value["inputs"]
    if (
        inputs["split"] != "dev"
        or inputs["question_count"] != 105
        or not inputs["private_input_member"].endswith(".jsonl")
        or inputs["candidate_relation_counts"]
        != {
            "SUPPORTED": 21,
            "PARTIALLY_SUPPORTED": 1,
            "NOT_APPLICABLE": 8,
        }
    ):
        raise NliCandidateError("NLI_INPUT_SCOPE_INVALID")
    for field in (
        "candidate_review_sha256",
        "private_package_sha256",
        "private_input_sha256",
    ):
        digest = inputs[field]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise NliCandidateError(f"NLI_INPUT_{field.upper()}_INVALID")

    benchmark = value["benchmark"]
    if (
        type(benchmark["pair_count"]) is not int
        or benchmark["pair_count"] < 1
        or type(benchmark["repetitions"]) is not int
        or benchmark["repetitions"] < 30
        or type(benchmark["warmup_repetitions"]) is not int
        or benchmark["warmup_repetitions"] < 1
        or benchmark["latency_scope"] != "NLI_PAIR_SCORING_ONLY_NOT_ONLINE_RAG"
    ):
        raise NliCandidateError("NLI_BENCHMARK_INVALID")

    decision = value["decision_policy"]
    for field in (
        "minimum_candidate_supported_retention",
        "minimum_human_finalized_positive_retention",
    ):
        threshold = decision[field]
        if (
            not isinstance(threshold, (int, float))
            or isinstance(threshold, bool)
            or not math.isfinite(threshold)
            or not 0 < threshold <= 1
        ):
            raise NliCandidateError(f"NLI_DECISION_{field.upper()}_INVALID")
    if decision["candidate_pass_enables_online_enforcement"] is not False:
        raise NliCandidateError("NLI_ONLINE_ENFORCEMENT_MUST_REMAIN_DISABLED")

    scope = value["scope"]
    if scope != {
        "competition_rag_core": "IN_SCOPE",
        "knowledge_base_integration": "OUT_OF_SCOPE_OTHER_OWNER",
        "frontend": "OUT_OF_SCOPE",
        "demo": "OUT_OF_SCOPE",
        "test": "NOT_READ_NOT_RUN",
        "acceptance": "NOT_READ_NOT_RUN",
        "online_enforcement": "DISABLED",
    }:
        raise NliCandidateError("NLI_SCOPE_INVALID")
    return NliCandidateConfig(
        run_id=value["run_id"],
        model=dict(model),
        inputs=dict(inputs),
        benchmark=dict(benchmark),
        decision_policy=dict(decision),
        scope=dict(scope),
    )


def _softmax(logits: Sequence[float]) -> tuple[float, float, float]:
    if (
        len(logits) != 3
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in logits
        )
    ):
        raise NliCandidateError("NLI_SCORER_LOGITS_INVALID")
    maximum = max(float(value) for value in logits)
    exponentials = [math.exp(float(value) - maximum) for value in logits]
    denominator = sum(exponentials)
    return tuple(value / denominator for value in exponentials)  # type: ignore[return-value]


def _label(probabilities: Sequence[float]) -> NliLabel:
    position = max(range(3), key=lambda index: probabilities[index])
    return (
        NliLabel.ENTAILMENT,
        NliLabel.NEUTRAL,
        NliLabel.CONTRADICTION,
    )[position]


def evaluate_nli_candidate(
    *,
    config: NliCandidateConfig,
    pairs: Sequence[NliPair],
    candidate_supported_pair_keys: Sequence[str],
    candidate_partial_pair_keys: Sequence[str],
    human_positive_claims: Sequence[PositiveClaimGroup],
    scorer: NliScorer,
    observation_sink: MutableSequence[NliObservation] | None = None,
) -> dict[str, Any]:
    if not pairs:
        raise NliCandidateError("NLI_WORKLOAD_EMPTY")
    pair_by_key = {pair.key: pair for pair in pairs}
    if len(pair_by_key) != len(pairs):
        raise NliCandidateError("NLI_WORKLOAD_PAIR_KEY_DUPLICATE")
    for pair in pairs:
        if not pair.key or not pair.premise.strip() or not pair.hypothesis.strip():
            raise NliCandidateError("NLI_WORKLOAD_PAIR_INVALID")
    ordered = [pair_by_key[key] for key in sorted(pair_by_key)]
    text_pairs = [(pair.premise, pair.hypothesis) for pair in ordered]
    token_lengths = list(scorer.token_lengths(text_pairs))
    logits = list(scorer.score(text_pairs))
    if len(token_lengths) != len(ordered) or len(logits) != len(ordered):
        raise NliCandidateError("NLI_SCORER_OUTPUT_COUNT_INVALID")
    if any(type(length) is not int or length < 1 for length in token_lengths):
        raise NliCandidateError("NLI_SCORER_TOKEN_LENGTH_INVALID")
    probabilities_by_key: dict[str, tuple[float, float, float]] = {}
    labels: dict[str, NliLabel] = {}
    for pair, row, token_length in zip(
        ordered, logits, token_lengths, strict=True
    ):
        probabilities = _softmax(row)
        label = _label(probabilities)
        probabilities_by_key[pair.key] = probabilities
        labels[pair.key] = label
        if observation_sink is not None:
            observation_sink.append(
                NliObservation(
                    pair_key=pair.key,
                    label=label,
                    probabilities=probabilities,
                    token_length=token_length,
                )
            )

    supported_keys = tuple(candidate_supported_pair_keys)
    partial_keys = tuple(candidate_partial_pair_keys)
    if (
        not supported_keys
        or len(set(supported_keys)) != len(supported_keys)
        or len(set(partial_keys)) != len(partial_keys)
        or any(key not in labels for key in (*supported_keys, *partial_keys))
    ):
        raise NliCandidateError("NLI_CANDIDATE_KEY_SCOPE_INVALID")
    candidate_retained = sum(
        labels[key] is NliLabel.ENTAILMENT for key in supported_keys
    )
    partial_labels = Counter(labels[key].value for key in partial_keys)

    if not human_positive_claims:
        raise NliCandidateError("NLI_HUMAN_POSITIVE_SCOPE_EMPTY")
    human_retained = 0
    for group in human_positive_claims:
        if (
            not group.pair_keys
            or len(set(group.pair_keys)) != len(group.pair_keys)
            or any(key not in labels for key in group.pair_keys)
        ):
            raise NliCandidateError("NLI_HUMAN_POSITIVE_GROUP_INVALID")
        human_retained += any(
            labels[key] is NliLabel.ENTAILMENT for key in group.pair_keys
        )

    candidate_retention = candidate_retained / len(supported_keys)
    human_retention = human_retained / len(human_positive_claims)
    decision_policy = config.decision_policy
    eligible = (
        candidate_retention
        >= decision_policy["minimum_candidate_supported_retention"]
        and human_retention
        >= decision_policy["minimum_human_finalized_positive_retention"]
    )
    label_counts = Counter(label.value for label in labels.values())
    return {
        "schema_version": "phase4_multilingual_nli_candidate_report_v1",
        "run_id": config.run_id,
        "model": {
            "model_id": config.model["model_id"],
            "revision": config.model["revision"],
            "max_length": config.model["max_length"],
            "batch_size": config.model["batch_size"],
            "label_mapping": list(config.model["label_mapping"]),
            "input_template": config.model["input_template"],
        },
        "workload": {
            "unique_pair_count": len(ordered),
            "truncated_pair_count": sum(
                length > config.model["max_length"] for length in token_lengths
            ),
            "maximum_pair_tokens": max(token_lengths),
            "label_counts": dict(sorted(label_counts.items())),
        },
        "positive_diagnostics": {
            "candidate_supported_total": len(supported_keys),
            "candidate_supported_retained": candidate_retained,
            "candidate_supported_retention": round(candidate_retention, 6),
            "candidate_partial_total": len(partial_keys),
            "candidate_partial_label_counts": dict(sorted(partial_labels.items())),
            "human_finalized_positive_total": len(human_positive_claims),
            "human_finalized_positive_retained": human_retained,
            "human_finalized_positive_retention": round(human_retention, 6),
        },
        "unavailable_metrics": {
            "negative_rejection": "NOT_MEASURABLE_NO_HUMAN_ADJUDICATED_NEGATIVES",
            "precision": "NOT_MEASURABLE_NO_HUMAN_ADJUDICATED_NEGATIVES",
            "human_agreement": "NOT_MEASURABLE_AI_ASSISTED_CANDIDATE",
        },
        "decision": {
            "positive_retention_gate": "PASS" if eligible else "FAIL",
            "decision": (
                decision_policy["pass_decision"]
                if eligible
                else decision_policy["fail_decision"]
            ),
            "online_enforcement_enabled": False,
            "candidate_promoted_to_truth": False,
        },
        "scope": dict(config.scope),
        "contains_private_text": False,
    }
