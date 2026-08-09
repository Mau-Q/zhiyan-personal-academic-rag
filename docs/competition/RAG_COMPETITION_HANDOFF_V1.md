# RAG Competition Evidence and Handoff Pack V1

## Status and boundary

本包已在精确提交 `d775dab706c2a05d5b838f644b77b257961a4549`
和 Run ID `competition_v1_20260809_01` 上取得用户操作的 Windows 真实复现
Gate PASS。它组装已经验证的 RAG Core，不修改检索成员、RRF、Prompt、
模型、Citation、`NO_EVIDENCE`、ACL、READY 或 EvidenceSet 决策语义。
独立 closeout 已对实际脱敏产物、后续运行时等价性与精确提交 CI 完成复核。
当前状态为 `RAG_COMPETITION_BASELINE_V1_FROZEN / RAG_OWNER_SCOPE_DONE_ENOUGH`。

Fixture/Fake 只用于本包结构测试，不能成为三个场景的真实结果。

## Reuse decision

结论为 `PARTIAL_REUSE`：

| Candidate | Reuse | Boundary |
| --- | --- | --- |
| Stage-1 remote Canary | 直接复用真实 PostgreSQL READY、ES、Milvus、RRF、Qwen、Answer API、INACTIVE 与三路 cleanup | Competition wrapper 只观察本次已授权响应并脱敏，不复制 RAG |
| Phase-2 academic QA V2 private package | 直接复用 PDF、问题、页码和 SHA-256 身份 | 问题与 PDF 继续只在 ignored `runtime/` |
| Phase-4 `verify_claim_evidence_sets` | 直接复用确定性多 Evidence 审计 | `allow_adjacent=false`；不新增检索、不读分数、`AUDIT_ONLY` |
| Phase-3/4 PowerShell patterns | 复用 exact HEAD、loopback、secure prompt、严格退出和静态检查模式 | Windows PowerShell 5.1 用户运行 |

没有采用 RAG 框架、评测平台、插件系统或新 Judge；仓库现有能力已覆盖最昂贵的身份、
生命周期和清理边界，引入外部依赖只会扩大风险。

## Exactly three scenarios

| Order | Scenario | Historical input | Required current proof |
| --- | --- | --- | --- |
| 1 | `COMP-QA-001` | `local3.answerable.tracer.max_risk` | real retrieval + Qwen Answer + Citation + page/Chunk Evidence |
| 2 | `COMP-EVIDENCESET-001` | `local3.answerable.tracer.ingredients` | at least two returned Evidence and at least one generated multi-Evidence Claim audited by EvidenceSet |
| 3 | `COMP-FAIL-CLOSED-001` | same isolated version after DELETE | three cleanup jobs, inactive visibility, Answer API `403 RAG_FORBIDDEN_SCOPE`, no stale Evidence reuse |

机器 dossier 位于 `machine/competition/scenarios/`，该目录必须恰好三个 JSON。历史
问题正文继续从私有 Phase-2 suite 读取；tracked dossier 只保存 Case ID、问题哈希、
允许答案点、不得声称项和页码，不公开私有题集正文。

## Windows attempts and cross-platform repair

首次用户运行在提交 `c46e82e3a006a61f2b9ca9e99e6bc3a0bdd7e0a8`、Run ID
`competition_v1_20260809_01` 上于静态 pack 验证阶段停止。Windows Git
`core.autocrlf=true` 将 `machine/phase4_multi_evidence_set_gate.json` 从索引 LF
检出为等价 CRLF；LF SHA-256 为
`3a30be94e1e52b8f5a2c78f63fbb65732045f2a6ae44cbfc16315656430967d7`，
CRLF 工作树 SHA-256 为
`78317b3539a7900d5ef304c05c955c819cf08499636c535959238633ae077911`。
该次尝试没有运行迁移、PostgreSQL/ES/Milvus 写入、真实检索或 Qwen，不是质量证据。

Competition tracked pack 文本身份现统一使用 LF 规范化 UTF-8 字节：纯 LF 与等价
CRLF 接受；UTF-8 BOM、孤立 CR、无效 UTF-8 和内容漂移继续失败关闭。私有
Phase-2 包、PDF、suite 和运行结果仍使用其既有原始字节身份，不因本修复放宽。
修复后的用户 Gate 保留原 Run ID `competition_v1_20260809_01`，不自动创建 `_02`；
新的 exact HEAD 由新候选发布 handoff 冻结。

第二次用户运行在修复提交 `df9d35f52b2cf3aeb6f2488eb2e7d5585d9ddbff`
上已通过 exact-HEAD finalizer 和私有输入 manifest 验证，PostgreSQL
fact-source migration 报告 `UNCHANGED`；但真实 runner 再次复核 finalized
artifact 时仍对 Windows CRLF 工作树使用原始字节 SHA，误报
`finalized competition artifact drifted`。该次未开始 Stage-1 真实检索、
Qwen 或三场景执行，不是 RAG 质量结果；迁移 `UNCHANGED` 也不表示新
业务数据写入。修复后 finalizer 与真实 runner 共用同一个 LF 规范文本哈希
实现，防止生产者与消费者身份语义分叉。Run ID 仍保留为
`competition_v1_20260809_01`。

第三次用户运行在 `9d514da08c484359dd46726662e38344ea2b735e`
上通过 finalizer、私有输入、迁移和 artifact 复核，首次进入真实
Stage-1 生成。Answer API 已返回 `COMPLETED` 和非空 Evidence，但旧
Stage-1 门禁仅接受以 `_CITATION_IDS_VALIDATED` 结尾的旧 warning，
因而把当前合法的
`_CITATION_IDS_VALIDATED_CLAIM_EVIDENCE_AUDIT_<PASS|FAILED>_NOT_ENFORCED`
误报为 `REAL_GENERATION_INITIAL_CITATION_GATE_FAILED`。这是 harness 协议假阴性，
不是 Citation 身份或 RAG 质量失败。

修复只允许生成层已定义的 citation-validated warning 精确后缀，任意包含、
拼接或未知后缀继续失败关闭。该次在 replay、inactivation 和 cleanup 之前
停止，因此 cleanup 仍为 `UNKNOWN_REQUIRES_SAME_RUN_RESUME_OR_OPERATOR_AUDIT`；
修复候选必须以同一私有输入和同一 Run ID 恢复现有 READY 生命周期，不创建
`_02`。

## Successful Windows real reproduction

用户在 Windows PowerShell 5.1 上以提交
`d775dab706c2a05d5b838f644b77b257961a4549`、同一私有输入和同一
Run ID `competition_v1_20260809_01` 完成 READY 恢复，版本化入口输出
`COMPETITION_REAL_REPRODUCTION_PASS`。脱敏证据表明：

- `resumed_from_ready=true`，READY reconciliation `PASS`；
- 两个真实学术问题均为 `COMPLETED`，每题返回 3 条 Evidence；
- 两题的 Citation ID、Evidence 身份和页码定位均通过；
- generation replay 与 byte-stable replay 两题均为 `true`；
- Reranker 为 `null`，保持默认 RRF 边界；
- DELETE 后 cleanup job `3/3`、runtime snapshot cleanup、不可见性证明与
  Answer API `403` 均通过；
- `redacted-results.json` 为 `PASS`，恰好 3 个场景，cleanup 为 `PASS`。

Windows 入口返回的 SHA-256 为：

- finalized manifest: `bec756c802a588a4517f18ca0280cc584a0803bbae29d0a2ac497c2f3083a340`；
- redacted result: `3e309bed036f4a5ad3f1d45cbd9d5abad256ce0db217c2ae3afa3c71fb9bc4fb`；
- private Stage-1 report: `40dbc613e32f97bc6100cbe476798af60f7734de264980c7bcbcc83d2eba2f98`。

该时点收录证据为用户返回的版本化 wrapper PASS 截图及其打印哈希，
因此只记录用户真实复现 Gate PASS。随后独立 closeout 取得实际
`redacted-results.json`，在 Mac 上重算 raw SHA-256 并完成内容核验；
脱敏产物仍不提交到仓库。

## Independent baseline closeout

独立 closeout 的冻结身份为：

| Field | Frozen value |
| --- | --- |
| Baseline | `RAG_COMPETITION_BASELINE_V1 / FROZEN` |
| Submission repository head | `fd5a517b56ba619ca461e262a5ea1a8ac8b9ac7b` |
| Windows real reproduction source | `d775dab706c2a05d5b838f644b77b257961a4549` |
| Runtime equivalence | `d775dab → fd5a517 = PASS` |
| Run ID | `competition_v1_20260809_01` |
| Redacted result SHA-256 | `3e309bed036f4a5ad3f1d45cbd9d5abad256ce0db217c2ae3afa3c71fb9bc4fb` |
| Private Stage-1 report SHA-256 | `40dbc613e32f97bc6100cbe476798af60f7734de264980c7bcbcc83d2eba2f98` |
| GitHub clean checkout | `Core tests / 31309664087 / PASS` |
| Competition RAG owner scope | `DONE_ENOUGH` |

实际产物通过 Schema、run/source identity、恰好三场景 PASS、Scenario A
Citation→Evidence 身份解析、Scenario B 多 Evidence/Chunk 审计记录、
`AUDIT_ONLY`、Scenario C `403 RAG_FORBIDDEN_SCOPE`、cleanup `3/3`、无 stale
Evidence 与实际序列化内容隐私核验。

`d775dab → fd5a517` 只有两个后续提交、共 10 个变更文件：
`736f2e4` 只记录真实复现权威；`fd5a517` 只将 Phase 3 离线
screening 身份组装拆分为已验证输入并以合成夹具使 clean-checkout CI
不依赖 ignored `runtime/`。Competition 真实入口、Stage-1、retrieval、Embedding、
RRF、Qwen/Prompt、Citation/Evidence、READY/ACL、cleanup、场景和 EvidenceSet 决策
均未改变。GitHub run `31309664087` 在 Ubuntu 24.04 / CPython 3.11.15 上
`make test = PASS`；前一 clean-checkout 运行的 14 个 runtime/path 错误降为 0。

正确表述是“Windows 复现 `d775dab`，submission repository head 是 `fd5a517`，
runtime equivalence 为 PASS”；不写成“Windows 复现 `fd5a517`”。

该冻结只收口 Competition RAG owner scope。Phase 3 仍为 `PARTIAL / NO_PROMOTION`
且 optimization `STOP`，Phase 4 仍为 `PARTIAL / AUDIT_ONLY`，300 ms 债务仍为
known/deferred；不表示 production ready 或正式 Acceptance 完成。

## Windows PowerShell 5.1 runbook

目标环境为用户操作的 Windows PowerShell 5.1。先使 Windows `main` 精确包含待验证
提交；不要在该主机修改 tracked 文件。私有 Phase-2 V2 包目录必须位于当前仓库的
`runtime/` 下并包含原 `manifest.json`、`suites/` 与 `papers/`。

运行版本化入口：

```powershell
.\deploy\remote\competition-v1\run_competition_pack_v1.ps1
```

入口会依次：

1. 要求输入 expected 40 位 commit、私有包目录和唯一 Run ID；
2. 检查 tracked worktree clean，且 `HEAD == origin/main == expected commit`；
3. 静态验证 manifest/schema/恰好三个场景，并在 ignored runtime 生成绑定 exact HEAD
   与所有 tracked pack artifact SHA-256 的 finalized manifest；
4. 以 secure prompt 读取 PostgreSQL 密码，只构造当前进程内 loopback
   `DATABASE_URL`，不打印密码或连接字符串；
5. 应用现有迁移，验证历史私有包 SHA-256，并选择两个既有问题；
6. 调用现有 isolated Stage-1 real Core：同一 READY 版本按顺序运行 Scenario A、B；
7. 以本次结构化 Qwen Claim 和请求内授权 Evidence 运行 `AUDIT_ONLY` EvidenceSet；
8. DELETE 后完成 ES、Milvus、runtime snapshot 三路 cleanup，再运行 Scenario C 的
   inactive Answer `403` 门；
9. 写入并校验 `redacted-results.json`，最后清除当前 PowerShell 进程内的连接变量。

若运行在 READY 后失败，禁止换 Run ID。先修复报告中的稳定组件错误，再用同一提交、
同一私有输入和同一 Run ID 重跑该入口；现有 Stage-1 幂等路径会从 READY 恢复并继续
到 INACTIVE/cleanup。若报告仍未给出 cleanup PASS，不得把任何场景标为通过，也不得
手工删除数据库或索引；应返回脱敏失败报告进入独立恢复 Gate。

## Redacted evidence contract

可交付文件为 `runtime/competition/v1/<run-id>/redacted-results.json`，结构由
`contracts/schemas/competition-redacted-result-v1.schema.json` 冻结。它只允许：

- Scenario、run、source/model identity 与状态；
- Answer 的展示副本及 SHA-256；
- Citation、document/page/chunk identity；
- 每条 Evidence 最多 240 字符的最小摘录及完整 quote SHA-256；
- EvidenceSet `AUDIT_ONLY` 记录、cleanup 证明和自然产生的身份。

禁止提交或返回 secret、`DATABASE_URL`、密码/token、私有 host/IP、完整 PDF、私有
corpus dump、原始数据库/索引、私有 trace 或模型 reasoning。该文件默认仍在 ignored
runtime；公开 Answer 或 Evidence 摘录前必须由 owner 再做论文许可与脱敏复核。

## Returned artifacts

只返回以下脱敏内容：

- `git rev-parse HEAD`；
- finalized baseline manifest 的 SHA-256；
- `redacted-results.json` 及其 SHA-256；
- private `stage1-report.json` 的 SHA-256（正文仅在不含私有路径/问题/正文时返回）；
- Reviewer A、Reviewer B 和 adjudication 文件的 SHA-256（完成真实人工评价后）。

不返回环境变量赋值行、密码、完整连接字符串、PDF、完整 Chunk 或私有输入目录。

## Stop

真实复现成功也只资格化后续 closeout；本任务结束后不自动开始算法、性能、前端、PPT、
视频或其他比赛任务。

```text
NO_NEW_RAG_ALGORITHM_WORK
NO_AUTOMATIC_NEXT_TASK
```
