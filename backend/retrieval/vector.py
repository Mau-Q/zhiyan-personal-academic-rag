"""Persistent exact-cosine index backed by real local dense embeddings."""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import struct
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.retrieval.embedding import (
    EmbeddingModelIdentity,
    EmbeddingProvider,
    OllamaEmbeddingProvider,
)
from backend.retrieval.fixture import is_chunk_authorized, load_chunks, load_scope
from backend.retrieval.sqlite_fts import chunks_fingerprint


JsonObject = dict[str, Any]
INDEX_SCHEMA_VERSION = "local_vector_index_v1"
RETRIEVAL_BACKEND = "local_dense_exact_cosine"
PASSAGE_TEMPLATE = "section_path_newline_text_v1"
QUERY_TEMPLATE = "raw_question_v1"
VECTOR_NORMALIZATION = "l2_float32_le_v1"
DEFAULT_VECTOR_MIN_SCORE = 0.5


class VectorIndexNotReadyError(ValueError):
    """Raised when vector identity, source chunks, or model identity drifted."""


@dataclass(frozen=True)
class ScoredChunk:
    chunk: JsonObject
    score: float


def _passage_text(chunk: Mapping[str, Any]) -> str:
    return f"{chunk['section_path']}\n{chunk['text']}"


def _normalize(vector: Sequence[float]) -> tuple[float, ...]:
    if not vector:
        raise ValueError("embedding vector must not be empty")
    converted = tuple(float(value) for value in vector)
    if not all(math.isfinite(value) for value in converted):
        raise ValueError("embedding vector contains a non-finite value")
    norm = math.sqrt(math.fsum(value * value for value in converted))
    if norm <= 0:
        raise ValueError("embedding vector norm must be positive")
    return tuple(value / norm for value in converted)


def _pack(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack(payload: bytes, dimension: int) -> tuple[float, ...]:
    expected_size = dimension * 4
    if len(payload) != expected_size:
        raise VectorIndexNotReadyError(
            f"embedding byte length must be {expected_size}, got {len(payload)}"
        )
    return struct.unpack(f"<{dimension}f", payload)


def _metadata(connection: sqlite3.Connection) -> dict[str, str]:
    try:
        rows = connection.execute("SELECT key, value FROM index_metadata").fetchall()
    except sqlite3.DatabaseError as exc:
        raise VectorIndexNotReadyError(f"invalid vector index: {exc}") from exc
    return {str(key): str(value) for key, value in rows}


class LocalVectorIndex:
    """Build and query an auditable exact-cosine SQLite vector index."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect_read_only(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise VectorIndexNotReadyError(f"vector index does not exist: {self.path}")
        try:
            connection = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise VectorIndexNotReadyError(f"cannot open vector index: {exc}") from exc
        connection.row_factory = sqlite3.Row
        return connection

    @classmethod
    def build(
        cls,
        path: Path,
        chunks: Iterable[Mapping[str, Any]],
        provider: EmbeddingProvider,
    ) -> "LocalVectorIndex":
        chunk_list = [dict(chunk) for chunk in chunks]
        if not chunk_list:
            raise ValueError("cannot build an empty vector index")
        chunk_ids = [chunk.get("chunk_id") for chunk in chunk_list]
        if any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in chunk_ids):
            raise ValueError("all vector index chunks require chunk_id")
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("vector index chunk_id values must be unique")
        for chunk in chunk_list:
            if not isinstance(chunk.get("section_path"), str) or not chunk["section_path"]:
                raise ValueError("all vector index chunks require section_path")
            if not isinstance(chunk.get("text"), str) or not chunk["text"]:
                raise ValueError("all vector index chunks require text")

        identity = provider.identity()
        vectors = provider.embed([_passage_text(chunk) for chunk in chunk_list])
        if len(vectors) != len(chunk_list):
            raise ValueError("embedding count does not match chunk count")
        normalized = [_normalize(vector) for vector in vectors]
        dimensions = {len(vector) for vector in normalized}
        if len(dimensions) != 1:
            raise ValueError("embedding dimensions are inconsistent")
        dimension = dimensions.pop()

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
        )
        os.close(file_descriptor)
        temporary_path = Path(temporary_name)
        try:
            connection = sqlite3.connect(temporary_path)
            try:
                connection.executescript(
                    """
                    PRAGMA journal_mode=DELETE;
                    PRAGMA synchronous=FULL;
                    CREATE TABLE index_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE vectors (
                        chunk_id TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        embedding BLOB NOT NULL
                    );
                    """
                )
                for chunk, vector in zip(chunk_list, normalized, strict=True):
                    connection.execute(
                        "INSERT INTO vectors(chunk_id, payload, embedding) VALUES (?, ?, ?)",
                        (
                            chunk["chunk_id"],
                            json.dumps(
                                chunk,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            _pack(vector),
                        ),
                    )
                metadata = {
                    "schema_version": INDEX_SCHEMA_VERSION,
                    "retrieval_backend": RETRIEVAL_BACKEND,
                    "source_chunks_sha256": chunks_fingerprint(chunk_list),
                    "chunk_count": str(len(chunk_list)),
                    "embedding_provider": identity.provider,
                    "embedding_model": identity.model,
                    "embedding_model_digest": identity.digest,
                    "embedding_dimension": str(dimension),
                    "passage_template": PASSAGE_TEMPLATE,
                    "query_template": QUERY_TEMPLATE,
                    "vector_normalization": VECTOR_NORMALIZATION,
                    "input_truncation": "provider_enabled_v1",
                    "similarity": "cosine",
                }
                connection.executemany(
                    "INSERT INTO index_metadata(key, value) VALUES (?, ?)", metadata.items()
                )
                connection.commit()
                quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
                if quick_check != "ok":
                    raise VectorIndexNotReadyError(
                        f"vector index quick_check failed: {quick_check}"
                    )
            finally:
                connection.close()
            os.replace(temporary_path, output_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return cls(output_path)

    def inspect(self) -> dict[str, str]:
        with closing(self._connect_read_only()) as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
            if quick_check != "ok":
                raise VectorIndexNotReadyError(f"vector index quick_check failed: {quick_check}")
            metadata = _metadata(connection)
            row_count = int(connection.execute("SELECT COUNT(*) FROM vectors").fetchone()[0])
        expected = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "retrieval_backend": RETRIEVAL_BACKEND,
            "passage_template": PASSAGE_TEMPLATE,
            "query_template": QUERY_TEMPLATE,
            "vector_normalization": VECTOR_NORMALIZATION,
            "input_truncation": "provider_enabled_v1",
            "similarity": "cosine",
        }
        for key, value in expected.items():
            if metadata.get(key) != value:
                raise VectorIndexNotReadyError(f"vector index {key} metadata is invalid")
        try:
            chunk_count = int(metadata["chunk_count"])
            if chunk_count < 1 or int(metadata["embedding_dimension"]) < 1:
                raise ValueError
        except (KeyError, ValueError) as exc:
            raise VectorIndexNotReadyError("vector index count or dimension is invalid") from exc
        if row_count != chunk_count:
            raise VectorIndexNotReadyError("vector index row count does not match metadata")
        for key in (
            "source_chunks_sha256",
            "embedding_provider",
            "embedding_model",
            "embedding_model_digest",
        ):
            if not metadata.get(key):
                raise VectorIndexNotReadyError(f"vector index {key} metadata is missing")
        source_digest = metadata["source_chunks_sha256"]
        if len(source_digest) != 64 or any(
            character not in "0123456789abcdef" for character in source_digest
        ):
            raise VectorIndexNotReadyError("vector index source_chunks_sha256 is invalid")
        return metadata

    def verify_source(self, chunks: Sequence[Mapping[str, Any]]) -> dict[str, str]:
        metadata = self.inspect()
        if metadata.get("source_chunks_sha256") != chunks_fingerprint(chunks):
            raise VectorIndexNotReadyError("vector index source fingerprint does not match chunks")
        if metadata.get("chunk_count") != str(len(chunks)):
            raise VectorIndexNotReadyError("vector index chunk count does not match chunks")
        return metadata

    def verify_provider(self, provider: EmbeddingProvider) -> EmbeddingModelIdentity:
        metadata = self.inspect()
        identity = provider.identity()
        expected = (
            metadata.get("embedding_provider"),
            metadata.get("embedding_model"),
            metadata.get("embedding_model_digest"),
        )
        actual = (identity.provider, identity.model, identity.digest)
        if actual != expected:
            raise VectorIndexNotReadyError(
                "embedding provider identity does not match vector index"
            )
        return identity

    def search(
        self,
        question: str,
        scope: Mapping[str, Any],
        provider: EmbeddingProvider,
        *,
        top_k: int = 3,
        min_score: float = 0.0,
        expected_chunks: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[ScoredChunk]:
        if not question.strip():
            raise ValueError("question must not be blank")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not -1.0 <= min_score <= 1.0:
            raise ValueError("min_score must be between -1 and 1")
        metadata = (
            self.verify_source(expected_chunks)
            if expected_chunks is not None
            else self.inspect()
        )
        self.verify_provider(provider)
        dimension = int(metadata["embedding_dimension"])
        query_vectors = provider.embed([question.strip()])
        if len(query_vectors) != 1:
            raise ValueError("embedding provider must return exactly one query vector")
        query = _normalize(query_vectors[0])
        if len(query) != dimension:
            raise VectorIndexNotReadyError("query embedding dimension does not match vector index")

        scored: list[ScoredChunk] = []
        with closing(self._connect_read_only()) as connection:
            rows = connection.execute(
                "SELECT chunk_id, payload, embedding FROM vectors ORDER BY chunk_id"
            )
            for row in rows:
                payload = json.loads(row["payload"])
                if not isinstance(payload, dict) or not is_chunk_authorized(payload, scope):
                    continue
                vector = _unpack(row["embedding"], dimension)
                score = math.fsum(left * right for left, right in zip(query, vector, strict=True))
                if score >= min_score:
                    scored.append(ScoredChunk(chunk=payload, score=score))
        scored.sort(key=lambda item: (-item.score, str(item.chunk["chunk_id"])))
        return scored[:top_k]

    def retrieve(
        self,
        question: str,
        scope: Mapping[str, Any],
        provider: EmbeddingProvider,
        *,
        top_k: int = 3,
        min_score: float = 0.0,
        expected_chunks: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[JsonObject]:
        return [
            item.chunk
            for item in self.search(
                question,
                scope,
                provider,
                top_k=top_k,
                min_score=min_score,
                expected_chunks=expected_chunks,
            )
        ]


def _provider(args: argparse.Namespace) -> OllamaEmbeddingProvider:
    return OllamaEmbeddingProvider(
        model=args.model,
        base_url=args.base_url,
        batch_size=args.batch_size,
        timeout_seconds=args.timeout,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or query a real local vector index")
    parser.add_argument("--model", default="bge-m3:latest")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=120.0)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--chunks", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)

    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--index", type=Path, required=True)

    query = subparsers.add_parser("query")
    query.add_argument("--index", type=Path, required=True)
    query.add_argument("--chunks", type=Path, required=True)
    query.add_argument("--scope", type=Path, required=True)
    query.add_argument("--question", required=True)
    query.add_argument("--top-k", type=int, default=3)
    query.add_argument("--min-score", type=float, default=DEFAULT_VECTOR_MIN_SCORE)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "inspect":
            payload: dict[str, Any] = LocalVectorIndex(args.index).inspect()
        elif args.command == "build":
            index = LocalVectorIndex.build(args.output, load_chunks(args.chunks), _provider(args))
            payload = index.inspect()
            payload["index"] = str(args.output)
        else:
            chunks = load_chunks(args.chunks)
            results = LocalVectorIndex(args.index).search(
                args.question,
                load_scope(args.scope),
                _provider(args),
                top_k=args.top_k,
                min_score=args.min_score,
                expected_chunks=chunks,
            )
            payload = {
                "results": [
                    {"score": item.score, "chunk": item.chunk} for item in results
                ]
            }
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"vector input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
