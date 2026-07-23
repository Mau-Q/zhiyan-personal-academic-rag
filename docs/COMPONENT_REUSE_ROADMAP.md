# 通用组件复用路线

## 原则

项目继续自主管理 PostgreSQL 唯一事实源、owner 权限前置、文档版本、
ES/Milvus 双索引 READY、失效先行、补偿/清理和引用身份。成熟组件只放在
这些合同下面，通过窄适配器复用；不引入第二套业务身份、状态机或在线真值。

每项复用都是独立 Gate。不得把数据库迁移、索引传输、PDF 解析、遥测和
评测框架同时引入，也不得以替换框架为由重跑或改写已经冻结的远程证据。

## 已采用

| 能力 | 复用组件 | 当前边界 |
|---|---|---|
| Milvus SDK | PyMilvus `MilvusClient` | 已在可选 `milvus` 依赖和 `PymilvusTransport` 中使用；业务身份、Schema 指纹、READY 与清理仍由仓库控制 |
| PDF 文本基础解析 | `pypdf` | 只处理可抽取文本的 PDF；无 OCR、版面或表格恢复 |
| 固定 Reranker | `sentence-transformers.CrossEncoder` | 冻结 `test=100` 质量门及 Windows RTX 4090 组件 P95 已通过；受控在线窄适配器已本地实现，只在 READY/ACL 与 RRF 后重排既有候选，默认路由仍待远程组合 P95 Gate 后决定 |

## 后续独立 Gate

### 1. Elasticsearch 批量传输

候选组件：官方 `elasticsearch-py` 与 `streaming_bulk`。

引入条件：

- 需要目标规模批次切分、429 退避或逐项失败证据；
- 保持现有 Index 命名、Mapping/源指纹、owner/version 校验、
  staged/active 状态与写后对账不变。

验收必须覆盖部分 Bulk 失败、429 有界重试、重复写、UTF-8、写后数量和
载荷漂移。该 Gate 只替换传输层，不与 Mapping、分词或 RRF 调参混合。

### 2. Docling 解析适配器

候选组件：Docling `DocumentConverter` 和标准 PDF Pipeline。

引入条件：

- 使用 20～30 篇含扫描页、表格、公式、双栏或复杂阅读顺序的论文建立
  独立解析对比；
- 输出先进入 Document IR，再由现有规范化、确定性 Splitter 和
  `ChunkRecordV1` 生成身份；
- Docling 不产生业务 `document_id/document_version_id/chunk_id`，
  也不控制生命周期或 READY。

评测记录页码、阅读顺序、表格/公式/OCR 覆盖、解析失败、耗时和资源。
没有实证增益时继续保留 `pypdf` 文本路径。

### 3. OpenTelemetry 技术遥测

候选组件：OpenTelemetry Python SDK 与 FastAPI/HTTP 客户端插桩。

引入条件：

- 先冻结业务 Trace 可记录字段、脱敏规则和保留期；
- 技术 Span 只记录阶段、耗时、状态和哈希/枚举，不记录完整问题、
  Chunk 正文、凭据或对象路径；
- 业务可审计快照继续由 PostgreSQL/Trace 合同保存，OTel 不成为事实源。

### 4. Ragas 辅助语义评测

候选组件：Ragas。

引入条件：

- 进入 Claim–Evidence 或生成质量独立 Gate；
- 模型、Prompt、温度、数据拆分和成本有完整谱系；
- 只作为 GPT/LLM 辅助指标，不替代 175 题人工标签、Acceptance、
  ACL、页码、引用存在性或确定性 nDCG/Precision。

### 5. Alembic Schema 迁移管理

当前不迁移。现有 `0001`～`0005` 已在远程应用并由
`rag_schema_migrations` 记录源文件 SHA-256。只有迁移数量和分支维护
成本显著上升时，才设计独立切换 Gate：

- 明确旧迁移 ID/摘要到 Alembic revision 的一次性映射和 stamp；
- 保留已应用 SQL 字节与审计证据，不重写历史；
- 先在空库和旧版本快照上验证升级，再由用户在 Windows 执行；
- 复杂数据搬迁继续使用应用专属脚本，不由 autogenerate 决定。

### 6. 长任务编排

Temporal 当前不采用。只有出现多 Worker、多天任务、人工暂停恢复、
跨服务补偿关系明显失控或现有 PostgreSQL 租约/重放难以维护时再评估。
届时 Workflow 只负责编排，PostgreSQL 业务事实和 READY 条件仍不迁走。

## 仅作实验参考

LangChain RecordManager、LlamaIndex IngestionPipeline、Haystack Pipeline
可用于小型对照实验或阅读测试设计，不接管生产入库与在线链路。它们的
Document/Record/Pipeline 抽象不能替代 owner-scoped PostgreSQL 事实、
双索引原子可见、撤权先失效和物理清理合同。

FastEmbed 可作为资源受限 Cross-Encoder 的备选实验后端，但不得在同一个
固定 Reranker Gate 中同时改变模型和推理后端。当前已冻结的
`sentence-transformers + bge-reranker-v2-m3` 结果必须保留。

固定 Reranker 的在线窄适配器已本地实现：只允许在 owner/READY
过滤和 ES/Milvus RRF 之后重排既有候选，不得扩张候选或绕过无证据、
越权和失效决定；无模型、标题不可用、推理失败或分数非法时回退同一批
已授权 RRF，身份无法证明时仍失败关闭。下一独立 Gate 只在 Windows
RTX 4090 上测量包含 READY 路由、召回、融合和重排的组合 P95；通过前
默认路由不变。
