# 本地 SQLite FTS5/BM25 检索基线

## 结论

项目已接入第一种持久化本地检索后端：SQLite FTS5 + BM25。它读取现有 `ChunkRecordV1`，生成被 Git 忽略的索引文件，通过原有授权判断后向同一个 Answer API 返回 Evidence。无需远程主机、额外 Python 依赖或模型下载。

当前执行边界为 `LOCAL_API_SQLITE_FTS5_FAKE_LLM`。检索后端是真实的本地持久化索引，但答案仍由 Fake LLM 证据拼装器生成，因此不能表述为真实模型质量通过，也不能替代后续 Elasticsearch、Milvus 或向量检索验收。

## 索引合同

- Schema：`sqlite_fts_index_v1`；
- 后端：`sqlite_fts5_bm25`；
- 分词：SQLite 内置 `porter unicode61`；
- 查询：安全分词后的 OR 查询，不直接执行用户输入的 FTS 语法；
- 排名：`bm25`，章节列和正文列权重为 `2.0,1.0`；
- 来源绑定：索引记录有序 Chunk 规范 JSON 的 SHA-256 和 Chunk 数；
- 失效关闭：来源指纹、Chunk 数、Schema 或算法配置不一致时拒绝启动或检索；
- 权限：检索命中必须再次通过既有 `AuthorizedScopeV1` 判断，未授权、跨租户和失效 Chunk 不得进入 Evidence。

## 公开 Fixture 冒烟

```bash
source .venv/bin/activate
make sqlite-fts-fixture-smoke
```

该命令在 `runtime/evaluation/` 重建索引，并通过同一个评测 Harness 调用 Answer API。公开结果必须为 6/6，覆盖 2 个可回答、3 个无证据和 1 个越权用例。

也可以分步执行：

```bash
.venv/bin/python -m backend.retrieval.sqlite_fts build \
  --chunks fixtures/chunks-v1.json \
  --output runtime/evaluation/fixture-sqlite-fts-v1.sqlite

.venv/bin/python -m backend.evaluation.harness \
  --cases evaluation/suites/fixture-sqlite-fts-v1.jsonl \
  --chunks fixtures/chunks-v1.json \
  --scope fixtures/authorized-scope-v1.json \
  --retrieval-backend sqlite_fts5 \
  --index runtime/evaluation/fixture-sqlite-fts-v1.sqlite \
  --output runtime/evaluation/fixture-sqlite-fts-v1-report.json
```

## 三论文同题集结果

三篇论文共 316 个 Chunk，索引来源指纹为 `2bc8cb4aab38e800954c0a32faafc7053c359d7fe0165c634a95eb1b96b2b4ff`。沿用此前 15 个问题和人工目标页，只将期望警告从 Fixture 边界改为 SQLite FTS5 边界。

首轮结果为 14/15：唯一失败的可回答题返回了同文档的评分细节页，但目标概览页位于第 4 名。诊断发现默认分词无法让 `graded` 匹配 `grading`，且功能词 `each` 产生排名噪声。改用 Porter 词干分析并将 `each` 设为停用词后，在不修改问题、页码或 `top_k=3` 的情况下达到：

| 类别 | 通过/总数 |
|---|---:|
| `ANSWERABLE` | 9/9 |
| `NO_EVIDENCE` | 3/3 |
| `FORBIDDEN` | 3/3 |
| 合计 | 15/15 |

真实题集、Chunk、SQLite 索引和完整报告只存在于 `runtime/evaluation/local-3-paper-v1/`，不进入 Git。

## 下一边界

该后端是本地 BM25 基线，不是最终混合检索。下一阶段应固定同一题集和 `top_k`，只新增一个向量检索变量，再比较词项重叠、SQLite BM25、向量和混合检索；真实生成模型仍后置。
