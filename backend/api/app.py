"""Fixture-only FastAPI adapter for the non-streaming RagAnswerV1 contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.models import ErrorV1, RagAnswerRequestV1, RagAnswerV1
from backend.rag.fixture_consumer import answer_fixture_question
from backend.retrieval.fixture import filter_authorized_chunks, load_chunks, load_scope


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS_PATH = ROOT / "fixtures" / "chunks-v1.json"
DEFAULT_SCOPE_PATH = ROOT / "fixtures" / "authorized-scope-v1.json"


def _error_response(*, status_code: int, code: str, message: str, retryable: bool) -> JSONResponse:
    error = ErrorV1(
        request_id=f"request_http_{status_code}",
        code=code,
        message=message,
        retryable=retryable,
    )
    return JSONResponse(status_code=status_code, content=error.model_dump(mode="json"))


def _narrow_scope(base_scope: dict[str, Any], document_ids: list[str]) -> dict[str, Any]:
    effective_scope = dict(base_scope)
    if document_ids:
        effective_scope["document_ids"] = document_ids
        effective_scope["library_ids"] = []
        effective_scope["folder_ids"] = []
    return effective_scope


def create_app(
    *,
    chunks_path: Path = DEFAULT_CHUNKS_PATH,
    scope_path: Path = DEFAULT_SCOPE_PATH,
) -> FastAPI:
    app = FastAPI(
        title="智研个人学术空间 RAG API",
        version="0.1.0",
        description="Stage 0 fixture-only API; no production data or remote model is used.",
    )
    app.state.chunks_path = chunks_path
    app.state.scope_path = scope_path

    @app.exception_handler(RequestValidationError)
    async def invalid_request_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request, exc
        return _error_response(
            status_code=422,
            code="RAG_INVALID_REQUEST",
            message="请求字段、长度或范围结构无效。",
            retryable=False,
        )

    @app.post(
        "/api/v1/rag/answers",
        operation_id="createRagAnswer",
        response_model=RagAnswerV1,
        responses={
            403: {"model": ErrorV1, "description": "请求范围未获授权"},
            422: {"model": ErrorV1, "description": "请求结构无效"},
        },
    )
    def create_rag_answer(payload: RagAnswerRequestV1) -> RagAnswerV1 | JSONResponse:
        chunks = load_chunks(app.state.chunks_path)
        base_scope = load_scope(app.state.scope_path)
        authorized_document_ids = {
            chunk["document_id"] for chunk in filter_authorized_chunks(chunks, base_scope)
        }
        requested_document_ids = set(payload.document_ids)
        if not requested_document_ids.issubset(authorized_document_ids):
            return _error_response(
                status_code=403,
                code="RAG_FORBIDDEN_SCOPE",
                message="请求包含未授权文档。",
                retryable=False,
            )

        effective_scope = _narrow_scope(base_scope, payload.document_ids)
        answer = answer_fixture_question(payload.question, effective_scope, chunks)
        return RagAnswerV1.model_validate(answer)

    return app


app = create_app()
