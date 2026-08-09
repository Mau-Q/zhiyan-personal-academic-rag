# RAG Competition Evidence and Handoff Pack V1

## Status and boundary

本包状态固定为 `READY_FOR_USER_REAL_REPRODUCTION_GATE`。它组装已经验证的 RAG
Core，不修改检索成员、RRF、Prompt、模型、Citation、`NO_EVIDENCE`、ACL、READY
或 EvidenceSet 决策语义。只有用户在精确提交上完成真实复现并返回合规证据后，未来
独立 closeout 才能判断是否冻结 `RAG_COMPETITION_BASELINE_V1`。

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
