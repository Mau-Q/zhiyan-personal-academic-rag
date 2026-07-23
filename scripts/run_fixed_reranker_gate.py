#!/usr/bin/env python3
"""Run the fixed Cross-Encoder over frozen local RRF candidates."""

from __future__ import annotations

import argparse
import json
import math
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.formal_corpus import load_manifest_and_items
from backend.evaluation.reranker import (
    FixedCrossEncoderConfig,
    build_decision,
    directory_sha256,
    load_config,
    load_document_titles,
    rerank_result,
)
from backend.evaluation.retrieval_metrics import (
    build_metrics_report,
    load_ranking_results,
)


class SentenceTransformersCrossEncoder:
    def __init__(self, *, config: FixedCrossEncoderConfig, cache_dir: Path):
        try:
            from huggingface_hub import snapshot_download
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                'reranker dependencies are missing; install with pip install -e ".[reranker]"'
            ) from exc
        model = config.model
        snapshot = snapshot_download(
            repo_id=str(model["model_id"]),
            revision=str(model["revision"]),
            cache_dir=cache_dir,
        )
        self.snapshot_path = Path(snapshot)
        self.snapshot_sha256 = directory_sha256(self.snapshot_path)
        self.encoder = CrossEncoder(
            str(self.snapshot_path),
            device=str(model["device"]),
            max_length=int(model["max_length"]),
            trust_remote_code=False,
        )
        self.batch_size = int(model["batch_size"])

    def token_lengths(self, pairs: list[tuple[str, str]]) -> list[int]:
        first, second = zip(*pairs, strict=True)
        encoded = self.encoder.tokenizer(
            list(first),
            list(second),
            add_special_tokens=True,
            truncation=False,
            padding=False,
        )
        return [len(token_ids) for token_ids in encoded["input_ids"]]

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        values = self.encoder.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        flattened = values.reshape(-1).tolist()
        return [float(value) for value in flattened]


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _portable_text_sha256(path: Path) -> str:
    normalized = path.read_text(encoding="utf-8").encode("utf-8")
    return sha256(normalized).hexdigest()


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


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    manifest, items, _ = load_manifest_and_items(args.manifest)
    selected_items = [item for item in items if item.split in config.evaluation_splits]
    items_by_id = {item.question_id: item for item in selected_items}
    chunks_value = json.loads(args.chunks.read_text(encoding="utf-8"))
    if not isinstance(chunks_value, list) or not chunks_value:
        raise ValueError("reranker chunks must be a non-empty array")
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in chunks_value}
    if len(chunks_by_id) != len(chunks_value):
        raise ValueError("reranker chunks contain duplicate identity")
    document_titles = load_document_titles(args.document_catalog)
    all_source_results = load_ranking_results(args.candidates)
    source_results = [
        result for result in all_source_results if result.question_id in items_by_id
    ]
    if {result.question_id for result in source_results} != set(items_by_id):
        raise ValueError("reranker candidate coverage does not match selected evaluation items")
    if any(result.dataset_version != manifest.dataset_version for result in source_results):
        raise ValueError("reranker candidate dataset identity drift")

    scorer = SentenceTransformersCrossEncoder(
        config=config,
        cache_dir=args.model_cache,
    )
    observations = []
    for position, source in enumerate(source_results, 1):
        item = items_by_id[source.question_id]
        observations.append(
            rerank_result(
                source=source,
                question=item.question,
                chunks_by_id=chunks_by_id,
                document_titles=document_titles,
                config=config,
                scorer=scorer,
            )
        )
        if position % 10 == 0 or position == len(source_results):
            print(
                f"fixed Cross-Encoder progress: {position}/{len(source_results)}",
                file=sys.stderr,
                flush=True,
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rankings_path = args.output_dir / "fixed_cross_encoder.jsonl"
    rankings_path.write_text(
        "".join(
            json.dumps(
                observation.result.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
            for observation in observations
        ),
        encoding="utf-8",
    )
    run_paths = {
        config.candidate_backend: args.candidates,
        "fixed_cross_encoder": rankings_path,
    }
    metrics_by_split: dict[str, Any] = {}
    for split in config.evaluation_splits:
        report = build_metrics_report(
            args.manifest,
            run_paths,
            split=split,
            k_values=list(config.metric_k_values),
        )
        metrics_by_split[split] = report
        _write_json(args.output_dir / f"{split}-metrics.json", report)
    primary_metrics = metrics_by_split[str(config.decision_policy["primary_split"])]
    decision = build_decision(metrics_report=primary_metrics, config=config)
    reranker_latencies = [
        observation.reranker_latency_ms
        for observation in observations
        if observation.pair_count
    ]
    decision["latency"] = {
        "device": config.model["device"],
        "reranker_query_count": len(reranker_latencies),
        "reranker_latency_ms_p50": round(_percentile(reranker_latencies, 0.50) or 0, 6),
        "reranker_latency_ms_p95": round(_percentile(reranker_latencies, 0.95) or 0, 6),
        "target_hardware_gate": "PENDING_WINDOWS_RTX_4090_IF_QUALITY_RETAINED",
    }
    _write_json(args.output_dir / "decision.json", decision)
    report = {
        "schema_version": "fixed_cross_encoder_run_report_v1",
        "dataset_version": manifest.dataset_version,
        "item_count": len(selected_items),
        "evaluation_splits": list(config.evaluation_splits),
        "candidate_backend": config.candidate_backend,
        "candidate_top_k": config.candidate_top_k,
        "output_top_k": config.output_top_k,
        "pair_count": sum(observation.pair_count for observation in observations),
        "truncated_pair_count": sum(
            observation.truncated_pair_count for observation in observations
        ),
        "maximum_pair_tokens": max(
            (observation.maximum_pair_tokens for observation in observations),
            default=0,
        ),
        "model": {
            **dict(config.model),
            "snapshot_sha256": scorer.snapshot_sha256,
        },
        "input_sha256": {
            "config": _portable_text_sha256(args.config),
            "manifest": _sha256(args.manifest),
            "chunks": _sha256(args.chunks),
            "candidates": _sha256(args.candidates),
            "document_catalog": _portable_text_sha256(args.document_catalog),
        },
        "output_sha256": {
            "rankings": _sha256(rankings_path),
            "decision": _sha256(args.output_dir / "decision.json"),
        },
        "decision": decision["decision"],
        "boundary": "LOCAL_PRIVATE_RUNTIME_FIXED_CANDIDATE_RERANKER_GATE",
    }
    _write_json(args.output_dir / "run-report.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--document-catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "evaluation/reranker/fixed-cross-encoder-v1.json",
    )
    parser.add_argument(
        "--model-cache",
        type=Path,
        default=ROOT / "runtime/models/huggingface",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = run(args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"fixed Cross-Encoder gate error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
