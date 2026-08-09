# Phase 3 Identity-Matched Candidate-Ladder Localization Gate

## 状态

- Gate：`COMPARISON_FAILURE_LOCALIZATION`
- 状态：`LOCAL_INSTRUMENTATION_PASS_REMOTE_USER_RUN_PENDING`
- 目的：对冻结 4 条 `dev` 以身份一致的当前在线 Control 路径记录 ES、Milvus、
  RRF 与最终 Top-3 候选阶梯，定位 earliest failure layer。
- 当前结论：`BLOCKED`。本地 instrumentation、独立裁决和 Windows PowerShell
  5.1 用户入口已就绪，但 Codex 不持有用户远程主机与 PostgreSQL 凭据，未执行
  在线 Run；不得以本地结果补造远程候选证据。
- 固定 Run ID：`phase3_candidate_ladder_20260809_01`。

## 现有证据的解释边界

`BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1` 和
`BILATERAL_COMPARISON_ROUTE_COVERAGE_TOP3_V1` 只在同一组冻结的 4 条 `dev`
比较样本上没有取得目标增益，因此两个具体变量继续关闭。该结果不能扩大解释为
查询拆分、术语扩展、路由覆盖、融合、重排或多 Evidence 方法类别整体无效，也
不能外推到未读取的 `test/Acceptance`。

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

当前 Control 没有独立的 pre-cutoff 深排名接口，20 之外必须写为
`UNOBSERVED_NOT_INFERRED`，不得为观察而把请求扩大到 50，也不得把“本次未返回”
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

在线 Run 必须创建隔离三文档 READY 生命周期；报告成立要求清理 9/9、READY
失败关闭和删除后 Answer API 403。清理不完整时结果只能是 `BLOCKED`，不得用第二个
Run ID 碰运气。

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
