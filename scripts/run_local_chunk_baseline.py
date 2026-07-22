#!/usr/bin/env python3
"""Run a controlled three-strategy Chunk baseline on local ignored assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import statistics
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from backend.evaluation.harness import EvaluationCaseV1, load_cases, run_suite
from backend.ingestion.service import ingest_pdf_bytes
from backend.ingestion.splitter import STRATEGIES
from backend.retrieval.embedding import OllamaEmbeddingProvider
from backend.retrieval.fixture import load_scope
from backend.retrieval.sqlite_fts import SQLiteFtsIndex, chunks_fingerprint
from backend.retrieval.vector import LocalVectorIndex


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "evaluation" / "local-3-paper-chunk-baseline-v1.json"
BACKEND_WARNINGS = {
    "sqlite_fts5": {
        "ANSWERABLE": "LOCAL_SQLITE_FTS5_FAKE_LLM",
        "NO_EVIDENCE": "LOCAL_SQLITE_FTS5_ONLY",
    },
    "local_vector": {
        "ANSWERABLE": "LOCAL_REAL_VECTOR_FAKE_LLM",
        "NO_EVIDENCE": "LOCAL_REAL_VECTOR_ONLY",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "baseline_id",
        "strategies",
        "papers",
        "retrieval",
    }:
        raise ValueError("chunk baseline config fields are invalid")
    if payload["schema_version"] != "local_chunk_baseline_v1":
        raise ValueError("chunk baseline schema_version is invalid")
    if not isinstance(payload["baseline_id"], str) or not payload["baseline_id"]:
        raise ValueError("chunk baseline baseline_id must be non-empty")
    if payload["strategies"] != list(STRATEGIES):
        raise ValueError("chunk baseline must pin all three strategies in canonical order")

    papers = payload["papers"]
    if not isinstance(papers, list) or not papers:
        raise ValueError("chunk baseline papers must be a non-empty array")
    document_ids: set[str] = set()
    file_names: set[str] = set()
    for paper in papers:
        if not isinstance(paper, dict) or set(paper) != {
            "document_id",
            "file_name",
            "sha256",
        }:
            raise ValueError("chunk baseline paper fields are invalid")
        if not all(isinstance(paper[key], str) and paper[key] for key in paper):
            raise ValueError("chunk baseline paper values must be non-empty strings")
        digest = paper["sha256"]
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("chunk baseline paper sha256 is invalid")
        if paper["document_id"] in document_ids or paper["file_name"] in file_names:
            raise ValueError("chunk baseline paper identities must be unique")
        document_ids.add(paper["document_id"])
        file_names.add(paper["file_name"])

    retrieval = payload["retrieval"]
    if not isinstance(retrieval, dict) or set(retrieval) != {
        "top_k",
        "vector_min_score",
        "embedding_model",
        "embedding_base_url",
        "embedding_batch_size",
        "embedding_timeout_seconds",
    }:
        raise ValueError("chunk baseline retrieval fields are invalid")
    if retrieval["top_k"] != 3:
        raise ValueError("chunk baseline top_k must remain 3")
    if not -1.0 <= float(retrieval["vector_min_score"]) <= 1.0:
        raise ValueError("chunk baseline vector_min_score is invalid")
    if not isinstance(retrieval["embedding_model"], str) or not retrieval["embedding_model"]:
        raise ValueError("chunk baseline embedding_model must be non-empty")
    if not isinstance(retrieval["embedding_base_url"], str) or not retrieval[
        "embedding_base_url"
    ].startswith(("http://", "https://")):
        raise ValueError("chunk baseline embedding_base_url is invalid")
    if not isinstance(retrieval["embedding_batch_size"], int) or retrieval[
        "embedding_batch_size"
    ] < 1:
        raise ValueError("chunk baseline embedding_batch_size is invalid")
    if float(retrieval["embedding_timeout_seconds"]) <= 0:
        raise ValueError("chunk baseline embedding_timeout_seconds is invalid")
    return payload


def parse_pdf_arguments(values: Sequence[str]) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        document_id, separator, raw_path = value.partition("=")
        if not separator or not document_id or not raw_path:
            raise ValueError("--pdf must use DOCUMENT_ID=PATH")
        if document_id in parsed:
            raise ValueError(f"duplicate --pdf document id: {document_id}")
        parsed[document_id] = Path(raw_path)
    return parsed


def cases_for_backend(
    cases: Sequence[EvaluationCaseV1], backend: str
) -> list[EvaluationCaseV1]:
    if backend not in BACKEND_WARNINGS:
        raise ValueError(f"unsupported chunk baseline backend: {backend}")
    adjusted = [case.model_copy(deep=True) for case in cases]
    for case in adjusted:
        warning = BACKEND_WARNINGS[backend].get(case.category)
        if warning is not None:
            case.expected.required_warnings = [warning]
    return adjusted


def chunk_metrics(chunks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not chunks:
        raise ValueError("cannot summarize empty chunks")
    lengths = sorted(len(str(chunk["text"])) for chunk in chunks)
    p95_index = max(0, math.ceil(len(lengths) * 0.95) - 1)
    per_document: dict[str, int] = {}
    for chunk in chunks:
        document_id = str(chunk["document_id"])
        per_document[document_id] = per_document.get(document_id, 0) + 1
    return {
        "chunk_count": len(chunks),
        "characters": {
            "min": lengths[0],
            "median": statistics.median(lengths),
            "mean": round(statistics.fmean(lengths), 3),
            "p95": lengths[p95_index],
            "max": lengths[-1],
        },
        "multi_page_chunk_count": sum(
            int(chunk["page_end"]) > int(chunk["page_start"]) for chunk in chunks
        ),
        "parent_linked_chunk_count": sum(
            chunk.get("parent_chunk_id") is not None for chunk in chunks
        ),
        "per_document_chunk_count": dict(sorted(per_document.items())),
        "source_chunks_sha256": chunks_fingerprint(chunks),
    }


def build_strategy_chunks(
    config: Mapping[str, Any],
    pdf_paths: Mapping[str, Path],
    scope: Mapping[str, Any],
    strategy: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_ids = {str(paper["document_id"]) for paper in config["papers"]}
    if set(pdf_paths) != expected_ids:
        missing = sorted(expected_ids - set(pdf_paths))
        extra = sorted(set(pdf_paths) - expected_ids)
        raise ValueError(f"PDF identity mismatch; missing={missing}, extra={extra}")
    tenant_id = scope.get("tenant_id")
    library_ids = scope.get("library_ids")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError("legacy local scope requires tenant_id")
    if not isinstance(library_ids, list) or not all(
        isinstance(value, str) and value for value in library_ids
    ):
        raise ValueError("legacy local scope requires library_ids")

    all_chunks: list[dict[str, Any]] = []
    parse_results: dict[str, Any] = {}
    for paper in config["papers"]:
        document_id = str(paper["document_id"])
        path = pdf_paths[document_id]
        if not path.is_file():
            raise ValueError(f"PDF does not exist for {document_id}: {path}")
        pdf_bytes = path.read_bytes()
        first = ingest_pdf_bytes(
            pdf_bytes,
            document_id=document_id,
            tenant_id=tenant_id,
            visibility="private",
            library_scope_ids=list(library_ids),
            strategy=strategy,
            expected_sha256=str(paper["sha256"]),
        )
        second = ingest_pdf_bytes(
            pdf_bytes,
            document_id=document_id,
            tenant_id=tenant_id,
            visibility="private",
            library_scope_ids=list(library_ids),
            strategy=strategy,
            expected_sha256=str(paper["sha256"]),
        )
        first_chunks = [chunk.model_dump(mode="json") for chunk in first.chunks]
        second_chunks = [chunk.model_dump(mode="json") for chunk in second.chunks]
        if first_chunks != second_chunks:
            raise ValueError(f"non-deterministic ingestion output for {document_id} {strategy}")
        all_chunks.extend(first_chunks)
        parse_results[document_id] = {
            "file_name": str(paper["file_name"]),
            "pdf_sha256": first.pdf_sha256,
            "parse_status": first.parse_status,
            "warnings": list(first.warnings),
            "chunk_count": len(first_chunks),
            "deterministic_rerun": True,
        }
    return all_chunks, dict(sorted(parse_results.items()))


def run_baseline(
    *,
    config_path: Path,
    cases_path: Path,
    scope_path: Path,
    pdf_paths: Mapping[str, Path],
    output_dir: Path,
) -> dict[str, Any]:
    config = load_config(config_path)
    cases = load_cases(cases_path)
    scope = load_scope(scope_path)
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    retrieval = config["retrieval"]
    provider = OllamaEmbeddingProvider(
        model=str(retrieval["embedding_model"]),
        base_url=str(retrieval["embedding_base_url"]),
        batch_size=int(retrieval["embedding_batch_size"]),
        timeout_seconds=float(retrieval["embedding_timeout_seconds"]),
    )
    identity = provider.identity()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    report: dict[str, Any] = {
        "schema_version": "local_chunk_baseline_report_v1",
        "baseline_id": config["baseline_id"],
        "execution_boundary": "LOCAL_3_PAPER_CHUNK_STRATEGY_BASELINE_FAKE_LLM",
        "inputs": {
            "config_sha256": _sha256(config_path),
            "cases_sha256": _sha256(cases_path),
            "scope_sha256": _sha256(scope_path),
            "paper_sha256": {
                str(paper["document_id"]): str(paper["sha256"])
                for paper in config["papers"]
            },
        },
        "retrieval_configuration": {
            **retrieval,
            "embedding_provider": identity.provider,
            "embedding_model_resolved": identity.model,
            "embedding_model_digest": identity.digest,
        },
        "strategies": {},
    }
    try:
        for strategy in config["strategies"]:
            strategy_dir = temporary / strategy
            strategy_dir.mkdir()
            chunks, parse_results = build_strategy_chunks(
                config, pdf_paths, scope, strategy
            )
            chunks_path = strategy_dir / "chunks.json"
            chunks_path.write_text(
                json.dumps(chunks, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            fts_path = strategy_dir / "sqlite-fts5.sqlite"
            vector_path = strategy_dir / "bge-m3-vector.sqlite"
            SQLiteFtsIndex.build(fts_path, chunks)
            LocalVectorIndex.build(vector_path, chunks, provider)
            sqlite_report = run_suite(
                cases_for_backend(cases, "sqlite_fts5"),
                chunks_path=chunks_path,
                scope_path=scope_path,
                suite_id=f"{config['baseline_id']}:{strategy}:sqlite_fts5",
                retrieval_backend="sqlite_fts5",
                index_path=fts_path,
            )
            vector_report = run_suite(
                cases_for_backend(cases, "local_vector"),
                chunks_path=chunks_path,
                scope_path=scope_path,
                suite_id=f"{config['baseline_id']}:{strategy}:local_vector",
                retrieval_backend="local_vector",
                vector_index_path=vector_path,
                embedding_provider=provider,
                embedding_model=str(retrieval["embedding_model"]),
                embedding_base_url=str(retrieval["embedding_base_url"]),
                vector_min_score=float(retrieval["vector_min_score"]),
            )
            (strategy_dir / "sqlite-fts5-report.json").write_text(
                json.dumps(sqlite_report, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            (strategy_dir / "bge-m3-vector-report.json").write_text(
                json.dumps(vector_report, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            report["strategies"][strategy] = {
                "parse": parse_results,
                "chunks": chunk_metrics(chunks),
                "retrieval": {
                    "sqlite_fts5": sqlite_report["summary"],
                    "local_vector": vector_report["summary"],
                },
            }
        (temporary / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.rename(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument(
        "--pdf",
        action="append",
        required=True,
        help="Repeat DOCUMENT_ID=PATH once per configured paper.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = run_baseline(
            config_path=args.config,
            cases_path=args.cases,
            scope_path=args.scope,
            pdf_paths=parse_pdf_arguments(args.pdf),
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"chunk baseline input error: {exc}")
        return 2
    summaries = {
        strategy: {
            backend: summary["passed"]
            for backend, summary in result["retrieval"].items()
        }
        for strategy, result in report["strategies"].items()
    }
    print(json.dumps(summaries, ensure_ascii=False, sort_keys=True))
    print(f"report={args.output_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
