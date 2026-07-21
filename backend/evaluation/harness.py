"""Thin, deterministic evaluation harness over the existing RAG Answer API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi.testclient import TestClient
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from backend.api.app import DEFAULT_CHUNKS_PATH, DEFAULT_SCOPE_PATH, create_app
from backend.rag.sqlite_fts_consumer import SQLITE_FTS_EXECUTION_BOUNDARY
from backend.rag.vector_consumer import RRF_EXECUTION_BOUNDARY, VECTOR_EXECUTION_BOUNDARY
from backend.retrieval.embedding import EmbeddingProvider
from backend.retrieval.hybrid import DEFAULT_CANDIDATE_K, DEFAULT_RRF_K
from backend.retrieval.vector import DEFAULT_VECTOR_MIN_SCORE


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = ROOT / "evaluation" / "suites" / "fixture-smoke-v1.jsonl"
HARNESS_VERSION = "thin_eval_harness_v1"
EXECUTION_BOUNDARY = "LOCAL_API_FAKE_LLM"
RetrievalBackend = Literal["lexical_overlap", "sqlite_fts5", "local_vector", "local_rrf"]

CaseId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceTargetV1(StrictModel):
    document_id: CaseId
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def page_range_must_be_ordered(self) -> "EvidenceTargetV1":
        if self.page_start > self.page_end:
            raise ValueError("page_start must be <= page_end")
        return self


class EvaluationExpectationV1(StrictModel):
    http_status: int = Field(ge=100, le=599)
    answer_status: Literal["COMPLETED", "NO_EVIDENCE", "DEGRADED", "FAILED"] | None = None
    error_code: CaseId | None = None
    min_evidence_count: int = Field(default=0, ge=0)
    max_evidence_count: int | None = Field(default=None, ge=0)
    required_evidence: list[EvidenceTargetV1] = Field(default_factory=list)
    forbidden_document_ids: list[CaseId] = Field(default_factory=list)
    required_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_count_range_must_be_ordered(self) -> "EvaluationExpectationV1":
        if (
            self.max_evidence_count is not None
            and self.min_evidence_count > self.max_evidence_count
        ):
            raise ValueError("min_evidence_count must be <= max_evidence_count")
        return self


class EvaluationCaseV1(StrictModel):
    case_id: CaseId
    category: Literal["ANSWERABLE", "NO_EVIDENCE", "FORBIDDEN"]
    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
    ]
    document_ids: list[CaseId]
    expected: EvaluationExpectationV1

    @field_validator("document_ids")
    @classmethod
    def document_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("document_ids must contain unique values")
        return value

    @model_validator(mode="after")
    def category_must_match_expected_contract(self) -> "EvaluationCaseV1":
        expected = self.expected
        if self.category == "ANSWERABLE" and not (
            expected.http_status == 200
            and expected.answer_status == "COMPLETED"
            and expected.min_evidence_count >= 1
            and expected.required_evidence
        ):
            raise ValueError(
                "ANSWERABLE requires HTTP 200, COMPLETED, evidence, and a page target"
            )
        if self.category == "NO_EVIDENCE" and not (
            expected.http_status == 200
            and expected.answer_status == "NO_EVIDENCE"
            and expected.max_evidence_count == 0
        ):
            raise ValueError("NO_EVIDENCE requires HTTP 200, NO_EVIDENCE, and zero evidence")
        if self.category == "FORBIDDEN" and not (
            expected.http_status == 403 and expected.error_code == "RAG_FORBIDDEN_SCOPE"
        ):
            raise ValueError("FORBIDDEN requires HTTP 403 and RAG_FORBIDDEN_SCOPE")
        return self


def load_cases(path: Path) -> list[EvaluationCaseV1]:
    """Load a non-empty JSONL suite and reject duplicate case identities."""

    cases: list[EvaluationCaseV1] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
            case = EvaluationCaseV1.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"invalid evaluation case at {path}:{line_number}: {exc}") from exc
        if case.case_id in seen:
            raise ValueError(
                f"duplicate evaluation case_id at {path}:{line_number}: {case.case_id}"
            )
        seen.add(case.case_id)
        cases.append(case)

    if not cases:
        raise ValueError(f"evaluation suite is empty: {path}")
    return cases


def _evidence_overlaps(evidence: dict[str, Any], target: EvidenceTargetV1) -> bool:
    return (
        evidence.get("document_id") == target.document_id
        and isinstance(evidence.get("page_start"), int)
        and isinstance(evidence.get("page_end"), int)
        and evidence["page_start"] <= target.page_end
        and evidence["page_end"] >= target.page_start
    )


def _run_case(client: TestClient, case: EvaluationCaseV1) -> dict[str, Any]:
    response = client.post(
        "/api/v1/rag/answers",
        json={
            "question": case.question,
            "document_ids": case.document_ids,
            "stream": False,
        },
    )
    body = response.json()
    evidence = body.get("evidence", []) if isinstance(body, dict) else []
    if not isinstance(evidence, list):
        evidence = []
    evidence = [item for item in evidence if isinstance(item, dict)]
    warnings = body.get("warnings", []) if isinstance(body, dict) else []
    if not isinstance(warnings, list):
        warnings = []

    failures: list[str] = []
    expected = case.expected
    if response.status_code != expected.http_status:
        failures.append(f"http_status expected {expected.http_status}, got {response.status_code}")
    if expected.answer_status is not None and body.get("status") != expected.answer_status:
        failures.append(
            f"answer_status expected {expected.answer_status}, got {body.get('status')}"
        )
    if expected.error_code is not None and body.get("code") != expected.error_code:
        failures.append(f"error_code expected {expected.error_code}, got {body.get('code')}")
    if len(evidence) < expected.min_evidence_count:
        failures.append(
            f"evidence_count expected >= {expected.min_evidence_count}, got {len(evidence)}"
        )
    if expected.max_evidence_count is not None and len(evidence) > expected.max_evidence_count:
        failures.append(
            f"evidence_count expected <= {expected.max_evidence_count}, got {len(evidence)}"
        )

    for target in expected.required_evidence:
        if not any(_evidence_overlaps(item, target) for item in evidence):
            failures.append(
                "required_evidence missing "
                f"{target.document_id}:{target.page_start}-{target.page_end}"
            )

    observed_document_ids = sorted(
        {str(item["document_id"]) for item in evidence if item.get("document_id")}
    )
    forbidden_hits = sorted(set(expected.forbidden_document_ids) & set(observed_document_ids))
    if forbidden_hits:
        failures.append(f"forbidden_document_ids present: {','.join(forbidden_hits)}")

    missing_warnings = sorted(set(expected.required_warnings) - set(map(str, warnings)))
    if missing_warnings:
        failures.append(f"required_warnings missing: {','.join(missing_warnings)}")

    observed_pages = sorted(
        {
            page
            for item in evidence
            for page in (item.get("page_start"), item.get("page_end"))
            if isinstance(page, int)
        }
    )
    return {
        "case_id": case.case_id,
        "category": case.category,
        "passed": not failures,
        "failures": failures,
        "observed": {
            "http_status": response.status_code,
            "answer_status": body.get("status") if isinstance(body, dict) else None,
            "error_code": body.get("code") if isinstance(body, dict) else None,
            "evidence_count": len(evidence),
            "document_ids": observed_document_ids,
            "pages": observed_pages,
            "warnings": warnings,
        },
    }


def run_suite(
    cases: list[EvaluationCaseV1],
    *,
    chunks_path: Path = DEFAULT_CHUNKS_PATH,
    scope_path: Path = DEFAULT_SCOPE_PATH,
    suite_id: str = "local-suite",
    retrieval_backend: RetrievalBackend = "lexical_overlap",
    index_path: Path | None = None,
    vector_index_path: Path | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    embedding_model: str = "bge-m3:latest",
    embedding_base_url: str = "http://127.0.0.1:11434",
    vector_min_score: float = DEFAULT_VECTOR_MIN_SCORE,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    rrf_k: int = DEFAULT_RRF_K,
) -> dict[str, Any]:
    """Run cases through the production-shaped local API adapter."""

    application = create_app(
        chunks_path=chunks_path,
        scope_path=scope_path,
        retrieval_backend=retrieval_backend,
        index_path=index_path,
        vector_index_path=vector_index_path,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_base_url=embedding_base_url,
        vector_min_score=vector_min_score,
        candidate_k=candidate_k,
        rrf_k=rrf_k,
    )
    client = TestClient(application)
    vector_metadata = (
        application.state.vector_index.inspect()
        if application.state.vector_index is not None
        else {}
    )
    results = [_run_case(client, case) for case in cases]
    category_summary: dict[str, dict[str, int]] = {}
    for category in ("ANSWERABLE", "NO_EVIDENCE", "FORBIDDEN"):
        selected = [item for item in results if item["category"] == category]
        category_summary[category] = {
            "total": len(selected),
            "passed": sum(1 for item in selected if item["passed"]),
        }

    passed = sum(1 for item in results if item["passed"])
    return {
        "harness_version": HARNESS_VERSION,
        "suite_id": suite_id,
        "execution_boundary": {
            "lexical_overlap": EXECUTION_BOUNDARY,
            "sqlite_fts5": SQLITE_FTS_EXECUTION_BOUNDARY,
            "local_vector": VECTOR_EXECUTION_BOUNDARY,
            "local_rrf": RRF_EXECUTION_BOUNDARY,
        }[retrieval_backend],
        "retrieval_backend": retrieval_backend,
        "retrieval_configuration": {
            "top_k": 3,
            "embedding_model": embedding_model
            if retrieval_backend in ("local_vector", "local_rrf")
            else None,
            "embedding_model_digest": vector_metadata.get("embedding_model_digest"),
            "embedding_dimension": int(vector_metadata["embedding_dimension"])
            if vector_metadata
            else None,
            "source_chunks_sha256": vector_metadata.get("source_chunks_sha256"),
            "vector_min_score": vector_min_score
            if retrieval_backend in ("local_vector", "local_rrf")
            else None,
            "candidate_k": candidate_k if retrieval_backend == "local_rrf" else None,
            "rrf_k": rrf_k if retrieval_backend == "local_rrf" else None,
        },
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "categories": category_summary,
        },
        "results": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the thin local evaluation harness over the RAG Answer API"
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE_PATH)
    parser.add_argument("--suite-id", default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--retrieval-backend",
        choices=("lexical_overlap", "sqlite_fts5", "local_vector", "local_rrf"),
        default="lexical_overlap",
    )
    parser.add_argument("--index", type=Path, default=None)
    parser.add_argument("--vector-index", type=Path, default=None)
    parser.add_argument("--embedding-model", default="bge-m3:latest")
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--vector-min-score", type=float, default=DEFAULT_VECTOR_MIN_SCORE
    )
    parser.add_argument("--candidate-k", type=int, default=DEFAULT_CANDIDATE_K)
    parser.add_argument("--rrf-k", type=int, default=DEFAULT_RRF_K)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        cases = load_cases(args.cases)
        report = run_suite(
            cases,
            chunks_path=args.chunks,
            scope_path=args.scope,
            suite_id=args.suite_id or args.cases.stem,
            retrieval_backend=args.retrieval_backend,
            index_path=args.index,
            vector_index_path=args.vector_index,
            embedding_model=args.embedding_model,
            embedding_base_url=args.embedding_base_url,
            vector_min_score=args.vector_min_score,
            candidate_k=args.candidate_k,
            rrf_k=args.rrf_k,
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"evaluation harness input error: {exc}", file=sys.stderr)
        return 2

    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(
            f"{report['summary']['passed']}/{report['summary']['total']} cases passed; "
            f"report={args.output}"
        )
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
