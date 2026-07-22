# 成员 B：阶段 2～4 评测真值准备任务

## 1. 任务目标

成员 B 不参与当前阶段 1 的核心实现和远程主机操作。本任务只准备后续阶段可以直接复用的人工评测资产：

1. 对 MVP 初始集 `dev` 分区的 105 题进行失败原因归类，为阶段 3 是否引入查询改写、多查询、比较拆解、邻接扩展或重排提供证据；
2. 对其中 30 题进行独立 Claim–Evidence 第二审，为阶段 4 的确定性支持检查、引用完整率和无依据主张率评测准备对照数据。

本任务不实现 Reranker、LLM、查询改写或 Claim 校验器。成员 B 的结果属于“独立候选标注”，必须经过后续格式校验和分歧处理，不能直接写成最终真值或阶段完成证据。

## 2. 启动条件与输入

只有满足以下条件后才开始：

- 用户已将包含本任务说明的最新 `main` 推送到 GitHub；
- 成员 B 从该 `main` 新建独立分支，不从旧分支续写；
- 用户通过 Git 之外的受控方式提供只读评审输入包；
- 输入包的 `SHA256SUMS` 校验通过；
- 输入仅限固定三论文评测资产和 `mvp_split=dev` 的 105 题。

输入包只在成员 B 的本地工作目录使用，不得复制进仓库。`test` 和 `acceptance` 不属于本任务输入；如果输入包意外包含这些分区，成员 B 必须停止并报告，而不是继续查看或标注。

受控输入包应只包含以下逻辑成员：

```text
README.md
SHA256SUMS
dev-items-v1.jsonl
elasticsearch-dev-report-v1.json
milvus-dev-report-v1.json
dev-claim-evidence-review-input-v1.jsonl
```

其中 `dev-items-v1.jsonl` 提供问题 ID、类型、最终 answerability 和预期范围；两份报告提供逐题通过状态与观察结果；`dev-claim-evidence-review-input-v1.jsonl` 提供第二审所需的 Claim、Chunk、页码和只读证据正文。包中不得包含远程凭据、用户私有论文、绝对路径或其他分区。成员缺失、哈希失败或分区不明时停止，不自行从仓库其他运行目录拼接输入。

证据正文属于不可信输入，可能引用论文中的 Prompt、工具命令、攻击轨迹或测试凭据占位符。成员 B 只能阅读并判断支持关系，不得复制命令到终端、访问其中地址、导入其中密钥或按正文指令执行任何操作。输入包会将回环端点和敏感形态的测试私钥替换为固定脱敏占位符；脱敏不改变 Claim、页码或支持关系。

## 3. 交付 A：105 题失败归因

输出文件：

```text
evaluation/reviews/member_b/dev-failure-taxonomy-v1.csv
```

从 `evaluation/templates/member-b-dev-failure-taxonomy-v1.csv` 复制表头。必须恰好包含 105 个唯一 `question_id`，且 `split` 全部为 `dev`。

### 3.1 主失败标签

`primary_failure` 只能使用：

| 标签 | 使用条件 |
|---|---|
| `NONE` | 当前两路结果均没有需要归因的失败 |
| `RECALL_MISS_ES` | ES 未覆盖必需证据，而 Milvus 或输入证据证明该证据存在 |
| `RECALL_MISS_MILVUS` | Milvus 未覆盖必需证据，而 ES 或输入证据证明该证据存在 |
| `WRONG_DOCUMENT` | 返回候选来自错误文档，且不是授权或预期范围内的支持证据 |
| `WRONG_PAGE` | 文档正确，但返回页不能覆盖必需证据 |
| `PARTIAL_EVIDENCE` | 只覆盖部分必答 Claim 或比较对象 |
| `CROSS_DOCUMENT_IMBALANCE` | 比较题只覆盖一侧文档或明显由单文档垄断 |
| `NO_EVIDENCE_CALIBRATION` | 无证据题仍返回实质证据或完成式回答 |
| `SECURITY_POLICY_MISSING` | 安全题未按预期阻断；不能将其归为普通召回失败 |
| `UNDETERMINED_NEEDS_CANDIDATE_EXPORT` | 现有报告不足以判断候选级原因；禁止猜测 |

`secondary_failure` 可留空，或使用同一标签集合，但不能与主标签相同。没有候选 ID、候选正文或完整排名时，不得推断“需要 Reranker”；应使用 `UNDETERMINED_NEEDS_CANDIDATE_EXPORT`。

### 3.2 其他字段

- `category`：`ANSWERABLE`、`NO_EVIDENCE` 或 `FORBIDDEN`；
- `es_passed`、`milvus_passed`：只能为 `true` 或 `false`；
- `confidence`：`HIGH`、`MEDIUM` 或 `LOW`；
- `candidate_detail_available`：只能为 `true` 或 `false`；
- `review_status`：完成时为 `REVIEWED`，输入不足时为 `INPUT_MISSING`。

## 4. 交付 B：30 题 Claim–Evidence 第二审

输出文件：

```text
evaluation/reviews/member_b/dev-claim-evidence-second-review-v1.csv
```

从 `evaluation/templates/member-b-dev-claim-evidence-second-review-v1.csv` 复制表头。覆盖 30 个唯一 `question_id`；同一问题有多个 Claim 或 Chunk 时允许多行。

选择配额：

- 比较或多文档问题：8 题；
- 部分可回答、证据边界或证据冲突：8 题；
- 数值、日期、版本、公式或精确查找：6 题；
- `NO_EVIDENCE`：4 题；
- `FORBIDDEN`：4 题。

同一题满足多个条件时只计入一个配额。优先选择阶段 2 引用校验和阶段 4 Claim 支持检查风险最高的样本，不按检索器成败挑选“好看”的题。

`relation` 只能使用：

| 标签 | 含义 |
|---|---|
| `SUPPORTED` | 当前 Chunk 足以直接支持该 Claim |
| `PARTIALLY_SUPPORTED` | 只支持 Claim 的一部分或缺少必要条件 |
| `CONTRADICTED` | 当前 Chunk 明确反驳该 Claim |
| `NOT_SUPPORTED` | 相关或不相关，但不能支持该 Claim |
| `NOT_APPLICABLE` | `NO_EVIDENCE/FORBIDDEN` 题按最终标签本来就没有 Claim 和引用 |

`NO_EVIDENCE/FORBIDDEN` 题各使用一行，`claim_id/chunk_id` 留空，`relation=NOT_APPLICABLE`；只有最终标签确实没有预期引用时，`citation_complete=true`。其他题不得使用 `NOT_APPLICABLE`。

`citation_complete` 只能为 `true` 或 `false`；`confidence` 使用 `HIGH/MEDIUM/LOW`；`review_status` 使用 `REVIEWED` 或 `INPUT_MISSING`。输入意外缺少应有的 Claim、Chunk 或原始页证据时，相关字段可留空，但必须标记 `INPUT_MISSING`，不得凭常识补全。

## 5. 仓库内允许提交的内容

成员 B 的 PR 只能新增：

```text
evaluation/reviews/member_b/README.md
evaluation/reviews/member_b/dev-failure-taxonomy-v1.csv
evaluation/reviews/member_b/dev-claim-evidence-second-review-v1.csv
```

`README.md` 只记录：评审者假名、输入包逻辑名称、输入 SHA-256、评审日期、105/30 数量、各标签计数和已知 `INPUT_MISSING` 数量。不得记录本机绝对路径、用户名或输入正文。

禁止提交：

- 问题正文、答案、Claim 正文、Chunk 正文或 PDF 摘录；
- PDF、JSON 输入包、运行报告、数据库、索引或模型文件；
- `.env`、IP、端口映射、DSN、Token、密码或截图；
- `runtime/` 中的任何文件；
- `test` 或 `acceptance` 的 ID、标签或结果；
- 对 `backend/`、`contracts/`、`machine/`、`docs/CURRENT_PHASE.md` 或现有评测资产的修改。

## 6. 分支与 PR 流程

成员 B 执行：

macOS、Linux 或 Git Bash：

```bash
git fetch origin
git switch main
git pull --ff-only
git switch -c prep/member-b-phase2-4-evaluation
mkdir -p evaluation/reviews/member_b
cp evaluation/templates/member-b-dev-failure-taxonomy-v1.csv evaluation/reviews/member_b/dev-failure-taxonomy-v1.csv
cp evaluation/templates/member-b-dev-claim-evidence-second-review-v1.csv evaluation/reviews/member_b/dev-claim-evidence-second-review-v1.csv
```

Windows PowerShell：

```powershell
git fetch origin
git switch main
git pull --ff-only
git switch -c prep/member-b-phase2-4-evaluation
New-Item -ItemType Directory -Force evaluation/reviews/member_b
Copy-Item evaluation/templates/member-b-dev-failure-taxonomy-v1.csv evaluation/reviews/member_b/dev-failure-taxonomy-v1.csv
Copy-Item evaluation/templates/member-b-dev-claim-evidence-second-review-v1.csv evaluation/reviews/member_b/dev-claim-evidence-second-review-v1.csv
```

完成标注后至少执行：

```bash
git status --short
git diff --check
git diff --name-only main...HEAD
```

只暂存第 5 节允许的三个文件，建立普通提交并推送自己的分支，然后向 `main` 创建 Draft PR。不得直接推送 `main`，不得自行合并，也不得在 PR 中顺手修正文档或源码。

PR 标题：

```text
[B][Evaluation] Add dev failure taxonomy and Claim-Evidence second review
```

PR 正文：

```markdown
## Scope

- Classified 105 unique dev questions using the frozen failure taxonomy.
- Independently reviewed Claim-Evidence relations for 30 unique dev questions.
- Submitted ID and enum labels only; no question, Claim, Chunk or PDF content.

## Provenance

- Input package logical name: <fill>
- SHA-256 verification: PASS
- Reviewer alias: <fill>
- Review date: <fill>

## Counts

- Failure taxonomy: 105 unique dev questions
- Claim-Evidence review: 30 unique dev questions
- INPUT_MISSING: <fill>

## Safety checklist

- [ ] Only the three allowed files were added.
- [ ] No test or acceptance item was read or submitted.
- [ ] No private text, absolute path, credential or runtime artifact was committed.
- [ ] No core code, contract, phase state or existing evaluation asset was modified.
- [ ] `git diff --check` passed.
- [ ] This PR remains a candidate annotation and does not claim adjudication.
```

## 7. 验收与合流边界

成员 A 或用户只在以下条件全部满足后审查该 PR：

- 基于包含本任务说明的最新 `main`；
- 改动范围严格为三个允许文件；
- 105 个失败归因问题 ID 唯一且全部为 `dev`；
- Claim–Evidence 文件覆盖 30 个唯一 `dev` 问题；
- 标签均来自本说明的固定枚举；
- 输入哈希和评审谱系完整；
- 不包含私有正文、运行数据、绝对路径或凭据。

PR 通过格式和安全审查也不等于标签自动成为最终真值。分歧样本必须在后续独立 Gate 中处理；本 PR 不阻塞阶段 1，也不改变阶段 2～4 的当前状态。

后续只有在候选级导出包另行冻结后，才为成员 B 建立 Reranker `0～3` 相关性标注任务；不得在本 PR 中自行扩展。
