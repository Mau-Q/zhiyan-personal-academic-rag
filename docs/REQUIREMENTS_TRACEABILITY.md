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
- `方案阶段 0 COMPLETE`：评测 Baseline、范围/资源/SLO 目标、数据身份适配和上游生命周期语义均已冻结；当前项目总体位于 `方案阶段 1 IN_PROGRESS`，同时存在部分阶段 2 的工程探路成果。

## 4. 需求追踪矩阵

| ID | 最高方案要求 | 当前状态 | 已有证据 | 关键缺口 |
|---|---|---|---|---|
| SR-01 | 冻结个人库知识源、用户范围、语料量、并发、硬件预算和 SLO | `COMPLETE` | `machine/phase_zero_scope_resource_slo.json`：500 篇标称/1000 篇验证上界、0.2 QPS、问答并发 2、入库并发 1、单台既有主机预算及阶段 1 SLO；`docs/PHASE_0_SCOPE_RESOURCE_SLO.md` | 数值已冻结为阶段 1 验收目标，但目标规模性能、真实 LLM 延迟和 PostgreSQL `owner_id` 生命周期仍待实测，不冒充已达标 |
| SR-02 | PostgreSQL 作为 `owner_id`、主键适配和生命周期唯一事实源 | `PARTIAL` | `backend/storage/` 已实现 PostgreSQL Schema、owner-scoped 映射、幂等版本/任务、生命周期 CAS 和持久化清理租约；本地 PDF 准备、双索引结果原子提交、ES/Milvus 版本写入及先 `INACTIVE` 后物理清理已接入 | 远程 PostgreSQL 尚未应用迁移或实跑；运行存储和在线权限切换尚未完成 |
| SR-03 | PDF/OCR、章节页码、三种 Chunk Baseline、版本和幂等入库 | `PARTIAL` | 三种切片策略已完成同源受控对比；本地持久化准备、双索引协调、ES/Milvus 版本写入及持久化清理已覆盖 PDF SHA、owner 映射、原子版本/任务绑定、页码、Chunk 进度、重放和单侧失败恢复 | 远程 PostgreSQL/ES/Milvus 实跑、PDF/Chunk 运行存储、OCR、MinIO 和物理删除故障验证未完成 |
| SR-04 | Elasticsearch 论文级和 Chunk 级 BM25 | `PARTIAL` | 远程 ES 9.4.3；严格 Mapping、ACL、BM25 适配器；316 Chunk Canary 14/15；175 题严格通过 85/175；本地隐藏版本索引写入器支持身份固定、部分写恢复、激活/失活和删除 | 新写入器远程复测、在线 Alias/READY 路由、中文分词选型、生产别名和性能基线未完成 |
| SR-05 | Milvus + BGE-M3 语义检索及版本一致性 | `PARTIAL` | 本地精确向量基线；远程 Milvus 2.6.18 + BGE-M3；固定源/模型身份、COSINE 和 HNSW 工程参数；316 Chunk Canary 12/15；175 题严格通过 109/175；本地版本写入器和持久化 Worker 支持模型/向量指纹固定、部分写恢复、激活/失活、重试和删除 | 新写入器与物理清理远程复测、在线 READY Collection 路由和性能基线未完成；不以远程 500 题或调参作为当前门禁 |
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
| 阶段 0：范围与 Baseline | `COMPLETE` | 175 题人工校验、ES/Milvus 同集单路 Baseline、三种 Chunk 受控 Baseline、单用户范围/资源/SLO 及数据身份/生命周期目标合同均已冻结；冻结目标不等于运行时达标 |
| 阶段 1：数据与索引最小闭环 | `IN_PROGRESS` | 本地 PostgreSQL Schema、幂等 PDF 准备、双索引状态协调、ES/Milvus 版本写入及持久化物理清理已实现；远程迁移/实跑和在线事实源权限门禁未完成 |
| 阶段 2：基础 RAG MVP | `PARTIAL` | 非流式 API、Evidence、拒答和远程 RRF Canary 可运行，但仍无真实生成模型、完整去重/多样性和生产验收 |
| 阶段 3：针对失败类型增强 | `NOT_STARTED` | 待基于人工校验 Baseline 的真实失败决定是否引入改写、拆解、去重、多样性或重排 |
| 阶段 4：Claim–Evidence 可靠性 | `NOT_STARTED` | 尚未建立结构化 Claim、Claim–Evidence 映射及确定性支持检查 |
| 阶段 5：复杂科研问答与复用 | `NOT_STARTED` | 暂未完成比较、多跳、时效问答与 Agent Evidence API |

## 6. 当前工作门禁

方案阶段 1 的下一门禁是：

1. **PostgreSQL 最小事实源：** 本地 Schema、适配器和原子任务状态已完成；由用户在隔离远程 PostgreSQL 应用迁移并返回脱敏证据；
2. **索引闭环：** 本地可重放准备、状态协调、ES/Milvus 版本写入和持久化物理清理已完成；下一步合并实现在线 READY、Alias/Collection 路由和 Answer API 可见性门禁；
3. **兼容边界：** 现有 `ChunkRecordV1.version_id` 由适配层映射到 `document_version_id`，不破坏 V1 Answer API；
4. **性能后置：** 闭环完成后再按 500/1000 篇冻结规模执行容量和延迟验收；当前仍不增加 RRF 调参、重排或真实 LLM。
