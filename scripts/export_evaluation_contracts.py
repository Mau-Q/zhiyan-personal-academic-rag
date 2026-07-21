#!/usr/bin/env python3
"""Export stable JSON Schemas for the formal retrieval evaluation contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.formal_corpus import (
    AnnotationRecordV1,
    EvaluationItemV1,
    EvaluationManifestV1,
)
from backend.evaluation.retrieval_metrics import RetrievalRankingResultV1


SCHEMA_DIR = ROOT / "contracts" / "schemas"
MODELS = {
    "retrieval-evaluation-manifest-v1.schema.json": EvaluationManifestV1,
    "retrieval-evaluation-item-v1.schema.json": EvaluationItemV1,
    "retrieval-annotation-record-v1.schema.json": AnnotationRecordV1,
    "retrieval-ranking-result-v1.schema.json": RetrievalRankingResultV1,
}


def serialized_schema(file_name: str, model: type) -> str:
    payload = model.model_json_schema()
    payload["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    payload["$id"] = (
        "https://github.com/Mau-Q/zhiyan-personal-academic-rag/contracts/" + file_name
    )
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export formal evaluation JSON Schemas")
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    mismatches: list[str] = []
    for file_name, model in MODELS.items():
        path = SCHEMA_DIR / file_name
        expected = serialized_schema(file_name, model)
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                mismatches.append(file_name)
        else:
            path.write_text(expected, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if mismatches:
        print(f"evaluation contracts drifted: {','.join(mismatches)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
