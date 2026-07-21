# Elasticsearch BM25 检索适配器

## 执行边界

该适配器把 `ChunkRecordV1` 写入真实 Elasticsearch，并在查询中执行服务端授权过滤。回答仍由 Fake LLM 证据拼装器生成，因此执行边界为 `REMOTE_API_ELASTICSEARCH_BM25_FAKE_LLM`，不得表述为真实生成模型完成。

## 固定结构

- Index Schema：`elasticsearch_bm25_index_v1`；
- Index：1 分片、0 副本，适用于当前单节点工程基线；
- `text`、`section_path`：`standard` analyzer；
- `section_path^2 + text`：OR 模式 BM25；
- 身份：Mapping `_meta` 固定算法配置、源 Chunk SHA-256 和数量；
- ACL：`is_active`、`visibility`、`tenant_id`、`document_id`、`library_scope_ids` 在 Elasticsearch 查询内过滤，返回后再次失败关闭检查；
- 漂移：Mapping 配置、源指纹或数量不匹配时拒绝启动或查询。

当前 analyzer 只作为可复测工程基线，不是最终中文分词选型。生产别名、认证、TLS、备份和性能参数继续待定。

## Windows 远程 Fixture 验证

远程仓库更新后，在仓库根目录使用 `.venv` 解释器执行：

```powershell
$py = ".\.venv\Scripts\python.exe"
```

```powershell
& $py -m backend.retrieval.elasticsearch --url "http://127.0.0.1:9200" --index "zhiyan-fixture-chunks-v1" build --chunks "fixtures/chunks-v1.json"
```

```powershell
& $py -m backend.retrieval.elasticsearch --url "http://127.0.0.1:9200" --index "zhiyan-fixture-chunks-v1" inspect
```

```powershell
& $py -m backend.retrieval.elasticsearch --url "http://127.0.0.1:9200" --index "zhiyan-fixture-chunks-v1" query --chunks "fixtures/chunks-v1.json" --scope "fixtures/authorized-scope-v1.json" --question "How are candidates combined before reranking?" --top-k 3
```

预期首条结果为 `chunk_fixture_001`。重复执行 `build` 会因 Index 已存在而失败关闭，不得为了重跑静默覆盖已有索引。

## 下一门禁

1. 远程公开 Fixture 建索引、inspect 和授权查询通过；
2. 再用私有 316 Chunk 建立独立版本 Index；
3. 固定 15 题 Canary 与 SQLite 结果对比；
4. Elasticsearch 单路通过后才开始 Milvus 适配器。

