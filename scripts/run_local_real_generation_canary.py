"""Run a non-secret local real-generation canary over frozen public Evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.rag.generation import OllamaGenerationProvider


REPORT_SCHEMA_VERSION = "local_real_generation_canary_report_v1"
DEFAULT_MODEL = "llama3.2:latest"
DEFAULT_MODEL_DIGEST = "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runtime/phases/source-phase2-real-generation-local-gate/canary.json"),
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--expected-digest", default=DEFAULT_MODEL_DIGEST)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    return parser


def _validate_output_path(path: Path) -> None:
    if path.is_absolute() or not path.parts or path.parts[0] != "runtime" or ".." in path.parts:
        raise ValueError("OUTPUT_MUST_BE_UNDER_RUNTIME")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        _validate_output_path(args.output)
        provider = OllamaGenerationProvider(
            model=args.model,
            expected_digest=args.expected_digest,
            base_url=args.ollama_url,
        )
        client = TestClient(create_app(generation_provider=provider))
        request = {
            "question": "How are candidates combined before reranking?",
            "document_ids": ["doc_fixture_001"],
            "stream": False,
        }
        first = client.post("/api/v1/rag/answers", json=request)
        second = client.post("/api/v1/rag/answers", json=request)
        no_evidence = client.post(
            "/api/v1/rag/answers",
            json={
                "question": "What is the measured ocean temperature?",
                "document_ids": ["doc_fixture_001"],
                "stream": False,
            },
        )
        forbidden = client.post(
            "/api/v1/rag/answers",
            json={
                "question": "quantum entanglement",
                "document_ids": ["doc_fixture_private_other_tenant"],
                "stream": False,
            },
        )
        first_payload = first.json()
        second_payload = second.json()
        no_evidence_payload = no_evidence.json()
        forbidden_payload = forbidden.json()
        conditions = (
            first.status_code == 200,
            first_payload.get("status") == "COMPLETED",
            bool(first_payload.get("citations")),
            first_payload.get("answer") == second_payload.get("answer"),
            no_evidence.status_code == 200,
            no_evidence_payload.get("status") == "NO_EVIDENCE",
            forbidden.status_code == 403,
            forbidden_payload.get("code") == "RAG_FORBIDDEN_SCOPE",
        )
        if not all(conditions):
            raise RuntimeError("LOCAL_REAL_GENERATION_CANARY_ASSERTION_FAILED")
        identity = provider.configured_identity()
        report: dict[str, object] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "PASS",
            "execution_boundary": "LOCAL_PUBLIC_FIXTURE_REAL_OLLAMA_GENERATION",
            "retrieval_parameters_changed": False,
            "model": identity.model,
            "model_digest": identity.digest,
            "prompt_version": identity.prompt_version,
            "prompt_sha256": identity.prompt_sha256,
            "decoding": {
                "temperature": identity.temperature,
                "seed": identity.seed,
                "num_predict": identity.num_predict,
                "num_ctx": identity.num_ctx,
                "think": identity.think,
            },
            "completed_status": first_payload["status"],
            "answer_sha256": _sha256_text(first_payload["answer"]),
            "stable_replay": True,
            "citation_count": len(first_payload["citations"]),
            "citation_ids_validated": True,
            "no_evidence_model_not_called": "NOT_CALLED_NO_EVIDENCE"
            in no_evidence_payload["warnings"][0],
            "unauthorized_scope_status": forbidden.status_code,
            "unauthorized_scope_code": forbidden_payload["code"],
            "limitations": [
                "Public fixture Evidence, not a remote PostgreSQL/ES/Milvus run",
                "Claim-to-Evidence semantic support remains a later phase",
            ],
        }
        _write(args.output, report)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except Exception as exc:
        failure = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "FAIL",
            "error_code": str(exc)
            if type(exc) is RuntimeError
            else type(exc).__name__,
        }
        try:
            _write(args.output, failure)
        except Exception:
            pass
        print(json.dumps(failure), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
