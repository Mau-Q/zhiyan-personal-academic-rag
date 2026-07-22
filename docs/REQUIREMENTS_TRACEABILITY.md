# 最高方案需求追踪

## 1. 最高依据身份

项目的最高层需求、目标架构和验收依据为：

- 文件名：`个人学术空间RAG问答系统建设与测试方案_副本.md`；
- 标题：《个人学术空间 RAG 问答系统建设与测试方案》；
- 当前已核对行数：`661`；
- SHA-256：`8f5c0c4c5f4eb403100aaebb528c969a58a740964b32f5493f00d848b29c0fc5`；
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
- 当前项目总体位于 `方案阶段 0 IN_PROGRESS`，同时存在部分阶段 1/2 的工程探路成果。

## 4. 需求追踪矩阵

| ID | 最高方案要求 | 当前状态 | 已有证据 | 关键缺口 |
|---|---|---|---|---|
| SR-01 | 冻结首期知识源、用户、语料量、并发、SLO 和授权 | `PARTIAL` | `docs/STAGE_0_SCOPE.md`、本地 3 论文 Canary | 正式语料量、峰值并发、硬件预算和 SLO 未冻结 |
| SR-02 | PostgreSQL 作为元数据、ACL 和生命周期唯一事实源 | `NOT_STARTED` | 合同与 Fixture 权限规则 | 真实 Schema、ACL 计算、时间戳和软删除未接入 |
| SR-03 | PDF/OCR、章节页码、父子 Chunk、版本和幂等入库 | `PARTIAL` | 本地文本层 PDF、`ChunkRecordV1`、稳定 ID 和页码 | OCR、MinIO、Outbox、死信、完整版本/删除链路未实现 |
| SR-04 | Elasticsearch 论文级和 Chunk 级 BM25 | `PARTIAL` | 远程 ES 9.4.3；严格 Mapping、ACL、BM25 适配器；316 Chunk 固定 Canary 14/15，拒答与越权 6/6 | 中文分词选型、生产别名和性能基线未实现 |
| SR-05 | Milvus + BGE-M3 语义检索及版本一致性 | `PARTIAL` | 本地精确向量基线；远程 Milvus 2.6.18 + BGE-M3；应用适配器固定源/模型身份、ACL、COSINE 与 HNSW 工程参数；316 Chunk 固定 Canary 12/15，拒答与越权 6/6 | 远程 500 题、参数调优和性能基线未完成 |
| SR-06 | 规范化、指代消解、意图路由、查询改写和拆解 | `NOT_STARTED` | API 问题输入合同 | 结构化路由、回退、实体保持和多轮未实现 |
| SR-07 | ES/Milvus 并行、RRF、去重、多样性、Cross-Encoder 重排 | `PARTIAL` | 本地 SQLite BM25 + BGE-M3 RRF 15/15；ES/Milvus 统一候选接口、版本化配置与远程 RRF Canary 14/15，与 ES 单路持平 | 去重/多样性、重排和扩展消融未完成；当前无净增益，暂缓增加复杂度 |
| SR-08 | 证据上下文、真实 LLM、强制引用、校验与拒答 | `PARTIAL` | Evidence/Citation、`NO_EVIDENCE`、Fake LLM Answer API | 真实模型、主张支持校验和冲突处理未实现 |
| SR-09 | 问答 API、SSE、Evidence API、Agent Evidence API 和原文定位 | `PARTIAL` | 非流式 Answer API、SSE 文件合同、PDF 页码 | SSE 运行、Evidence API、Agent API 和鉴权预览未实现 |
| SR-10 | Trace、反馈、指标、告警和运营闭环 | `PARTIAL` | Trace 合同与评测报告结构 | 持久化、反馈 API、看板、告警和难例回流未实现 |
| SR-11 | 150～250 条人工校验 MVP 初始集、约 500 条稳定迭代集、800～1500 条正式验收集 | `PARTIAL` | 15 题 Canary；三论文 316 Chunk 源快照；500 条 AI 工程候选及四路检索结果；175 条已按 `105/35/35` 拆分完成人工校验，166 条原样通过、9 条修订、4 条专家签署 | 同集 ES/Milvus 单路 Baseline 和正式独立盲测未完成 |
| SR-12 | 性能、容量、故障、安全、灰度和回滚 | `NOT_STARTED` | 本地单元/合同/权限边界测试 | 远程资源、目标规模压测、故障注入、专项安全与发布未验收 |

`COMPLETE`、`PARTIAL`、`NOT_STARTED` 均按最高方案的完整口径判断，不用仓库内部里程碑结果替代。

## 5. 方案阶段完成度

| 方案阶段 | 当前判断 | 说明 |
|---|---|---|
| 阶段 0：范围与 Baseline | `IN_PROGRESS` | 175 题已完成人工校验，并保留 500 题工程候选池和远程工程基线；同集 ES/Milvus Baseline、目标语料量、峰值并发和 SLO 仍未冻结 |
| 阶段 1：数据与索引最小闭环 | `PARTIAL` | 本地链路及远程 ES/Milvus/BGE-M3 应用 Canary 可用，PostgreSQL 仅完成主机基线；正式 Schema、Outbox 和完整生命周期未完成 |
| 阶段 2：基础 RAG MVP | `PARTIAL` | 非流式 API、Evidence、拒答和远程 RRF Canary 可运行，但仍无真实生成模型、完整去重/多样性和生产验收 |
| 阶段 3：针对失败类型增强 | `NOT_STARTED` | 待基于人工校验 Baseline 的真实失败决定是否引入改写、拆解、去重、多样性或重排 |
| 阶段 4：Claim–Evidence 可靠性 | `NOT_STARTED` | 尚未建立结构化 Claim、Claim–Evidence 映射及确定性支持检查 |
| 阶段 5：复杂科研问答与复用 | `NOT_STARTED` | 暂未完成比较、多跳、时效问答与 Agent Evidence API |

## 6. 当前工作门禁

方案阶段 0 的下一门禁是：

1. **单路 Baseline：** 175 题人工校验已完成，下一步对同一冻结集运行 ES only 和 Milvus only，保留分类指标和真实失败；
2. **范围收口：** 基于单路结果冻结目标语料量、峰值并发、硬件预算和 SLO；
3. **复杂度门禁：** 现有 500 题四路和 15 题远程 Canary 作为工程证据保留；本轮不实现重排、真实 LLM、HyDE、multi-query、multi-hop 或在线 NLI，也不调 RRF。

同集 ES/Milvus 单路 Baseline 和范围/SLO 未收口前，不得将阶段 0 标记为完成。
