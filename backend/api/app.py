"""Fixture-only FastAPI adapter for the non-streaming RagAnswerV1 contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.models import ErrorV1, RagAnswerRequestV1, RagAnswerV1
from backend.rag.fixture_consumer import answer_fixture_question
from backend.rag.sqlite_fts_consumer import answer_sqlite_fts_question
from backend.rag.vector_consumer import answer_rrf_question, answer_vector_question
from backend.retrieval.embedding import EmbeddingProvider, OllamaEmbeddingProvider
from backend.retrieval.fixture import filter_authorized_chunks, load_chunks, load_scope
from backend.retrieval.hybrid import (
    DEFAULT_CANDIDATE_K,
    DEFAULT_RRF_K,
    LocalRrfHybridRetriever,
)
from backend.retrieval.sqlite_fts import SQLiteFtsIndex
from backend.retrieval.vector import DEFAULT_VECTOR_MIN_SCORE, LocalVectorIndex


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS_PATH = ROOT / "fixtures" / "chunks-v1.json"
DEFAULT_SCOPE_PATH = ROOT / "fixtures" / "authorized-scope-v1.json"
RetrievalBackend = Literal["lexical_overlap", "sqlite_fts5", "local_vector", "local_rrf"]


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
    retrieval_backend: RetrievalBackend = "lexical_overlap",
    index_path: Path | None = None,
    vector_index_path: Path | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    embedding_model: str = "bge-m3:latest",
    embedding_base_url: str = "http://127.0.0.1:11434",
    vector_min_score: float = DEFAULT_VECTOR_MIN_SCORE,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    rrf_k: int = DEFAULT_RRF_K,
) -> FastAPI:
    chunks = load_chunks(chunks_path)
    sqlite_index: SQLiteFtsIndex | None = None
    vector_index: LocalVectorIndex | None = None
    hybrid_retriever: LocalRrfHybridRetriever | None = None
    if retrieval_backend in ("sqlite_fts5", "local_rrf"):
        if index_path is None:
            raise ValueError(f"index_path is required for {retrieval_backend} retrieval")
        sqlite_index = SQLiteFtsIndex(index_path)
        sqlite_index.verify_source(chunks)
    if retrieval_backend in ("local_vector", "local_rrf"):
        if vector_index_path is None:
            raise ValueError(f"vector_index_path is required for {retrieval_backend} retrieval")
        if embedding_provider is None:
            embedding_provider = OllamaEmbeddingProvider(
                model=embedding_model,
                base_url=embedding_base_url,
            )
        vector_index = LocalVectorIndex(vector_index_path)
        vector_index.verify_source(chunks)
        vector_index.verify_provider(embedding_provider)
    if retrieval_backend == "local_rrf":
        assert sqlite_index is not None
        assert vector_index is not None
        assert embedding_provider is not None
        hybrid_retriever = LocalRrfHybridRetriever(
            sqlite_index,
            vector_index,
            embedding_provider,
            candidate_k=candidate_k,
            rrf_k=rrf_k,
            vector_min_score=vector_min_score,
        )
    elif retrieval_backend not in ("lexical_overlap", "sqlite_fts5", "local_vector"):
        raise ValueError(f"unsupported retrieval backend: {retrieval_backend}")

    boundaries = {
        "lexical_overlap": "Stage 0 fixture-only lexical retrieval with Fake LLM",
        "sqlite_fts5": "local SQLite FTS5/BM25 with Fake LLM",
        "local_vector": "real local dense vector retrieval with Fake LLM",
        "local_rrf": "local SQLite FTS5 plus dense RRF retrieval with Fake LLM",
    }
    boundary = boundaries[retrieval_backend]
    app = FastAPI(
        title="智研个人学术空间 RAG API",
        version="0.1.0",
        description=f"{boundary}; no remote model is used.",
    )
    app.state.chunks_path = chunks_path
    app.state.scope_path = scope_path
    app.state.retrieval_backend = retrieval_backend
    app.state.sqlite_index = sqlite_index
    app.state.vector_index = vector_index
    app.state.embedding_provider = embedding_provider
    app.state.vector_min_score = vector_min_score
    app.state.hybrid_retriever = hybrid_retriever

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
        if app.state.retrieval_backend == "sqlite_fts5":
            answer = answer_sqlite_fts_question(
                payload.question,
                effective_scope,
                chunks,
                app.state.sqlite_index,
            )
        elif app.state.retrieval_backend == "local_vector":
            answer = answer_vector_question(
                payload.question,
                effective_scope,
                chunks,
                app.state.vector_index,
                app.state.embedding_provider,
                min_score=app.state.vector_min_score,
            )
        elif app.state.retrieval_backend == "local_rrf":
            answer = answer_rrf_question(
                payload.question,
                effective_scope,
                chunks,
                app.state.hybrid_retriever,
            )
        else:
            answer = answer_fixture_question(payload.question, effective_scope, chunks)
        return RagAnswerV1.model_validate(answer)

    return app


app = create_app()
