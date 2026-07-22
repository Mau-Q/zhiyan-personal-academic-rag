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

## 阶段 1 持久化准备

`backend.ingestion.persistent.prepare_persistent_pdf_ingestion` 将同一解析和 Chunk 实现接到 PostgreSQL 事实源：

```text
校验 PDF SHA-256
→ 按 owner_id 幂等建立文档映射
→ 原子绑定 document_version_id 与入库幂等 Key
→ REGISTERED/FAILED/REVIEW 进入 PROCESSING
→ 解析与 ChunkRecordV1
→ 记录页码/Chunk 完成时间
→ 保持 PROCESSING，等待 ES/Milvus 双索引
```

该路径将 PostgreSQL `document_version_id` 写入现有 `ChunkRecordV1.version_id`，并固定将待索引 Chunk 输出为 `is_active=false`。只有后续 ES 和 Milvus 均就绪且事实源进入 `READY` 后，才能对在线检索可见。相同请求重放会复用映射、版本、任务和 Chunk ID；同一幂等 Key 换用另一 PDF 会在产生新版本前失效关闭。

## 双索引生命周期协调

`backend.ingestion.index_lifecycle.publish_prepared_indexes` 接收两个显式的版本索引写入器。两路先以非活动 Chunk 幂等暂存并核对版本、数量和源指纹，再逐侧记录 PostgreSQL 状态；只有两路激活均成功，才在同一数据库事务中将版本提升为 `READY` 并将入库任务记为 `SUCCEEDED`。单侧暂存或激活失败会记录稳定错误码，已激活侧执行非活动补偿，版本继续保持 `PROCESSING`，可由同一请求重放。

删除、撤权和过期使用 `inactivate_and_schedule_cleanup`：先提交 PostgreSQL `INACTIVE`，再失效查询可见性、将两路索引标记为非活动，最后分别排入异步物理清理。后续清理失败只会形成待处理结果，不会回滚事实源或重新激活版本。

Elasticsearch 侧已实现 `ElasticsearchVersionIndexWriter`：物理索引名由 owner/version 身份哈希确定，不暴露原始 ID；首次写入创建严格 Mapping 和隐藏物理索引，重放时核对 owner、document、version、源 Chunk 指纹、数量及 Mapping，允许补齐部分写入但拒绝来源、配置、外来 Chunk 或超量漂移。激活、失活和物理删除均再次核对 owner/version 身份。该写入器不会创建在线 Alias，因此本地激活不等于在线可检索。

Milvus 侧已实现 `MilvusVersionIndexWriter`：每个 owner/version 使用身份哈希确定且未接入在线路由的独立 Collection；描述固定源 Chunk、Embedding provider/model/digest、维度、COSINE/HNSW 参数和完整向量指纹。完整重放只核验已有 payload 与向量，不重复调用 Embedding；部分写恢复先重新计算预期向量并核验已有行，再只 Upsert 缺失行。激活/失活同步更新标量字段和完整 payload，物理删除再次核验 Collection 身份。

当前尚未连接远程 PostgreSQL、Elasticsearch、Milvus 或 Embedding 服务，未实现持久化清理队列、在线 Alias/Collection 与 READY 路由或 Answer API 的 PostgreSQL 可见性门禁，也没有将任何真实版本提升为 `READY`。
