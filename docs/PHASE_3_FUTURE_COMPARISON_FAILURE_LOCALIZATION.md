# Phase 3 Identity-Matched Candidate-Ladder Localization Gate

## 状态

- Gate：`COMPARISON_FAILURE_LOCALIZATION`
- 状态：`LOCALIZATION_COMPLETE`
- 目的：对冻结 4 条 `dev` 以身份一致的当前在线 Control 路径记录 ES、Milvus、
  RRF 与最终 Top-3 候选阶梯，定位 earliest failure layer。
- 当前结论：用户在 Windows PowerShell 5.1 上完成了固定在线 Run，
  报告与独立 adjudication 均为 `PASS`，实验决定为
  `LOCALIZATION_COMPLETE`。该结果只完成 failure-layer 定位，不促成 Phase 3
  晋级，不选择下一算法。
- 固定 Run ID：`phase3_candidate_ladder_20260809_01`。

## 正式证据与定位结果

- 源码提交：`4a908f1fa8a4d87cdb351c0bb3e5f5df1aab63fc`；
- cohort SHA-256：
  `3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8`；
- manifest SHA-256：
  `05c36a393a51a8aa705e17d1ac3895df074b9273f8af6bfad06c9904c458c63f`；
- report SHA-256：
  `f110daba4bc5d26c952b682502f812a156f6e3fde8ecd04b716db73b99e45186`；
- adjudication SHA-256：
  `4fba0e27d44abfd009e496a0430b5da2eabfdc009a57f0c5b8cb8d7e297fed8f`；
- `local3.assisted.0033 / .0304 / .0383` 均定位为
  `RRF_FUSION_OR_RANKING`；
- `local3.assisted.0387` 的 primary 为 `ES_CANDIDATE_RETRIEVAL`，co-primary
  为 `MILVUS_CANDIDATE_RETRIEVAL`；
- 汇总为 `RRF_FUSION_OR_RANKING=3/4`、`ES_CANDIDATE_RETRIEVAL=1/4`
  primary；
- 清理为 9/9，READY 对账失败关闭，删除后 Answer API 为 403。

`.0387` 只证明当前正式 `candidate_k=20` 边界内两个 backend 均未观察
到目标文档。20 之外保持 `UNAVAILABLE_PRE_CUTOFF_NOT_OBSERVED`；不得写成
目标不在索引、不在 20 之后，或已证明 Embedding 失败。

## 现有证据的解释边界

`BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1` 和
`BILATERAL_COMPARISON_ROUTE_COVERAGE_TOP3_V1` 只在同一组冻结的 4 条 `dev`
比较样本上没有取得目标增益，因此两个具体变量继续关闭。该结果不能扩大解释为
查询拆分、术语扩展、路由覆盖、融合、重排或多 Evidence 方法类别整体无效，也
不能外推到未读取的 `test/Acceptance`。
历史保留的 Top-3 与聚合指标证据不足以区分 backend 候选、RRF 融合或
最终排序阶段的丢失；本次固定 candidate-ladder Run 只补齐该可观测性缺口。

当前不调参、不重跑两个失败变量，不复用既有 Run ID，不改变默认 RRF、Reranker、
NLI `AUDIT_ONLY` 或独立 300 ms 性能债。

## 当前 Gate 的定位顺序

按同一冻结请求、隔离授权 owner、活动 document/version/chunk 身份逐层记录正确
Evidence 的存在、名次与丢失位置：

1. **ES 当前候选边界：** 当前正式路径实际请求 `candidate_k=20`；记录返回给
   fusion 的身份、分数与路由内名次；
2. **Milvus 当前候选边界：** 同样记录实际返回给 fusion 的最多 20 条候选；
3. **RRF 完整输入融合序：** 对实际进入 RRF 的候选记录来源路由、来源名次、
   融合分数与全序；
4. **最终 Top-3：** 正确 Evidence 是否在最终选择或重排阶段被挤出；
5. **Chunk / 邻块 / Evidence Set：** 正确信息是否跨 Chunk 边界、位于同版本邻块，
   或必须由多个 Evidence 共同支持；
6. **标签与指标：** gold Chunk、相关等级、双侧命中和聚合指标是否与可接受 Evidence
   一致。

本次 Control 没有独立的 pre-cutoff 深排名接口，20 之外必须写为
`UNAVAILABLE_PRE_CUTOFF_NOT_OBSERVED`，不得为观察而把请求扩大到 50，也不得把“本次未返回”
写成索引中绝对不存在。

完整报告只落入被忽略的 `runtime/`，记录定位所需的 Run、owner、version、物理
route、model digest、Chunk/page、rank、score 和 target-match 身份，不记录问题、
Evidence 正文、生成回答或密钥；公开 Answer API schema 不增加诊断字段。

## 零行为变化设计

`OnlineVersionRrfRetriever` 新增可选内部 `candidate_ladder_observer`。未提供 observer
时执行路径与返回保持原样；提供 observer 时只复制已经由当前请求产生的每路 ES /
Milvus `RankedChunk`、同一 RRF 算术得到的融合全序及其 Top-3，不新增 ES、Milvus、
Embedding、LLM 或 Judge 调用。focused parity test 对 observer 开/关的最终
`RankedChunk` 列表做逐对象相等断言；独立裁决器重新计算每个融合分数、tie-break
全序和 Top-3 前缀，任何身份、算术、holdout 或 cleanup 漂移均拒绝。

本次在线 Run 已以隔离三文档 READY 生命周期完成；清理 9/9、READY
失败关闭和删除后 Answer API 403 均通过。该单次 Run ID 已关闭，不得复用或
创建第二个 Run ID。

## 定位后的策略边界

本 Gate 只返回定位。即使 4/4 完成分类，也不在本 Gate 选择或实现新的 retrieval
算法、邻块或 EvidenceSet 变量。固定交接行：

```text
NO_NEXT_ALGORITHM_SELECTED
```

## 保持不变

- 查询拆分 V1 与 Route Coverage V1 继续关闭且不重跑；不创建第三个 treatment；
- `test/Acceptance` 继续封存；
- 默认 RRF、Reranker、NLI `AUDIT_ONLY` 和 300 ms 独立性能债不变；
- 不涉及知识库接入、前端、演示或 Agent API；
- 不阻塞 `phase4-multi-evidence-set-local-ready`。
