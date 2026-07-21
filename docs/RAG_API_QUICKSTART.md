# 非流式 RAG Answer API

## 边界

当前 API 是成员 A 的本地实现，默认保持 Fixture 词项重叠模式，也支持显式注入 SQLite FTS5/BM25：

- 使用仓库内 `AuthorizedScopeV1` 和 `ChunkRecordV1` Fixture；
- 客户端 `document_ids` 只能收窄服务端范围，不能扩大权限；
- 返回 `RagAnswerV1` 或 `ErrorV1`；
- 仅支持 `stream=false`；
- SQLite 模式使用本地持久化索引并校验源 Chunk 指纹；
- 不连接 PostgreSQL、Elasticsearch、Milvus、真实 LLM 或远程 4090。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
SSL_CERT_FILE=/etc/ssl/cert.pem python -m pip install '.[dev,server]'
```

`SSL_CERT_FILE` 只用于本机 Python 未配置默认 CA 文件的情况；如果 `pip` 能正常校验证书，则无需设置。

## 启动

```bash
uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

## 请求

```bash
curl -sS http://127.0.0.1:8000/api/v1/rag/answers \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "How are candidates combined before reranking?",
    "document_ids": ["doc_fixture_001"],
    "stream": false
  }'
```

无证据问题仍返回 HTTP 200，但 `status=NO_EVIDENCE`。请求越权文档返回 HTTP 403 和 `RAG_FORBIDDEN_SCOPE`；字段无效返回 HTTP 422 和 `RAG_INVALID_REQUEST`。

## 测试

```bash
make test
```

响应中的 `FIXTURE_ONLY_FAKE_LLM` 是强制边界，当前输出不得作为真实检索或模型质量结果。

SQLite 模式由 `create_app(retrieval_backend="sqlite_fts5", index_path=...)` 注入，响应边界为 `LOCAL_SQLITE_FTS5_FAKE_LLM`。公开可执行入口是 `make sqlite-fts-fixture-smoke`，详见 [`SQLITE_FTS_RETRIEVAL.md`](SQLITE_FTS_RETRIEVAL.md)。

真实本地向量模式使用 `local_vector` 和 `vector_index_path`；RRF 混合模式使用 `local_rrf`，同时传入 FTS `index_path` 与 `vector_index_path`。两者仍由 Fake LLM 拼装答案，并分别携带真实向量或 RRF 的执行边界警告。公开入口为 `make vector-fixture-smoke` 和 `make rrf-fixture-smoke`，详见 [`LOCAL_VECTOR_RRF_RETRIEVAL.md`](LOCAL_VECTOR_RRF_RETRIEVAL.md)。
