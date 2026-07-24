#!/usr/bin/env python3
"""Run the frozen multilingual NLI positive-retention Gate on RTX 4090."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.claim_evidence_nli import (
    NliCandidateConfig,
    NliCandidateError,
    NliPair,
    NliScorer,
    PositiveClaimGroup,
    evaluate_nli_candidate,
    load_nli_candidate_config,
)
from backend.evaluation.reranker import directory_sha256


DEFAULT_CONFIG = (
    ROOT / "evaluation/claim_evidence/phase4-multilingual-nli-rtx4090-v1.json"
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lf_canonical_sha256(path: Path) -> str:
    payload = path.read_bytes()
    if b"\r" in payload.replace(b"\r\n", b""):
        raise NliCandidateError("NLI_TEXT_LINE_ENDING_INVALID")
    return hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise NliCandidateError("NLI_BENCHMARK_VALUES_EMPTY")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _pair_key(question_id: str, claim_id: str, chunk_id: str) -> str:
    value = f"{question_id}\0{claim_id}\0{chunk_id}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _load_private_rows(
    path: Path, config: NliCandidateConfig
) -> dict[str, dict[str, Any]]:
    if not path.is_file() or _sha256(path) != config.inputs["private_input_sha256"]:
        raise NliCandidateError("NLI_PRIVATE_INPUT_HASH_DRIFT")
    rows: dict[str, dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(raw)
        if (
            row.get("schema_version")
            != config.inputs["private_input_schema_version"]
            or row.get("split") != "dev"
        ):
            raise NliCandidateError("NLI_PRIVATE_INPUT_SCOPE_INVALID")
        question_id = row.get("question_id")
        if not isinstance(question_id, str) or question_id in rows:
            raise NliCandidateError("NLI_PRIVATE_INPUT_ID_INVALID")
        rows[question_id] = row
    if len(rows) != config.inputs["question_count"]:
        raise NliCandidateError("NLI_PRIVATE_INPUT_COUNT_INVALID")
    return rows


def _load_candidate_reviews(
    path: Path, config: NliCandidateConfig
) -> list[dict[str, str]]:
    if (
        not path.is_file()
        or _lf_canonical_sha256(path)
        != config.inputs["candidate_review_sha256"]
    ):
        raise NliCandidateError("NLI_CANDIDATE_REVIEW_HASH_DRIFT")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_FIELDS:
            raise NliCandidateError("NLI_CANDIDATE_REVIEW_HEADER_INVALID")
        rows = list(reader)
    if (
        len({row["question_id"] for row in rows}) != 30
        or Counter(row["relation"] for row in rows)
        != config.inputs["candidate_relation_counts"]
    ):
        raise NliCandidateError("NLI_CANDIDATE_REVIEW_SCOPE_INVALID")
    return rows


def build_workload(
    *,
    private_rows: Mapping[str, Mapping[str, Any]],
    reviews: Sequence[Mapping[str, str]],
    expected_candidate_supported: int = 21,
    expected_candidate_partial: int = 1,
    expected_human_positives: int = 225,
) -> tuple[
    list[NliPair],
    list[str],
    list[str],
    list[PositiveClaimGroup],
]:
    pairs: dict[str, NliPair] = {}

    def add_pair(
        question_id: str,
        claim_id: str,
        chunk_id: str,
        premise: str,
        hypothesis: str,
    ) -> str:
        key = _pair_key(question_id, claim_id, chunk_id)
        pair = NliPair(key=key, premise=premise, hypothesis=hypothesis)
        existing = pairs.get(key)
        if existing is not None and existing != pair:
            raise NliCandidateError("NLI_PAIR_IDENTITY_COLLISION")
        pairs[key] = pair
        return key

    candidate_supported: list[str] = []
    candidate_partial: list[str] = []
    for review in reviews:
        item = private_rows.get(review["question_id"])
        if item is None:
            raise NliCandidateError("NLI_REVIEW_QUESTION_NOT_IN_INPUT")
        labels = item["final_labels"]
        answerability = labels["answerability"]
        relation = review["relation"]
        if relation == "NOT_APPLICABLE":
            if (
                answerability not in {"NO_EVIDENCE", "FORBIDDEN"}
                or review["claim_id"]
                or review["chunk_id"]
                or review["citation_complete"] != "true"
            ):
                raise NliCandidateError("NLI_NOT_APPLICABLE_INVALID")
            continue
        if answerability not in {"ANSWERABLE", "PARTIALLY_ANSWERABLE"}:
            raise NliCandidateError("NLI_REVIEW_ANSWERABILITY_INVALID")
        claims = {
            claim["claim_id"]: claim["text"]
            for claim in labels["reference_claims"]
        }
        chunks = {
            chunk["chunk_id"]: chunk["text"]
            for chunk in item["frozen_evidence_chunks"]
        }
        claim_id = review["claim_id"]
        chunk_id = review["chunk_id"]
        if claim_id not in claims or chunk_id not in chunks:
            raise NliCandidateError("NLI_REVIEW_CLAIM_OR_CHUNK_NOT_IN_INPUT")
        key = add_pair(
            review["question_id"],
            claim_id,
            chunk_id,
            chunks[chunk_id],
            claims[claim_id],
        )
        if relation == "SUPPORTED":
            candidate_supported.append(key)
        elif relation == "PARTIALLY_SUPPORTED":
            candidate_partial.append(key)
        else:
            raise NliCandidateError("NLI_UNADJUDICATED_NEGATIVE_FORBIDDEN")

    human_positive_claims: list[PositiveClaimGroup] = []
    for question_id, item in private_rows.items():
        labels = item["final_labels"]
        claims = {
            claim["claim_id"]: claim["text"]
            for claim in labels["reference_claims"]
        }
        chunks = {
            chunk["chunk_id"]: chunk["text"]
            for chunk in item["frozen_evidence_chunks"]
        }
        support: dict[str, list[str]] = {claim_id: [] for claim_id in claims}
        for judgment in labels["chunk_judgments"]:
            chunk_id = judgment["chunk_id"]
            if chunk_id not in chunks:
                raise NliCandidateError("NLI_HUMAN_SUPPORT_CHUNK_NOT_IN_INPUT")
            for claim_id in judgment["supports_claims"]:
                if claim_id not in support:
                    raise NliCandidateError("NLI_HUMAN_SUPPORT_CLAIM_NOT_IN_INPUT")
                support[claim_id].append(chunk_id)
        for claim_id, chunk_ids in support.items():
            if not chunk_ids:
                raise NliCandidateError("NLI_HUMAN_POSITIVE_WITHOUT_SUPPORT")
            keys = tuple(
                add_pair(
                    question_id,
                    claim_id,
                    chunk_id,
                    chunks[chunk_id],
                    claims[claim_id],
                )
                for chunk_id in sorted(set(chunk_ids))
            )
            human_positive_claims.append(PositiveClaimGroup(pair_keys=keys))

    if (
        len(candidate_supported) != expected_candidate_supported
        or len(candidate_partial) != expected_candidate_partial
    ):
        raise NliCandidateError("NLI_CANDIDATE_RELATION_COUNT_DRIFT")
    if len(human_positive_claims) != expected_human_positives:
        raise NliCandidateError("NLI_HUMAN_POSITIVE_COUNT_DRIFT")
    return (
        sorted(pairs.values(), key=lambda pair: pair.key),
        candidate_supported,
        candidate_partial,
        human_positive_claims,
    )


class SentenceTransformersNliScorer(NliScorer):
    def __init__(self, *, config: NliCandidateConfig, cache_dir: Path):
        try:
            import torch
            from huggingface_hub import snapshot_download
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                'NLI dependencies are missing; install with pip install -e ".[reranker]"'
            ) from exc
        if not torch.cuda.is_available():
            raise NliCandidateError("NLI_CUDA_UNAVAILABLE")
        gpu_name = torch.cuda.get_device_name(0)
        if "RTX 4090" not in gpu_name:
            raise NliCandidateError("NLI_TARGET_GPU_INVALID")
        model = config.model
        snapshot = snapshot_download(
            repo_id=str(model["model_id"]),
            revision=str(model["revision"]),
            cache_dir=cache_dir,
            allow_patterns=list(model["allowed_files"]),
        )
        self.snapshot_path = Path(snapshot)
        self.snapshot_sha256 = directory_sha256(self.snapshot_path)
        if self.snapshot_sha256 != model["snapshot_sha256"]:
            raise NliCandidateError("NLI_MODEL_SNAPSHOT_HASH_DRIFT")
        self.encoder = CrossEncoder(
            str(self.snapshot_path),
            device="cuda",
            max_length=int(model["max_length"]),
            trust_remote_code=False,
            model_kwargs={"torch_dtype": torch.float16},
        )
        id2label = {
            int(key): str(value).casefold()
            for key, value in self.encoder.model.config.id2label.items()
        }
        if [id2label[index] for index in range(3)] != model["label_mapping"]:
            raise NliCandidateError("NLI_MODEL_LABEL_MAPPING_DRIFT")
        self.batch_size = int(model["batch_size"])
        self.torch = torch
        self.gpu_name = gpu_name

    def score(self, pairs: Sequence[tuple[str, str]]) -> list[list[float]]:
        values = self.encoder.predict(
            list(pairs),
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        if getattr(values, "ndim", None) != 2 or values.shape[1] != 3:
            raise NliCandidateError("NLI_MODEL_OUTPUT_SHAPE_INVALID")
        return [[float(value) for value in row] for row in values.tolist()]

    def token_lengths(self, pairs: Sequence[tuple[str, str]]) -> list[int]:
        first, second = zip(*pairs, strict=True)
        encoded = self.encoder.tokenizer(
            list(first),
            list(second),
            add_special_tokens=True,
            truncation=False,
            padding=False,
        )
        return [len(token_ids) for token_ids in encoded["input_ids"]]

    def benchmark(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        warmup_repetitions: int,
        repetitions: int,
    ) -> list[float]:
        for _ in range(warmup_repetitions):
            self.score(pairs)
        self.torch.cuda.synchronize()
        latencies: list[float] = []
        for _ in range(repetitions):
            started = time.perf_counter()
            self.score(pairs)
            self.torch.cuda.synchronize()
            latencies.append((time.perf_counter() - started) * 1000)
        return latencies


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = load_nli_candidate_config(args.config)
    if _lf_canonical_sha256(args.config) != args.config_sha256:
        raise NliCandidateError("NLI_CONFIG_HASH_DRIFT")
    candidate_path = ROOT / config.inputs["candidate_review_path"]
    private_rows = _load_private_rows(args.private_input, config)
    reviews = _load_candidate_reviews(candidate_path, config)
    pairs, supported, partial, human_claims = build_workload(
        private_rows=private_rows,
        reviews=reviews,
    )
    scorer = SentenceTransformersNliScorer(
        config=config,
        cache_dir=args.model_cache,
    )
    report = evaluate_nli_candidate(
        config=config,
        pairs=pairs,
        candidate_supported_pair_keys=supported,
        candidate_partial_pair_keys=partial,
        human_positive_claims=human_claims,
        scorer=scorer,
    )
    benchmark_pairs = [
        (pair.premise, pair.hypothesis)
        for pair in pairs[: config.benchmark["pair_count"]]
    ]
    latencies = scorer.benchmark(
        benchmark_pairs,
        warmup_repetitions=config.benchmark["warmup_repetitions"],
        repetitions=config.benchmark["repetitions"],
    )
    report["model"]["snapshot_sha256"] = scorer.snapshot_sha256
    report["runtime"] = {
        "torch_version": scorer.torch.__version__,
        "cuda_runtime": scorer.torch.version.cuda,
        "gpu_name": scorer.gpu_name,
    }
    report["benchmark"] = {
        "scope": config.benchmark["latency_scope"],
        "pair_count": len(benchmark_pairs),
        "repetitions": len(latencies),
        "latency_ms_p50": round(statistics.median(latencies), 6),
        "latency_ms_p95": round(_percentile(latencies, 0.95), 6),
    }
    report["input_sha256"] = {
        "config": args.config_sha256,
        "candidate_review": _lf_canonical_sha256(candidate_path),
        "private_input": _sha256(args.private_input),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--private-input", type=Path, required=True)
    parser.add_argument("--model-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    try:
        report = run(build_parser().parse_args())
    except NliCandidateError as exc:
        error_code = str(exc)
    except json.JSONDecodeError:
        error_code = "NLI_INPUT_JSON_INVALID"
    except OSError:
        error_code = "NLI_IO_FAILED"
    except RuntimeError:
        error_code = "NLI_RUNTIME_FAILED"
    except (KeyError, TypeError):
        error_code = "NLI_INPUT_CONTRACT_INVALID"
    else:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "decision": report["decision"]["decision"],
                    "positive_retention_gate": report["decision"][
                        "positive_retention_gate"
                    ],
                    "online_enforcement_enabled": False,
                },
                sort_keys=True,
            )
        )
        return 0
    print(
        json.dumps(
            {"status": "FAIL", "error_code": error_code},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
