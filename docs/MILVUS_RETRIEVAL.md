# Milvus 向量检索适配器

## 当前边界

该适配器把同一 `ChunkRecordV1`、授权范围和 Embedding 身份接入远程 Milvus。回答仍由 Fake LLM 生成，执行边界为 `REMOTE_API_MILVUS_BGE_M3_FAKE_LLM`。远程 316 Chunk/15 题 Canary 已完成；这不代表远程 500 题、性能或生产参数已经验收。

## 固定身份与失败关闭

- Collection 描述绑定源 Chunk SHA-256、数量、Embedding provider/model/digest、维度、输入模板和归一化版本；
- Schema 关闭动态字段，保存 ACL 过滤字段与完整 Chunk payload；
- 查询前校验 Collection、源数据和模型身份，漂移即失败；
- Milvus 服务端先执行租户、可见性、文档/库范围和 `is_active` 过滤，返回后再复用应用授权判断；
- Folder-only 范围当前无法由该 Schema 解析，按失败关闭处理。

## 本地版本写入器

`backend.ingestion.milvus_writer.MilvusVersionIndexWriter` 实现阶段 1 的版本化派生索引写入。每个 owner/version 对应一个身份哈希命名的独立 Collection，原始 ID 不进入 Collection 名；Collection 不会自动加入在线配置。描述除检索参数外还绑定 document/version、源 Chunk 指纹、数量和完整 float32 向量指纹。

首次写入使用 Upsert 并强制 Chunk 保持非活动。完整重放验证 Schema、payload、模型身份和实际向量指纹，不重复调用 Embedding；部分写恢复先重新计算并验证已有向量，只补缺失主键。激活/失活同时更新 Milvus 标量与 payload 中的 `is_active`，删除前再次核验 Collection 身份。上述能力目前只通过本地确定性测试，尚未在远程 Milvus/BGE-M3 上复测，也没有接入在线 READY 路由。

## 工程基线参数

- `FLOAT_VECTOR`，BGE-M3 为 1024 维；
- `COSINE`；
- HNSW：`M=16`、`efConstruction=200`、查询 `ef=64`；
- `Strong` consistency，1 shard；
- 默认最低分 `0.50`。

这些参数只用于固定 Canary，已完成 316 Chunk 验证，但尚未经过 500 题、并发和资源测试，不能标记为生产最终值。

## 远程 Canary 结果

- 固定 15 题结果为 `12/15`：`ANSWERABLE 6/9`、`NO_EVIDENCE 3/3`、`FORBIDDEN 3/3`；
- 结果与本地精确 BGE-M3 向量基线一致；
- 3 个未通过项分别缺少冻结目标证据页 `doc_arxiv_2602_11409:6-6`、`doc_arxiv_2601_03260:8-8`、`doc_arxiv_2603_04915:5-5`；
- 未通过项按真实召回缺口保留，不修改题目、目标页、阈值或 HNSW 参数追求满分。

## Windows PowerShell 远程验证

先使用仓库 Python 3.11 安装可选依赖：

```powershell
& $py -m pip install -e ".[milvus]"
```

使用新的版本化 Collection 建立索引：

```powershell
& $py -m backend.retrieval.milvus --uri "http://127.0.0.1:19530" --collection "zhiyan_canary_chunks_v1" --model "bge-m3:latest" build --chunks "remote-es-canary-input-v1/chunks-v1.json"
```

检查身份：

```powershell
& $py -m backend.retrieval.milvus --uri "http://127.0.0.1:19530" --collection "zhiyan_canary_chunks_v1" --model "bge-m3:latest" inspect
```

运行同一 15 题 Harness：

```powershell
& $py -m backend.evaluation.harness --cases "remote-es-canary-input-v1/cases-milvus-v1.jsonl" --chunks "remote-es-canary-input-v1/chunks-v1.json" --scope "remote-es-canary-input-v1/authorized-scope-v1.json" --suite-id "remote-milvus-canary-v1" --retrieval-backend "milvus_vector" --milvus-uri "http://127.0.0.1:19530" --milvus-collection "zhiyan_canary_chunks_v1" --embedding-model "bge-m3:latest" --output "remote-es-canary-input-v1/milvus-report.json"
```

Milvus 专用题目副本只调整预期执行边界告警，不修改问题、分类或目标证据。Collection 名不能复用已有名称，适配器不会覆盖现有 Collection。运行报告留在远程本机，不提交私有题目、Chunk、模型或凭据。

与 Elasticsearch 共用的候选接口、版本化配置和最小 RRF 见 [Elasticsearch + Milvus 最小 RRF](REMOTE_RRF_RETRIEVAL.md)。远程 RRF Canary 已完成 `14/15`，与 ES 单路持平，未产生净增益。
