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

当前未连接远程 PostgreSQL，未保存 PDF/Chunk 私有运行产物，也未将任何版本提升为 `READY`。
