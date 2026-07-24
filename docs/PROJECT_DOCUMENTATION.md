# 智研个人学术空间 RAG 项目文档

> 文档用途：比赛提交、技术评审与仓库导览
> 当前口径：以 `main` 分支中的版本化合同、机器状态和已核验报告为准
> 能力范围：个人论文库的证据约束型 RAG 核心服务

## 1. 项目概述

智研个人学术空间 RAG 面向个人已拥有或已获授权的论文资料，建设一条可追溯、
可拒答、可审计、可删除的检索增强生成核心链路。项目关注的不是“让模型尽可能多
地回答”，而是让系统能够回答四个更基础的问题：

1. 当前回答使用了哪一个用户、哪一篇论文、哪一个文档版本和哪些 Chunk？
2. 被引用的证据是否仍处于授权且可见的 `READY` 状态？
3. 模型生成的 Claim 是否能回到具体 Citation 和 EvidenceSet？
4. 当证据不足、权限不符或版本已失效时，系统能否可靠拒答并完成物理清理？

因此，本项目把 PostgreSQL 事实源、双索引生命周期、授权过滤、引用校验、
`NO_EVIDENCE` 和 Claim–Evidence 审计放在与召回质量同等重要的位置。当前已验证
的主链为：

```text
PDF / Chunk
→ PostgreSQL READY / owner ACL
→ Elasticsearch + Milvus
→ rank-only RRF
→ 真实模型生成
→ Citation
→ Multi-Evidence EvidenceSet 审计
→ NO_EVIDENCE
→ 删除失效与 ES / Milvus / runtime 三路清理
```

这是一条经过本地回归和脱敏远程 Gate 验证的 RAG 核心链，不等于完整产品、
生产级服务或最高方案全部完成。

> **图片占位 01：系统总体架构图**
> 建议内容：展示 PostgreSQL、Elasticsearch、Milvus、RAG 主链及权限边界。
> 建议形式：横向架构图。
> 建议尺寸：1600 × 900。
> 后续文件名：`01-system-architecture.png`

## 2. 项目背景与核心问题

### 2.1 个人论文库为什么需要独立的 RAG 边界

通用搜索和开放语料问答适合发现资料，但不能天然代表用户自己的论文库，也不能
保证结果来自当前授权版本。个人学术场景还存在几个容易被普通 Demo 忽略的问题：

- 同一论文可能被重复导入、重新解析或重新切片，旧版本不能继续参与召回；
- 关键词召回与向量召回各有盲区，单路结果不能直接代表最终证据；
- 模型可能生成看似合理、但没有对应 Chunk 支持的陈述；
- PDF 已删除不等于索引、快照和在线路由已经同步失效；
- 无证据问题、越权问题和内容安全问题是不同的失败类型，不能混成一句拒答；
- 评测集如果未经拆分、泄漏控制和人工裁决，较高指标也可能没有可信解释。

本项目将这些问题收敛为“证据、身份、权限和生命周期一致性”问题，再在其上叠加
召回、生成和审计能力。

### 2.2 项目目标

当前目标是提供一个边界清楚的 RAG 核心服务：

- 以不可变文档版本和稳定 Chunk 身份组织论文证据；
- 以 PostgreSQL 作为授权、状态和路由的唯一事实源；
- 通过 Elasticsearch 与 Milvus 提供词法和语义互补召回；
- 通过 RRF 进行默认的无分数标定融合；
- 让真实模型只能消费已授权、已重验的 Evidence；
- 输出可验证 Citation，并在无证据时失败关闭；
- 对单证据和多证据 Claim 执行确定性审计；
- 在文档删除后先失效在线可见性，再可靠完成三路物理清理。

### 2.3 当前职责边界

当前仓库负责 RAG 核心、合同、评测工具、版本化远程执行入口和脱敏证据。它当前
不负责：

- 上层知识库产品接入；
- 前端页面和比赛演示界面；
- 对外 Agent API；
- 阶段 5 的复杂比较、多跳、时效问答和跨应用复用；
- 完整生产运维、灰度发布、告警看板和容量验收。

这些能力可以在核心边界稳定后继续建设，但不得在当前材料中写成已经完成。

## 3. 最高方案与当前实现

项目的最高层建设方案定义了目标架构、测试体系和阶段 0～5。仓库不复制该方案
全文，而是记录其文件身份、SHA-256、需求映射和当前证据；具体身份见
[最高方案需求追踪](REQUIREMENTS_TRACEABILITY.md)。

最高方案描述的是完整建设目标，当前仓库描述的是已经实现并通过 Gate 的子集。
二者关系如下：

| 领域 | 最高方案目标 | 当前实现与边界 |
|---|---|---|
| 数据接入 | PDF、对象存储、OCR、结构化解析、版本化 Chunk | 带文本层 PDF、`filesystem_v1` PDF 对象、不可变 Chunk 快照和三种切片 Baseline 已验证；正式 MinIO 应用适配与 OCR 未完成 |
| 事实源 | PostgreSQL 管理身份、权限、状态和任务 | owner 范围、单活动版本、幂等任务、CAS 生命周期和清理租约已实现并远程验证 |
| 检索 | ES 词法、Milvus 向量、Hybrid、Reranker | ES/Milvus 真实适配、并行召回和 RRF 已验证；固定 Reranker 可选但不默认启用 |
| 生成 | 证据约束生成、引用、拒答 | Qwen 真实生成、Citation 稳定映射和 `NO_EVIDENCE` 已验证 |
| 可靠性 | Claim–Evidence、冲突与多证据审计 | 确定性 EvidenceSet 审计核心完成，保持 `AUDIT_ONLY`；通用语义 Judge 和在线硬裁决未完成 |
| 产品化 | SSE、反馈、看板、告警、前端和复用 API | 非流式 Answer API 与合同存在；其余多数能力未完成或不在当前交付范围 |
| 正式验收 | 目标规模、性能、安全、故障、800～1500 题盲测 | 当前有 175 题人工集、500 题工程集和多类 Canary；完整正式验收尚未进入 |

这种区分保证了设计目标不会被缩小，也避免仓库中的局部里程碑被误写成整个系统
已经交付。

## 4. 系统总体架构

### 4.1 核心组件

| 组件 | 当前职责 | 明确不承担的职责 |
|---|---|---|
| PostgreSQL | owner、文档/版本/Chunk 身份、生命周期、双索引路由、任务与清理事实 | 不承担全文相关性排序 |
| Elasticsearch | 对授权活动版本执行 BM25 词法召回 | 不决定最终授权和版本真值 |
| Milvus | 对授权活动版本执行 BGE-M3 稠密向量召回 | 不决定最终授权和版本真值 |
| RRF | 按名次融合 ES/Milvus 候选，减少跨后端分数不可比问题 | 不生成新证据、不改变 ACL |
| 可选 Reranker | 对同一批已授权 RRF 候选重新排序 | 不扩张候选，不覆盖身份校验，不是默认路径 |
| Answer / Generation | 基于 Evidence 生成结构化回答、Claim 和引用 | 证据不足时不得绕过拒答 |
| EvidenceSet 审计 | 校验引用身份、数字、单位、比较、限定、冲突和部分支持 | 不冒充人工真值或通用语义蕴含 |
| 清理 Worker | 执行 ES、Milvus、runtime snapshot 三路持久化清理任务 | 不通过手工旁路删除破坏审计链 |

### 4.2 单一事实源与可重建索引

PostgreSQL 是系统的唯一事实源。ES 和 Milvus 保存检索结构，但它们不能自行宣布
某个版本可见。在线请求必须先从 PostgreSQL 获得 owner 范围内的 `READY` 路由，
召回后还要重新核对文档、版本和 Chunk 身份。

这一设计把“索引中存在”与“用户当前可访问”分离开来：

- PostgreSQL 决定事实；
- ES/Milvus 提供可重建的检索能力；
- 生成层只接收通过事实源与身份重验的 Evidence；
- 删除先改变事实源可见性，再异步完成物理清理。

## 5. PDF 入库、Chunk 与版本生命周期

### 5.1 稳定身份

系统使用分层身份避免文件名、索引内部 ID 或运行目录成为事实依据：

- `paper_id`：论文层面的稳定标识；
- `document_id`：用户空间中的文档标识；
- `document_version_id`：一次不可变解析与索引版本；
- `chunk_id`：版本内的稳定证据单元；
- `source_fingerprint`、解析版本和 Embedding 身份：用于重放与一致性校验。

同一文档的新版本不会原地改写旧 Chunk。新版本必须完成自己的 PDF 对象、Chunk
快照、ES 索引与 Milvus Collection，再通过一致性核验进入 `READY`。

### 5.2 入库主流程

1. 接收 PDF 并计算来源指纹，创建 owner 范围内的文档与版本身份；
2. 保存可重开的 PDF 对象，提取文本和页码；
3. 按固定切片策略生成不可变 Chunk 快照；
4. 将 Chunk 与版本元数据写入 PostgreSQL；
5. 分别构建版本化 Elasticsearch 索引和 Milvus Collection；
6. 核对两路索引的数量、身份、模型和来源指纹；
7. 只有全部条件满足，PostgreSQL 才将该版本切换为 `READY`；
8. 对相同 Run ID 的恢复执行幂等重放，不创建重复事实。

任何单侧索引失败、身份漂移或对账失败都不能进入 `READY`。远程 Stage 1 Gate
已经验证：Embedding 单侧不可用时版本失败关闭；恢复后可以在同一 Run ID
完成双索引对账、在线回答和后续清理。

### 5.3 三种 Chunk Baseline

项目对同一三论文、316 Chunk 来源做过受控切片比较：

| 策略 | Chunk 数 | SQLite BM25 Canary | BGE-M3 向量 Canary | 结论 |
|---|---:|---:|---:|---|
| 固定窗口 | 279 | 15/15 | 12/15 | 可用，但没有总体优势 |
| 段落/句子 | 316 | 15/15 | 12/15 | 保留为当前证据来源之一 |
| 章节父子 | 316 | 15/15 | 12/15 | 没有形成明确总体胜出 |

这组结果说明“更复杂切片”在当前小样本上没有自动带来提升，因此项目保留真实
结果，不通过改写结论制造赢家。

> **图片占位 02：PDF 入库与双索引 READY 生命周期图**
> 建议内容：展示 PDF 指纹、不可变 Chunk、PostgreSQL、ES/Milvus 写入、对账、READY 与失败关闭。
> 建议形式：泳道流程图。
> 建议尺寸：1600 × 1000。
> 后续文件名：`02-ingestion-ready-lifecycle.png`

## 6. READY、ACL、版本失效与清理

### 6.1 在线可见性

在线检索遵循 fail-closed 原则：

1. 从可信请求上下文取得 owner；
2. PostgreSQL 只解析该 owner 下的活动 `READY` 文档版本；
3. ES/Milvus 请求携带对应版本物理路由和过滤条件；
4. 合并前后均检查候选的 document/version/chunk 身份；
5. 未授权、非活动、未知或身份漂移的候选不得进入 Evidence。

当前权限主叙事是 owner 范围与活动版本，而不是旧式全局
`tenant_id/visibility` 过滤器。后者只能作为历史实现语境，不能替代当前事实源
合同。

### 6.2 版本失效

文档删除或版本替换时，系统先在 PostgreSQL 中把版本切换为 `INACTIVE`。从这一
时刻起：

- READY 路由不再返回该版本；
- Answer API 对已失效文档返回 403；
- 即使 ES/Milvus 的物理数据尚在清理队列中，也不能再次召回；
- 旧版本 Chunk 不能与新版本 Evidence 混合。

### 6.3 三路清理

每个失效版本对应三类持久化清理任务：

1. 删除 Elasticsearch 版本索引；
2. 删除 Milvus 版本 Collection；
3. 删除 runtime PDF/Chunk snapshot。

任务由带租约的 Worker 领取，记录尝试和终态；异常时通过只读审计定位残留，再
使用版本化恢复 Gate 精确处理既有任务。阶段 3 的失败运行曾真实暴露待清理任务，
后续恢复证明 9/9 任务可以转为 `SUCCEEDED`，Chunk、PDF 和全局非终态计数回到
零。该过程同时说明：失败证据、恢复证据和质量证据必须分开解释。

> **图片占位 03：在线 RAG 主链流程图**
> 建议内容：展示请求、READY/ACL 解析、ES/Milvus 并行召回、RRF、生成、Citation、审计与拒答。
> 建议形式：横向时序流程图。
> 建议尺寸：1800 × 900。
> 后续文件名：`03-online-rag-pipeline.png`

> **图片占位 04：owner/ACL、版本失效与清理流程图**
> 建议内容：展示 owner 隔离、活动版本切换、删除后 403 和 ES/Milvus/runtime 三路清理。
> 建议形式：状态机与泳道组合图。
> 建议尺寸：1600 × 1000。
> 后续文件名：`04-acl-version-cleanup.png`

## 7. 检索、融合与可选重排

### 7.1 Elasticsearch 与 Milvus

Elasticsearch 使用 BM25 提供词法匹配，适合术语、题名、精确短语和局部锚点；
Milvus 使用 BGE-M3 向量提供语义召回，适合同义改写和跨表述检索。两路使用相同
的授权活动版本快照，在线执行时并行召回。

远程同源三论文 Canary 的结果为：

| 路径 | Top-3 严格通过 | 解释 |
|---|---:|---|
| Elasticsearch | 14/15 | 当前小样本最佳单路之一 |
| Milvus + BGE-M3 | 12/15 | 与本地向量结果一致 |
| ES + Milvus RRF | 14/15 | 与 ES 持平，没有净增益 |

RRF 未在这组 Canary 上超过 ES，但它保留了双路召回的统一主链和稳定融合合同。
因此默认决策是继续使用原 RRF，而不是基于一次小样本结果进行融合调参。

### 7.2 rank-only RRF

默认融合只使用候选名次，不直接比较 ES 与 Milvus 的原始分数：

```text
RRF(d) = Σ 1 / (k + rank_i(d))
```

当前冻结的在线参数为每路候选 `candidate_k=20`、`rrf_k=60`、最终
`top_k=3`。RRF 不增加检索请求，不改变 owner/ACL，不创建新 Chunk，也不替代
检索后的身份重验。

### 7.3 固定 Cross-Encoder Reranker

固定 `BAAI/bge-reranker-v2-m3` 只对 RRF 前 20 个已授权候选重排，并输出前 3：

| 指标（冻结 test=100） | RRF | RRF + Reranker | 变化 |
|---|---:|---:|---:|
| nDCG@10 | 0.647269 | 0.747810 | +0.100541， relative +15.5331% |
| Precision@5 | 0.231111 | 0.251111 | +0.020000 |

在远程 RTX 4090 上，同一冻结组件的 pair-scoring 为
`P50=169.3867 ms / P95=188.22683 ms`。但完整在线分段 Gate 的
base retrieval `P95=376.394385 ms`、Reranker `P95=132.456 ms`、
combined `P95=504.71613 ms`，未满足 300 ms 目标。

因此，质量增益与端到端性能结论必须同时保留：

- Reranker 作为受控可选组件保留；
- 默认在线路径仍为 RRF；
- Reranker 异常时只能回退同一批 RRF 候选，不能扩张候选；
- 300 ms 是独立性能债，不以“功能通过”替代性能验收。

> **图片占位 05：ES、Milvus、RRF、Reranker 对比图**
> 建议内容：对比词法召回、向量召回、名次融合和候选重排的输入、输出、优势与边界。
> 建议形式：四列对比图加指标小图表。
> 建议尺寸：1800 × 1000。
> 后续文件名：`05-retrieval-fusion-reranker.png`

## 8. 真实生成、Citation 与拒答

### 8.1 真实模型链路

项目已经在冻结 Evidence、Prompt、解码参数和模型身份下完成真实模型验证。
模型选型最终结果为 Qwen 4/4、llama3.2 3/4，决定晋级 `qwen3:14b`，并固定
`think=false`；llama3.2 保留为回退候选。此前的失败报告没有被覆盖，而是作为
门禁设计演进证据继续保留。

普通学术问答验收使用三篇论文、每篇三题，共 9 题：

- 3/3 文档通过；
- 9/9 问题完成真实生成；
- 每次回答均通过 Citation 集合校验；
- 两次回放的 Citation 集合稳定；
- 页码定位、删除后 403 和三路清理通过。

自然语言答案的逐字一致性仅作观测，不是生成模型的硬门禁；确定性的 Citation
身份和安全边界才是必须稳定的部分。

### 8.2 Citation

Citation 不是回答末尾的装饰文本，而是从请求内 Evidence 位置映射出的结构化
结果。系统检查：

- Citation 编号是否存在于当前请求的 Evidence 集合；
- owner、document、version 和 chunk 身份是否一致；
- Evidence 是否属于当前活动版本；
- 页码与定位信息是否来自对应 Chunk；
- 回放时 Citation 集合是否保持稳定。

只有通过这些检查的引用才可以随回答返回。

### 8.3 `NO_EVIDENCE`

如果授权范围内没有足够 Evidence，系统返回 `NO_EVIDENCE`，并且不调用生成
模型。该边界避免模型在空上下文中自由补全。

需要注意，`NO_EVIDENCE`、`RAG_FORBIDDEN_SCOPE` 和内容安全拒答不是同一语义：

- `NO_EVIDENCE`：授权范围内没有可支持回答的证据；
- `RAG_FORBIDDEN_SCOPE`：请求指向未授权或已失效范围；
- 内容安全策略：当前尚未形成完整独立策略层，不能用前两者冒充。

## 9. Multi-Evidence EvidenceSet 审计

### 9.1 为什么需要 EvidenceSet

单个 Claim 可能同时依赖两个或多个 Evidence，例如跨文档比较、数值差异或
冲突披露。逐条 Citation 存在，并不自动说明整个 Claim 获得支持。EvidenceSet
将一个 Claim 绑定的一个或多个 Evidence 作为整体进行审计。

### 9.2 确定性审计合同

当前 `verify_claim_evidence_sets` 接收：

- 已授权的请求内 Evidence；
- 可信 `expected_owner_id`；
- 每篇文档的唯一活动版本映射；
- 活动 `chunk_id → (document_id, version_id)` 身份快照。

它失败关闭地校验：

- owner、活动状态、文档/版本/Chunk 身份；
- Chunk 唯一性和跨版本混入；
- 数字、单位、比较对象和限定条件；
- 因果、全称、首次、唯一、最优等高风险关系；
- 同单位不同数值形成的显式冲突；
- 多子句中的部分支持。

固定输出为：

- `SUPPORTED_BY_EVIDENCE_SET`；
- `PARTIALLY_SUPPORTED`；
- `CONFLICTING_EVIDENCE`；
- `INSUFFICIENT_EVIDENCE`。

### 9.3 有界邻块

只有原绑定证据不足，而且请求内存在同 owner、同文档、同活动版本、双向邻接的
候选 Chunk 时，审计器才允许最多加入一个邻块。加入必须能够把结论提升为支持
或显式冲突，并记录 `RETRIEVAL_SCORE_UNCHANGED`。

该机制不发起新检索，不读取或修改相关性分数，也不把旧版本邻块混入证据。

### 9.4 `AUDIT_ONLY`

EvidenceSet 当前保持 `AUDIT_ONLY`：

- 它记录审计结论，但不自动删除或改写模型 Claim；
- 它是确定性身份与锚点检查，不是人工语义真值；
- 它不代表通用 NLI、LLM Judge 或在线硬裁决完成；
- 当前被拒绝的多语言 NLI 候选不会被暗中启用。

> **图片占位 06：Multi-Evidence EvidenceSet 工作原理图**
> 建议内容：展示 Claim、多个 Citation/Evidence、身份校验、锚点检查、冲突和四态输出。
> 建议形式：从输入集合到审计状态的分层流程图。
> 建议尺寸：1600 × 1000。
> 后续文件名：`06-multi-evidence-set.png`

## 10. 阶段 0～4 的真实完成状态

| 阶段 | 当前状态 | 已完成的核心内容 | 未完成或后置内容 |
|---|---|---|---|
| 阶段 0：范围与 Baseline | `COMPLETE` | 个人库范围、资源/SLO 目标、身份生命周期合同、175 题人工集、单路与 Chunk Baseline | 冻结目标不等于目标规模性能已经达成 |
| 阶段 1：数据与索引最小闭环 | `COMPLETE` | PDF/Chunk 持久化、PostgreSQL READY、ES/Milvus 双索引、恢复、删除后 403、三路清理 | 正式 MinIO、OCR 和生产容量不属于本阶段已完成结论 |
| 阶段 2：基础 RAG MVP | `COMPLETE` | RRF、真实 Qwen 生成、Citation、`NO_EVIDENCE`、ACL/版本/定位硬门禁、9/9 学术问答、Reranker 决策 | 300 ms 性能目标未通过 |
| 阶段 3：针对失败类型增强 | `PARTIAL / WORKSTREAM_CLOSED_WITHOUT_PROMOTION` | 两个冻结 `dev` V1 完成可信比较与清理 | 没有变量获得稳定净增益；不读 test/Acceptance，不为形式新增第三变量 |
| 阶段 4：Claim–Evidence 可靠性 | `PARTIAL` | 确定性单/多 EvidenceSet 审计核心完成，默认 `AUDIT_ONLY` | 人工 pair 金标、Precision、负例拒绝率、人工一致率、语义 Judge 和在线硬裁决未完成 |

阶段 5 为 `NOT_STARTED`，不属于当前完成范围。最新动态状态以
[当前阶段](CURRENT_PHASE.md) 和
[机器状态](../machine/project_state.json) 为准。

> **图片占位 07：阶段 0～4 项目路线与完成状态图**
> 建议内容：展示各阶段目标、当前状态、关键 Gate 和后移边界。
> 建议形式：横向路线图，使用 COMPLETE、PARTIAL、NOT_STARTED 三类状态。
> 建议尺寸：1800 × 900。
> 后续文件名：`07-project-roadmap-status.png`

## 11. 主要评测与验证证据

### 11.1 175 题人工校验集

175 题是当前最重要的人工验证检索集：

- 拆分为 `dev/test/acceptance=105/35/35`；
- 166 条原样通过；
- 9 条完成标签修订；
- 4 条经过专家签署；
- 题型覆盖精确查找、单文档事实、语义改写、比较、证据边界和安全。

在同一 316 Chunk、`top_k=3` 和相同索引身份下，远程单路结果为：

| 指标 | Elasticsearch BM25 | Milvus + BGE-M3 |
|---|---:|---:|
| 总通过 | 85/175 | 109/175 |
| 可回答合同 | 84/138 | 109/138 |
| 无证据拒答 | 1/17 | 0/17 |
| 安全拒答 | 0/20 | 0/20 |
| 必需证据目标命中 | 114/192 | 144/192 |

两路同时通过 78 题，仅 ES 通过 7 题，仅 Milvus 通过 31 题，两路均未通过
59 题。该结果说明 Milvus 是当前更强单路基线，也说明无证据校准和独立安全策略
仍有明显缺口。由于 RRF Canary 没有超过 ES，且互补明显偏向 Milvus，项目没有
运行或调参 175 题 RRF。

### 11.2 500 题工程评测集

500 题用于工程迭代，不冒充完整人工金标：

- Qwen3.7-plus、`enable_thinking=false` 完成 500/500 候选生成，失败 0；
- 总消耗 1,177,007 Token；
- 最终得到 500 个唯一、通过合同的 `GPT_ASSISTED` 草稿；
- 泄漏分组后恢复 `dev/test/acceptance=300/100/100`，跨拆分泄漏组为 0；
- 四路本地排名均完成 500/500；
- test `nDCG@10` 依次为词项 0.457569、SQLite BM25 0.502652、
  BGE-M3 向量 0.631910、RRF 0.647269。

风险队列包含 213 题，其外部 AI 审计不能替代人工结论；当前人工决定数为 0。
25 个冲突候选也仍待人工复核。因此，该数据集只能作为工程证据，不能标记为
`LOCKED` 或正式独立盲测集。

### 11.3 三论文 Canary

三论文 Canary 使用 316 Chunk 和固定 15 题，提供低成本、同源的回归信号：

- 本地 SQLite BM25：15/15；
- 本地 BGE-M3 向量：12/15；
- 本地 RRF：15/15；
- 远程 Elasticsearch：14/15；
- 远程 Milvus：12/15；
- 远程 RRF：14/15。

Canary 适合发现身份、路由和明显回归，但样本规模不足以替代 175 题人工集或未来
正式验收集。

### 11.4 真实远程环境

版本化远程 Gate 在用户控制的 Windows 11 主机上执行，主要环境包括：

- Intel Core i7-12700K、64 GB 内存、NVIDIA RTX 4090 24 GB；
- WSL2 与 Docker；
- PostgreSQL 18.4，迁移 `0001`～`0005`；
- Elasticsearch 9.4.3；
- Milvus 2.6.18；
- Ollama 0.30.10 与 1024 维 BGE-M3。

远程证据证明冻结提交上的真实运行结果，不表示这些服务此刻持续在线，也不等同
于生产部署、生产安全配置或目标规模容量验收。

### 11.5 关键质量与性能证据汇总

| Gate | 关键结果 | 当前决策 |
|---|---|---|
| 真实学术问答 | 3 篇文档、9/9 问题通过，Citation 集合稳定 | Qwen 真实生成主链成立 |
| 固定 Reranker | test=100 的 nDCG@10 0.647269 → 0.747810 | 质量组件保留 |
| RTX 4090 Reranker | pair-scoring P95 188.22683 ms | 组件性能可用 |
| 完整在线分段 | 30/30 应用，combined P95 504.71613 ms | 不默认启用；300 ms 债务保留 |
| Multi-Evidence | 单/多证据、冲突、部分支持、邻块边界专项回归通过 | 正式审计核心，保持 `AUDIT_ONLY` |
| 多语言 NLI 候选 | 9/21 候选正例、124/225 人工谱系正例，均低于 0.85；P95 64.03166 ms | 性能不能覆盖质量失败，候选拒绝 |

> **图片占位 08：关键评测结果图**
> 建议内容：汇总 175 题单路结果、Canary、Reranker 质量增益、在线 P95 和 NLI 候选结论。
> 建议形式：多面板柱状图与状态卡片。
> 建议尺寸：1800 × 1100。
> 后续文件名：`08-key-evaluation-results.png`

## 12. 未晋级实验及准确解释

### 12.1 双文档比较问题拆分 V1

阶段 3 在冻结的 4 个 `dev` 双文档比较难例上，只改变查询拆分这一变量。可信
远程 `_07` 结果为：

- Control 与 Treatment 双侧 Top-3 命中均为 0/4；
- Recall@3 增益为 0；
- nDCG@3 下降 0.017739；
- 固定 15 题为 14/15；
- 身份违规为 0，清理 9/9、READY 失败关闭和删除后 403 通过。

结论是该 V1 在当前冻结输入和实现下不晋级，继续关闭。它不证明“查询拆分”这一
方法类别在所有数据上无效，也没有读取 `test/Acceptance`。

### 12.2 双文档 Top-3 路由覆盖 V1

第二变量在恰好两个授权 READY 文档路由时，尝试让最终 Top-3 至少保留两路各一
个最高 RRF 候选。远程结果为：

- 选择器 4/4 生效，3/4 改变最终 Top-3；
- Control 与 Treatment 双侧命中仍均为 0/4；
- 宏观 Recall@3 均为 0.145833；
- nDCG@3 均为 0.220967；
- 固定 15 题为 14/15；
- 清理 9/9 和删除后 403 通过。

这说明“改变文档覆盖”确实发生，但没有转化为目标质量增益。该 V1 不晋级、
不重跑、不调参；结论同样不能扩大为所有覆盖或多样性方法无效。

### 12.3 多语言 NLI 候选

固定多语言 NLI 模型在 RTX 4090 上达到组件 `P95=64.03166 ms`，但质量门失败：

- AI 辅助候选正例保留 9/21；
- 人工终审谱系正例保留 124/225；
- 两者都低于 0.85 门槛。

后续脱敏诊断显示跨语言和学术排版/领域失效是主要方向，标签与严格 NLI 语义
错配为次要方向。该诊断不是新人工金标，不允许降低门槛、回写数据或启用在线
硬裁决。

### 12.4 为什么保留失败证据

项目将未晋级实验作为一等工程证据，因为它们说明：

- 变量是否真的作用于目标路径；
- 质量失败与基础设施失败是否被区分；
- 清理、ACL 和 holdout 是否在失败时仍受保护；
- “组件速度足够”是否被错误替换成“质量足够”；
- 下一次实验是否需要先定位证据丢失层，而不是继续叠加算法。

阶段 3 因未达到“目标失败集稳定净增益”而不记为完成，但当前工作流已经收口，
不要求为了形式新增第三个变量。

## 13. 项目创新点与技术价值

### 13.1 证据、身份和生命周期统一

系统不是先做检索、再在外围补权限，而是让 owner、活动版本和 Chunk 身份贯穿
入库、召回、生成、引用、审计和删除。该设计减少旧版本泄漏、跨用户混入和
“索引仍在所以仍可访问”等常见风险。

### 13.2 `READY` 作为双索引原子可见门

Elasticsearch 与 Milvus 均可重建，但只有 PostgreSQL 对账通过后，版本才能
进入 `READY`。单侧失败不产生半可见知识，恢复也必须沿同一版本身份幂等执行。

### 13.3 从 Citation 到 EvidenceSet

项目把“回答附引用”推进为“Claim 绑定 EvidenceSet 并审计”。单/多 Evidence、
数值单位、比较限定、冲突和部分支持都有明确状态，同时保持
`AUDIT_ONLY`，避免确定性词面规则越权成为语义裁决器。

### 13.4 失败关闭与可恢复清理

删除先使版本在线失效，再由持久化三路任务完成物理清理。即使远程 Gate 中途
失败，也能通过只读审计和精确恢复闭环证明没有残留可见性。

### 13.5 证据分级的评测治理

项目严格区分：

- 175 题人工校验集；
- 500 题 GPT 辅助工程集；
- 15 题 Canary；
- AI 辅助候选标签；
- 真实远程报告；
- 本地 Fixture/Fake 合同测试。

不同证据回答不同问题，不能互相冒充。未晋级实验和旧失败报告也不覆盖删除，
从而保留可审查的决策链。

### 13.6 单变量 Gate 与默认值治理

RRF、Reranker、比较拆分、路由覆盖和 NLI 都有独立 Gate。组件通过不会自动
改变默认路径，质量、性能、安全和清理结论分别记录。当前默认值因此是经过
决策约束的结果，而不是“最新代码即默认”。

> **图片占位 09：项目创新点总结图**
> 建议内容：概括身份贯通、双索引 READY、EvidenceSet、失败关闭清理、证据分级和单变量 Gate。
> 建议形式：六项创新价值卡片或环形信息图。
> 建议尺寸：1600 × 1000。
> 后续文件名：`09-project-innovations.png`

## 14. 当前限制与未来可选增强

### 14.1 当前限制

- 正式 MinIO 应用适配和 OCR 尚未完成；
- 目标规模为 500 篇标称、1000 篇验证上界，但目标规模容量与性能尚未验收；
- 300 ms 检索性能目标未通过，当前完整在线 P95 为 504.71613 ms；
- Reranker 虽有质量增益，但不默认启用；
- 无证据校准和独立内容安全策略层仍不完整；
- EvidenceSet 是确定性审计，不是通用语义 Judge；
- pair-level 人工正负金标、Precision、负例拒绝率和人工一致率未完成；
- SSE 运行、Trace 持久化、反馈 API、看板、告警、灰度和回滚未完整验收；
- 800～1500 题正式独立盲测尚未进入；
- 仓库当前没有项目级开源许可证。

### 14.2 未来可选增强

以下方向只能在新 Gate 中评估，不能视为当前承诺：

- 优化 Query Embedding 与 READY 路由解析，独立偿还 300 ms 性能债；
- 在不放宽事实源与 ACL 的前提下接入正式 MinIO 和 OCR；
- 先定位比较失败在 ES/Milvus Top-50、RRF Top-50、最终 Top-3、Chunk/邻块或
  标签指标中的丢失层，再选择新的阶段 3 变量；
- 建立 pair-level 人工正负样本后，重新比较 NLI 或离线 LLM Judge；
- 建设完整内容安全策略、Trace/反馈闭环和生产运维 Gate；
- 在明确授权后进入阶段 5 的复杂问答与复用能力。

知识库接入、前端、演示和 Agent API 属于上层产品工作，不是当前文档声明的
未来默认实施项。

## 15. 工程质量、安全与公开仓库边界

### 15.1 本地与远程证据分工

本地 CI/Harness 负责验证代码、合同、权限语义、确定性回归和 PowerShell
静态兼容性。远程 Windows 入口由用户在冻结提交上执行真实 PostgreSQL、ES、
Milvus、模型和 RTX 4090 Gate，再只提交脱敏摘要。

Mac 上的 PowerShell 解析与静态分析不能替代 Windows PowerShell 5.1 行为验证；
历史远程结果也不能被解释为服务当前持续在线。

### 15.2 数据与密钥规则

Git 只保存源码、合同、配置样例、公开 Fixture 和脱敏元数据。以下内容不得进入
版本历史：

- `.env`、API Key、数据库密码、完整连接串和签名凭据；
- 私有问题、用户 PDF、真实 Chunk、Claim/Evidence 正文；
- PostgreSQL dump、SQLite live data、ES/Milvus/MinIO 数据目录；
- 模型权重、Embedding 缓存、虚拟环境与依赖缓存；
- `runtime/`、日志、Trace 正文、完整运行报告；
- 本机绝对路径和远程私有主机信息。

详细规则见[仓库策略](REPOSITORY_POLICY.md)和
[项目安全边界](PROJECT_GUARDRAILS.md)。

### 15.3 最小开发与验证入口

项目要求 Python 3.11+，Makefile 强制使用仓库 `.venv`：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev,server]'
```

提交前最小完整门禁：

```bash
make harness-validate
make test
make powershell-check
git diff --check
```

API 启动和最小请求见 [RAG API 快速开始](RAG_API_QUICKSTART.md)。

## 16. 关键目录与文档导航

### 16.1 目录

| 目录 | 内容 |
|---|---|
| `backend/api/` | Answer API 与请求边界 |
| `backend/ingestion/` | PDF 入库、双索引写入、生命周期和清理 |
| `backend/storage/` | PostgreSQL 事实源、迁移、PDF/Chunk 快照 |
| `backend/retrieval/` | ES、Milvus、RRF、在线路由与可选 Reranker |
| `backend/rag/` | 生成、Citation、Claim–Evidence 与 EvidenceSet |
| `backend/evaluation/` | 评测合同、指标和候选组件 |
| `contracts/` | 版本化 API、数据身份和 Schema 合同 |
| `evaluation/` | 可公开的策略、冻结配置和脱敏评测元数据 |
| `machine/` | 机器可读项目状态、功能清单和 Gate 决策 |
| `deploy/remote/` | 用户执行的版本化远程验证入口 |
| `tests/` | Harness、合同、存储、入库、检索、RAG、API 和评测测试 |
| `docs/` | 当前阶段、专题 Gate 和项目说明 |

### 16.2 权威与状态

- [仓库协作与完成规则](../AGENTS.md)
- [项目首页](../README.md)
- [当前阶段](CURRENT_PHASE.md)
- [最高方案需求追踪](REQUIREMENTS_TRACEABILITY.md)
- [长期产品决策](PRODUCT_DECISIONS.md)
- [项目安全边界](PROJECT_GUARDRAILS.md)
- [机器状态](../machine/project_state.json)
- [功能清单](../machine/feature_list.json)

### 16.3 核心技术专题

- [数据身份与 API 合同](../contracts/README.md)
- [PostgreSQL 事实源](POSTGRESQL_FACT_SOURCE.md)
- [本地 PDF 与持久化入库](LOCAL_PDF_INGESTION.md)
- [远程检索 Baseline](REMOTE_RETRIEVAL_BASELINE.md)
- [阶段 2 收口](PHASE_2_CLOSEOUT.md)
- [普通学术问答验收](PHASE_2_ACADEMIC_QA_ACCEPTANCE.md)
- [固定 Reranker 评测](FIXED_RERANKER_EVALUATION.md)
- [正式检索评测框架](FORMAL_RETRIEVAL_EVALUATION_V1.md)
- [阶段 3 查询拆分 Gate](PHASE_3_COMPARISON_DEV_GATE.md)
- [阶段 3 路由覆盖 Gate](PHASE_3_COMPARISON_ROUTE_COVERAGE_GATE.md)
- [未来比较失败定位](PHASE_3_FUTURE_COMPARISON_FAILURE_LOCALIZATION.md)
- [Claim–Evidence 核心 Gate](PHASE_4_CLAIM_EVIDENCE_CORE_GATE.md)
- [候选二审接收 Gate](PHASE_4_CLAIM_EVIDENCE_CANDIDATE_INTAKE.md)
- [多语言 NLI 候选 Gate](PHASE_4_MULTILINGUAL_NLI_CANDIDATE_GATE.md)
- [Multi-Evidence EvidenceSet Gate](PHASE_4_MULTI_EVIDENCE_SET_GATE.md)

## 17. 结论

当前项目已经完成从 PDF/Chunk、PostgreSQL READY/ACL、ES/Milvus 双路召回、
RRF、真实生成、Citation、`NO_EVIDENCE` 到删除失效和三路清理的核心闭环，并
进一步形成正式的确定性 Multi-Evidence EvidenceSet 审计能力。

项目的技术价值不只在于接入多个数据库或模型，而在于把身份、权限、版本、
证据、拒答、审计和清理纳入同一条可验证链路。与此同时，项目保留了 RRF 无净
增益、阶段 3 两个 V1 未晋级、NLI 质量失败和 300 ms 未达标等真实结论。

阶段 0～2 已完成；阶段 3 工作流收口但不记为完成；阶段 4 的确定性审计核心完成，
整体仍为 `PARTIAL`。知识库产品接入、前端、演示、Agent API 和阶段 5 不在当前
完成范围。

## 18. 图片制作清单

下表仅用于后续统一制作。当前文档没有引用任何不存在的图片文件。

| 编号 | 用途 | 建议内容 | 建议形式 | 建议尺寸 | 后续文件名 |
|---:|---|---|---|---|---|
| 01 | 解释系统全貌 | PostgreSQL、ES、Milvus、RAG 主链和权限边界 | 横向架构图 | 1600 × 900 | `01-system-architecture.png` |
| 02 | 解释入库与可见条件 | PDF 指纹、Chunk 快照、双索引、对账、READY 和失败关闭 | 泳道流程图 | 1600 × 1000 | `02-ingestion-ready-lifecycle.png` |
| 03 | 解释在线问答 | READY/ACL、并行召回、RRF、生成、Citation、审计和拒答 | 横向时序流程图 | 1800 × 900 | `03-online-rag-pipeline.png` |
| 04 | 解释权限和删除 | owner 隔离、活动版本、403、三路清理与恢复 | 状态机与泳道组合图 | 1600 × 1000 | `04-acl-version-cleanup.png` |
| 05 | 解释检索组件差异 | ES、Milvus、RRF、Reranker 的输入、输出、优势、边界和指标 | 四列对比图 | 1800 × 1000 | `05-retrieval-fusion-reranker.png` |
| 06 | 解释多证据审计 | Claim、Citation、EvidenceSet、身份/锚点校验、冲突和四态输出 | 分层流程图 | 1600 × 1000 | `06-multi-evidence-set.png` |
| 07 | 展示建设进度 | 阶段 0～4 状态、关键 Gate、未完成边界和阶段 5 未启动 | 横向路线图 | 1800 × 900 | `07-project-roadmap-status.png` |
| 08 | 汇总评测证据 | 175 题、Canary、Reranker、在线 P95 和 NLI 候选结果 | 多面板数据图 | 1800 × 1100 | `08-key-evaluation-results.png` |
| 09 | 总结技术价值 | 身份贯通、双索引 READY、EvidenceSet、清理恢复、证据分级、单变量 Gate | 创新卡片信息图 | 1600 × 1000 | `09-project-innovations.png` |
