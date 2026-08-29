# Competition RAG Visual Evidence Ledger

本账本只服务于 `01-system-architecture`、`03-online-rag-pipeline`、
`06-multi-evidence`、`08-key-evaluation-results` 四张图。图中每一项实质性事实都必须
引用本账本行号；短标题、分组名和“问题/回答”等纯结构词不单独构成事实声明。

## 冻结身份与解释规则

- baseline：`RAG_COMPETITION_BASELINE_V1 / FROZEN / DONE_ENOUGH`；
- Windows 真实复现源：`d775dab706c2a05d5b838f644b77b257961a4549`；
- submission repository head：`fd5a517b56ba619ca461e262a5ea1a8ac8b9ac7b`；
- 本轮开始时冻结权威 closeout commit：`038df52ad1fe453420b43cd1dcf9b9e117f7277c`；
- Run ID：`competition_v1_20260809_01`；
- 正确谱系表述：Windows 复现 `d775dab`，`fd5a517` 是 submission repository
  head，二者 runtime equivalence 为 `PASS`。不得写成 Windows 复现 `fd5a517`。

“Safe for competition”中的 `YES_WITH_BOUNDARY` 表示该事实可展示，但必须同时保留
该行给出的限制语；不得只取有利半句。

## 01-system-architecture

| ID | Visual element / claim | Exact wording | Source file | Source location | Evidence class | Safe for competition |
|---|---|---|---|---|---|---|
| 01-E01 | baseline 身份 | `RAG_COMPETITION_BASELINE_V1 · FROZEN` | `machine/competition/rag_competition_baseline.json` | lines 2–6 | FROZEN_BASELINE | YES |
| 01-E02 | 可信来源、版本和 owner 事实源 | `获准 PDF → Chunk → PostgreSQL owner / 版本 / 快照` | `docs/REQUIREMENTS_TRACEABILITY.md` | lines 37–38, 56–57 | ARCHITECTURE_CONTRACT | YES_WITH_BOUNDARY：OCR 未完成 |
| 01-E03 | READY 条件 | `解析、Chunk、ES、Milvus 全部就绪后进入 READY` | `contracts/schemas/document-version-lifecycle-v1.schema.json` | lines 41–43, 49–56, 65–84 | ARCHITECTURE_CONTRACT | YES |
| 01-E04 | owner / ACL | `owner ACL / 授权范围` | `contracts/schemas/authorized-scope-v1.schema.json` | lines 7–23 | ARCHITECTURE_CONTRACT | YES |
| 01-E05 | 在线 READY 路由 | `PostgreSQL READY 版本解析与重验` | `backend/retrieval/online.py` | lines 199–264, 266–299, 505–519 | ARCHITECTURE_CONTRACT | YES |
| 01-E06 | Elasticsearch 通道 | `Elasticsearch · BM25 词项检索` | `machine/competition/rag-competition-pack-v1.json`; `backend/retrieval/online.py` | lines 35–45; lines 438–468 | FROZEN_BASELINE / ARCHITECTURE_CONTRACT | YES |
| 01-E07 | Milvus 通道 | `Milvus · BGE-M3 向量检索` | `machine/competition/rag-competition-pack-v1.json`; `backend/retrieval/online.py` | lines 29–45; lines 442–477, 637–657 | FROZEN_BASELINE / ARCHITECTURE_CONTRACT | YES |
| 01-E08 | 并行检索 | `ES 与 Milvus 并行召回` | `backend/retrieval/online.py` | lines 411–502 | ARCHITECTURE_CONTRACT | YES |
| 01-E09 | 冻结检索参数 | `每路候选 Top-20 · RRF k=60 · 生成证据 Top-3` | `machine/competition/rag-competition-pack-v1.json` | lines 41–45 | FROZEN_BASELINE | YES |
| 01-E10 | RRF 融合 | `按名次做 RRF 融合` | `backend/retrieval/online.py` | lines 713–753 | ARCHITECTURE_CONTRACT | YES |
| 01-E11 | 默认策略 | `默认 RRF；Reranker OFF` | `machine/competition/rag-competition-pack-v1.json` | lines 41–51 | FROZEN_BASELINE | YES_WITH_BOUNDARY：Reranker 仅可选非默认 |
| 01-E12 | 生成模型与 Prompt | `Qwen3 14B · academic-evidence-answer-v1 · think=false` | `machine/competition/rag-competition-pack-v1.json` | lines 17–27 | FROZEN_BASELINE | YES |
| 01-E13 | 证据约束生成 | `问题 + 已授权 Evidence → 结构化 Claim → Answer` | `backend/rag/generation.py` | lines 23–30, 39–63, 251–294 | ARCHITECTURE_CONTRACT | YES |
| 01-E14 | Citation / Evidence 身份 | `Citation → Evidence → document / page / chunk / version` | `contracts/schemas/rag-answer-v1.schema.json` | lines 44–78 | ARCHITECTURE_CONTRACT | YES |
| 01-E15 | EvidenceSet | `Claim → EvidenceSet · AUDIT_ONLY` | `machine/phase4_multi_evidence_set_gate.json` | lines 22–59 | ARCHITECTURE_CONTRACT | YES_WITH_BOUNDARY：非语义 Judge |
| 01-E16 | 生命周期 | `DELETE / INACTIVE → PostgreSQL、Elasticsearch、Milvus / runtime snapshot 清理` | `docs/competition/RAG_COMPETITION_HANDOFF_V1.md` | lines 157–170 | REAL_WINDOWS_REPRODUCTION / ARCHITECTURE_CONTRACT | YES |
| 01-E17 | 失败关闭 | `失活后 403 RAG_FORBIDDEN_SCOPE；不复用 stale Evidence` | `machine/competition/rag_competition_baseline.json` | lines 47–54 | REAL_WINDOWS_REPRODUCTION | YES |
| 01-E18 | OCR 边界 | `OCR 未完成，不进入主架构完成态` | `docs/REQUIREMENTS_TRACEABILITY.md` | line 38 | KNOWN_LIMITATION | YES |

## 03-online-rag-pipeline

| ID | Visual element / claim | Exact wording | Source file | Source location | Evidence class | Safe for competition |
|---|---|---|---|---|---|---|
| 03-E01 | 问题与服务端 owner scope | `用户问题 → owner / scope 校验` | `backend/api/app.py` | lines 285–316 | ARCHITECTURE_CONTRACT | YES |
| 03-E02 | 未授权或未就绪 | `未授权 / 未就绪 / 无法验证 → 403 RAG_FORBIDDEN_SCOPE` | `backend/api/app.py` | lines 317–341 | ARCHITECTURE_CONTRACT | YES |
| 03-E03 | READY 解析 | `只解析 PostgreSQL READY 版本` | `backend/retrieval/online.py` | lines 199–264 | ARCHITECTURE_CONTRACT | YES |
| 03-E04 | 快照和版本一致性 | `加载 READY Chunk 快照并校验版本与 Chunk 唯一性` | `backend/retrieval/online.py` | lines 388–410 | ARCHITECTURE_CONTRACT | YES |
| 03-E05 | 双路并行 | `Elasticsearch BM25 ∥ Milvus / BGE-M3` | `backend/retrieval/online.py` | lines 411–502 | ARCHITECTURE_CONTRACT | YES |
| 03-E06 | 候选身份重验 | `候选必须匹配 owner / document / version / active` | `backend/retrieval/online.py` | lines 695–711 | ARCHITECTURE_CONTRACT | YES |
| 03-E07 | 融合与 Top-3 | `候选 Top-20 → RRF k=60 → Evidence Top-3` | `machine/competition/rag-competition-pack-v1.json`; `backend/retrieval/online.py` | lines 41–45; lines 713–753 | FROZEN_BASELINE / ARCHITECTURE_CONTRACT | YES |
| 03-E08 | 无证据拒答 | `无有效 Evidence → NO_EVIDENCE / 当前授权范围内证据不足` | `backend/rag/answer_builder.py` | lines 34–44 | ARCHITECTURE_CONTRACT | YES |
| 03-E09 | 无证据不调用模型 | `NO_EVIDENCE 时不调用真实生成模型` | `backend/rag/generation.py` | lines 425–447 | ARCHITECTURE_CONTRACT | YES |
| 03-E10 | Qwen 生成 | `Qwen3 14B 基于 Evidence 生成结构化 Claim` | `machine/competition/rag-competition-pack-v1.json`; `backend/rag/generation.py` | lines 17–27; lines 275–334 | FROZEN_BASELINE / ARCHITECTURE_CONTRACT | YES |
| 03-E11 | 引用门禁 | `引用编号必须落在本次 Evidence 内` | `backend/rag/generation.py` | lines 341–384, 401–413 | ARCHITECTURE_CONTRACT | YES |
| 03-E12 | 生成失败关闭 | `生成或引用门禁失败 → DEGRADED，保留已授权证据卡` | `backend/rag/generation.py` | lines 416–422, 448–489 | ARCHITECTURE_CONTRACT | YES |
| 03-E13 | 成功输出字段 | `Answer + Citation + Evidence（document / page / chunk / version）` | `contracts/schemas/rag-answer-v1.schema.json` | lines 7–35, 44–78 | ARCHITECTURE_CONTRACT | YES |
| 03-E14 | 已验证 403 | `DELETE 后 Answer API 403，stale Evidence reused=false` | `machine/competition/rag_competition_baseline.json` | lines 47–54 | REAL_WINDOWS_REPRODUCTION | YES |
| 03-E15 | 延迟边界 | `300 ms 目标未达成 / deferred` | `machine/competition/rag_competition_baseline.json` | lines 71–75 | KNOWN_LIMITATION | YES_WITH_BOUNDARY：不得画成已达标 |

## 06-multi-evidence

| ID | Visual element / claim | Exact wording | Source file | Source location | Evidence class | Safe for competition |
|---|---|---|---|---|---|---|
| 06-E01 | 结构化 Claim | `回答拆为可核验 Claim；每个 Claim 绑定一个或多个 citation_ids` | `backend/rag/generation.py` | lines 23–30, 39–63 | ARCHITECTURE_CONTRACT | YES |
| 06-E02 | 冻结概念例的三类答案点 | `内容感知 token surprisal；重复/连贯性缺口指标；尾部聚合` | `machine/competition/scenarios/comp-evidenceset-001.json` | lines 17–20 | FROZEN_BASELINE | YES_WITH_BOUNDARY：仅可作脱敏结构示意，不冒充逐字回答或原文引文 |
| 06-E03 | 真实多证据要求 | `至少 2 条 Evidence，至少 1 个多 Evidence Claim` | `machine/competition/scenarios/comp-evidenceset-001.json` | lines 26–33 | FROZEN_BASELINE | YES |
| 06-E04 | 真实多证据通过 | `COMP-EVIDENCESET-001 = PASS；multi_evidence_record = PASS` | `machine/competition/rag_competition_baseline.json` | lines 37–45 | REAL_WINDOWS_REPRODUCTION | YES |
| 06-E05 | 1 Claim → 2 Citation → 2 Chunk | `已观测：至少 1 个 Claim 绑定多条 Citation / 多个 Chunk` | `docs/competition/RAG_COMPETITION_HANDOFF_V1.md`; `machine/competition/scenarios/comp-evidenceset-001.json` | lines 125–128; lines 26–33 | REAL_WINDOWS_REPRODUCTION | YES_WITH_BOUNDARY：图中 2+2 为脱敏结构表达，不显示私有 ID/正文 |
| 06-E06 | 身份检查 | `owner、活动 document/version、Chunk 唯一身份、引用位置` | `machine/phase4_multi_evidence_set_gate.json` | lines 22–37 | ARCHITECTURE_CONTRACT | YES |
| 06-E07 | 确定性检查 | `数字、单位、比较对象、限定条件、关系、核心重合、同单位冲突` | `machine/phase4_multi_evidence_set_gate.json` | lines 38–46 | ARCHITECTURE_CONTRACT | YES |
| 06-E08 | 审计输出状态 | `SUPPORTED / PARTIAL / CONFLICT / INSUFFICIENT`（图内用短中文） | `machine/phase4_multi_evidence_set_gate.json` | lines 22–29 | ARCHITECTURE_CONTRACT | YES_WITH_BOUNDARY：是确定性状态，不是人工语义真值 |
| 06-E09 | 请求内审计 | `只审计已授权、请求内 Evidence；不读不改检索分数` | `backend/rag/claim_evidence.py` | lines 280–295 | ARCHITECTURE_CONTRACT | YES |
| 06-E10 | 邻块策略 | `最多加入 1 个同文档、同活动版本、双向邻接的请求内 Chunk` | `machine/phase4_multi_evidence_set_gate.json` | lines 47–54 | ARCHITECTURE_CONTRACT | YES_WITH_BOUNDARY：Competition 场景运行时 allow_adjacent=false |
| 06-E11 | 关键边界 | `EvidenceSet = AUDIT_ONLY；不自动删除 Claim` | `machine/phase4_multi_evidence_set_gate.json` | lines 55–59 | ARCHITECTURE_CONTRACT | YES |
| 06-E12 | 非人工 Gold / 无新 Judge | `human semantic Gold = false；new Judge = false` | `machine/competition/rag-competition-pack-v1.json` | lines 53–57 | FROZEN_BASELINE | YES |
| 06-E13 | 不自动裁决 | `审计，不自动裁决` | `docs/competition/COMPETITION_HUMAN_EVALUATION_V1.md` | lines 44–49 | KNOWN_LIMITATION | YES |

## 08-key-evaluation-results

| ID | Visual element / claim | Exact wording | Source file | Source location | Evidence class | Safe for competition |
|---|---|---|---|---|---|---|
| 08-E01 | Windows 复现身份 | `Windows 真实复现源：d775dab；Run ID：competition_v1_20260809_01` | `docs/competition/RAG_COMPETITION_HANDOFF_V1.md` | lines 82–87 | REAL_WINDOWS_REPRODUCTION | YES |
| 08-E02 | 三场景 | `冻结 Competition 场景 3/3 PASS` | `machine/competition/rag_competition_baseline.json` | lines 37–45 | REAL_WINDOWS_REPRODUCTION | YES |
| 08-E03 | 场景分项 | `Evidence QA PASS / Multi-Evidence Audit PASS / Fail-Closed PASS` | `machine/competition/rag_competition_baseline.json` | lines 37–45 | REAL_WINDOWS_REPRODUCTION | YES |
| 08-E04 | 两个真实问题 | `2 个真实问题 COMPLETED；每题 3 条 Evidence` | `docs/competition/RAG_COMPETITION_HANDOFF_V1.md` | lines 89–92 | REAL_WINDOWS_REPRODUCTION | YES |
| 08-E05 | 引用和回放 | `Citation / Evidence / 页码身份 PASS；generation replay 与 byte-stable replay PASS` | `docs/competition/RAG_COMPETITION_HANDOFF_V1.md` | lines 89–96 | REAL_WINDOWS_REPRODUCTION | YES |
| 08-E06 | 清理与 403 | `cleanup 3/3；inactive visibility PASS；403；no stale Evidence` | `machine/competition/rag_competition_baseline.json` | lines 47–54 | REAL_WINDOWS_REPRODUCTION | YES |
| 08-E07 | Top-20 screening | `固定 BGE Reranker Top-20：0/3 bilateral Top-3 recovery` | `machine/phase3_fixed_reranker_screening_gate.json` | lines 32–38, 63–75 | SCREENING_RESULT | YES_WITH_BOUNDARY：仅适用于冻结失败集 |
| 08-E08 | Top-50 screening | `固定 BGE Reranker Top-50：0/3 bilateral Top-3 recovery` | `machine/phase3_fixed_reranker_top50_screening_gate.json` | lines 39–48, 94–113 | SCREENING_RESULT | YES_WITH_BOUNDARY：仅适用于冻结失败集 |
| 08-E09 | 排序决策 | `SCREENING_WEAKENED → 保留默认 RRF → Phase 3 optimization STOP` | `docs/PRODUCT_DECISIONS.md` | line 75 | SCREENING_RESULT | YES_WITH_BOUNDARY：不否定所有 reranker / ranking 方法 |
| 08-E10 | clean checkout | `GitHub clean checkout · Ubuntu 24.04 · CPython 3.11.15 · make test PASS` | `machine/competition/rag_competition_baseline.json` | lines 55–64 | CLEAN_CHECKOUT_CI | YES |
| 08-E11 | 历史 clean-checkout 错误 | `14 → 0` | `machine/competition/rag_competition_baseline.json` | lines 55–64 | CLEAN_CHECKOUT_CI | YES_WITH_BOUNDARY：是 clean-checkout runtime/path errors，不是产品缺陷总数 |
| 08-E12 | submission head | `GitHub Core tests 的精确提交：fd5a517` | `machine/competition/rag_competition_baseline.json` | lines 55–61 | CLEAN_CHECKOUT_CI | YES |
| 08-E13 | 三提交谱系 | `Windows d775dab · submission fd5a517 · frozen authority 038df52` | `docs/competition/RAG_COMPETITION_HANDOFF_V1.md`; Git repository | lines 109–139; `git rev-parse HEAD` at task start | FROZEN_BASELINE | YES_WITH_BOUNDARY：不得合并身份 |
| 08-E14 | 性能债 | `combined P95 ≈ 504.7 ms；目标 300 ms；未达成 / deferred` | `docs/CURRENT_PHASE.md`; `machine/competition/rag_competition_baseline.json` | lines 174–177; lines 71–75 | KNOWN_LIMITATION | YES |
| 08-E15 | 阶段边界 | `Phase 3 = PARTIAL / NO_PROMOTION；Phase 4 = PARTIAL / AUDIT_ONLY` | `machine/competition/rag_competition_baseline.json` | lines 71–75 | KNOWN_LIMITATION | YES |
| 08-E16 | 正式验收与生产边界 | `800–1500 正式 Acceptance 未完成；不声称 production ready` | `docs/REQUIREMENTS_TRACEABILITY.md`; `docs/competition/RAG_COMPETITION_HANDOFF_V1.md` | line 46; lines 141–143 | KNOWN_LIMITATION | YES |

## 不得作为图中事实使用的来源

- `PROJECT_DOCUMENTATION_REVISED.md`：当前仓库不存在，不能引用；
- ignored `runtime/` 中的私有问题、完整 Answer、完整 Evidence/Chunk 或报告正文：不得
  为了图形完整性复制进仓库；
- Fixture/Fake 结构测试：不得替代 Windows 真实复现或 clean-checkout CI；
- 习惯性的 RAG 组件（Agent、会话记忆、在线 NLI Judge、生产监控、完整 OCR）：没有
  冻结证据，不得画入这四张图。
