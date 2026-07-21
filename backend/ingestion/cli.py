"""Command-line entrypoint for local PDF to ChunkRecordV1 conversion."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.ingestion.service import PdfIngestionError, ingest_pdf_bytes
from backend.ingestion.splitter import STRATEGIES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert one local text PDF into a ChunkRecordV1 JSON array"
    )
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--visibility", choices=("public", "tenant", "private"), required=True)
    parser.add_argument("--library-scope-id", action="append", default=[])
    parser.add_argument("--strategy", choices=STRATEGIES, required=True)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--embedding-version", default="not_embedded_v1")
    parser.add_argument("--allow-parse-review", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = ingest_pdf_bytes(
            args.pdf.read_bytes(),
            document_id=args.document_id,
            tenant_id=args.tenant_id,
            visibility=args.visibility,
            library_scope_ids=args.library_scope_id,
            strategy=args.strategy,
            expected_sha256=args.expected_sha256,
            allow_parse_review=args.allow_parse_review,
            embedding_version=args.embedding_version,
        )
    except (OSError, PdfIngestionError) as exc:
        code = getattr(exc, "code", "PDF_READ_FAILED")
        print(
            json.dumps({"error": {"code": code, "message": str(exc)}}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    payload = json.dumps(
        [chunk.model_dump(mode="json") for chunk in result.chunks],
        ensure_ascii=False,
        indent=2,
    )
    if args.output is None:
        print(payload)
    else:
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": "COMPLETED",
                    "document_id": result.document_id,
                    "version_id": result.version_id,
                    "parse_status": result.parse_status,
                    "warnings": list(result.warnings),
                    "strategy": result.strategy,
                    "chunk_count": len(result.chunks),
                    "output": str(args.output),
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
