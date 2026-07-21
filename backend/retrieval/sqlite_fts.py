"""Persistent local SQLite FTS5/BM25 index for ChunkRecordV1 objects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

from backend.retrieval.fixture import is_chunk_authorized, load_chunks, load_scope


JsonObject = dict[str, Any]
INDEX_SCHEMA_VERSION = "sqlite_fts_index_v1"
RETRIEVAL_BACKEND = "sqlite_fts5_bm25"
INDEX_CONFIGURATION = {
    "schema_version": INDEX_SCHEMA_VERSION,
    "retrieval_backend": RETRIEVAL_BACKEND,
    "tokenizer": "porter_unicode61",
    "query_mode": "OR",
    "bm25_column_weights": "2.0,1.0",
}

_TOKEN_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "before",
    "does",
    "each",
    "for",
    "how",
    "in",
    "is",
    "of",
    "or",
    "the",
    "to",
    "what",
}


class IndexNotReadyError(ValueError):
    """Raised when the index is missing, corrupt, or built from different chunks."""


def chunks_fingerprint(chunks: Sequence[Mapping[str, Any]]) -> str:
    """Return a stable SHA-256 over the ordered canonical chunk payloads."""

    serialized = json.dumps(
        list(chunks),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_chunks(chunks: Sequence[Mapping[str, Any]]) -> None:
    seen: set[str] = set()
    required_strings = (
        "chunk_id",
        "document_id",
        "version_id",
        "text",
        "section_path",
        "tenant_id",
        "visibility",
    )
    for position, chunk in enumerate(chunks):
        if not isinstance(chunk, Mapping):
            raise ValueError(f"chunk at position {position} must be an object")
        has_required_strings = all(
            isinstance(chunk.get(field), str) and chunk[field] for field in required_strings
        )
        if not has_required_strings:
            raise ValueError(f"chunk at position {position} is missing required string fields")
        chunk_id = str(chunk["chunk_id"])
        if chunk_id in seen:
            raise ValueError(f"duplicate chunk_id: {chunk_id}")
        seen.add(chunk_id)
        if (
            not isinstance(chunk.get("page_start"), int)
            or not isinstance(chunk.get("page_end"), int)
            or chunk["page_start"] < 1
            or chunk["page_start"] > chunk["page_end"]
        ):
            raise ValueError(f"chunk {chunk_id} has an invalid page range")
        libraries = chunk.get("library_scope_ids")
        if not isinstance(libraries, list) or not all(
            isinstance(value, str) and value for value in libraries
        ):
            raise ValueError(f"chunk {chunk_id} has invalid library_scope_ids")
        if not isinstance(chunk.get("is_active"), bool):
            raise ValueError(f"chunk {chunk_id} has invalid is_active")


def _query_expression(question: str) -> str | None:
    terms: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_PATTERN.finditer(question):
        term = match.group(0).lower()
        if term in _STOP_WORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    if not terms:
        return None
    return " OR ".join(f'"{term}"' for term in terms)


def _metadata(connection: sqlite3.Connection) -> dict[str, str]:
    try:
        rows = connection.execute("SELECT key, value FROM index_metadata").fetchall()
    except sqlite3.DatabaseError as exc:
        raise IndexNotReadyError(f"invalid SQLite FTS index: {exc}") from exc
    return {str(key): str(value) for key, value in rows}


class SQLiteFtsIndex:
    """Build and query a local persistent FTS5 index without widening authorization."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect_read_only(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise IndexNotReadyError(f"SQLite FTS index does not exist: {self.path}")
        try:
            connection = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise IndexNotReadyError(f"cannot open SQLite FTS index: {exc}") from exc
        connection.row_factory = sqlite3.Row
        return connection

    @classmethod
    def build(
        cls,
        path: Path,
        chunks: Iterable[Mapping[str, Any]],
    ) -> "SQLiteFtsIndex":
        chunk_list = [dict(chunk) for chunk in chunks]
        if not chunk_list:
            raise ValueError("cannot build an empty SQLite FTS index")
        _validate_chunks(chunk_list)

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
                    CREATE TABLE chunks (
                        rowid INTEGER PRIMARY KEY,
                        chunk_id TEXT NOT NULL UNIQUE,
                        payload TEXT NOT NULL,
                        section_path TEXT NOT NULL,
                        body TEXT NOT NULL
                    );
                    CREATE VIRTUAL TABLE chunks_fts USING fts5(
                        section_path,
                        body,
                        content='chunks',
                        content_rowid='rowid',
                        tokenize='porter unicode61'
                    );
                    """
                )
                for chunk in chunk_list:
                    cursor = connection.execute(
                        """
                        INSERT INTO chunks(chunk_id, payload, section_path, body)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            chunk["chunk_id"],
                            json.dumps(
                                chunk,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            chunk["section_path"],
                            chunk["text"],
                        ),
                    )
                    connection.execute(
                        "INSERT INTO chunks_fts(rowid, section_path, body) VALUES (?, ?, ?)",
                        (cursor.lastrowid, chunk["section_path"], chunk["text"]),
                    )
                metadata = {
                    **INDEX_CONFIGURATION,
                    "source_chunks_sha256": chunks_fingerprint(chunk_list),
                    "chunk_count": str(len(chunk_list)),
                }
                connection.executemany(
                    "INSERT INTO index_metadata(key, value) VALUES (?, ?)", metadata.items()
                )
                connection.commit()
                quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
                if quick_check != "ok":
                    raise IndexNotReadyError(f"SQLite quick_check failed: {quick_check}")
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
                raise IndexNotReadyError(f"SQLite quick_check failed: {quick_check}")
            metadata = _metadata(connection)
        for key, expected in INDEX_CONFIGURATION.items():
            if metadata.get(key) != expected:
                raise IndexNotReadyError(f"SQLite FTS index {key} metadata is invalid")
        return metadata

    def verify_source(self, chunks: Sequence[Mapping[str, Any]]) -> dict[str, str]:
        metadata = self.inspect()
        expected = chunks_fingerprint(chunks)
        if metadata.get("source_chunks_sha256") != expected:
            raise IndexNotReadyError("SQLite FTS index source fingerprint does not match chunks")
        if metadata.get("chunk_count") != str(len(chunks)):
            raise IndexNotReadyError("SQLite FTS index chunk count does not match chunks")
        return metadata

    def retrieve(
        self,
        question: str,
        scope: Mapping[str, Any],
        *,
        top_k: int = 3,
        expected_chunks: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[JsonObject]:
        if not question.strip():
            raise ValueError("question must not be blank")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if expected_chunks is not None:
            self.verify_source(expected_chunks)
        expression = _query_expression(question)
        if expression is None:
            return []

        with closing(self._connect_read_only()) as connection:
            rows = connection.execute(
                """
                SELECT chunks.payload, bm25(chunks_fts, 2.0, 1.0) AS score
                FROM chunks_fts
                JOIN chunks ON chunks.rowid = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY score ASC, chunks.chunk_id ASC
                """,
                (expression,),
            )
            authorized: list[JsonObject] = []
            for row in rows:
                payload = json.loads(row["payload"])
                if isinstance(payload, dict) and is_chunk_authorized(payload, scope):
                    authorized.append(payload)
                    if len(authorized) == top_k:
                        break
        return authorized


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or inspect a local SQLite FTS5 index")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build an index from ChunkRecordV1 JSON")
    build.add_argument("--chunks", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)

    inspect = subparsers.add_parser("inspect", help="Validate and print index metadata")
    inspect.add_argument("--index", type=Path, required=True)

    query = subparsers.add_parser("query", help="Run an authorized BM25 query")
    query.add_argument("--index", type=Path, required=True)
    query.add_argument("--chunks", type=Path, required=True)
    query.add_argument("--scope", type=Path, required=True)
    query.add_argument("--question", required=True)
    query.add_argument("--top-k", type=int, default=3)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.command == "build":
            chunks = load_chunks(args.chunks)
            index = SQLiteFtsIndex.build(args.output, chunks)
            payload: dict[str, Any] = index.inspect()
            payload["index"] = str(args.output)
        elif args.command == "inspect":
            payload = SQLiteFtsIndex(args.index).inspect()
        else:
            chunks = load_chunks(args.chunks)
            payload = {
                "results": SQLiteFtsIndex(args.index).retrieve(
                    args.question,
                    load_scope(args.scope),
                    top_k=args.top_k,
                    expected_chunks=chunks,
                )
            }
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"SQLite FTS input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
