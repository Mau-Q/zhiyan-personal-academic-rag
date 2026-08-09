# RAG Golden Scenario Demo Cards

使用边界：本文件恰好包含三个冻结 Competition 场景。历史私有问题、完整 Answer、完整 Evidence/Chunk 与 PDF 不进入仓库；展示问题为 tracked 文本或依据冻结答案点形成的脱敏展示版，不冒充私有原题逐字内容。

## Card 1 — `COMP-QA-001`

**Scenario**
`COMP-QA-001 / EVIDENCE_GROUNDED_QA / PASS`

**Purpose**
证明系统能基于当前 owner 已授权且处于 READY 的论文证据完成学术问答，并将 Answer 中的 Citation 解析到 Evidence 的文档、页码、Chunk 与版本身份。

**User-visible question**
脱敏展示问题：**“请解释论文中的 MAX-composite step-risk 操作，以及为什么最大值能保留局部尖锐失效而不是被平均稀释？”**

说明：该文字依据冻结 acceptable answer points 形成，**不是私有原题逐字内容**。私有原题仅以 source case ID `local3.answerable.tracer.max_risk` 与 question SHA-256 绑定。

**Expected proof**

- 回答定义 MAX-composite step-risk 操作；
- 说明 maximum 能保留 sharp localized breakdown，而不会被 averaging 稀释；
- `status=COMPLETED`；
- Citation 与 Evidence 均非空且请求内映射有效；
- Evidence 命中授权文档 `doc_arxiv_2602_11409` 的 page 4 位置合同；
- 不引入未由 Evidence 支持的公式、阈值、benchmark 或因果保证。

**Observed proof**

- 冻结场景结果：`PASS`；
- 真实 Answer 状态：`COMPLETED`；
- 返回 Evidence：3 条；
- Citation ID、Evidence 身份与页码定位：`PASS`；
- generation replay 与本次 byte-stable replay：`PASS`；
- 公开材料不展示真实 Chunk ID、完整 Answer 或 PDF 正文。

**What the judge should notice**
评委应从 Citation 继续看到 Evidence 的 page/chunk/version 身份，而不是只看到回答末尾的引用编号。该场景证明来源身份与位置门禁通过；回答语义正确性仍保留人工判断边界。

**Demo narration**
“这道题只访问当前 owner 已授权且处于 READY 的论文版本。系统先用 BM25 与 BGE-M3/Milvus 双路召回，再由 RRF 选择最多 3 条 Evidence。Qwen 的回答携带请求内 Citation。现在展开其中一条 Citation，可以继续定位到论文页码、Chunk 和版本。冻结 Gate 中该场景返回 3 条 Evidence，并通过 Citation/Evidence/页码身份与回放门禁。”

**Failure/claim boundary**

- 不说“Citation 验证等于答案语义必然正确”；
- 不展示或复述私有原题、完整 Answer、完整 Chunk/PDF；
- 不添加未声明的 averaging formula、threshold、benchmark result 或 causal guarantee；
- 不把一个场景 PASS 外推为全部学术问题准确率。

证据：[`comp-qa-001.json`](../../machine/competition/scenarios/comp-qa-001.json)、[`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json)、[`RAG_COMPETITION_HANDOFF_V1.md`](RAG_COMPETITION_HANDOFF_V1.md)。

## Card 2 — `COMP-EVIDENCESET-001`

**Scenario**
`COMP-EVIDENCESET-001 / MULTI_EVIDENCE_CLAIM_AUDIT / PASS`

**Purpose**
证明一个真实生成 Claim 可以同时绑定多个请求内 Citation/Evidence，并在不新增检索、不修改分数的前提下进入确定性 EvidenceSet 审计。

**User-visible question**
脱敏展示问题：**“请说明风险刻画中的内容感知 token surprisal、重复/连贯性缺口指标与尾部聚合如何共同出现。”**

说明：该文字依据冻结 acceptable answer points 形成，**不是私有原题逐字内容**。私有原题仅以 source case ID `local3.answerable.tracer.ingredients` 与 question SHA-256 绑定。

**Expected proof**

- 回答包含 content-aware token surprisal；
- 回答包含 repetition 与 coherence-gap 的 situational-awareness indicators；
- 回答包含 tail-focused aggregation；
- 至少返回 2 条 Evidence；
- 至少 1 个生成 Claim 绑定多条 Evidence；
- 授权位置合同覆盖 page 1–3；
- `evidence_set_mode=AUDIT_ONLY`。

**Observed proof**

- 冻结场景结果：`PASS`；
- 真实 Answer 状态：`COMPLETED`；
- 返回 Evidence：3 条；
- `multi_evidence_record=PASS`；
- 已观测脱敏结构：`1 Claim → 2 Citations → 2 Evidence/Chunks`；
- EvidenceSet 运行模式：`AUDIT_ONLY`。

**What the judge should notice**
重点不是“回答有两个引用”，而是同一个 Claim 明确分叉到两条 Citation，再解析到两个具有 page/chunk/version 身份的 Evidence。随后系统记录身份、数字/单位、比较、限定、核心重合和冲突等确定性检查结果；终点是审计记录，不是自动删除或重写。

**Demo narration**
“这里选择回答中的一个多证据 Claim。它不是只带一个泛化来源，而是同时绑定 Citation 1 和 Citation 2；两条 Citation 分别解析到两个授权 Chunk。EvidenceSet 随后检查 owner、活动版本、Chunk 身份以及可确定性检查的支持条件。最重要的边界是：这套能力是 `AUDIT_ONLY`——审计，不自动裁决。”

**Failure/claim boundary**

- 不说“EvidenceSet 自动消除幻觉”“100% 事实正确”或“自动判断语义真伪”；
- 不把脱敏 Claim/Chunk α/β 当成 Windows 逐字 Answer、真实 Chunk ID 或原文引文；
- 不说存在人工 semantic Gold 或新 NLI/LLM Judge；
- 不说审计失败会自动删除 Claim、重写 Answer、重新检索；
- Competition 场景使用 `allow_adjacent=false`，不声称本次运行加入了邻块。

证据：[`comp-evidenceset-001.json`](../../machine/competition/scenarios/comp-evidenceset-001.json)、[`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json)、[`06-multi-evidence.svg`](visuals/rendered/06-multi-evidence.svg)。

## Card 3 — `COMP-FAIL-CLOSED-001`

**Scenario**
`COMP-FAIL-CLOSED-001 / FAIL_CLOSED_INACTIVE / PASS`

**Purpose**
证明同一隔离运行中的文档在 DELETE/INACTIVE 后不能继续用于回答，已返回过的 Evidence、Citation、Answer 或 runtime snapshot 也不得作为 stale 内容复用。

**User-visible question**
Tracked display text：**`This deleted document must remain unavailable.`**
中文说明：**“这篇已删除文档必须保持不可用。”**

**Expected proof**

- `actual_refusal=true`；
- Answer API 返回 `403 RAG_FORBIDDEN_SCOPE`；
- returned Evidence count = 0；
- cleanup jobs succeeded = 3；
- runtime snapshot cleanup 与 inactive visibility 均已证明；
- `stale_evidence_reused=false`。

**Observed proof**

- 冻结场景结果：`PASS`；
- `actual_refusal=true`；
- HTTP status：`403`；
- error code：`RAG_FORBIDDEN_SCOPE`；
- Evidence returned：`0`；
- `stale_evidence_reused=false`；
- Elasticsearch、Milvus、runtime snapshot cleanup：`3/3 PASS`；
- inactive visibility：`PASS`。

**What the judge should notice**
系统不是只在“能回答”时表现正确。文档失活后，即使前两个场景已经成功产生过 Answer 和 Evidence，后续请求也不会复用旧证据，而是返回 403。失败关闭与物理 cleanup 同时被记录，且 cleanup 不能重新激活事实源。

**Demo narration**
“现在在同一隔离生命周期中删除刚才使用的文档。系统先将版本置为 INACTIVE，再完成 Elasticsearch、Milvus 和 runtime snapshot 三路 cleanup。我们再次请求这份知识，Answer API 返回 `403 RAG_FORBIDDEN_SCOPE`，Evidence 为 0，旧 Evidence 没有被复用。这个场景说明系统不仅能回答，也能在不应该回答时正确拒绝。”

**Failure/claim boundary**

- cleanup 任一环节、snapshot cleanup 或 inactive visibility 未证明时，不得宣布 PASS；
- 不把该场景外推为覆盖所有安全威胁、所有删除竞态或完整生产安全验收；
- 不说 403 与 `NO_EVIDENCE` 相同；前者是范围不可授权/不可证明，后者是合法范围内证据不足；
- 不展示之前的完整 Answer、Evidence 或私有文档内容。

证据：[`comp-fail-closed-001.json`](../../machine/competition/scenarios/comp-fail-closed-001.json)、[`competition.py`](../../backend/validation/competition.py)、[`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json)。
