# Milvus 向量检索适配器

## 当前边界

该适配器把同一 `ChunkRecordV1`、授权范围和 Embedding 身份接入远程 Milvus。回答仍由 Fake LLM 生成，执行边界为 `REMOTE_API_MILVUS_BGE_M3_FAKE_LLM`。本地测试通过不代表远程 316 Chunk、500 题、性能或生产参数已经验收。

## 固定身份与失败关闭

- Collection 描述绑定源 Chunk SHA-256、数量、Embedding provider/model/digest、维度、输入模板和归一化版本；
- Schema 关闭动态字段，保存 ACL 过滤字段与完整 Chunk payload；
- 查询前校验 Collection、源数据和模型身份，漂移即失败；
- Milvus 服务端先执行租户、可见性、文档/库范围和 `is_active` 过滤，返回后再复用应用授权判断；
- Folder-only 范围当前无法由该 Schema 解析，按失败关闭处理。

## 工程基线参数

- `FLOAT_VECTOR`，BGE-M3 为 1024 维；
- `COSINE`；
- HNSW：`M=16`、`efConstruction=200`、查询 `ef=64`；
- `Strong` consistency，1 shard；
- 默认最低分 `0.50`。

这些参数只用于固定 Canary，尚未经过 316 Chunk/500 题、并发和资源测试，不能标记为生产最终值。

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
& $py -m backend.evaluation.harness --cases "remote-es-canary-input-v1/cases-v1.jsonl" --chunks "remote-es-canary-input-v1/chunks-v1.json" --scope "remote-es-canary-input-v1/authorized-scope-v1.json" --suite-id "remote-milvus-canary-v1" --retrieval-backend "milvus_vector" --milvus-uri "http://127.0.0.1:19530" --milvus-collection "zhiyan_canary_chunks_v1" --embedding-model "bge-m3:latest" --output "remote-es-canary-input-v1/milvus-report.json"
```

Collection 名不能复用已有名称，适配器不会覆盖现有 Collection。运行报告留在远程本机，不提交私有题目、Chunk、模型或凭据。
