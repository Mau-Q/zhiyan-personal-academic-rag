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
- `方案阶段 0/1 COMPLETE`：评测 Baseline 与范围已冻结，数据与索引最小闭环的本地合同和远程 v2 运行证据均完成；当前项目总体位于 `方案阶段 2 IN_PROGRESS`。

## 4. 需求追踪矩阵

| ID | 最高方案要求 | 当前状态 | 已有证据 | 关键缺口 |
|---|---|---|---|---|
| SR-01 | 冻结个人库知识源、用户范围、语料量、并发、硬件预算和 SLO | `COMPLETE` | `machine/phase_zero_scope_resource_slo.json`：500 篇标称/1000 篇验证上界、0.2 QPS、问答并发 2、入库并发 1、单台既有主机预算及阶段 1 SLO；`docs/PHASE_0_SCOPE_RESOURCE_SLO.md` | 数值已冻结为阶段 1 验收目标，但目标规模性能、真实 LLM 延迟和 PostgreSQL `owner_id` 生命周期仍待实测，不冒充已达标 |
| SR-02 | PostgreSQL 作为 `owner_id`、主键适配和生命周期唯一事实源 | `COMPLETE` | `backend/storage/` 已实现 owner-scoped 映射、幂等版本/任务、生命周期 CAS、单活动版本、不可变 Chunk 快照和三路清理租约；远程 `0001`～`0005` 与 v2 READY/删除闭环通过 | 目标规模性能与运维告警仍由 SR-12 跟踪，不否定本项事实源合同完成 |
| SR-03 | PDF/OCR、章节页码、三种 Chunk Baseline、版本和幂等入库 | `PARTIAL` | 三种切片策略已完成同源对比；远程 `filesystem_v1` PDF 对象重开、PostgreSQL Chunk 快照、重放恢复和 INACTIVE 后清理闭环已通过 | OCR 与正式 MinIO 应用适配未完成，不把 MVP 文件对象后端冒充最终架构 |
| SR-04 | Elasticsearch 论文级和 Chunk 级 BM25 | `PARTIAL` | 远程 ES 9.4.3；316 Chunk Canary 14/15；175 题 85/175；版本写入器、READY 持久化 Answer API 和删除清理均远程通过 | 中文分词选型和目标规模性能基线未完成 |
| SR-05 | Milvus + BGE-M3 语义检索及版本一致性 | `PARTIAL` | 远程 Milvus 2.6.18 + BGE-M3；316 Chunk Canary 12/15；175 题 109/175；版本 Collection、READY 持久化 Answer API 和删除清理均远程通过 | 目标规模性能基线未完成；不以远程 500 题或调参作为当前门禁 |
| SR-06 | 基础规范化和最小路由；改写、多查询和多跳按失败后置 | `PARTIAL` | API 问题输入合同与默认检索链路 | 最小路由合同尚未冻结；高级能力继续保持后置 |
| SR-07 | ES/Milvus 并行、RRF、去重、多样性、Cross-Encoder 重排 | `PARTIAL` | 本地 SQLite BM25 + BGE-M3 RRF 15/15；远程 RRF Canary 14/15，与 ES 单路持平；固定 BGE Reranker 在冻结 `test=100` 上将 `nDCG@10` 从 `0.647269` 提升到 `0.747810`、`Precision@5 +0.02`，本地质量结论为保留 | Windows RTX 4090 P95 与最终在线启用/回退尚未收口；去重/多样性和扩展消融仍未完成 |
| SR-08 | 证据上下文、真实 LLM、强制引用、校验与拒答 | `PARTIAL` | Evidence/Citation、`NO_EVIDENCE`；llama3.2 与 Qwen 均已通过远程 READY + ES/Milvus RRF 真实生成闭环，Qwen 报告 SHA-256 `0CB1B569D8A782FC526266E1A7193EF6299B66D5DBC72DCC989FDB951B8A1160`；固定公开 Evidence 模型选型 v4 以 Qwen `4/4` 对 llama3.2 `3/4` 晋级；3 文档 9 题 v2 已远程 `3/3` 文档、`9/9` 问题通过，最终第 3 篇报告 SHA-256 `3C106423AB3575B11B3B0142A66F19A2C949B8BAED3457F1BCA101A9931302FA` | Claim 语义支持校验和冲突处理仍未完成；答案字节一致只作观测，不替代引用集合与确定性门禁 |
| SR-09 | 问答 API、SSE、内部 Evidence 合同和鉴权原文定位 | `PARTIAL` | 非流式 Answer API、SSE 文件合同、PDF 页码 | SSE 运行、独立 Evidence 消费和鉴权预览未实现；对外 Agent Evidence API 保持后置 |
| SR-10 | Trace、反馈、指标、告警和运营闭环 | `PARTIAL` | Trace 合同与评测报告结构 | 持久化、反馈 API、看板、告警和难例回流未实现 |
| SR-11 | 固定 175 题 MVP 初始集、约 500 条稳定迭代集、800～1500 条正式验收集 | `PARTIAL` | 175 题已按 `105/35/35` 拆分完成人工校验，166 条原样通过、9 条修订、4 条专家签署；ES 85/175、Milvus 109/175；500 题四路工程结果保留 | 无证据校准和安全策略层缺口需分流；800～1500 题正式独立盲测尚未进入 |
| SR-12 | 性能、容量、故障、安全、灰度和回滚 | `PARTIAL` | 本地单元/合同/权限边界测试；远程已验证 Embedding 单侧不可达时不进入 READY，同 Run ID 恢复后双索引对账与物理清理成功 | 目标规模压测、更完整的故障矩阵、专项安全、灰度和发布回滚未验收 |

`COMPLETE`、`PARTIAL`、`NOT_STARTED` 均按最高方案的完整口径判断，不用仓库内部里程碑结果替代。

## 5. 方案阶段完成度

| 方案阶段 | 当前判断 | 说明 |
|---|---|---|
| 阶段 0：范围与 Baseline | `COMPLETE` | 175 题人工校验、ES/Milvus 同集单路 Baseline、三种 Chunk 受控 Baseline、单用户范围/资源/SLO 及数据身份/生命周期目标合同均已冻结；冻结目标不等于运行时达标 |
| 阶段 1：数据与索引最小闭环 | `COMPLETE` | 远程 v2 已通过 PDF/Chunk 持久化、owner/版本 READY 对账、ES/Milvus 在线 Evidence、同 Run ID 恢复、删除后 403 和三路清理；报告 SHA-256 `6B2AB3BAAD55AE8FA506C0D1FD7A310D9EF3A3833A93E33DD1A2D8A0938A9D8C` |
| 阶段 2：基础 RAG MVP | `PARTIAL` | 非流式 API、Evidence、拒答、远程 RRF Canary、llama3.2/Qwen READY 真实生成闭环、模型选型和 3 文档 9 题 v2 均通过；固定 BGE Reranker 本地 `test=100` 质量门通过 | 固定 Reranker 仍需目标 RTX 4090 P95 与最终在线启用/回退收口；生产验收仍未完成 |
| 阶段 3：针对失败类型增强 | `NOT_STARTED` | 待基于人工校验 Baseline 的真实失败决定是否引入改写、拆解、去重、多样性或重排 |
| 阶段 4：Claim–Evidence 可靠性 | `NOT_STARTED` | 尚未建立结构化 Claim、Claim–Evidence 映射及确定性支持检查 |
| 阶段 5：复杂科研问答与复用 | `NOT_STARTED` | 暂未完成比较、多跳、时效问答与 Agent Evidence API |

## 6. 当前工作门禁

方案阶段 2 的下一门禁是：

1. **已完成本地 Gate：** 第 10.3 节差距已冻结；固定本机模型、Prompt 和解码的真实生成 Canary 已通过，且不修改检索；
2. **已完成远程 Gate：** 用户在提交 `91aca5a` 复用 PostgreSQL READY + ES/Milvus RRF Evidence 完成同一真实生成配置的稳定回放、引用门禁、删除后 403 和三路清理；
3. **已完成模型选型 Gate：** 固定 Evidence/Prompt/解码比较 `qwen3:14b` 与 `llama3.2:latest`，远程 v2 以 `4/4` 对 `2/4` 决定 `PROMOTE_QWEN3_14B`；
4. **已完成远程 Qwen Gate：** 冻结摘要的 Qwen 已完成真实生成、引用、ACL、版本、删除后 403 和三路清理闭环；
5. **已完成学术问答 Gate：** v2 三篇各 `3/3`、合计 `9/9` 远程通过；最终第 3 篇报告 SHA-256 `3C106423AB3575B11B3B0142A66F19A2C949B8BAED3457F1BCA101A9931302FA`，原 HTTP 失败报告继续保留；
6. **已完成本地 Reranker 质量 Gate：** 冻结 `test=100` 上 `nDCG@10` 相对提升 `15.5331%`、`Precision@5 +0.02`，四个关键类型门禁通过；M4 P95 只作本地观测；
7. **当前独立 Gate：** 在用户控制的 Windows RTX 4090 上复用相同 revision、snapshot、输入模板、Batch Size 和冻结输入，记录目标 P95 并完成最终启用/回退；MinIO/OCR/通用性能继续保持独立变量。
