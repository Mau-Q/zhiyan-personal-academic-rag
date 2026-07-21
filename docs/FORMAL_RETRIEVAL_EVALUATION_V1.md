# 正式检索评测体系 V1

## 当前结论

正式检索评测的合同、校验器、拆分规则、双标注谱系和指标计算已就绪；真实 500 条人工评测集尚未采集，当前状态为：

`FRAMEWORK_READY / DATA_COLLECTION_PENDING / NOT_LOCK_READY`

公开 Fixture 只有 4 条合成样本，用于证明合同和失败关闭语义，不能计入阶段 0 的 500 条正式样本。原有 3 论文 15 题继续作为工程 Canary，也不能并入正式 `dev/test/acceptance` 后制造规模完成。

## 目标规模

最高方案阶段 0 要求 200～500 条初始评测集，第 6 章同时建议首期不少于 500 条。因此 V1 目标固定为 `500` 条，以同时满足两个口径。只有以下条件同时成立后，Manifest 才能进入 `LOCKED`：

- `dev/test/acceptance` 恰好 500 条最终样本，在线难例不得计入该规模；
- 数据快照、Chunk 快照、样本和标注记录 SHA-256 一致；
- 拆分与分层比例通过；
- 同一泄漏组不跨拆分；
- 每条至少两名标注者独立标注；
- 完成仲裁；
- 高难度和标准/时效问题完成专家复核；
- Acceptance 保持盲测。

## 数据合同

Manifest、样本、标注和运行结果分别由以下合同约束：

- `retrieval_evaluation_manifest_v1`：数据集身份、目标规模、快照、拆分、分层和质量门禁；
- `retrieval_evaluation_item_v1`：问题、授权范围、路由、相关 Chunk、主张、禁止主张和最终标注；
- `retrieval_annotation_record_v1`：独立标注、仲裁和专家复核的不可混淆谱系；
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
4. 标注者 A、B 独立提交 `ANNOTATOR` 记录，互不可见；
5. 计算并记录一致性，存在冲突时由第三人提交 `ADJUDICATOR` 记录；
6. `hard` 或 `standards_freshness` 样本必须再提交 `EXPERT_REVIEWER` 记录；
7. 最终样本必须指向仲裁或专家记录，且最终标签逐字段一致；
8. 锁定后不静默改题、页码或标签；语料/页码漂移必须升级数据集版本。

标注者 ID 使用项目内假名，不保存真实身份信息。自动生成只能协助候选整理，不能代替两名人工标注或专家结论。

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

验证公开设计 Fixture：

```bash
make formal-evaluation-fixture
```

验证真实数据集是否达到锁定条件：

```bash
python3 -m backend.evaluation.formal_corpus \
  --manifest runtime/evaluation/formal-retrieval-v1/manifest.json \
  --require-lock-ready
```

比较多个检索运行：

```bash
python3 -m backend.evaluation.retrieval_metrics \
  --manifest runtime/evaluation/formal-retrieval-v1/manifest.json \
  --run sqlite_fts5=runtime/evaluation/formal-retrieval-v1/sqlite.jsonl \
  --run local_vector=runtime/evaluation/formal-retrieval-v1/vector.jsonl \
  --run local_rrf=runtime/evaluation/formal-retrieval-v1/rrf.jsonl \
  --split test \
  --k 3,5,10,20,50 \
  --output runtime/evaluation/formal-retrieval-v1/test-metrics.json
```

## 下一门禁

1. 共享方冻结首期知识源、用户类型和实际语言分布；
2. 从真实语料快照建立 500 条问题候选和泄漏组；
3. 完成双人独立标注、仲裁与专家复核；
4. 锁定 `dev/test/acceptance` 后，运行词项、BM25、向量和 RRF 的正式对比；
5. 只有扩展集证明稳定排序缺口后，才打开重排实现门禁。
