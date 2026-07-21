"""Deterministic member-A consumer for the Stage 0 RAG contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.rag.answer_builder import build_answer
from backend.retrieval.fixture import load_chunks, load_scope, retrieve_chunks


JsonObject = dict[str, Any]


def answer_fixture_question(
    question: str,
    scope: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    *,
    top_k: int = 3,
) -> JsonObject:
    """Return a deterministic RagAnswerV1 from authorized fixture chunks."""

    retrieved = retrieve_chunks(question, chunks, scope, top_k=top_k)
    return build_answer(
        question,
        scope,
        retrieved,
        execution_boundary="LOCAL_API_FAKE_LLM",
        completed_warning="FIXTURE_ONLY_FAKE_LLM",
        no_evidence_warning="FIXTURE_ONLY",
        answer_prefix="依据当前授权 Fixture 证据：",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Stage 0 fixture-only RAG consumer")
    parser.add_argument(
        "--question", required=True, help="Question to match against authorized chunks"
    )
    parser.add_argument(
        "--scope",
        type=Path,
        default=Path("fixtures/authorized-scope-v1.json"),
        help="AuthorizedScopeV1 JSON path",
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=Path("fixtures/chunks-v1.json"),
        help="ChunkRecordV1 fixture array path",
    )
    parser.add_argument("--top-k", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    answer = answer_fixture_question(
        args.question,
        load_scope(args.scope),
        load_chunks(args.chunks),
        top_k=args.top_k,
    )
    print(json.dumps(answer, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
