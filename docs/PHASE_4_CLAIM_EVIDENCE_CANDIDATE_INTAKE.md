# Phase 4 Claim–Evidence 候选二审接收 Gate

## 结论

成员 B 的 PR #15 三份候选资产已按原始 Git Blob 完整接收，并与冻结私有
`dev` 输入逐项对账。接收 Gate 为
`PASS / CANDIDATE_INTAKE_PASS_HARD_ENFORCEMENT_DISABLED`，但候选标签没有
晋升为人工真值。

成员 B 的交付明确标识为 `member-b-ai-assisted`，PR 正文也将其限定为
“供后续人工裁决的候选标注”。因此本 Gate 不计算 Precision、负例拒绝率或
人工一致率，也不把 30 题写成独立人工金标。

## 接收与对账结果

- 失败归因覆盖 105 个唯一 `dev` 问题，45 条 `NONE`，60 条记录系统候选
  失败类型；这些失败类型不表示 60 条数据本身错误；
- Claim–Evidence 覆盖 30 个唯一 `dev` 问题：
  `SUPPORTED=21 / PARTIALLY_SUPPORTED=1 / NOT_APPLICABLE=8`；
- 8 条 `NOT_APPLICABLE` 精确对应 4 条 `NO_EVIDENCE` 与 4 条
  `FORBIDDEN`，且没有 Claim/Chunk 身份；
- 21 条 `SUPPORTED` 均与冻结输入既有 `supports_claims` 绑定一致；
- 唯一 `PARTIALLY_SUPPORTED` 是候选新增的细粒度绑定，冻结输入未把该
  Claim–Chunk 标成完整支持；
- 105/30 的 ID、枚举、数量、split、Claim/Chunk 身份及输入哈希均通过；
- 未读取或运行 `test/Acceptance`。

冻结输入中的 3 条 `PARTIALLY_ANSWERABLE` 按成员 B 交付合同映射到三分类
`ANSWERABLE`。该映射由校验器显式执行，不是静默修改标签。

## 对现有轮子的诊断

直接复用当前确定性 `verify_claim_evidence`：

- B 候选的 21 条 `SUPPORTED` 只保留 6 条，保留率 `0.285714`；
- 175 题人工终审谱系中的 225 条正例 Claim 只保留 110 条，正例保留率
  `0.488889`；
- 主要风险是跨语言、同义改写和语义蕴含无法由词法锚点证明。

这两个结果都只证明高误杀风险。由于没有经过人工裁决的负例，本 Gate 不得
推导 Precision、无依据主张拒绝率或人机一致率。

因此默认生成模式改为 `AUDIT_ONLY`：仍验证并记录结果，但不删除模型 Claim。
显式 enforcement 只供单元测试和未来候选比较，不进入默认在线路径。

## 可重复入口

策略、候选 CSV 和私有输入均绑定 SHA-256：

```bash
.venv/bin/python scripts/run_phase4_claim_evidence_candidate_intake.py
```

运行器拒绝绝对路径、路径穿越、哈希漂移、重复 ID、holdout split、未知枚举、
Claim/Chunk 身份漂移和类别不一致。脱敏报告只包含数量、枚举、指标和决定，
不包含问题、Claim、Evidence 正文或本机绝对路径。

## 下一大 Gate

只有形成经过人工裁决的正负 Claim–Chunk 关系后，才比较固定多语言 NLI
Cross-Encoder 与既有本地 LLM 离线 Judge。现有 BGE Reranker 是相关性模型，
不复用为蕴含器；Ragas/Haystack 不提供本项目需要的真值或语义模型，因此
不新增全栈框架。

下一 Gate 仍不包含知识库接入、前端、演示、远程部署或
`test/Acceptance`。人工裁决和离线候选门槛通过前，在线硬裁决保持禁止。
