"""Fixture-only FastAPI adapter for the non-streaming RagAnswerV1 contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.models import ErrorV1, RagAnswerRequestV1, RagAnswerV1
from backend.rag.elasticsearch_consumer import answer_elasticsearch_question
from backend.rag.fixture_consumer import answer_fixture_question
from backend.rag.milvus_consumer import answer_milvus_question
from backend.rag.online_consumer import answer_online_ready_question
from backend.rag.remote_hybrid_consumer import answer_remote_rrf_question
from backend.rag.sqlite_fts_consumer import answer_sqlite_fts_question
from backend.rag.vector_consumer import answer_rrf_question, answer_vector_question
from backend.retrieval.embedding import EmbeddingProvider, OllamaEmbeddingProvider
from backend.retrieval.elasticsearch import (
    ElasticsearchBm25Index,
    ElasticsearchTransport,
    UrllibElasticsearchTransport,
)
from backend.retrieval.fixture import filter_authorized_chunks, load_chunks, load_scope
from backend.retrieval.hybrid import (
    DEFAULT_CANDIDATE_K,
    DEFAULT_RRF_K,
    LocalRrfHybridRetriever,
)
from backend.retrieval.milvus import MilvusTransport, MilvusVectorIndex, PymilvusTransport
from backend.retrieval.online import (
    OnlineScopeForbiddenError,
    OnlineVersionRrfRetriever,
    OnlineVisibilityUnavailableError,
)
from backend.retrieval.remote_config import RemoteRetrievalConfigV1
from backend.retrieval.remote_hybrid import RemoteRrfHybridRetriever
from backend.retrieval.sqlite_fts import SQLiteFtsIndex
from backend.retrieval.vector import DEFAULT_VECTOR_MIN_SCORE, LocalVectorIndex


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS_PATH = ROOT / "fixtures" / "chunks-v1.json"
DEFAULT_SCOPE_PATH = ROOT / "fixtures" / "authorized-scope-v1.json"
RetrievalBackend = Literal[
    "lexical_overlap",
    "sqlite_fts5",
    "local_vector",
    "local_rrf",
    "elasticsearch_bm25",
    "milvus_vector",
    "remote_rrf",
    "online_remote_rrf",
]


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
    elasticsearch_url: str = "http://127.0.0.1:9200",
    elasticsearch_index: str | None = None,
    elasticsearch_transport: ElasticsearchTransport | None = None,
    milvus_uri: str = "http://127.0.0.1:19530",
    milvus_collection: str | None = None,
    milvus_transport: MilvusTransport | None = None,
    remote_retrieval_config: RemoteRetrievalConfigV1 | None = None,
    authenticated_owner_id: str | None = None,
    online_rrf_retriever: OnlineVersionRrfRetriever | None = None,
) -> FastAPI:
    chunks = load_chunks(chunks_path)
    sqlite_index: SQLiteFtsIndex | None = None
    vector_index: LocalVectorIndex | None = None
    hybrid_retriever: LocalRrfHybridRetriever | None = None
    elasticsearch_bm25_index: ElasticsearchBm25Index | None = None
    milvus_vector_index: MilvusVectorIndex | None = None
    remote_rrf_retriever: RemoteRrfHybridRetriever | None = None
    remote_top_k = 3
    if retrieval_backend == "online_remote_rrf":
        if authenticated_owner_id is None or online_rrf_retriever is None:
            raise ValueError(
                "authenticated_owner_id and online_rrf_retriever are required "
                "for online_remote_rrf retrieval"
            )
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
    elif retrieval_backend == "elasticsearch_bm25":
        if elasticsearch_index is None:
            raise ValueError("elasticsearch_index is required for elasticsearch_bm25 retrieval")
        if elasticsearch_transport is None:
            elasticsearch_transport = UrllibElasticsearchTransport(base_url=elasticsearch_url)
        elasticsearch_bm25_index = ElasticsearchBm25Index(
            elasticsearch_index, elasticsearch_transport
        )
        elasticsearch_bm25_index.verify_source(chunks)
    elif retrieval_backend == "milvus_vector":
        if milvus_collection is None:
            raise ValueError("milvus_collection is required for milvus_vector retrieval")
        if embedding_provider is None:
            embedding_provider = OllamaEmbeddingProvider(
                model=embedding_model, base_url=embedding_base_url
            )
        if milvus_transport is None:
            milvus_transport = PymilvusTransport(uri=milvus_uri)
        milvus_vector_index = MilvusVectorIndex(milvus_collection, milvus_transport)
        milvus_vector_index.verify_source(chunks)
        milvus_vector_index.verify_provider(embedding_provider)
    elif retrieval_backend == "remote_rrf":
        if remote_retrieval_config is None:
            raise ValueError("remote_retrieval_config is required for remote_rrf retrieval")
        elasticsearch_config = remote_retrieval_config.elasticsearch
        milvus_config = remote_retrieval_config.milvus
        fusion_config = remote_retrieval_config.fusion
        if elasticsearch_transport is None:
            elasticsearch_transport = UrllibElasticsearchTransport(
                base_url=elasticsearch_config.url,
                timeout_seconds=elasticsearch_config.timeout_seconds,
            )
        elasticsearch_bm25_index = ElasticsearchBm25Index(
            elasticsearch_config.index, elasticsearch_transport
        )
        elasticsearch_bm25_index.verify_source(chunks)
        if embedding_provider is None:
            embedding_provider = OllamaEmbeddingProvider(
                model=milvus_config.embedding_model,
                base_url=milvus_config.embedding_base_url,
            )
        if milvus_transport is None:
            milvus_transport = PymilvusTransport(uri=milvus_config.uri)
        milvus_vector_index = MilvusVectorIndex(
            milvus_config.collection, milvus_transport
        )
        milvus_vector_index.verify_source(chunks)
        milvus_vector_index.verify_provider(embedding_provider)
        remote_rrf_retriever = RemoteRrfHybridRetriever(
            elasticsearch_bm25_index,
            milvus_vector_index,
            embedding_provider,
            candidate_k=fusion_config.candidate_k,
            rrf_k=fusion_config.rrf_k,
            vector_min_score=fusion_config.vector_min_score,
        )
        remote_top_k = fusion_config.top_k
    elif retrieval_backend not in (
        "lexical_overlap",
        "sqlite_fts5",
        "local_vector",
        "online_remote_rrf",
    ):
        raise ValueError(f"unsupported retrieval backend: {retrieval_backend}")

    boundaries = {
        "lexical_overlap": "Stage 0 fixture-only lexical retrieval with Fake LLM",
        "sqlite_fts5": "local SQLite FTS5/BM25 with Fake LLM",
        "local_vector": "real local dense vector retrieval with Fake LLM",
        "local_rrf": "local SQLite FTS5 plus dense RRF retrieval with Fake LLM",
        "elasticsearch_bm25": "remote Elasticsearch BM25 retrieval with Fake LLM",
        "milvus_vector": "remote Milvus/BGE-M3 vector retrieval with Fake LLM",
        "remote_rrf": "remote Elasticsearch plus Milvus RRF retrieval with Fake LLM",
        "online_remote_rrf": (
            "PostgreSQL READY-gated versioned Elasticsearch plus Milvus RRF "
            "retrieval with Fake LLM"
        ),
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
    app.state.elasticsearch_bm25_index = elasticsearch_bm25_index
    app.state.milvus_vector_index = milvus_vector_index
    app.state.remote_rrf_retriever = remote_rrf_retriever
    app.state.remote_top_k = remote_top_k
    app.state.authenticated_owner_id = authenticated_owner_id
    app.state.online_rrf_retriever = online_rrf_retriever

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
        requested_document_ids = set(payload.document_ids)
        if app.state.retrieval_backend == "online_remote_rrf":
            base_scope = {
                **base_scope,
                "user_id": app.state.authenticated_owner_id,
                "tenant_id": app.state.authenticated_owner_id,
                "include_public": False,
                "document_ids": [],
                "library_ids": [],
                "folder_ids": [],
            }
        else:
            authorized_document_ids = {
                chunk["document_id"]
                for chunk in filter_authorized_chunks(chunks, base_scope)
            }
            if not requested_document_ids.issubset(authorized_document_ids):
                return _error_response(
                    status_code=403,
                    code="RAG_FORBIDDEN_SCOPE",
                    message="请求包含未授权文档。",
                    retryable=False,
                )

        effective_scope = _narrow_scope(base_scope, payload.document_ids)
        if app.state.retrieval_backend == "online_remote_rrf":
            try:
                answer = answer_online_ready_question(
                    payload.question,
                    effective_scope,
                    chunks,
                    app.state.online_rrf_retriever,
                    owner_id=app.state.authenticated_owner_id,
                    document_ids=payload.document_ids,
                )
            except OnlineScopeForbiddenError:
                return _error_response(
                    status_code=403,
                    code="RAG_FORBIDDEN_SCOPE",
                    message="请求包含未授权或未就绪文档。",
                    retryable=False,
                )
            except OnlineVisibilityUnavailableError:
                return _error_response(
                    status_code=403,
                    code="RAG_FORBIDDEN_SCOPE",
                    message="请求范围当前无法由事实源验证。",
                    retryable=True,
                )
        elif app.state.retrieval_backend == "remote_rrf":
            answer = answer_remote_rrf_question(
                payload.question,
                effective_scope,
                chunks,
                app.state.remote_rrf_retriever,
                top_k=app.state.remote_top_k,
            )
        elif app.state.retrieval_backend == "elasticsearch_bm25":
            answer = answer_elasticsearch_question(
                payload.question,
                effective_scope,
                chunks,
                app.state.elasticsearch_bm25_index,
            )
        elif app.state.retrieval_backend == "milvus_vector":
            answer = answer_milvus_question(
                payload.question,
                effective_scope,
                chunks,
                app.state.milvus_vector_index,
                app.state.embedding_provider,
                min_score=app.state.vector_min_score,
            )
        elif app.state.retrieval_backend == "sqlite_fts5":
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
