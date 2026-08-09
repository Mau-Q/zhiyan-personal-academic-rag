# RAG Competition Content Pack

状态：`PPT_AND_TECHNICAL_REPORT_RAG_CONTENT_PACK / READY_FOR_INTEGRATION`

用途：作为后续比赛 PPT、技术报告、Demo 与答辩脚本的 RAG 统一内容源。本文件只组织已经冻结的事实、实证、限制与表述边界，不新增 RAG 实现、实验或用户评价。

## 0. 冻结身份与使用规则

| 项目 | 冻结值 | 表述要求 |
|---|---|---|
| Baseline | `RAG_COMPETITION_BASELINE_V1 / FROZEN` | 可表述为“冻结 Competition baseline” |
| RAG owner scope | `DONE_ENOUGH` | 仅表示当前 Competition RAG 责任范围收口，不表示项目全部完成 |
| Windows 真实复现源 | `d775dab706c2a05d5b838f644b77b257961a4549` | Windows 复现的是 `d775dab` |
| Submission repository head | `fd5a517b56ba619ca461e262a5ea1a8ac8b9ac7b` | clean-checkout CI 与 submission head |
| Baseline authority closeout | `038df52ad1fe453420b43cd1dcf9b9e117f7277c` | 冻结 baseline 权威的后续提交 |
| Visual specification | `7818f3304b39d5946b175bb54070ba656fe10ede` | 冻结四张图的规格 |
| Visual rendering | `c2de741550348f53dae33787e87e303e488db451` | 渲染四张比赛级 SVG |
| Runtime equivalence | `d775dab → fd5a517 = PASS` | 不得写成“Windows 复现了 fd5a517” |
| Run ID | `competition_v1_20260809_01` | 仅作内部证据追踪，不要求上屏 |

核心来源：[`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json)、[`rag-competition-pack-v1.json`](../../machine/competition/rag-competition-pack-v1.json)、[`RAG_COMPETITION_HANDOFF_V1.md`](RAG_COMPETITION_HANDOFF_V1.md) 与 [`VISUAL_EVIDENCE_LEDGER.md`](visuals/VISUAL_EVIDENCE_LEDGER.md)。

统一术语：`READY`、`owner ACL`、`Elasticsearch / BM25`、`Milvus / BGE-M3`、`candidate Top-20`、`RRF k=60`、`Evidence Top-3`、`Qwen3 14B`、`Citation`、`Evidence`、`Claim`、`EvidenceSet`、`AUDIT_ONLY`、`RAG_FORBIDDEN_SCOPE`。

## 1. Executive Summary

本项目的 RAG Core 不是“向量库接大模型”的单点功能，而是一条从可信知识版本到可追溯回答、再到删除后失败关闭的技术闭环：获准文献形成 owner-scoped 的版本与 Chunk 快照；只有完成解析、Chunk、Elasticsearch 和 Milvus 双索引的版本才能进入 `READY`；在线请求先经过 owner ACL 与 READY 校验，再由 Elasticsearch/BM25 和 Milvus/BGE-M3 并行召回，每路候选上限 20，默认使用 `RRF k=60` 融合为 `Evidence Top-3`；Qwen3 14B 在 `academic-evidence-answer-v1`、`think=false` 的冻结配置下，只依据这些 Evidence 生成结构化 Claim、Answer 与 Citation。

Citation 可以继续映射到 Evidence 的 document、page、chunk 与 version 身份。一个 Claim 可绑定一个或多个 Citation，并进入确定性 EvidenceSet 审计；该能力严格保持 `AUDIT_ONLY`，即“审计，不自动裁决”。无有效证据时系统返回 `NO_EVIDENCE` 且不调用生成模型；越权、未 READY 或失活时返回 `403 RAG_FORBIDDEN_SCOPE`；生成或引用门禁失败时进入 `DEGRADED` 并保留已授权证据卡。DELETE 后，版本先失活，再完成 Elasticsearch、Milvus 与 runtime snapshot 三路 cleanup，旧 Evidence 不得复用。

冻结 Windows Competition Gate 的三个场景为 `3/3 PASS`，但该结果只覆盖恰好三个冻结场景，不代表 100% 泛化准确率。固定 BGE Reranker 在冻结排序失败集的 Top-20 和 Top-50 screening 均为 `0/3 bilateral Top-3 recovery`，因此保留默认 RRF，Phase 3 retrieval/ranking optimization 停止。性能债不隐藏：combined P95 约 `504.7 ms`，高于 `300 ms` 目标，状态仍为未达成、deferred；正式 800–1500 条 Acceptance、真实用户评价与 production readiness 均未完成。

## 2. RAG Competition Story

### 2.1 一句话主张

> 系统围绕学术场景建立了“可信版本—授权混合检索—证据约束生成—可追溯 Citation—多证据审计—生命周期失败关闭”的完整 RAG Core，而不是只把向量检索结果交给大模型。

### 2.2 推荐叙事顺序

1. 研究资料不是上传后立即可问，而是先形成 owner-scoped 文档版本和不可变 Chunk 快照。
2. 只有解析、Chunk、Elasticsearch、Milvus 全部就绪的版本才能进入 `READY`。
3. 在线请求先经过 owner ACL 与 READY 门禁；候选在检索后还要重验身份。
4. Elasticsearch/BM25 与 Milvus/BGE-M3 并行召回，每路候选 Top-20；默认用 `RRF k=60` 按名次融合。
5. 最多 3 条已授权 Evidence 进入 Qwen3 14B；生成层输出结构化 Claim、Answer 与 Citation。
6. Citation 可回溯到 Evidence 的 document/page/chunk/version；一个 Claim 可绑定多个 Citation/Chunk。
7. EvidenceSet 只执行确定性 `AUDIT_ONLY`，记录支持、部分支持、冲突或证据不足，不自动删除 Claim。
8. 无证据、越权/失活、生成/引用失败分别进入 `NO_EVIDENCE`、403 与 `DEGRADED`，不强行回答。
9. DELETE 后先失活，再做三路 cleanup；冻结 Gate 观察到 403 且 `stale_evidence_reused=false`。
10. 技术方案由真实 Gate、负向实验和已知限制共同决定；Reranker 没有因“更先进”而默认采用。

### 2.3 评委应带走的结论

- 证据进入模型前有 owner 与 READY 双重约束。
- 混合检索使用异构双路召回，但融合时不直接比较 BM25/COSINE 原始分数。
- 回答不是文本黑盒：Citation 与 Evidence 身份可追溯，Claim 可进行多证据审计。
- 系统不仅能回答，也能在无证据、越权或知识已删除时失败关闭。
- 决策保留失败证据：Reranker screening 失败与 300 ms 性能债均公开呈现。

## 3. Technical Architecture

### 3.1 设计目标

技术架构的核心不是扩大模型自由度，而是限制什么知识可以进入生成、回答中的依据如何回溯、知识失效后如何停止继续使用。PostgreSQL 负责 owner、版本、生命周期与 Chunk 快照事实；Elasticsearch 和 Milvus 是受 READY 路由约束的检索通道，不是第二套授权事实源。

### 3.2 冻结主链

```text
获准 PDF / 文献来源
        ↓
Chunk + page / neighbor identity
        ↓
PostgreSQL owner / document version / snapshot
        ↓
READY + owner ACL
        ↓
Elasticsearch / BM25  ∥  Milvus / BGE-M3
        ↓
candidate Top-20 per channel
        ↓
RRF k=60（默认；Reranker OFF）
        ↓
Evidence Top-3
        ↓
Qwen3 14B + academic-evidence-answer-v1 + think=false
        ↓
Claim + Answer + Citation
        ↓
Citation → Evidence → document / page / chunk / version
```

### 3.3 Figure integration — 图 01

- 图：[`01-system-architecture.svg`](visuals/rendered/01-system-architecture.svg)
- PPT：`RAG-02`，作为系统闭环的主架构图。
- 技术报告：第 2～6 节之前，作为“可信版本—检索—生成—审计—生命周期”的总览。
- 引入句：**“先看完整闭环：READY 是入口，Citation/Evidence 是输出证据链，DELETE/cleanup/403 是生命周期终点。”**
- 评委应注意：默认 RRF、Reranker OFF、EvidenceSet `AUDIT_ONLY`、OCR 未完成与非 production-ready 边界均在图中可见。
- 图注：**图 01｜冻结 RAG 核心架构。** 获准文献形成 owner-scoped 的版本化 Chunk，并在 PostgreSQL、Elasticsearch 与 Milvus 一致就绪后进入 READY；在线问题经 BM25 与 BGE-M3 双路召回、默认 RRF 融合和 Qwen 证据约束生成，Citation 可回溯到 document/page/chunk/version。EvidenceSet 仅作确定性 `AUDIT_ONLY`，删除后通过失活、三路 cleanup 和 403 失败关闭。

### 3.4 不能由架构图推断的内容

- OCR 完整链路、正式 MinIO、生产监控、Agent 编排、会话记忆、在线 NLI Judge 均未完成或不在冻结 baseline。
- READY 不等于“文件已上传”；它要求解析、Chunk 与双索引就绪并保持活动状态。
- Reranker 是可选、非默认组件，未进入冻结在线主链。

## 4. Online RAG Flow

### 4.1 单次请求顺序

1. Answer API 接收问题并由服务端校验 owner/scope。
2. PostgreSQL 只解析当前授权范围内的 `READY` 版本；未授权、未 READY、已失活或无法证明身份时返回 `403 RAG_FORBIDDEN_SCOPE`。
3. 系统加载 READY Chunk 快照，校验 version/chunk 唯一身份。
4. Elasticsearch/BM25 与 BGE-M3→Milvus 并行召回，每路最多 20 个候选。
5. 候选必须再次匹配 owner/document/version/active；身份漂移继续失败关闭。
6. 两路排名经 `RRF k=60` 融合，最多选择 3 条有效 Evidence。
7. 若为 0 条有效 Evidence，返回 `NO_EVIDENCE`，不调用真实生成模型。
8. 若存在有效 Evidence，Qwen3 14B 基于 Evidence 生成结构化 Claim，并要求 citation_ids 只引用本次 Evidence。
9. Citation 门禁通过后返回 Answer + Citation + Evidence；生成或引用门禁失败则返回 `DEGRADED`，保留已授权证据卡。

### 4.2 四种终态必须区分

| 终态 | 含义 | 生成模型 | Evidence |
|---|---|---|---|
| `COMPLETED` | 授权 READY Evidence 存在，生成与 Citation 门禁通过 | 调用 | 返回本次已授权 Evidence |
| `NO_EVIDENCE` | 当前授权范围内没有有效证据 | **不调用** | 0 条有效 Evidence |
| `403 RAG_FORBIDDEN_SCOPE` | 未授权、未 READY、失活或范围无法证明 | 不进入合法生成路径 | 不复用旧 Evidence |
| `DEGRADED` | 生成或 Citation 门禁失败 | 调用失败或输出未过门禁 | 只保留已授权证据卡 |

### 4.3 Figure integration — 图 03

- 图：[`03-online-rag-pipeline.svg`](visuals/rendered/03-online-rag-pipeline.svg)
- PPT：`RAG-03`，解释一次请求如何成功或失败关闭。
- 技术报告：第 4 节“证据约束生成与引用追踪”之前，承接架构图并展开在线时序。
- 引入句：**“架构完整不等于每次都回答；这条流程把成功、无证据、越权和生成失败拆成四个不同终态。”**
- 评委应注意：`403 ≠ NO_EVIDENCE ≠ DEGRADED`；成功与失败终点不合并；默认路径无 Reranker；性能限制仍为 deferred。
- 图注：**图 03｜单次在线 RAG 请求流程。** 请求先经过服务端 owner/scope 与 PostgreSQL READY 门禁，再由 Elasticsearch BM25 与 Milvus/BGE-M3 并行召回、RRF 融合 Top-3 Evidence，最后由 Qwen 生成并验证 Citation。无证据、越权/失活、生成/引用门禁失败分别进入 `NO_EVIDENCE`、403 与 `DEGRADED` 失败关闭路径。

## 5. Claim–Evidence / Multi-Evidence

### 5.1 能力说明

生成 Prompt 要求回答由结构化 Claim 组成，每个 Claim 携带一个或多个本次请求内的 citation_ids。Citation 解析到已授权 Evidence，并保留 document、page、chunk、version 身份。EvidenceSet 随后执行两类检查：

- 身份检查：owner、活动 document/version、Chunk 唯一身份与 Citation 位置；
- 确定性支持检查：数字、单位、比较对象、限定条件、关系、核心重合与同单位冲突。

审计结果可记录为支持、部分支持、冲突或证据不足。这些是确定性审计状态，不是人工语义真值。

### 5.2 冻结实证

`COMP-EVIDENCESET-001` 在 Windows Competition Gate 中通过，观察到至少一个真实生成 Claim 同时绑定多条 Citation 与多个 Chunk。比赛材料使用脱敏结构表达：

```text
1 Claim
  → 2 Citations
  → 2 Evidence / Chunks
```

该 `2 + 2` 是已观测绑定结构的脱敏表达，不公开私有问题、完整 Answer、真实 Chunk ID 或原文摘录。

### 5.3 强制边界

```text
EvidenceSet = AUDIT_ONLY
human semantic Gold = false
new Judge = false
automatic claim deletion = false
```

推荐中文短句：**“审计，不自动裁决。”**

### 5.4 Figure integration — 图 06

- 图：[`06-multi-evidence.svg`](visuals/rendered/06-multi-evidence.svg)
- PPT：`RAG-04`，作为 RAG 技术差异点的中心图。
- 技术报告：第 5 节“Claim–Evidence 与 Multi-Evidence 审计”，紧随 Citation 身份说明。
- 引入句：**“Citation 不只服务展示；系统把回答拆成 Claim，并保留 Claim 到一个或多个 Evidence 的可检查绑定。”**
- 评委应注意：Claim B 明确分叉到两条 Citation 和两个 Chunk；底部审计轨的终点是 `AUDIT_ONLY`，不连向自动删除、重写或重新检索。
- 图注：**图 06｜多证据 Claim–Evidence 审计。** 冻结 Competition 真实场景已观测到至少一个生成 Claim 同时绑定两条 Citation 和两个 Chunk；系统可沿 Citation 回溯 Evidence 身份，再执行 owner/活动版本与数字、比较、限定、冲突等确定性检查。该 EvidenceSet 仅为 `AUDIT_ONLY`，不等于人工语义 Gold，也不自动删除 Claim 或消除幻觉。

## 6. Evaluation and Falsification

### 6.1 Competition 真实复现

- Windows PowerShell 5.1 真实复现源：`d775dab`。
- 冻结 Competition 场景：`3/3 PASS`。
- 两个真实问题均为 `COMPLETED`，每题返回 3 条 Evidence。
- Citation/Evidence/页码身份、generation replay 与本次 byte-stable replay 均通过。
- DELETE 后 cleanup `3/3`、runtime snapshot cleanup、不可见性、403 与 no-stale Evidence 通过。
- 限制语：**仅代表冻结的三个 Competition 场景；不代表系统准确率 100%。**

### 6.2 排序方案的负向筛选

| 方案 | 冻结结果 | 决策 |
|---|---|---|
| Fixed BGE Reranker，Top-20 | `0/3 bilateral Top-3 recovery` | `SCREENING_WEAKENED` |
| 同一 Fixed BGE Reranker，Top-50 exposure | `0/3 bilateral Top-3 recovery` | 扩大 exposure 仍未恢复 |
| 在线默认 | 保留 `RRF k=60` | Reranker 继续非默认，Phase 3 optimization `STOP` |

推荐表述：**“没有因为 Reranker 看起来更先进就默认采用；冻结失败集的 Top-20 与 Top-50 screening 均未恢复任一 bilateral Top-3 案例，因此保留更有证据支持的 RRF 默认策略。”**

限定：该结果只削弱当前 fixed reranker family 在冻结 3 条失败上的采用依据，不否定所有 Reranker、所有 ranking 方法或未来在不同代表性负载下的条件式重开。

### 6.3 Clean-checkout 可复现性

- 精确 submission head：`fd5a517`。
- GitHub Core tests：Ubuntu 24.04 / CPython 3.11.15。
- `make test = PASS`。
- historical clean-checkout runtime/path errors：`14 → 0`。

`14 → 0` 只表示 clean-checkout 的 runtime/path errors 清零，不是全部产品缺陷清零。

### 6.4 Figure integration — 图 08

- 图：[`08-key-evaluation-results.svg`](visuals/rendered/08-key-evaluation-results.svg)
- PPT：`RAG-06`，作为 RAG 段落收束页。
- 技术报告：第 7～10 节之间，汇总真实 Gate、证伪、可复现性与限制。
- 引入句：**“冻结 baseline 不只由成功结果构成：真实复现、负向实验、clean checkout 与未达成指标同时进入决策。”**
- 评委应注意：`3/3` 的范围限定、两个 `0/3` 的冻结失败集限定、`14→0` 的 clean-checkout 限定，以及三提交谱系未被合并。
- 图注：**图 08｜冻结 baseline 的关键验证与负向决策。** Windows 真实复现的三个 Competition 场景全部通过，Citation/Evidence 身份、回放、cleanup/403 与 clean-checkout CI 均有证据；固定 BGE Reranker 的 Top-20/Top-50 screening 均为 0/3，因此保留默认 RRF 并停止 Phase 3 排序优化。combined P95 约 504.7 ms，高于 300 ms 目标，明确记为未达成、deferred。

## 7. Three Golden Scenarios

> 详细卡片见 [`RAG_GOLDEN_SCENARIO_CARDS.md`](RAG_GOLDEN_SCENARIO_CARDS.md)。以下内容只使用脱敏展示问题，不公开私有原题、完整 Answer 或 Chunk/PDF 正文。

### 7.1 `COMP-QA-001` — Evidence QA

- 目的：证明授权论文问题可以得到 grounded Answer，并把 Citation 追溯到 page/chunk/version。
- 脱敏展示问题：请解释论文中的 MAX-composite step-risk 操作，以及为什么最大值能保留局部尖锐失效而不是被平均稀释。（非私有原题逐字内容）
- 预期答案点：定义 MAX-composite step-risk；解释 maximum 保留局部尖锐 breakdown。
- 观察结果：`PASS / COMPLETED`；返回 3 条 Evidence；Citation/Evidence/页码身份与回放门禁通过。
- 位置证明：冻结 dossier 要求授权文档 `doc_arxiv_2602_11409` 的 page 4；材料中只展示页码与脱敏身份，不展示私有 Chunk/PDF。
- PASS 判据：状态 `COMPLETED`，Citation 与 Evidence 均非空且映射合法，位置门禁通过。
- 限制：确定性 Citation/位置通过不替代人工对 Answer 语义正确性的最终判断。

### 7.2 `COMP-EVIDENCESET-001` — Multi-Evidence Audit

- 目的：证明一个真实生成 Claim 可同时绑定多个 Citation/Evidence，并进入确定性审计。
- 脱敏展示问题：请说明风险刻画中的内容感知 token surprisal、重复/连贯性缺口指标与尾部聚合如何共同出现。（非私有原题逐字内容）
- 预期答案点：content-aware token surprisal；repetition/coherence-gap indicators；tail-focused aggregation。
- 观察结果：`PASS / COMPLETED`；至少 2 条 Evidence；至少 1 个真实生成 Claim 形成多 Evidence 绑定。
- 核心证明：`1 Claim → 2 Citations → 2 Chunks`；授权页范围为 page 1–3。
- PASS 判据：完成回答、至少两条 Evidence、EvidenceSet audit status 为 PASS。
- 限制：EvidenceSet 始终为 `AUDIT_ONLY`；无人工语义 Gold、无新 Judge、不自动删除 Claim。

### 7.3 `COMP-FAIL-CLOSED-001` — Fail-Closed

- 目的：证明同一隔离生命周期中的文档 DELETE 后不再被继续用于回答。
- 可展示问题：`This deleted document must remain unavailable.`（中文说明：这篇已删除文档必须保持不可用。）
- 观察结果：`PASS`；`actual_refusal=true`；`403 RAG_FORBIDDEN_SCOPE`；Evidence 返回 0；`stale_evidence_reused=false`；cleanup `3/3`。
- PASS 判据：三路 cleanup、runtime snapshot cleanup、inactive visibility 均通过，失活 Answer API 返回 403。
- 限制：该场景证明既有 owner/READY/DELETE 生命周期合同，不外推为覆盖所有安全威胁或所有失败流程。

## 8. Reproducibility

可复现性由三个不同身份共同支撑，必须分开表述：

```text
Windows real reproduction source = d775dab
        ↓ runtime equivalence PASS
submission repository head = fd5a517
        ↓ baseline authority closeout
authority = 038df52
        ↓ visual specification / rendering
7818f33 / c2de741
```

Windows 真实复现使用版本化 PowerShell 5.1 wrapper、exact-HEAD 检查、loopback 服务、secure prompt 与严格退出；真实运行产物保留在 ignored runtime。比赛公开材料不得包含密码、连接字符串、私有主机、完整 PDF、私有 corpus、原始数据库/索引、完整 Chunk、私有 trace 或模型 reasoning。

## 9. Known Limitations

1. `combined P95 ≈ 504.7 ms`，高于 `300 ms` 目标；状态为 `NOT ACHIEVED / DEFERRED`。
2. Reranker 不是默认在线路径；当前 fixed reranker family 在冻结 3 条排序失败上为 `SCREENING_WEAKENED`。
3. Phase 3 为 `PARTIAL / NO_PROMOTION`，retrieval/ranking optimization 已 `STOP`，不等于最高方案阶段 3 完成。
4. Phase 4 为 `PARTIAL / AUDIT_ONLY`；pair-level 人工 Gold、新 NLI/LLM Judge 与在线硬裁决后置。
5. OCR、正式 MinIO、目标规模性能、生产监控、Agent API、前端与阶段 5 复杂问答未完成或不在本 baseline。
6. 800–1500 条正式独立 Acceptance 未完成；不能声称 production ready。
7. `3/3 PASS` 只覆盖三个冻结 Competition 场景；不能转写为准确率 100%。
8. byte-stable replay 只是在本次两个真实问题上的观察，不是自然语言生成的永久保证。
9. 真实用户评价尚无完成结果，保持 `PENDING_REAL_USER_EVALUATION`。

## 10. Competition-Safe Claims

以下表述可用于比赛材料，但必须保留限定语：

- “系统采用 PostgreSQL READY/owner 事实源、Elasticsearch BM25 与 Milvus/BGE-M3 双路召回、默认 RRF 融合和 Qwen3 14B 证据约束生成。”
- “冻结参数为每路 candidate Top-20、`RRF k=60`、`Evidence Top-3`。”
- “Citation 可以映射到 Evidence 的 document/page/chunk/version 身份。”
- “无有效 Evidence 时返回 `NO_EVIDENCE`，且不调用生成模型；越权、未 READY 或已失活时返回 403。”
- “EvidenceSet 支持一个 Claim 绑定一个或多个 Evidence 的确定性审计，模式为 `AUDIT_ONLY`。”
- “Windows 真实复现的三个冻结 Competition 场景为 `3/3 PASS`。”
- “固定 BGE Reranker 的 Top-20 与 Top-50 frozen screening 均为 `0/3 bilateral Top-3 recovery`，因此保留默认 RRF。”
- “GitHub clean checkout 在精确 `fd5a517`、Ubuntu 24.04 / CPython 3.11.15 上 `make test PASS`。”
- “combined P95 约 504.7 ms，300 ms 目标尚未达到。”

完整证据级别与用法见 [`RAG_COMPETITION_CLAIMS_LEDGER.md`](RAG_COMPETITION_CLAIMS_LEDGER.md)。

## 11. Claims We Must Not Make

- 不说“系统自动消除幻觉”“100% 事实正确”或“EvidenceSet 自动判定语义真伪”。
- 不说“Reranker 已默认启用”或“Top-50 已证明更优”。
- 不说“3/3 等于全部问题准确率 100%”。
- 不说“Windows 复现了 fd5a517”；Windows 复现源是 `d775dab`。
- 不说“14→0 表示全部产品缺陷清零”。
- 不说“300 ms 已达成”“SLO 已验收”或“production ready”。
- 不说“Phase 3/4 已全部完成”。
- 不说“OCR、生产监控、Agent 编排、会话记忆、在线 NLI Judge 已完成”。
- 不编造用户数、满意度、准确率、节省时间、接受分、Cohen's kappa 或用户引语。
- 不把脱敏结构示意当成 Windows 逐字回答或论文原文引文。

## 12. Pending User Evaluation

当前状态：`PENDING_REAL_USER_EVALUATION`。

仓库已提供 [`COMPETITION_HUMAN_EVALUATION_V1.md`](COMPETITION_HUMAN_EVALUATION_V1.md) 与双评审 worksheet 模板，但没有已完成的真实用户评价结果。后续集成表面需要展示用户评价时使用：

```text
[待真实用户评价完成后填入]
```

评价完成前不得填写用户数量、满意度、答案准确率、节省时间、acceptance score、Cohen's kappa 或用户原话。只有三个场景时，kappa 也可能因样本与类别变化不足而 `NOT_COMPUTABLE`。

## 13. Recommended PPT Mapping

建议使用 6 页，不让 RAG 段落压过整个项目：

| Slide | Takeaway | Main visual |
|---|---|---|
| `RAG-01` | 学术 RAG 的关键不是“能生成”，而是“证据能进入、能追溯、能失效” | 简洁问题—约束—结果叙事，不新增技术图 |
| `RAG-02` | READY 到 Citation/cleanup 构成完整技术闭环 | 图 01：`01-system-architecture.svg` |
| `RAG-03` | 只有授权 READY Evidence 进入生成；三类失败明确分流 | 图 03：`03-online-rag-pipeline.svg` |
| `RAG-04` | 一个 Claim 可绑定多个 Citation/Chunk，但只审计、不自动裁决 | 图 06：`06-multi-evidence.svg` |
| `RAG-05` | 三个 Golden Scenario 分别证明回答、审计与失败关闭 | 3 个场景的精简横向叙事；不放私有问答正文 |
| `RAG-06` | 真实复现、负向实验、可复现性和性能债共同支撑决策 | 图 08：`08-key-evaluation-results.svg` |

逐页可见文案、讲者备注与禁用表述见 [`RAG_PPT_CONTENT_MAP.md`](RAG_PPT_CONTENT_MAP.md)。

## 14. Recommended Technical Report Mapping

| 报告节 | 内容重点 | 主要证据/图 |
|---|---|---|
| 1. RAG 模块目标与设计原则 | 可信版本、最小授权、可追溯、失败关闭 | Baseline + 图 01 引入 |
| 2. 数据与知识版本管理 | owner、document/version、Chunk 快照、READY | 图 01 |
| 3. 混合检索与融合策略 | ES/BM25、Milvus/BGE-M3、Top-20、RRF 60、Top-3 | 图 01、Reranker screening |
| 4. 证据约束生成与引用追踪 | Qwen/Prompt/think=false、Citation 与四级身份 | 图 03 |
| 5. Claim–Evidence 与 Multi-Evidence 审计 | 1→2→2、确定性审计、AUDIT_ONLY | 图 06 |
| 6. 权限、生命周期与失败关闭 | NO_EVIDENCE、403、DEGRADED、DELETE cleanup | 图 03、场景 C |
| 7. 评测设计与关键实验 | 实证与证伪并重；Reranker 0/3 | 图 08 |
| 8. 真实 Competition Gate | 三个场景、运行身份、脱敏边界 | Golden Scenario 卡 |
| 9. 可复现性 | Windows source、submission head、CI 与 14→0 限定 | 图 08 |
| 10. 已知局限与适用边界 | 504.7>300、阶段、Acceptance、UAT pending | 图 08 limitation rail |

正式段落草案见 [`RAG_TECHNICAL_REPORT_DRAFT.md`](RAG_TECHNICAL_REPORT_DRAFT.md)。

## 15. Demo / Defense Talking Points

### 15.1 90 秒 Demo 叙事

1. **先说明输入边界：** “这两道学术问题只访问当前 owner 已授权且处于 READY 的文档版本。”
2. **展示 Evidence QA：** 提问后指出 Answer 不是唯一结果；Citation 还可展开到 Evidence 的页码、Chunk 与版本身份。
3. **展示 Multi-Evidence：** 选择一个 Claim，展示它同时连到 2 条 Citation 与 2 个 Chunk；立即补充“EvidenceSet 是 `AUDIT_ONLY`，审计而不自动裁决”。
4. **执行失活：** 在同一隔离生命周期中 DELETE 文档，说明先失活再清理三路对象。
5. **展示拒绝：** 再次请求同一知识，展示 `403 RAG_FORBIDDEN_SCOPE`、Evidence 0、no stale reuse。
6. **收束证据：** “三个冻结场景 3/3 通过；Reranker 负向 screening 没有恢复失败集，所以默认仍是 RRF；性能 300 ms 目标尚未达到。”

### 15.2 常见答辩问题

**为什么不用纯向量检索？**
学术问题同时包含精确术语和语义改写。系统保留 Elasticsearch/BM25 与 Milvus/BGE-M3 两路排序，再用 RRF 按名次融合，避免直接比较异构原始分数。冻结默认是这条双路 RRF，而不是单路向量。

**为什么默认不用 Reranker？**
Reranker 组件曾在受控评测中显示局部指标增益，但在当前冻结的三条排序失败上，Top-20 与 Top-50 screening 都是 `0/3 bilateral Top-3 recovery`；同时 combined P95 约 504.7 ms 已高于 300 ms 目标。因此没有足够证据把它设为默认，当前保留默认 RRF。

**怎么保证回答有来源？**
生成模型只接收已授权 Evidence；Claim 携带请求内 citation_ids；Citation 必须落在本次 Evidence 集合中，并能映射到 document/page/chunk/version。该机制证明来源身份与位置合法，但语义正确性仍需要人工判断。

**EvidenceSet 能不能解决幻觉？**
不能这样表述。EvidenceSet 对身份、数字、单位、比较、限定、核心重合和冲突做确定性审计，模式为 `AUDIT_ONLY`。它不是人工语义 Gold 或在线 Judge，也不自动删除 Claim；准确表述是“帮助暴露可检查的 Claim–Evidence 关系”。

**删除论文后旧 Evidence 会不会继续出现？**
冻结 fail-closed 场景中，DELETE 后三路 cleanup、runtime snapshot cleanup 与不可见性证明通过；后续 Answer API 返回 403，Evidence 为 0，`stale_evidence_reused=false`。该证据针对既有 owner/READY/DELETE 生命周期，不外推到所有安全威胁。

**为什么 P95 没达到 300 ms？**
Windows 分段观测的 combined P95 约 504.7 ms；主要成本曾定位在 Query Embedding 与 READY 路由解析。当前任务没有继续性能优化，原因是 baseline 要先冻结可解释、可复现的 RAG Core。比赛材料如实将 300 ms 记为未达成、deferred，而不是隐藏或改写指标。

**3/3 PASS 是否代表系统准确率 100%？**
不是。3/3 只表示恰好三个冻结 Competition 场景通过，分别覆盖 Evidence QA、Multi-Evidence Audit 与 Fail-Closed。它不是大规模 benchmark，也不能推断到所有问题。

**为什么 Phase 3/4 没有全部完成？**
Phase 3 的两个增强变量没有取得稳定净增益，fixed reranker screening 也没有恢复冻结失败集，因此 workstream 按证据停止但阶段保持 `PARTIAL / NO_PROMOTION`。Phase 4 已完成确定性 Multi-Evidence 审计核心，但人工 pair-level Gold、新 Judge 与在线硬裁决后置，所以整体仍为 `PARTIAL / AUDIT_ONLY`。

**如何证明代码不是只在自己的电脑上能跑？**
真实 Competition Gate 由用户在 Windows PowerShell 5.1 上对 `d775dab` 执行；独立 closeout 又确认到 submission head `fd5a517` 的 runtime equivalence 为 PASS，并且 GitHub clean checkout 在 Ubuntu 24.04 / CPython 3.11.15 上 `make test PASS`。这三项证据身份分开记录。

### 15.3 收束语

> 当前证据支持的是一条冻结、可追溯、会拒答、可清理并经过真实 Gate 的 RAG Core；它不支持“自动消除幻觉”“准确率 100%”或“production ready”。
