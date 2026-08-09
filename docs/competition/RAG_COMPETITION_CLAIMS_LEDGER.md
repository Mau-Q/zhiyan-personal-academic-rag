# RAG Competition Claims Ledger

用途：约束 PPT、技术报告、Demo 与答辩中可以说什么、证据强度是什么、必须保留哪些限定语。`Allowed usage=FORBIDDEN` 的行是明确禁止或当前不受支持的表述，不得为了文案简洁删掉否定词。

证据强度枚举：`PROVEN_REAL_RUN`、`FROZEN_BASELINE`、`PROVEN_CI`、`HISTORICAL_GATE`、`SCREENING_RESULT`、`KNOWN_LIMITATION`、`DESIGN_FACT`、`PENDING_USER_VALIDATION`。

## Allowed claims

| Claim ID | Competition wording | Evidence | Strength | Allowed usage | Required qualifier |
|---|---|---|---|---|---|
| RAG-A01 | `RAG_COMPETITION_BASELINE_V1` 已冻结，Competition RAG owner scope 为 `DONE_ENOUGH`。 | [`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json) lines 2–6 | FROZEN_BASELINE | PPT / 报告 / Demo / 答辩 | 只表示当前 Competition RAG 责任范围收口，不表示项目全部完成 |
| RAG-A02 | 系统以 PostgreSQL 管理 owner、文档版本、生命周期与 Chunk 快照事实。 | [`REQUIREMENTS_TRACEABILITY.md`](../REQUIREMENTS_TRACEABILITY.md) SR-02；视觉账本 `01-E02`～`01-E05` | DESIGN_FACT | PPT / 报告 / 答辩 | 不声称 OCR、正式 MinIO 或生产运维完成 |
| RAG-A03 | 解析、Chunk、Elasticsearch 与 Milvus 全部就绪且版本活动时才进入 `READY`。 | 视觉账本 `01-E03`；生命周期合同 | DESIGN_FACT | PPT / 报告 / Demo | READY 不等于文件上传成功 |
| RAG-A04 | 服务端 `owner ACL` 与 READY 共同约束可见知识范围，候选检索后还会重验身份。 | 视觉账本 `01-E04`～`01-E05`、`03-E01`～`03-E06` | DESIGN_FACT | PPT / 报告 / Demo / 答辩 | 客户端只能收窄范围，不能提供可信 ACL 结论 |
| RAG-A05 | 在线召回使用 Elasticsearch/BM25 与 Milvus/BGE-M3 两个并行通道。 | [`rag-competition-pack-v1.json`](../../machine/competition/rag-competition-pack-v1.json) lines 29–45；视觉账本 `01-E06`～`01-E08` | FROZEN_BASELINE | PPT / 报告 / Demo | 不把双路存在表述为对所有数据均优于单路 |
| RAG-A06 | 冻结检索参数为每路 `candidate Top-20`、`RRF k=60`、`Evidence Top-3`。 | [`rag-competition-pack-v1.json`](../../machine/competition/rag-competition-pack-v1.json) lines 41–45 | FROZEN_BASELINE | PPT / 报告 / Demo / 答辩 | 指当前冻结默认路径 |
| RAG-A07 | 默认使用 RRF 按名次融合，Reranker 为 `OFF` / 可选非默认。 | [`rag-competition-pack-v1.json`](../../machine/competition/rag-competition-pack-v1.json) lines 41–51 | FROZEN_BASELINE | PPT / 报告 / Demo / 答辩 | 不说 Reranker 已默认在线启用 |
| RAG-A08 | 真实生成模型为 Qwen3 14B，Prompt identity 为 `academic-evidence-answer-v1`，`think=false`。 | [`rag-competition-pack-v1.json`](../../machine/competition/rag-competition-pack-v1.json) lines 17–27 | FROZEN_BASELINE | PPT / 报告 / Demo | 当前冻结模型/Prompt 配置，不外推其他模型 |
| RAG-A09 | Qwen 只消费本次请求内已授权 Evidence，并输出结构化 Claim、Answer 与 Citation。 | 视觉账本 `01-E13`、`03-E10`～`03-E13` | DESIGN_FACT | PPT / 报告 / Demo | 只说明上下文与合同约束，不等于语义永远正确 |
| RAG-A10 | Citation 可映射到 Evidence 的 document、page、chunk、version 身份。 | 视觉账本 `01-E14`、`03-E13` | DESIGN_FACT | PPT / 报告 / Demo / 答辩 | Citation 身份合法不替代人工语义判断 |
| RAG-A11 | 当前授权范围没有有效 Evidence 时返回 `NO_EVIDENCE`，且不调用真实生成模型。 | 视觉账本 `03-E08`～`03-E09` | DESIGN_FACT | PPT / 报告 / Demo / 答辩 | 不把 `NO_EVIDENCE` 与 403 混同 |
| RAG-A12 | 未授权、未 READY、已失活或范围无法证明时返回 `403 RAG_FORBIDDEN_SCOPE`。 | 视觉账本 `03-E02`、`03-E14` | DESIGN_FACT | PPT / 报告 / Demo | 只约束已有 owner/READY/生命周期合同，不外推所有安全威胁 |
| RAG-A13 | 生成或 Citation 门禁失败时返回 `DEGRADED` 并保留已授权证据卡。 | 视觉账本 `03-E12` | DESIGN_FACT | 报告 / 答辩；PPT 可精简 | `DEGRADED` 不是成功生成 |
| RAG-A14 | 一个 Claim 可以绑定一个或多个请求内 Citation/Evidence。 | 视觉账本 `06-E01`、`06-E03` | DESIGN_FACT | PPT / 报告 / Demo | 审计不新增检索、不修改 RRF 分数 |
| RAG-A15 | Windows 冻结场景已观测 `1 Claim → 2 Citations → 2 Chunks`。 | [`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json) lines 37–45；视觉账本 `06-E04`～`06-E05` | PROVEN_REAL_RUN | PPT / 报告 / Demo / 答辩 | 2+2 是脱敏结构表达，不公开私有 ID/正文 |
| RAG-A16 | EvidenceSet 执行身份与数字、单位、比较、限定、核心重合、冲突等确定性审计。 | 视觉账本 `06-E06`～`06-E09` | DESIGN_FACT | PPT / 报告 / Demo / 答辩 | 这是确定性检查，不是通用语义蕴含 |
| RAG-A17 | EvidenceSet 模式为 `AUDIT_ONLY`：审计，不自动裁决。 | [`rag-competition-pack-v1.json`](../../machine/competition/rag-competition-pack-v1.json) lines 53–57；视觉账本 `06-E11`～`06-E13` | FROZEN_BASELINE | PPT / 报告 / Demo / 答辩 | `human semantic Gold=false`、`new Judge=false`、不自动删除 Claim |
| RAG-A18 | Windows 真实复现的三个冻结 Competition 场景为 `3/3 PASS`。 | [`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json) lines 37–45 | PROVEN_REAL_RUN | PPT / 报告 / Demo / 答辩 | 仅指恰好三个冻结场景，不是准确率 100% |
| RAG-A19 | 两个真实问题均 `COMPLETED`，每题返回 3 条 Evidence，Citation/Evidence/页码身份与回放门禁通过。 | [`RAG_COMPETITION_HANDOFF_V1.md`](RAG_COMPETITION_HANDOFF_V1.md) lines 82–96 | PROVEN_REAL_RUN | PPT / 报告 / Demo | byte-stable replay 只限本次两个问题的观察 |
| RAG-A20 | DELETE 后 cleanup `3/3`、runtime snapshot cleanup、inactive visibility 与 403 通过，Evidence 为 0，未复用 stale Evidence。 | [`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json) lines 47–54；[`competition.py`](../../backend/validation/competition.py) lines 244–284 | PROVEN_REAL_RUN | PPT / 报告 / Demo / 答辩 | 只证明已有 fail-closed 生命周期场景 |
| RAG-A21 | Fixed BGE Reranker Top-20 frozen screening 为 `0/3 bilateral Top-3 recovery`。 | [`phase3_fixed_reranker_screening_gate.json`](../../machine/phase3_fixed_reranker_screening_gate.json) | SCREENING_RESULT | PPT / 报告 / 答辩 | 只适用于冻结失败集与当前 fixed reranker family |
| RAG-A22 | 同一 Fixed BGE Reranker Top-50 exposure 仍为 `0/3 bilateral Top-3 recovery`。 | [`phase3_fixed_reranker_top50_screening_gate.json`](../../machine/phase3_fixed_reranker_top50_screening_gate.json) | SCREENING_RESULT | PPT / 报告 / 答辩 | 扩大 exposure 未恢复这三条，不否定全部方法 |
| RAG-A23 | 依据两个 0/3 结果，当前保留默认 RRF，Phase 3 retrieval/ranking optimization `STOP`。 | [`PRODUCT_DECISIONS.md`](../PRODUCT_DECISIONS.md) PD-071 | SCREENING_RESULT | PPT / 报告 / 答辩 | Phase 3 仍为 `PARTIAL / NO_PROMOTION`，不是完成 |
| RAG-A24 | GitHub clean checkout 在精确 `fd5a517`、Ubuntu 24.04 / CPython 3.11.15 上 `make test PASS`。 | [`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json) lines 55–64 | PROVEN_CI | PPT / 报告 / 答辩 | 这是 clean-checkout CI，不替代 Windows 真实运行 |
| RAG-A25 | historical clean-checkout runtime/path errors 从 14 降为 0。 | [`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json) lines 55–64 | PROVEN_CI | PPT / 报告 | 不是全部产品缺陷清零 |
| RAG-A26 | Windows 复现源为 `d775dab`，submission head 为 `fd5a517`，二者 runtime equivalence 为 PASS。 | [`RAG_COMPETITION_HANDOFF_V1.md`](RAG_COMPETITION_HANDOFF_V1.md) lines 109–139 | FROZEN_BASELINE | PPT 脚注 / 报告 / 答辩 | 不得写成“Windows 复现了 fd5a517” |
| RAG-A27 | combined P95 约 `504.7 ms`，`300 ms` 目标未达成、deferred。 | [`CURRENT_PHASE.md`](../CURRENT_PHASE.md)；视觉账本 `08-E14` | KNOWN_LIMITATION | PPT / 报告 / 答辩 | 必须同时展示实际值、目标与未达成状态 |
| RAG-A28 | Phase 3 为 `PARTIAL / NO_PROMOTION`，Phase 4 为 `PARTIAL / AUDIT_ONLY`。 | [`rag_competition_baseline.json`](../../machine/competition/rag_competition_baseline.json) lines 71–75 | KNOWN_LIMITATION | PPT / 报告 / 答辩 | Competition freeze 未改写阶段完成度 |
| RAG-A29 | 800–1500 条正式独立 Acceptance 未完成，不能声称 production ready。 | [`REQUIREMENTS_TRACEABILITY.md`](../REQUIREMENTS_TRACEABILITY.md) SR-11；[`RAG_COMPETITION_HANDOFF_V1.md`](RAG_COMPETITION_HANDOFF_V1.md) lines 141–143 | KNOWN_LIMITATION | PPT / 报告 / 答辩 | 不用已有 3 场景或 175/500 资产替代正式 Acceptance |
| RAG-A30 | 真实用户评价当前为 `PENDING_REAL_USER_EVALUATION`。 | [`COMPETITION_HUMAN_EVALUATION_V1.md`](COMPETITION_HUMAN_EVALUATION_V1.md)；仓库中无已完成双评审结果 | PENDING_USER_VALIDATION | 报告 / PPT 占位 | 使用 `[待真实用户评价完成后填入]`，不得填 0 或编造结果 |
| RAG-A31 | 历史 3 文档 9 问题真实 Qwen Gate 已通过。 | [`REQUIREMENTS_TRACEABILITY.md`](../REQUIREMENTS_TRACEABILITY.md) lines 68–70；[`rag-competition-pack-v1.json`](../../machine/competition/rag-competition-pack-v1.json) lines 65–77 | HISTORICAL_GATE | 技术报告背景；答辩补充 | 明确为历史 Gate，不替代当前 Competition reproduction |

## Forbidden / unsupported claims

| Claim ID | Competition wording | Evidence | Strength | Allowed usage | Required qualifier |
|---|---|---|---|---|---|
| RAG-F01 | “EvidenceSet 自动消除幻觉。” | EvidenceSet 明确 `AUDIT_ONLY`；无人工 Gold、无新 Judge | FROZEN_BASELINE | **FORBIDDEN** | 可改为“帮助审计 Claim–Evidence 绑定，不自动裁决” |
| RAG-F02 | “系统自动判定 Claim 的语义真伪或保证 100% 事实正确。” | [`rag-competition-pack-v1.json`](../../machine/competition/rag-competition-pack-v1.json) lines 53–57 | KNOWN_LIMITATION | **FORBIDDEN** | 确定性检查不等于人工语义判断 |
| RAG-F03 | “审计失败会自动删除 Claim、重写 Answer 或重新检索。” | `automatic_claim_deletion=false`；Competition `allow_adjacent=false` | FROZEN_BASELINE | **FORBIDDEN** | 默认仅记录审计状态 |
| RAG-F04 | “Reranker 已默认在线启用。” | frozen default 为 `Reranker OFF` | FROZEN_BASELINE | **FORBIDDEN** | 可说“可选非默认组件” |
| RAG-F05 | “Top-50 证明 Reranker 更优。” | Top-50 screening 为 `0/3` | SCREENING_RESULT | **FORBIDDEN** | 准确表述为“扩大 exposure 仍未恢复冻结案例” |
| RAG-F06 | “0/3 证明所有 Reranker 或所有 ranking 方法无效。” | PD-071 的方法类别边界 | SCREENING_RESULT | **FORBIDDEN** | 只削弱当前 fixed reranker family 在冻结失败集上的依据 |
| RAG-F07 | “三个场景 3/3 PASS，所以系统准确率 100%。” | 视觉账本 `08-E02` 的限定 | PROVEN_REAL_RUN | **FORBIDDEN** | 3/3 仅指恰好三个冻结场景 |
| RAG-F08 | “Windows 复现了 submission head fd5a517。” | 正确谱系为 Windows `d775dab`、submission `fd5a517` | FROZEN_BASELINE | **FORBIDDEN** | 必须分开写两个身份与 runtime equivalence PASS |
| RAG-F09 | “byte-stable replay 是所有自然语言生成的永久保证。” | 本次仅两个问题观察为 true | PROVEN_REAL_RUN | **FORBIDDEN** | 限定为本次两个真实问题 |
| RAG-F10 | “clean-checkout errors 14→0 表示全部产品缺陷清零。” | 该字段仅为 historical runtime/path errors | PROVEN_CI | **FORBIDDEN** | 必须带 `clean-checkout runtime/path` 限定 |
| RAG-F11 | “系统已经达到 300 ms。” | combined P95 约 504.7 ms | KNOWN_LIMITATION | **FORBIDDEN** | 必须写“未达成 / deferred” |
| RAG-F12 | “Phase 3 与 Phase 4 已全部完成。” | Phase 3/4 均为 `PARTIAL` | KNOWN_LIMITATION | **FORBIDDEN** | Phase 3 workstream STOP 不等于阶段完成；Phase 4 仅审计核心完成 |
| RAG-F13 | “系统 production ready / SLO 已验收。” | 300 ms、正式 Acceptance、生产运维均未完成 | KNOWN_LIMITATION | **FORBIDDEN** | 可说“冻结 Competition RAG Core 已完成当前 owner scope” |
| RAG-F14 | “OCR、正式 MinIO、生产监控、Agent 编排、会话记忆或在线 NLI Judge 已完成。” | [`REQUIREMENTS_TRACEABILITY.md`](../REQUIREMENTS_TRACEABILITY.md) 的缺口与视觉账本禁止来源 | KNOWN_LIMITATION | **FORBIDDEN** | 不在冻结 baseline 中 |
| RAG-F15 | “403 证明系统覆盖所有安全威胁。” | `COMP-FAIL-CLOSED-001` 限定既有生命周期 | PROVEN_REAL_RUN | **FORBIDDEN** | 只证明 owner/READY/DELETE fail-closed 场景 |
| RAG-F16 | “Citation 门禁通过就证明 Answer 语义正确。” | Citation 只证明请求内映射与身份位置合法 | DESIGN_FACT | **FORBIDDEN** | 语义正确性仍需人工判断 |
| RAG-F17 | “图 06 的 Claim、Chunk α/β 是 Windows 逐字输出或论文原文。” | 图 06 明确为脱敏结构示意 | FROZEN_BASELINE | **FORBIDDEN** | 只可说绑定结构由真实 Gate 观测 |
| RAG-F18 | “已有 N 位满意用户、X% 准确率、节省 Y% 时间、acceptance score 或用户引语。” | 无真实用户评价结果 | PENDING_USER_VALIDATION | **FORBIDDEN** | 评价完成前使用 `[待真实用户评价完成后填入]` |
| RAG-F19 | “Cohen's kappa 已达到某数值。” | 仅有评价协议，无已完成双评审结果；3 场景下也可能不可计算 | PENDING_USER_VALIDATION | **FORBIDDEN** | 未计算时写 `PENDING`；条件不满足时写 `NOT_COMPUTABLE` |

## Integration checklist

在任何最终 PPT、技术报告、Demo 脚本或答辩提纲进入交付前，逐项确认：

- `Reranker default = NO`；
- `EvidenceSet = AUDIT_ONLY`；
- `300 ms achieved = NO`；
- `3/3` 只指冻结的三个 Competition 场景；
- `Production ready = NO`；
- `real-user evaluation = PENDING_REAL_USER_EVALUATION`；
- Windows `d775dab`、submission `fd5a517`、authority `038df52` 没有合并；
- 图 06 的 1→2→2 被标记为脱敏结构，不公开私有内容；
- `14→0` 带有 clean-checkout runtime/path 限定；
- 没有编造用户结果、benchmark、业务收益或生产成熟度。
