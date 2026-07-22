# 本地 PDF 到 ChunkRecordV1

## Legacy 本地边界

当前实现仅处理具有可提取文本层的 PDF：

- 使用 `pypdf`，不调用网络；
- 不启用 OCR、Docling、远程模型、数据库或向量库；
- 切分策略必须显式选择；
- PDF SHA-256 不一致时停止；
- `REVIEW` 状态必须显式允许，`FAILED` 状态始终停止；
- 权限字段由调用方可信配置注入，不从 PDF 内容推测；
- 未生成向量时使用 `embedding_version=not_embedded_v1`。

## 命令

```bash
.venv/bin/python -m backend.ingestion.cli \
  --pdf /local/path/paper.pdf \
  --expected-sha256 <catalog-sha256> \
  --document-id doc_local_001 \
  --tenant-id tenant_fixture \
  --visibility private \
  --library-scope-id lib_fixture \
  --strategy section_parent_child_v1 \
  --output /tmp/chunks-v1.json
```

输出文件是 `ChunkRecordV1` JSON 数组，可以直接传给现有 Fixture 检索和 Answer API。PDF 与输出均不得提交到仓库。

## 策略

- `fixed_boundary_v1`：固定长度基线；
- `paragraph_sentence_v1`：尽量保留段落和句子；
- `section_parent_child_v1`：按主要章节切分并生成父 Chunk 标识。

项目不设置自动策略。首次单篇论文联调显式使用 `section_parent_child_v1`。

## 阶段 1 运行存储

`backend.ingestion.persistent.prepare_and_persist_pdf_ingestion` 将同一解析和 Chunk 实现接到运行存储：

```text
校验 PDF SHA-256
→ 按 owner_id 幂等建立文档映射
→ 原子绑定 document_version_id 与入库幂等 Key
→ REGISTERED/FAILED/REVIEW 进入 PROCESSING
→ 解析与 ChunkRecordV1
→ 以 owner/document/version 的不透明确定性对象键原子保存 PDF
→ 将不可变 Chunk 快照和 PDF 对象定位注册到 PostgreSQL
→ 重读并核对 PDF SHA-256、Chunk 数量和完整快照指纹
→ 保持 PROCESSING，等待 ES/Milvus 双索引
```

PDF 载荷保存在调用方配置的持久对象根目录，PostgreSQL 只保存对象键、哈希、大小和 Chunk 快照；不会把 PDF 字节塞入事实源。当前 `filesystem_v1` 是不新增依赖的 MVP 对象后端，正式 MinIO 适配仍独立保留。该路径将 PostgreSQL `document_version_id` 写入现有 `ChunkRecordV1.version_id`，并固定将待索引 Chunk 输出为 `is_active=false`。相同请求重放会复用映射、版本、任务、对象键和 Chunk ID；对象或 Chunk 载荷漂移会失败关闭。

## 双索引生命周期协调

`backend.ingestion.index_lifecycle.publish_prepared_indexes` 接收两个显式的版本索引写入器。两路先以非活动 Chunk 幂等暂存并核对版本、数量和源指纹，再逐侧记录 PostgreSQL 状态；只有两路激活均成功，才在同一数据库事务中将版本提升为 `READY` 并将入库任务记为 `SUCCEEDED`。单侧暂存或激活失败会记录稳定错误码，已激活侧执行非活动补偿，版本继续保持 `PROCESSING`，可由同一请求重放。

删除、撤权和过期使用 `inactivate_and_schedule_cleanup`：先提交 PostgreSQL `INACTIVE`，再失效查询可见性、将两路索引标记为非活动，最后分别排入异步物理清理。后续清理失败只会形成待处理结果，不会回滚事实源或重新激活版本。

Elasticsearch 侧已实现 `ElasticsearchVersionIndexWriter`：物理索引名由 owner/version 身份哈希确定，不暴露原始 ID；首次写入创建严格 Mapping 和隐藏物理索引，重放时核对 owner、document、version、源 Chunk 指纹、数量及 Mapping，允许补齐部分写入但拒绝来源、配置、外来 Chunk 或超量漂移。激活、失活和物理删除均再次核对 owner/version 身份。在线路由不依赖独立 Alias 真相，而是在 PostgreSQL 返回精确 `READY` 版本后再次核验隐藏物理索引的身份、数量和全部活动状态。

Milvus 侧已实现 `MilvusVersionIndexWriter`：每个 owner/version 使用身份哈希确定的独立 Collection；描述固定源 Chunk、Embedding provider/model/digest、维度、COSINE/HNSW 参数和完整向量指纹。完整重放只核验已有 payload 与向量，不重复调用 Embedding；部分写恢复先重新计算预期向量并核验已有行，再只 Upsert 缺失行。激活/失活同步更新标量字段和完整 payload，物理删除再次核验 Collection 身份。在线路由再次核验 Collection 身份、Embedding 模型和全部活动行。

持久化物理清理由 `PersistentIndexCleanupScheduler` 和 `PersistentIndexCleanupWorker` 完成。`0002_cleanup_queue.sql` 与 `0004_runtime_snapshots.sql` 只允许已进入 `INACTIVE` 的 owner/document/version 入队；每次失效固定产生 ES、Milvus 和 `runtime_snapshot` 三项任务。运行快照任务先按 PostgreSQL 中的精确对象定位核验并删除 PDF，再删除 PostgreSQL Chunk 和对象注册；数据库触发器禁止在版本仍活动时清除。Worker 先恢复过期租约，再通过 `FOR UPDATE SKIP LOCKED` 独占一项到期任务，失败时仅记录稳定错误码并按有界指数退避进入 `RETRY`。删除已经不存在的物理对象仍按成功处理，不会重新激活事实源。

`PostgresReadyRouteResolver` 只接收 PostgreSQL `READY + is_active` 版本，并要求请求中的每个 `document_id` 都属于服务端鉴权 owner；`OnlineVersionRrfRetriever` 随后按这些精确版本从 PostgreSQL 加载 Chunk 快照，再选择确定性 ES Index 与 Milvus Collection并统一 RRF。Answer API 的 `online_remote_rrf` 装配只接受服务端 `authenticated_owner_id`，不加载 Fixture Chunk 或 Fixture Scope；PostgreSQL 快照、物理路由或候选身份任一无法证明时返回现有 403 合同。

本地代码和专项门禁已覆盖 PDF 对象重开、Chunk 快照重放、READY-only 加载、持久化快照 Answer API、INACTIVE 后 403 以及三项可恢复物理清理。先前远程基础设施生命周期 Canary 已通过；新增的 `0004` 迁移和持久化 Answer API v2 Canary 仍需由用户在远程主机实跑，未回收该证据前不宣称整个阶段 1 完成。
