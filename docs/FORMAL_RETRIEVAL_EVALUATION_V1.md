# 正式检索评测体系 V1

## 当前结论

正式检索评测的合同、校验器、拆分规则、评审谱系和指标计算已就绪。最新最高方案将评测分为三层：

- MVP 初始集：`175/175 HUMAN_VALIDATED`，166 条原样通过、9 条修订标签、4 条专家签署；
- 稳定迭代集：约 500 条，当前现有 AI 工程集及四路结果归于此层；
- 正式验收集：800–1500 条独立盲测，不是 MVP 启动前置。

公开 Fixture 只用于证明合同和失败关闭语义，3 论文 15 题继续作为快速 Canary。它们和 AI 辅助 500 题都不替代 175 题的真实人工校验。

## 目标规模

阶段 0 先以 175 条建立可归因 Baseline。固定类别配额为精确查找 30、单文档事实 50、语义改写 30、比较 20、无答案/部分答案/冲突 25、权限/注入/恶意输入 20；新拆分为 `dev/test/acceptance=105/35/35`，同一泄漏组只选一题，Acceptance 保持盲测。现有 500 题不删除，但定位为候选池和稳定迭代证据。

175 题队列由版本化策略和确定性生成器约束，私有问题、证据和决策只写入被忽略的 `runtime/`。所有决策初始为 `PENDING`；AI 提议只是待审内容，不得计为人工签署。

现有 500 题 V1 合同的 `LOCKED` 仍保留以下高强度质量门禁，但它只是稳定迭代集的内部状态，不自动等于最高方案的 800～1500 条正式独立验收：

- `dev/test/acceptance` 恰好 500 条最终样本，在线难例不得计入该规模；
- 数据快照、Chunk 快照、样本和标注记录 SHA-256 一致；
- 拆分与分层比例通过；
- 同一泄漏组不跨拆分；
- 每条至少两名人工标注者独立标注；
- 有冲突的样本完成仲裁；
- 高难度和标准/时效问题完成对应背景人员复核；
- Acceptance 保持盲测。

## 数据合同

Manifest、样本、标注和运行结果分别由以下合同约束：

- `retrieval_evaluation_manifest_v1`：数据集身份、目标规模、快照、拆分、分层和质量门禁；
- `retrieval_evaluation_item_v1`：问题、授权范围、路由、相关 Chunk、主张、禁止主张和最终标注；
- `retrieval_annotation_record_v1`：人工、GPT、合成 Fixture、仲裁和专家复核的不可混淆谱系；
- `retrieval_ranking_result_v1`：后端、Top-K、决策、延迟和有序候选。

JSON Schema 由 Pydantic 模型机械导出，使用以下命令检查漂移：

```bash
python3 scripts/export_evaluation_contracts.py --check
```

真实问题、私有 Chunk、标注记录和盲测集只进入被 Git 忽略的 `runtime/evaluation/formal-retrieval-v1/`。Git 只保存合同、工具、说明和合成 Fixture。

## 分层规则

样本允许多标签，避免把“标准问题”“无答案问题”和“对抗问题”错误地视为互斥类别：

| 类型 | 目标区间 |
|---|---:|
| 精确查找 | 8%～12% |
| 单文档事实问答 | 12%～18% |
| 单文档解释/总结 | 8%～12% |
| 跨文档语义问答 | 12%～18% |
| 比较问题 | 8%～12% |
| 多跳问题 | 8%～12% |
| 教材/教学解释 | 3%～7% |
| 标准与时效问题 | 8%～12% |
| 无答案/证据不足 | 10%～20% |
| 对抗与安全问题 | 5%～10% |

同时记录语言、查询形态和难度。中文、英文、中英混合、短查询、长查询、错别字、缩写和多轮追问需要覆盖真实用户分布，但正式比例要根据首期知识源和用户范围再冻结，不能由 Fixture 推断。

## 拆分与防泄漏

V1 初始拆分固定为：

- `dev` 60%：参数、阈值、Prompt 和权重调优；
- `test` 20%：日常固定回归，不参与调参；
- `acceptance` 20%：项目负责人保管的盲测集；
- `online_hard_cases`：单独管理，不计入上述比例。

每条样本必须指定 `leakage_group_id`。同一文档上的近似问题、同一问题改写、多轮派生问题和共享答案模板必须进入同一泄漏组，校验器拒绝任何跨拆分泄漏。Acceptance 指标命令默认拒绝执行，只有负责人明确解锁时才能使用 `--allow-acceptance`。

## 标注与仲裁流程

1. 冻结语料和 Chunk 快照；
2. 问题编写者依据原文和业务分层出题，不根据某个检索后端的结果反向写题；
3. 为每题记录授权范围、路由、0～3 级 Chunk 相关性、参考主张、可接受答案点、禁止主张和引用；
4. 低风险 `dev/test` 可使用单个可复现 GPT `ANNOTATOR` 记录，并按 10%～20% 做分层人工抽检；
5. GPT 记录必须固定模型身份、Prompt 版本和温度；
6. 单 GPT 低风险样本使用 `GPT_ASSISTED`；存在第二评审且一致时可停在 `DOUBLE_ANNOTATED`；
7. 存在冲突时由人工提交 `ADJUDICATOR`；GPT 不得担任仲裁者；
8. Acceptance、无答案、越权、安全问题必须有人复核；`hard` 或 `standards_freshness` 还必须提交人工 `EXPERT_REVIEWER`；
9. 最终仲裁或专家标签必须与样本逐字段一致；
10. 锁定后不静默改题、页码或标签；语料/页码漂移必须升级数据集版本。

标注者 ID 使用项目内假名，不保存真实身份信息。旧的 500 题工程基线允许 GPT 承担低风险初标，并保留更高强度 `LOCKED` 合同；新的 175 题 MVP 初始集不沿用抽检口径，每题都必须完成真实人工校验。

完整的后续阶段选测原则见 [风险驱动测试策略](RISK_BASED_TESTING_STRATEGY.md)。

## 检索指标

正式指标按相关性 `0～3` 计算：

- `Recall@K`：相关性 ≥ 2 的 Chunk 被召回的比例；
- `Precision@K`：前 K 中相关性 ≥ 2 的比例；
- `MRR@K`：第一个相关 Chunk 的倒数排名；
- `nDCG@K`：使用 0～3 分级相关性的排序质量；
- 无答案识别 Recall、拒答 Precision、有答案错误拒答率；
- 越权阻断率；
- P50/P95 检索延迟；
- 按问题类型分别报告 Recall 和 nDCG。

多后端报告会给出逐项差值，但不自动宣布“胜出”。混合检索是否晋级、是否接入重排仍需结合最高方案建议：混合 Recall 相对最佳单路提升、关键类别不退化；重排需证明 nDCG 增益并满足 Precision 和延迟预算。

## 可执行入口

冻结本地 Chunk 源并初始化空的 500 题工作区：

```bash
python3 scripts/init_assisted_evaluation_workspace.py \
  --chunks runtime/evaluation/local-3-paper-v1/chunks/all-three.json \
  --output-dir runtime/evaluation/formal-retrieval-v1 \
  --corpus-id local-3-paper-v1 \
  --dataset-id local-3-paper-assisted-evaluation-v1 \
  --dataset-version local-3-paper-assisted-v1 \
  --created-at <ISO-8601-with-timezone>
```

初始化器验证 `ChunkRecordV1`、拒绝失效或重复 Chunk、拒绝覆盖非空工作区，并生成源快照、空 JSONL、Manifest 和初始化报告。空题集必须保持 `engineering_ready=false / lock_ready=false`。

按固定配额生成 500 个槽位和 50 个内部容错分组：

```bash
python3 scripts/prepare_assisted_evaluation_batches.py \
  --policy evaluation/assisted-500-policy-v1.json \
  --chunks runtime/evaluation/local-3-paper-v1/chunks/all-three.json \
  --prompt evaluation/prompts/assisted-question-generation-v1.md \
  --output-dir runtime/evaluation/formal-retrieval-v1/generation-v1
```

50 个文件只是便于校验和失败重试，不代表需要手工调用 50 次。使用 DashScope 时，500 个逐题请求由一个命令并发执行；默认 20 路并发，强制 `qwen3.7-plus`、`temperature=0`、`enable_thinking=false` 和 JSON 输出：

```bash
python3 scripts/run_assisted_generation_qwen.py \
  --env-file /path/to/private/.env \
  --batch-dir runtime/evaluation/formal-retrieval-v1/generation-v1/batches \
  --output-dir runtime/evaluation/formal-retrieval-v1/qwen3.7-plus-v1 \
  --model qwen3.7-plus \
  --workers 20
```

执行器不修改 `.env`，不打印密钥；逐题原子落盘，重复运行时跳过已完成题目，并对 408、409、429 和 5xx 自动重试。只有 `run-report.json` 达到 `completed_count=500 / failed_count=0` 后，才允许把生成阶段记为完成。

macOS Python 使用独立 CA 路径时，执行器显式加载 `certifi` 并保持主机名和证书链校验开启，不允许以关闭 TLS 校验作为修复。当前实跑已完成 500/500，失败 0。原始候选仍须经过题面去重、槽位约束、引用范围和正式合同校验，不能因模型调用完成就直接标记为正式题集。

定向修复后，使用最终化工具合并原始结果与多轮修复，并在新目录输出清洗候选和正式草稿：

```bash
python3 scripts/finalize_assisted_candidates.py \
  --batch-dir runtime/evaluation/formal-retrieval-v1/generation-v1/batches \
  --raw-results runtime/evaluation/formal-retrieval-v1/qwen3.7-plus-v1/results.jsonl \
  --repair-results runtime/evaluation/formal-retrieval-v1/qwen3.7-plus-repairs-v1/repair-results.jsonl \
  --repair-results runtime/evaluation/formal-retrieval-v1/qwen3.7-plus-repairs-v2/repair-results.jsonl \
  --output-dir runtime/evaluation/formal-retrieval-v1/qwen3.7-plus-finalized-v1
```

最终化工具从冻结 slot 恢复主题型、文档范围和 answerability，将自由文本路由固定为 `HYBRID_QA`，从相关性判断派生引用，并让无证据/越权题保持无支持证据。输出为 500 个唯一题面、500 个通过 `EvaluationItemV1` 的草稿。

随后使用本机同一 Ollama `bge-m3:latest` 对完整题面和参考答案分别编码，按题面高相似、同文档答案模板高相似、共享 Chunk 题面相似和题面/答案联合相似四条规则建立泄漏组：

```bash
python3 scripts/build_assisted_formal_corpus.py \
  --candidates runtime/evaluation/formal-retrieval-v1/qwen3.7-plus-finalized-v1/normalized-candidates-v1.jsonl \
  --manifest runtime/evaluation/formal-retrieval-v1/manifest.json \
  --embedding-cache runtime/evaluation/formal-retrieval-v1/qwen3.7-plus-finalized-v1/leakage-embedding-cache-v1.json \
  --report runtime/evaluation/formal-retrieval-v1/leakage-and-import-report-v1.json \
  --submitted-at 2026-07-21T17:50:09+08:00
```

实跑得到 68 条匹配边、443 个泄漏组，其中 33 个为多题组，最大组 7 题。原拆分有 24 个组跨越多个 split；按组重分配 30 题后恢复 `dev/test/acceptance=300/100/100`，跨拆分泄漏组为 0。正式工作区现有 500 个 `GPT_ASSISTED` items 和 500 条 Qwen 标注记录，Manifest 状态为 `ANNOTATION`。25 个冲突候选以及 Acceptance、无证据/越权/安全题和专业高难题仍须按风险策略人工确认，四类合并去重为 213 题；其中 75 题已覆盖低风险 `dev/test` 的 20.7%，因此不再额外制造一套抽检工作。人工记录尚未回填前不得标记为 `engineering_ready` 或 `LOCKED`。

人工复核不再拆成多个批次。用一个命令生成单一去重包：

```bash
python3 scripts/prepare_risk_review_package.py \
  --manifest runtime/evaluation/formal-retrieval-v1/manifest.json \
  --batch-dir runtime/evaluation/formal-retrieval-v1/generation-v1/batches \
  --output-dir runtime/evaluation/formal-retrieval-v1/risk-review-package-v1 \
  --created-at 2026-07-21T18:01:21+08:00
```

包内 `risk-review-queue-v1.jsonl` 为 213 条只读问题、Qwen 提议和冻结 Chunk 文本，`risk-review-decisions-v1.jsonl` 为唯一需要填写的文件。每题只出现一次，多种风险通过 `review_reasons` 合并；模板预填现有标签以减少机械录入，但 `review_outcome` 全部保持 `PENDING`。实跑分布为 `P0/P1/P2=50/126/37`、`HUMAN_EXPERT/HUMAN_REVIEWER=50/163`，当前人工完成数为 0。ZIP 只含 README、队列、决策模板、汇总和 SHA-256 清单，不含 `.env`、PDF 或其他运行文件。

验证公开设计 Fixture：

```bash
make formal-evaluation-fixture
```

验证真实数据集是否达到锁定条件：

```bash
.venv/bin/python -m backend.evaluation.formal_corpus \
  --manifest runtime/evaluation/formal-retrieval-v1/manifest.json \
  --require-lock-ready
```

验证 GPT 辅助 500 题是否达到近期门禁：

```bash
.venv/bin/python -m backend.evaluation.formal_corpus \
  --manifest runtime/evaluation/formal-retrieval-v1/manifest.json \
  --require-engineering-ready
```

同一报告分别输出 `engineering_ready` 和 `lock_ready`，两者不能互相替代。

比较多个检索运行：

```bash
.venv/bin/python -m backend.evaluation.retrieval_metrics \
  --manifest runtime/evaluation/formal-retrieval-v1/manifest.json \
  --run sqlite_fts5=runtime/evaluation/formal-retrieval-v1/sqlite.jsonl \
  --run local_vector=runtime/evaluation/formal-retrieval-v1/vector.jsonl \
  --run local_rrf=runtime/evaluation/formal-retrieval-v1/rrf.jsonl \
  --split test \
  --k 3,5,10,20,50 \
  --output runtime/evaluation/formal-retrieval-v1/test-metrics.json
```

本地四路排名由 `scripts/run_formal_retrieval_rankings.py` 一次生成，参数由 `evaluation/formal/local-retrieval-baseline-v1.json` 固定。该工具批量预计算查询向量，但仍使用已锁定的 SQLite FTS5、BGE-M3 精确余弦和 RRF 参数。实跑为每路 `500/500`；dev/test 上向量与 RRF 的排序优势不一致，因此重排仍为 `DEFER_RERANK`。

## 下一门禁

1. 175 题已完成人工校验，分类、拆分、泄漏组、修订后正式合同和专家签署均通过；
2. 同一冻结集的 ES only/Milvus only 私有输入包已通过谱系、数量、合同、校验和 ZIP 完整性检查；下一步只生成两路远程报告，不先做融合调参；
3. 现有 500 题四路结果和 213 题 AI 审计只作为工程证据，不冒充 175 题的人工结论；
4. 远程 RRF 14/15 与 ES 持平，当前不实现重排、真实 LLM、HyDE、multi-query、multi-hop、在线 NLI 或远程 500 题全量跑测。
