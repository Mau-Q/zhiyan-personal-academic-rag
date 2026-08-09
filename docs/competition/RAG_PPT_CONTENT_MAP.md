# RAG PPT Content Map

## Communication job

到本段结束时，比赛评委应理解：本项目的 RAG 价值不在“接入了大模型”，而在于可信版本、授权混合检索、证据约束生成、可追溯 Citation、多证据审计和失败关闭共同形成了可验证闭环；同时，团队按真实 Gate 与负向实验做决策，并公开保留未达成的性能和验证边界。

建议页数：**6 页**。每页只承担一个叙事任务；RAG 段落用于较大项目时，不再增加独立目录页、重复架构页或纯参数页。

## RAG-01

**Slide ID**
`RAG-01`

**Slide title**
学术 RAG 的难点不是“生成”，而是证据能进入、能追溯、能失效

**Single takeaway**
系统围绕三件事设计：只让可信授权知识进入回答、让每个回答依据可回溯、让失效知识不再继续使用。

**Main visual**
不使用新增复杂图。采用一个水平三段式短链：`可信进入 → 可追溯回答 → 失败关闭`，右下角以小号术语列出 `READY / Citation / DELETE→403`。该页是叙事开场，不与后续四张技术图争夺信息。

**Supporting evidence**
[`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json)、[`RAG_COMPETITION_HANDOFF_V1.md`](RAG_COMPETITION_HANDOFF_V1.md)、[`VISUAL_EVIDENCE_LEDGER.md`](visuals/VISUAL_EVIDENCE_LEDGER.md) 的 `01-E01`～`01-E17`。

**On-slide text**

```text
可信进入
owner ACL + READY

可追溯回答
Citation → Evidence → page / chunk / version

失败关闭
NO_EVIDENCE / 403 / DELETE cleanup

冻结边界：默认 RRF · EvidenceSet AUDIT_ONLY
```

**Speaker notes**
“如果只看最终 Answer，很容易把这套系统误解为向量库加大模型。我们的设计从知识版本进入开始：owner 与 READY 决定可见性；生成后 Citation 保留证据身份；DELETE 后失活、清理并返回 403。后面五页按这个闭环展开。”

`[Sources] machine/competition/rag_competition_baseline.json; docs/competition/RAG_COMPETITION_HANDOFF_V1.md; docs/competition/visuals/VISUAL_EVIDENCE_LEDGER.md`

**Do-not-say boundary**
不要说“自动消除幻觉”“所有问题都能回答”“生产系统已完成”；不要在开场暗示 OCR、Agent 编排或生产监控已完成。

## RAG-02

**Slide ID**
`RAG-02`

**Slide title**
从 READY 到 Citation 与 cleanup，RAG Core 形成完整技术闭环

**Single takeaway**
冻结主链由 PostgreSQL READY/owner 事实源、ES+Milvus 双路检索、默认 RRF、Evidence Top-3、Qwen grounded generation 与可追溯 Citation 组成，生命周期终点是失活、三路 cleanup 和 403。

**Main visual**
全幅使用 [`01-system-architecture.svg`](visuals/rendered/01-system-architecture.svg)。保持 16:9 比例，不裁掉底部冻结边界。图前引入句：“先看完整闭环：READY 是入口，Citation/Evidence 是输出证据链，DELETE/cleanup/403 是生命周期终点。”

**Supporting evidence**
[`01-system-architecture.spec.md`](visuals/01-system-architecture.spec.md)、[`rag-competition-pack-v1.json`](../../machine/competition/rag-competition-pack-v1.json)、视觉账本 `01-E01`～`01-E18`。

**On-slide text**

```text
每路 candidate Top-20
RRF k=60
Evidence Top-3
Qwen3 14B · think=false

默认 RRF · Reranker OFF
```

除标题和以上短标记外，不再叠加解释段落；图中已有完整节点与边界。

**Speaker notes**
“PostgreSQL 是 owner、版本和生命周期事实源。文档只有在解析、Chunk、ES、Milvus 全部就绪后才进入 READY。在线问题同时进入 BM25 与 BGE-M3/Milvus，两路各取 Top-20，用 RRF 60 按名次融合，再选最多 3 条 Evidence。Qwen 只看到这些 Evidence。回答中的 Citation 可以继续定位到 document/page/chunk/version。Reranker 没有进入默认主链。”

`[Sources] docs/competition/visuals/01-system-architecture.spec.md; docs/competition/visuals/VISUAL_EVIDENCE_LEDGER.md; machine/competition/rag-competition-pack-v1.json`

**Do-not-say boundary**
不要说“READY 等于上传完成”“OCR 已完成”“Reranker 默认启用”“EvidenceSet 是语义 Judge”“403 覆盖所有故障”“production ready”。

## RAG-03

**Slide ID**
`RAG-03`

**Slide title**
只有授权且 READY 的 Evidence 进入生成，失败路径彼此分离

**Single takeaway**
一次请求可能完成 grounded Answer，也可能以 `NO_EVIDENCE`、403 或 `DEGRADED` 失败关闭；系统不把“没有证据”和“没有权限”混为一谈。

**Main visual**
全幅使用 [`03-online-rag-pipeline.svg`](visuals/rendered/03-online-rag-pipeline.svg)。保持底部三个终态与右侧性能限制完整可见。图前引入句：“架构完整不等于每次都回答；这条流程把成功、无证据、越权和生成失败拆成四个终态。”

**Supporting evidence**
[`03-online-rag-pipeline.spec.md`](visuals/03-online-rag-pipeline.spec.md)、视觉账本 `03-E01`～`03-E15`，以及实现中 `NO_EVIDENCE` 不调用真实生成模型的门禁。

**On-slide text**

```text
COMPLETED：Answer + Citation + Evidence
NO_EVIDENCE：证据不足，不调用模型
403：未授权 / 未 READY / 已失活
DEGRADED：生成或引用门禁失败，保留已授权证据卡
```

**Speaker notes**
“owner/READY 校验发生在检索前，候选身份重验发生在检索后。没有有效 Evidence 时，不调用 Qwen，而是返回 NO_EVIDENCE。越权、未 READY 或已失活时返回 403，并且不复用旧 Evidence。若生成或 Citation 门禁失败，则进入 DEGRADED，只保留授权证据卡。右下角性能标记也必须保留：504.7 ms 高于 300 ms，当前是 deferred。”

`[Sources] docs/competition/visuals/03-online-rag-pipeline.spec.md; docs/competition/visuals/VISUAL_EVIDENCE_LEDGER.md; backend/rag/generation.py`

**Do-not-say boundary**
不要说“所有请求都会生成”“NO_EVIDENCE 等于权限错误”“Citation 合法就证明语义正确”“DEGRADED 是成功回答”“300 ms 已达成”。

## RAG-04

**Slide ID**
`RAG-04`

**Slide title**
一个 Claim 可连接多条证据，但 EvidenceSet 只审计、不自动裁决

**Single takeaway**
冻结真实场景观察到 `1 Claim → 2 Citations → 2 Chunks`；系统可记录确定性审计状态，却不把它包装成人工语义真值或自动幻觉消除。

**Main visual**
全幅使用 [`06-multi-evidence.svg`](visuals/rendered/06-multi-evidence.svg)。保留顶部“脱敏结构示意”与“Windows Gate 已观测”双标签，以及底部 `EvidenceSet = AUDIT_ONLY` 边界。图前引入句：“Citation 不只服务展示；它把 Claim 与一个或多个请求内 Evidence 连接起来。”

**Supporting evidence**
[`comp-evidenceset-001.json`](../../machine/competition/scenarios/comp-evidenceset-001.json)、[`06-multi-evidence.spec.md`](visuals/06-multi-evidence.spec.md)、视觉账本 `06-E01`～`06-E13`。

**On-slide text**

```text
Windows Gate 已观测
1 Claim → 2 Citations → 2 Chunks

EvidenceSet = AUDIT_ONLY
审计，不自动裁决
```

**Speaker notes**
“多证据不是把两段文字拼在一起。生成层先输出结构化 Claim 和 citation_ids；Citation 再解析到请求内授权 Evidence。EvidenceSet 检查 owner、活动版本、Chunk 身份，以及数字、单位、比较、限定和冲突。图中的 Claim 文本和 Chunk α/β 是脱敏结构示意；真实运行证明的是绑定结构。没有人工 pair-level Gold，也没有新 Judge，更不会自动删除 Claim。”

`[Sources] machine/competition/scenarios/comp-evidenceset-001.json; docs/competition/visuals/06-multi-evidence.spec.md; docs/competition/visuals/VISUAL_EVIDENCE_LEDGER.md`

**Do-not-say boundary**
不要说“图中文字是 Windows 逐字回答”“Chunk α/β 是真实原文”“EvidenceSet 100% 判真”“自动消除幻觉”“自动删 Claim、重写 Answer 或重新检索”。

## RAG-05

**Slide ID**
`RAG-05`

**Slide title**
三个 Golden Scenario 分别证明：能回答、能审计、也能正确拒绝

**Single takeaway**
冻结 Gate 以三个互补场景覆盖 evidence-grounded QA、multi-evidence audit 与 DELETE 后 fail-closed；`3/3 PASS` 只代表这三个场景。

**Main visual**
采用单一水平时间线，不使用密集 UI 卡片：

```text
COMP-QA-001
Evidence QA
COMPLETED · 3 Evidence · page/chunk trace
        →
COMP-EVIDENCESET-001
1 Claim → 2 Citations → 2 Chunks · AUDIT_ONLY
        →
COMP-FAIL-CLOSED-001
DELETE → cleanup 3/3 → 403 · Evidence 0
```

不展示私有问题、完整 Answer、完整 Chunk 或 PDF。

**Supporting evidence**
三个 scenario dossier、[`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json) 与 [`RAG_GOLDEN_SCENARIO_CARDS.md`](RAG_GOLDEN_SCENARIO_CARDS.md)。

**On-slide text**

```text
3 / 3 PASS
仅限冻结 Competition 三场景

能回答：Citation / Evidence / 页码身份通过
能审计：真实多证据绑定，AUDIT_ONLY
能拒绝：403 · Evidence 0 · no stale reuse
```

**Speaker notes**
“第一个场景证明 grounded Answer 与位置追踪；第二个场景证明一个真实生成 Claim 可以引用多个 Chunk；第三个场景在同一隔离生命周期中 DELETE 文档，再请求时返回 403，并证明三路 cleanup 与 no-stale Evidence。这里的 3/3 不是准确率，而是三个事先冻结的比赛场景全部通过。”

`[Sources] machine/competition/scenarios/comp-qa-001.json; machine/competition/scenarios/comp-evidenceset-001.json; machine/competition/scenarios/comp-fail-closed-001.json; machine/competition/rag_competition_baseline.json`

**Do-not-say boundary**
不要展示私有原题或完整 Evidence；不要把 3/3 说成 100% 准确率；不要把 Fail-Closed 外推为覆盖全部安全威胁；不要把 `AUDIT_ONLY` 说成自动裁决。

## RAG-06

**Slide ID**
`RAG-06`

**Slide title**
真实 Gate、负向实验和未达成指标共同决定技术路线

**Single takeaway**
冻结 baseline 由 Windows 真实复现、Citation/回放门禁、Reranker 证伪结果与 clean-checkout CI 共同支撑；性能债和阶段边界保持可见。

**Main visual**
全幅使用 [`08-key-evaluation-results.svg`](visuals/rendered/08-key-evaluation-results.svg)。不裁掉底部 limitation rail、provenance 与 `3/3`/`0/3` 限定。图前引入句：“冻结 baseline 不只由成功结果构成；失败实验和未达成指标也进入决策。”

**Supporting evidence**
[`08-key-evaluation-results.spec.md`](visuals/08-key-evaluation-results.spec.md)、视觉账本 `08-E01`～`08-E16`、两个 fixed reranker screening gate 与 frozen baseline。

**On-slide text**

```text
3/3 frozen scenarios PASS
Top-20 0/3 · Top-50 0/3
make test PASS · clean-checkout errors 14→0

combined P95 ≈ 504.7 ms > 300 ms
未达成 / deferred
```

**Speaker notes**
“三个场景在 Windows 上真实复现通过；两个真实问题各返回 3 Evidence，Citation 身份和回放门禁通过。另一方面，同一固定 BGE Reranker 在 Top-20 与 Top-50 都没有恢复冻结三条排序失败，因此停止 Phase 3 排序优化并保留默认 RRF。精确 submission head 的 clean checkout 在 Ubuntu/Python 上 make test PASS；14→0 只指 runtime/path errors。性能债没有隐藏：504.7 ms 仍高于 300 ms。”

`[Sources] docs/competition/visuals/08-key-evaluation-results.spec.md; docs/competition/visuals/VISUAL_EVIDENCE_LEDGER.md; machine/competition/rag_competition_baseline.json; machine/phase3_fixed_reranker_screening_gate.json; machine/phase3_fixed_reranker_top50_screening_gate.json`

**Do-not-say boundary**
不要说“Windows 复现了 fd5a517”“3/3 是准确率 100%”“0/3 否定所有 Reranker”“14→0 是全部缺陷清零”“300 ms 已达成”“Phase 3/4 已完成”“production ready”。

## Figure placement summary

| Figure | PPT placement | Introduced by | What the audience should notice |
|---|---|---|---|
| `01-system-architecture.svg` | `RAG-02` 全幅主图 | READY 是入口，Citation 与 cleanup 是两类终点 | 默认 RRF、Top-20/60/Top-3、Qwen、AUDIT_ONLY、DELETE→403 |
| `03-online-rag-pipeline.svg` | `RAG-03` 全幅主图 | 架构完整不代表每次都回答 | `403 ≠ NO_EVIDENCE ≠ DEGRADED`，无证据不调用模型 |
| `06-multi-evidence.svg` | `RAG-04` 全幅主图 | Citation 把 Claim 连到多条请求内 Evidence | 1→2→2 与“审计，不自动裁决”并列出现 |
| `08-key-evaluation-results.svg` | `RAG-06` 全幅收束图 | 成功、证伪、可复现与限制共同决定路线 | 3/3 范围、两个 0/3、14→0 限定、504.7>300 与三提交谱系 |
