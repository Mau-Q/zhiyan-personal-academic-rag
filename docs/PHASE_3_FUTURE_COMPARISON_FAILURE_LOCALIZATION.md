# Phase 3 Future Comparison Failure Localization Gate

## 状态

- Gate：`COMPARISON_FAILURE_LOCALIZATION`
- 状态：`FUTURE_OPTION_DOCUMENTED_NOT_ACTIVE`
- 目的：如果未来重新开启最高方案阶段 3，先定位正确 Evidence 在检索与证据形成链路的哪一层丢失，再选择一个新的增强变量。
- 当前影响：无。本项不实现功能、不运行数据、不阻塞已经完成的 Phase 4 Multi-Evidence Evidence Set Gate。

## 现有证据的解释边界

`BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1` 和
`BILATERAL_COMPARISON_ROUTE_COVERAGE_TOP3_V1` 只在同一组冻结的 4 条 `dev`
比较样本上没有取得目标增益，因此两个具体变量继续关闭。该结果不能扩大解释为
查询拆分、术语扩展、路由覆盖、融合、重排或多 Evidence 方法类别整体无效，也
不能外推到未读取的 `test/Acceptance`。

当前不调参、不重跑两个失败变量，不复用既有 Run ID，不改变默认 RRF、Reranker、
NLI `AUDIT_ONLY` 或独立 300 ms 性能债。

## 未来 Gate 的定位顺序

只有未来明确重新开启阶段 3 时，才按同一冻结请求、授权 owner、活动
document/version/chunk 身份逐层记录正确 Evidence 的存在、名次与丢失位置：

1. **ES Top-50：** 正确 Evidence 是否进入词法召回及其名次；
2. **Milvus Top-50：** 正确 Evidence 是否进入向量召回及其名次；
3. **RRF Top-50：** 两路候选融合后是否仍存在及其名次；
4. **最终 Top-3：** 正确 Evidence 是否在最终选择或重排阶段被挤出；
5. **Chunk / 邻块 / Evidence Set：** 正确信息是否跨 Chunk 边界、位于同版本邻块，
   或必须由多个 Evidence 共同支持；
6. **标签与指标：** gold Chunk、相关等级、双侧命中和聚合指标是否与可接受 Evidence
   一致。

该 Gate 只允许输出脱敏的身份哈希、布尔存在性、名次、层级错误码和指标摘要；
不得把私有正文、原始 ID 或 `test/Acceptance` 带入诊断。

## 定位后的变量选择

- ES 与 Milvus Top-50 都缺失：优先评估术语扩展或结构化比较维度拆分；
- 单路存在但在 RRF Top-50 丢失：再评估融合策略；
- RRF Top-50 存在但最终 Top-3 丢失：再评估有限重排或覆盖选择；
- 正确信息跨 Chunk 边界或分散在多个片段：再评估最多一个同版本邻块或
  Evidence Set；
- 检索结果可接受但标签或指标未认可：先修正标签与指标口径，不用调参迎合错误
  gold。

上述方向是诊断后的候选，不是当前批准实现的变量。任何重新开启仍需独立冻结单一
假设、输入、去留门槛和安全边界。

## 保持不变

- 查询拆分 V1 与 Route Coverage V1 继续关闭且不重跑；
- `test/Acceptance` 继续封存；
- 默认 RRF、Reranker、NLI `AUDIT_ONLY` 和 300 ms 独立性能债不变；
- 不涉及知识库接入、前端、演示或 Agent API；
- 不阻塞 `phase4-multi-evidence-set-local-ready`。
