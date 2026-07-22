# Elasticsearch + Milvus 最小 RRF

## 决策依据

固定 3 论文、15 题、`top_k=3` Canary 已显示两路失败互补：

- Elasticsearch 为 `14/15`，唯一失败是 `local3.answerable.evmbench.modes`；与远程 Milvus 结果一致的本地精确 BGE-M3 在该题命中目标第 2 页；
- Milvus 为 `12/15`，3 个缺失目标页的题都已被 Elasticsearch 命中；
- 两路 Top-3 结果的证据并集因此覆盖 `15/15`，这只证明值得验证最小 RRF，不等于远程 RRF 已实跑 `15/15`。

## 固定结果接口

Elasticsearch 和 Milvus 适配器都先返回 `RankedChunk`：

- `backend`：候选来源；
- `rank`：从 1 开始的连续名次；
- `score`：有限的后端原始分数；
- `chunk`：已通过服务端与应用侧授权校验的 `ChunkRecordV1`。

非法命中结构、非有限分数、不连续名次或重复 `chunk_id` 都失败关闭。既有 RAG 消费者仍通过 `retrieve()` 只获取 Chunk，因此 Answer API 合同不变。

## 固定配置

[`deploy/remote/retrieval-config.example.json`](../deploy/remote/retrieval-config.example.json) 是无密钥的 `remote_retrieval_config_v1`，固定：

- Elasticsearch URL、版本化 Index 名和请求超时；
- Milvus URI、版本化 Collection 名、Embedding 模型与服务 URL；
- `top_k=3`、`candidate_k=20`、`rrf_k=60`、`vector_min_score=0.50`。

配置拒绝额外字段、URL 内凭据和非法范围。`MILVUS_TOKEN` 继续只由主机环境提供，不写入文件或报告。

## 融合规则

两路各自取前 20 个授权候选，仅按 `1 / (60 + rank)` 相加；不直接比较 BM25 分数与 COSINE 分数。并列时按最佳单路名次、`chunk_id` 确定性排序。两路返回同一 `chunk_id` 但 payload 不一致时失败关闭。

## 远程验证边界

当前只完成本地适配器、Fixture Answer API 和 Harness 验证。远程主机后续使用现有 Index、Collection、316 Chunk 和原 15 题；不改题目、目标页、`top_k`、阈值或 HNSW 参数，不同时加入重排、真实 LLM 或 500 题远程全量。具体操作命令在当次交互中一次性给全并分条展示，不写入长期文档。
