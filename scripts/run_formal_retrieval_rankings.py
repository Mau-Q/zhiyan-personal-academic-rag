#!/usr/bin/env python3
"""Run the four local retrieval backends over a formal evaluation corpus."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.formal_corpus import load_manifest_and_items
from backend.evaluation.retrieval_metrics import RetrievalRankingResultV1
from backend.retrieval.embedding import EmbeddingModelIdentity, OllamaEmbeddingProvider
from backend.retrieval.fixture import load_chunks, load_scope, retrieve_chunks
from backend.retrieval.hybrid import LocalRrfHybridRetriever
from backend.retrieval.sqlite_fts import SQLiteFtsIndex
from backend.retrieval.vector import LocalVectorIndex


CONFIG_KEYS = {
    "schema_version",
    "backends",
    "top_k",
    "metric_k_values",
    "embedding_model",
    "embedding_model_digest",
    "vector_min_score",
    "rrf_candidate_k",
    "rrf_k",
}


def load_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != CONFIG_KEYS:
        raise ValueError("formal retrieval config fields are invalid")
    if value["schema_version"] != "formal_local_retrieval_config_v1":
        raise ValueError("unsupported formal retrieval config")
    if value["backends"] != [
        "lexical_overlap",
        "sqlite_fts5",
        "local_vector",
        "local_rrf",
    ]:
        raise ValueError("formal retrieval backends are not the frozen four-way set")
    if not isinstance(value["top_k"], int) or value["top_k"] < 1:
        raise ValueError("formal retrieval top_k must be positive")
    return value


class CachedEmbeddingProvider:
    def __init__(
        self,
        provider: OllamaEmbeddingProvider,
        texts: list[str],
    ):
        started = time.perf_counter()
        vectors = provider.embed(texts)
        self.mean_latency_ms = (time.perf_counter() - started) * 1000 / len(texts)
        self._identity = provider.identity()
        self._vectors = dict(zip(texts, vectors, strict=True))

    def identity(self) -> EmbeddingModelIdentity:
        return self._identity

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            return [self._vectors[text] for text in texts]
        except KeyError as exc:
            raise ValueError("embedding text was not preloaded") from exc


def _record(
    *,
    run_id: str,
    dataset_version: str,
    question_id: str,
    backend: str,
    top_k: int,
    latency_ms: float,
    chunks: list[dict[str, Any]],
) -> RetrievalRankingResultV1:
    return RetrievalRankingResultV1.model_validate(
        {
            "schema_version": "retrieval_ranking_result_v1",
            "run_id": run_id,
            "dataset_version": dataset_version,
            "question_id": question_id,
            "backend": backend,
            "top_k": top_k,
            "decision": "EVIDENCE_FOUND" if chunks else "NO_EVIDENCE",
            "latency_ms": latency_ms,
            "candidates": [
                {
                    "rank": rank,
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "score": None,
                }
                for rank, chunk in enumerate(chunks, 1)
            ],
        }
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    top_k = config["top_k"]
    manifest, items, _ = load_manifest_and_items(args.manifest)
    chunks = load_chunks(args.chunks)
    scope = load_scope(args.scope)
    sqlite_index = SQLiteFtsIndex(args.sqlite_index)
    vector_index = LocalVectorIndex(args.vector_index)
    sqlite_index.verify_source(chunks)
    vector_index.verify_source(chunks)
    provider = CachedEmbeddingProvider(
        OllamaEmbeddingProvider(
            model=config["embedding_model"],
            base_url=args.embedding_base_url,
            batch_size=args.embedding_batch_size,
            timeout_seconds=args.embedding_timeout,
        ),
        [item.question for item in items],
    )
    vector_index.verify_provider(provider)
    if provider.identity().digest != config["embedding_model_digest"]:
        raise ValueError("embedding model digest does not match frozen config")
    hybrid = LocalRrfHybridRetriever(
        sqlite_index,
        vector_index,
        provider,
        candidate_k=config["rrf_candidate_k"],
        rrf_k=config["rrf_k"],
        vector_min_score=config["vector_min_score"],
    )
    backends = {
        "lexical_overlap": lambda question: retrieve_chunks(
            question, chunks, scope, top_k=top_k
        ),
        "sqlite_fts5": lambda question: sqlite_index.retrieve(
            question, scope, top_k=top_k
        ),
        "local_vector": lambda question: vector_index.retrieve(
            question,
            scope,
            provider,
            top_k=top_k,
            min_score=config["vector_min_score"],
        ),
        "local_rrf": lambda question: hybrid.retrieve(
            question, scope, top_k=top_k
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for backend, retrieve in backends.items():
        records: list[RetrievalRankingResultV1] = []
        for item in items:
            started = time.perf_counter()
            found = retrieve(item.question)
            latency_ms = (time.perf_counter() - started) * 1000
            if backend in {"local_vector", "local_rrf"}:
                latency_ms += provider.mean_latency_ms
            records.append(
                _record(
                    run_id=f"{backend}.ai-audited-v1",
                    dataset_version=manifest.dataset_version,
                    question_id=item.question_id,
                    backend=backend,
                    top_k=top_k,
                    latency_ms=latency_ms,
                    chunks=found,
                )
            )
        path = args.output_dir / f"{backend}.jsonl"
        path.write_text(
            "".join(
                json.dumps(
                    record.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
                for record in records
            ),
            encoding="utf-8",
        )
        counts[backend] = len(records)
    report = {
        "schema_version": "formal_local_retrieval_run_report_v1",
        "dataset_version": manifest.dataset_version,
        "item_count": len(items),
        "top_k": top_k,
        "metric_k_values": config["metric_k_values"],
        "backend_counts": counts,
        "embedding_model": provider.identity().__dict__,
        "embedding_mean_batch_allocated_latency_ms": provider.mean_latency_ms,
        "boundary": "LOCAL_EXACT_VECTOR_SQLITE_RRF_RETRIEVAL_ONLY",
    }
    (args.output_dir / "run-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--sqlite-index", type=Path, required=True)
    parser.add_argument("--vector-index", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "evaluation/formal/local-retrieval-baseline-v1.json",
    )
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-batch-size", type=int, default=32)
    parser.add_argument("--embedding-timeout", type=float, default=180)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = run(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"formal retrieval run error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
