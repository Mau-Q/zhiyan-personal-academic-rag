# 最高方案需求追踪

## 1. 最高依据身份

项目的最高层需求、目标架构和验收依据为：

- 文件名：`个人学术空间RAG问答系统建设与测试方案_副本.md`；
- 标题：《个人学术空间 RAG 问答系统建设与测试方案》；
- 当前已核对行数：`725`；
- SHA-256：`43fd5d4af4d38884c2449b9ff39fcee537cf27af5a7a700747a932be5f74dc78`；
- 覆盖范围：第 1～10 章，包括目标、架构、数据治理、在线链路、测试、API、可观测性、部署和阶段 0～5。

原文件由项目文档目录管理，不在源码仓库重复保存。仓库只记录身份、需求映射和实施证据，避免两份正文漂移。原文变更后，必须重新计算哈希并审查本文档。

## 2. 权威层级

1. 当前用户的明确指令；
2. 上述最高方案；
3. 本需求追踪、产品决策和当前阶段文档；
4. 仓库 Harness、执行合同和版本化 API 合同；
5. 代码、测试、运行报告和其他说明。

Harness 负责约束“怎么开发和证明”，不得缩小、改写或替代最高方案的最终建设与验收目标。

## 3. 阶段命名对齐

- `方案阶段 0～5`：最高方案第 10 章定义的项目阶段，用于判断最终建设完成度；
- `仓库 M0/M1`：GitHub 中已使用的内部工程里程碑，只证明某个窄范围实现和门禁通过；
- `仓库 M0_COMPLETE` 不等于 `方案阶段 0 COMPLETE`；
- 当前项目总体位于 `方案阶段 0 IN_PROGRESS`：评测 Baseline 与范围/资源/SLO 目标已冻结，数据身份适配和上游生命周期语义仍待冻结；同时存在部分阶段 1/2 的工程探路成果。

## 4. 需求追踪矩阵

| ID | 最高方案要求 | 当前状态 | 已有证据 | 关键缺口 |
|---|---|---|---|---|
| SR-01 | 冻结个人库知识源、用户范围、语料量、并发、硬件预算和 SLO | `COMPLETE` | `machine/phase_zero_scope_resource_slo.json`：500 篇标称/1000 篇验证上界、0.2 QPS、问答并发 2、入库并发 1、单台既有主机预算及阶段 1 SLO；`docs/PHASE_0_SCOPE_RESOURCE_SLO.md` | 数值已冻结为阶段 1 验收目标，但目标规模性能、真实 LLM 延迟和 PostgreSQL `owner_id` 生命周期仍待实测，不冒充已达标 |
| SR-02 | PostgreSQL 作为 `owner_id`、主键适配和生命周期唯一事实源 | `NOT_STARTED` | 既有 Fixture ACL 和失败关闭规则 | 实际 Schema、`paper_id ↔ document_id`、`owner_id`、上游时间戳及软删除未接入；现有 V1 合同仍是 legacy 权限字段 |
| SR-03 | PDF/OCR、章节页码、三种 Chunk Baseline、版本和幂等入库 | `PARTIAL` | 三种切片策略已实现并完成同源受控对比：每种 SQLite BM25 15/15、BGE-M3 12/15，无总体胜者；本地文本层 PDF、稳定 ID 和页码已验证 | OCR、MinIO 入库资产和完整版本/删除链路未完成；未因小样本持平切换默认策略 |
| SR-04 | Elasticsearch 论文级和 Chunk 级 BM25 | `PARTIAL` | 远程 ES 9.4.3；严格 Mapping、ACL、BM25 适配器；316 Chunk Canary 14/15；175 题严格通过 85/175 | `owner_id/is_active` 目标字段迁移、中文分词选型、生产别名和性能基线未完成 |
| SR-05 | Milvus + BGE-M3 语义检索及版本一致性 | `PARTIAL` | 本地精确向量基线；远程 Milvus 2.6.18 + BGE-M3；固定源/模型身份、COSINE 和 HNSW 工程参数；316 Chunk Canary 12/15；175 题严格通过 109/175 | `owner_id/is_active` 目标字段迁移、版本/删除对账和性能基线未完成；不以远程 500 题或调参作为当前门禁 |
| SR-06 | 基础规范化和最小路由；改写、多查询和多跳按失败后置 | `PARTIAL` | API 问题输入合同与默认检索链路 | 最小路由合同尚未冻结；高级能力继续保持后置 |
| SR-07 | ES/Milvus 并行、RRF、去重、多样性、Cross-Encoder 重排 | `PARTIAL` | 本地 SQLite BM25 + BGE-M3 RRF 15/15；ES/Milvus 统一候选接口、版本化配置与远程 RRF Canary 14/15，与 ES 单路持平 | 去重/多样性、重排和扩展消融未完成；当前无净增益，暂缓增加复杂度 |
| SR-08 | 证据上下文、真实 LLM、强制引用、校验与拒答 | `PARTIAL` | Evidence/Citation、`NO_EVIDENCE`、Fake LLM Answer API | 真实模型、主张支持校验和冲突处理未实现 |
| SR-09 | 问答 API、SSE、内部 Evidence 合同和鉴权原文定位 | `PARTIAL` | 非流式 Answer API、SSE 文件合同、PDF 页码 | SSE 运行、独立 Evidence 消费和鉴权预览未实现；对外 Agent Evidence API 保持后置 |
| SR-10 | Trace、反馈、指标、告警和运营闭环 | `PARTIAL` | Trace 合同与评测报告结构 | 持久化、反馈 API、看板、告警和难例回流未实现 |
| SR-11 | 固定 175 题 MVP 初始集、约 500 条稳定迭代集、800～1500 条正式验收集 | `PARTIAL` | 175 题已按 `105/35/35` 拆分完成人工校验，166 条原样通过、9 条修订、4 条专家签署；ES 85/175、Milvus 109/175；500 题四路工程结果保留 | 无证据校准和安全策略层缺口需分流；800～1500 题正式独立盲测尚未进入 |
| SR-12 | 性能、容量、故障、安全、灰度和回滚 | `NOT_STARTED` | 本地单元/合同/权限边界测试 | 远程资源、目标规模压测、故障注入、专项安全与发布未验收 |

`COMPLETE`、`PARTIAL`、`NOT_STARTED` 均按最高方案的完整口径判断，不用仓库内部里程碑结果替代。

## 5. 方案阶段完成度

| 方案阶段 | 当前判断 | 说明 |
|---|---|---|
| 阶段 0：范围与 Baseline | `IN_PROGRESS` | 175 题人工校验、ES/Milvus 同集单路 Baseline、三种 Chunk 受控 Baseline 及单用户范围/资源/SLO 目标均已冻结；`paper_id ↔ document_id`、`owner_id` 和上游生命周期目标语义仍待冻结 |
| 阶段 1：数据与索引最小闭环 | `PARTIAL` | 本地链路及远程 ES/Milvus/BGE-M3 应用 Canary 可用，PostgreSQL 仅完成主机基线；正式 Schema、Outbox 和完整生命周期未完成 |
| 阶段 2：基础 RAG MVP | `PARTIAL` | 非流式 API、Evidence、拒答和远程 RRF Canary 可运行，但仍无真实生成模型、完整去重/多样性和生产验收 |
| 阶段 3：针对失败类型增强 | `NOT_STARTED` | 待基于人工校验 Baseline 的真实失败决定是否引入改写、拆解、去重、多样性或重排 |
| 阶段 4：Claim–Evidence 可靠性 | `NOT_STARTED` | 尚未建立结构化 Claim、Claim–Evidence 映射及确定性支持检查 |
| 阶段 5：复杂科研问答与复用 | `NOT_STARTED` | 暂未完成比较、多跳、时效问答与 Agent Evidence API |

## 6. 当前工作门禁

方案阶段 0 的下一门禁是：

1. **数据语义冻结：** 明确 PostgreSQL `owner_id`、`paper_id ↔ document_id`、文档版本、上游时间戳和软删除字段及状态机，但本阶段不接入运行时；
2. **阶段 1 交接：** 数据合同冻结后，阶段 1 再实现可重放 Outbox/幂等入库、ES/Milvus 状态对账和撤权失效；
3. **性能后置：** 数据与索引闭环完成后，按 `machine/phase_zero_scope_resource_slo.json` 的 500/1000 篇与单用户流量模型执行容量和延迟验收；
4. **复杂度门禁：** 当前不跑 175 题 RRF，不重跑远程 500 题，不增加重排、真实 LLM、HyDE、multi-query、multi-hop 或在线 NLI。
