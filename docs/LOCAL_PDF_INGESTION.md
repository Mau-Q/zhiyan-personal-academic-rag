# 本地 PDF 到 ChunkRecordV1

## 边界

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
python3 -m backend.ingestion.cli \
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
