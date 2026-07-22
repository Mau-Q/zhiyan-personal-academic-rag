# 单篇真实 PDF 本地联调记录

## 输入身份

- 文献：TRACER: Trajectory Risk Aggregation for Critical Episodes in Agentic Reasoning
- arXiv：`2602.11409`
- 清单页数：10
- SHA-256：`3e7e4628ffadc9183e85341b3a88050c3b58a06dec02926c8f2028b55879d6ea`
- PDF 保存策略：仅本地读取，不进入 Git

## 入库命令

```bash
.venv/bin/python -m backend.ingestion.cli \
  --pdf <local-pdf-path> \
  --expected-sha256 3e7e4628ffadc9183e85341b3a88050c3b58a06dec02926c8f2028b55879d6ea \
  --document-id doc_arxiv_2602.11409 \
  --tenant-id tenant_fixture \
  --visibility private \
  --library-scope-id lib_fixture \
  --strategy section_parent_child_v1 \
  --output <temporary-output-path>
```

## 2026-07-21 结果

- PDF SHA-256 与清单一致；
- `parse_status=PASS`，无解析警告；
- 生成 63 个 `ChunkRecordV1`；
- 页码覆盖第 1～10 页；
- 12 个 Chunk 正确记录跨页范围；
- 63 条 JSON Schema 校验通过；
- 相邻 Chunk 双向链接校验通过；
- 相同输入和配置重复执行，输出文件字节完全一致；
- IEEE 罗马数字主章节可识别；
- 参考文献作者首字母不再误判为主章节。

## Answer API 验证

使用上述真实 Chunk 临时启动本地 API：

| 场景 | HTTP | 结果 |
|---|---:|---|
| 文献内 TRACER 问题 | 200 | `COMPLETED`，返回 Evidence、Citation 和页码 |
| 文献外海洋盐度问题 | 200 | `NO_EVIDENCE` |
| 未授权文档 ID | 403 | `RAG_FORBIDDEN_SCOPE` |

当前回答仍由确定性 Fixture/Fake LLM 消费者拼装，并带有 `FIXTURE_ONLY_FAKE_LLM`。本记录只证明 PDF、Chunk、权限、检索、拒答和引用链路可运行，不代表真实模型质量或真实向量检索效果。
