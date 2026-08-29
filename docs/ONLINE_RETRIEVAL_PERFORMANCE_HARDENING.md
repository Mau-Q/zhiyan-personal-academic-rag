# 在线检索性能硬化记录

## 1. 当前结论

当前状态：`LOCAL_HARDENING_IMPLEMENTED_REMOTE_300MS_GATE_PENDING`。

本轮只处理仓库内部可以独立完成的在线检索执行层优化。历史 Windows 分段运行的
完整在线 `combined P95=504.71613 ms`、目标 `300 ms` 仍是已知未达成结果；本轮
没有新的远程主机运行，因此不能把代码改动写成 300 ms 已达标或已经取得新的
P95 数值。

## 2. 已实现的边界内改动

### 2.1 READY 物理路由校验并行

同一个 READY route 的 Elasticsearch 与 Milvus 物理路由校验都是只读操作，现由
两个受控线程并行执行。PostgreSQL READY 解析、物理身份校验和失败关闭语义没有
放宽；任一侧失败仍然使整个 route 解析失败。

### 2.2 单请求共享 Query Embedding

一次在线请求创建短生命周期的 embedding 协调器：

- 相同 route query 只计算一次向量；
- 多个不同 route query 通过 provider 的批量接口一次提交；
- Milvus route 接收已经计算的 query vector，只负责归一化、维度和索引身份校验；
- 模型身份只在当前请求内复用，不建立跨请求缓存，不改变模型或向量索引身份。

这消除了多文档请求中每个 route 重复调用 Query Embedding 的执行浪费，同时保留
每个 Milvus route 的来源指纹、模型身份和候选合同检查。

### 2.3 多 route 后端任务并行提交

所有 READY route 的 ES/Milvus 搜索任务先提交，再按稳定 route 顺序收集结果；线程池
有上限，避免请求范围扩大时无限创建线程。RRF 排名、`candidate_k=20`、`k=60`、
`top_k=3`、ACL、候选身份重验和检索后 PostgreSQL 重验均未改变。

### 2.4 READY 阶段与 Query Embedding 重叠

在 PostgreSQL 已确认 owner、READY 和请求范围合法后，在线检索会预热原始问题的
Query Embedding，并与 ES/Milvus 物理路由校验并行。该预热不在 PostgreSQL 事实确认
之前启动；启用查询拆分规划器时不预热原始问题，避免为已被替换的 route query
额外计算向量。预热耗时仍计入 Query Embedding 观测，失败仍按原有 fail-closed
路径处理。

### 2.5 物理校验请求合并

Elasticsearch 版本路由校验将 index identity/settings 与总量、owner/version
数量、active 数量分别收敛为一个身份读取和一个聚合计数请求；Milvus 路由校验
移除可由 `describe_collection` 覆盖的重复存在性探针。校验的身份字段、行/文档
数量、active 状态、模型身份和失败关闭边界没有放宽。

### 2.6 Milvus 路由校验内部并行

Milvus 路由校验现在并行取得 Collection 描述、Embedding 模型身份和完整逻辑行
快照，再按原顺序执行相同的字段、向量指纹、数量和 active 状态校验。并行只改变
只读校验的等待方式，不改变任何写入、生命周期、身份或失败关闭语义。

## 3. 细分观测与验证边界

本轮还把 READY 路由解析的总耗时拆成可脱敏的子阶段：PostgreSQL READY 查询、
ES 物理路由校验工作、Milvus 物理路由校验工作，以及两者并行的墙钟耗时。该观测
不改变路由身份、请求次数、失败关闭或缓存边界，用于区分事实源查询成本、物理路由
校验成本和线程并行调度成本。远程摘要会同时保留这些子阶段的 P50/P95。

本地测试覆盖：

- READY route 的 ES/Milvus 并行校验；
- 多 route 后端搜索的并行提交；
- 相同 query 的 embedding 调用次数和预计算向量传递；
- 预计算向量不再触发 Milvus provider 的重复 embedding；
- 原有检索、API、Reranker 和阶段 Gate 合同回归。

这些是代码与合同证据，不是远程性能证据。要判断是否缩小 `504.71613 ms` 与
`300 ms` 的差距，仍需在原目标硬件、冻结模型/输入/候选边界和独立性能 Gate 下
重新运行并记录新的分段 P50/P95。

## 4. 最新远程观测

用户在提交 `4bd20b300f4cf1fbbe29f5a613a34915753959ce`、Run ID
`online_retrieval_hardening_02` 上完成了 30/30 `APPLIED` 观测。阶段合同为 `PASS`，
无 fallback、候选扩张或候选边界违规，三路清理成功且删除后 Answer API 为 403；但
`combined P95=451.664035 ms`，仍因 `ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 失败。
其中 base retrieval P95 为 `321.346145 ms`，Reranker P95 为 `132.19982 ms`。

新的细分结果显示：PostgreSQL READY 查询 P95 仅 `0.733275 ms`，READY 物理校验
墙钟 P95 为 `135.59779 ms`，ES/Milvus 物理校验工作分别为 `121.245905/134.50391 ms`；
Query Embedding P95 为 `155.4337 ms`，后端并行墙钟 P95 为 `189.226644 ms`。
因此当前主要剩余成本在物理路由校验、Query Embedding 与重复的后端验证工作，而非
PostgreSQL 或 RRF。该结果是新的远程失败证据，不是 300 ms 达标证据。

随后用户在提交 `e8b095f67081755a0062cd6c689132a7b2ac9616`、Run ID
`online_retrieval_hardening_03` 上完成 30/30 `APPLIED` 观测。阶段合同仍为 `PASS`，
但 `combined P95=339.26415 ms`，base retrieval P95 已降至 `208.942905 ms`，
Reranker P95 为 `132.377305 ms`，因此仍以同一组合 P95 门禁失败。READY 物理校验
墙钟 P95 为 `134.69246 ms`，Milvus 物理校验工作仍为 `133.720935 ms`；后端并行
墙钟降至 `98.26941 ms`。这证明前一轮的预热与 ES 请求合并有效，但下一瓶颈仍是
Milvus 路由校验和组合 Reranker 预算。

## 5. 明确未处理的事项

- 正式 Acceptance、真实用户评价和生产运维仍需要相应外部参与或独立工作流；
- 本轮没有更换模型、放宽阈值、减少候选、引入重复问题缓存或修改默认 RRF；
- 本轮没有重开 Phase 3 排序优化、查询拆分、路由覆盖、NLI 或阶段 5；
- 本轮没有运行真实生成或正式 Acceptance；远程性能 Gate 由用户在 Windows 目标
  硬件上执行，Mac 只根据其脱敏摘要判断。
