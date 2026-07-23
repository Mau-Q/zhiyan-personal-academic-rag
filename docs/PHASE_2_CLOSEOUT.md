# 阶段 2 基础 RAG MVP 收口

## 1. 结论

阶段 2 按最高方案第 10.3 节的退出条件完成。默认在线检索继续使用
PostgreSQL READY/owner 前置、持久化 Chunk 身份校验、ES/Milvus 并行召回
与 RRF；固定 Cross-Encoder 保留为可选组件，不晋级默认路径。

该结论是“功能与阶段退出条件完成”，不是“生产性能验收完成”。固定
Reranker 的在线组合 `P95 <= 300 ms` 门禁没有通过，性能优化显式后移，
不得把阶段完成状态解释为 SLO 已达标。

## 2. 退出条件映射

| 最高方案阶段 2 退出条件 | 收口证据 |
|---|---|
| Hybrid 与最佳单路对比完成 | 远程 ES/Milvus RRF Canary 为 14/15，与 ES 单路 14/15 持平；结果保留为无净增益，不调参制造通过 |
| Reranker 增益完成验证并作出保留/回退决策 | 冻结 `test=100` 上 `nDCG@10` 相对提升 `15.5331%`、`Precision@5 +0.02`；Windows RTX 4090 固定组件 P95 通过，决定保留为可选组件；在线组合性能失败后决定不晋级默认路径 |
| 引用、ACL、版本和定位硬门禁通过 | PostgreSQL READY/owner、版本与 Chunk 身份、ES/Milvus 路由、引用编号、页码定位、删除后 403 和三路清理均有远程证据 |
| 指定文档和普通学术问答可稳定回放 | 阶段 2 固定 3 篇文档、每篇 3 题，共 9/9 通过 Qwen 真实生成、引用集合稳定回放和清理闭环 |

## 3. 最终在线性能证据

用户在 Windows RTX 4090 上以提交
`3303bed1c6faead6980dc5246a9d0a0a06d1a751` 和 Run ID
`online_retrieval_profile_20260723_01` 完成 30 个样本：

- 30/30 `APPLIED`，无回退、候选扩张或候选边界违规；
- `base_retrieval_stage_status=PASS`，分段样本数 30；
- base retrieval `P50=287.5011 ms / P95=376.394385 ms`；
- Reranker `P50=129.59815 ms / P95=132.456 ms`；
- combined `P50=416.2398 ms / P95=504.71613 ms`；
- READY 路由解析 `P95=145.48693 ms`；
- Chunk 快照 `P95=3.873615 ms`；
- Elasticsearch 总工作 `P95=35.634955 ms`；
- Query Embedding `P95=189.838925 ms`；
- Milvus ANN `P95=6.03377 ms`，Milvus 总工作 `P95=212.73846 ms`；
- 后端并行墙钟 `P95=214.176715 ms`；
- READY 重验 `P95=1.025855 ms`，RRF `P95=0.12001 ms`；
- Retriever 总计 `P95=376.25004 ms`；
- 三路清理成功，失效后 Answer API 为 403；
- 稳定失败码为 `ONLINE_RERANKER_COMBINED_P95_EXCEEDED`；
- 脱敏报告 SHA-256 为
  `235FE36A97B7F4E462AD502595CB0CF38C139022703B6C4EA1E93E19D3AC765B`。

不同阶段的 P95 不能直接相加成单次请求，但分段结果足以证明当前主要成本
位于 Query Embedding 和 READY 路由解析，而不是 ES 查询、Milvus ANN、
Chunk 快照或 RRF。

## 4. 后移边界

后续性能硬化作为阶段 3 的独立携带 Gate，不与查询改写、多查询、比较拆解、
父子 Chunk、邻接扩展或召回调参混合：

1. 先在冻结模型、snapshot、问题模板和候选边界下比较可复用推理运行时；
2. READY 路由优化只能改变执行方式，不能删除 PostgreSQL 真值、物理路由
   身份、活动状态、Chunk 来源或检索后重验；
3. 不通过重复问题缓存、减少候选、放宽 300 ms 或更换模型来制造原 Gate
   通过；
4. 任一运行时替换必须独立验证模型身份、候选集合、排序质量、失败关闭和
   Windows P95；
5. 性能 Gate 通过前，固定 Reranker 保持非默认；原 RRF 路径继续作为阶段
   2 的默认可用基线。

正式 MinIO、OCR、目标规模压测、完整故障矩阵、灰度和生产回滚仍由各自
后续要求跟踪，不属于阶段 2 退出条件。
