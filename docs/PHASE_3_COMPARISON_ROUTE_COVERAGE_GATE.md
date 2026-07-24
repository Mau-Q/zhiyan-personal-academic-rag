# 阶段 3 双文档路由覆盖 Gate

## 结论

本 Gate 已冻结并完成阶段 3 第二个单一变量的默认关闭实现，也已完成一次
用户运行的远程配对 dev Gate：

```text
BILATERAL_COMPARISON_ROUTE_COVERAGE_TOP3_V1
```

它不改写问题、不增加召回、不改变 RRF 分数。仅当请求明确包含比较标记、
PostgreSQL 已解析出恰好两个授权 READY 文档路由且最终输出仍为 Top-3 时，
从完整既有 RRF 顺序中保留两条路由各自排名最高的一个候选，再按原 RRF
顺序补足第三个候选。候选、分数、身份或选择结果无法证明时回退原 RRF Top-3。

Windows Run ID `phase3_comparison_route_coverage_dev_20260724_01` 的结果为
可信质量失败，裁决为 `KEEP_COMPARISON_ROUTE_COVERAGE_DISABLED`：

- 四个目标 Treatment 均为 `APPLIED`，其中 3 个改变了 Top-3；
- Control/Treatment 双侧 Top-3 命中均为 `0/4`；
- 两分支 Recall@3 均为 `0.145833`、nDCG@3 均为 `0.220967`，增益均为 0；
- 固定 15 题为 `14/15`；
- 清理 9/9、READY 失败关闭和删除后 403 均通过，无需恢复。

报告 SHA-256 为
`C2758BE68E614D5E075595B34C2386FA200B7DE13358DF8DB5193CCAD69A6A19`，
裁决 SHA-256 为
`7492DC7574A2176351DDEEBCDED80230D66216FA2C923BBB4713182945CE4797`。
不得调参或复用该 Run ID，`test/Acceptance` 继续封存。

## 为什么选择这个变量

`BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1` 的可信在线 `_07` 结果显示：

- Control/Treatment 的双侧 Top-3 命中均为 `0/4`；
- Recall@3 没有增益；
- nDCG@3 下降 `0.017739`；
- 清理、身份和非目标不退化证据可信，无需恢复。

因此不能继续修改或调参重跑查询拆分。现有在线实现已经对每个 READY 文档
路由分别执行 ES 和 Milvus，再统一进行 RRF；下一假设直接作用于最终 Top-3
覆盖，且不改变召回和融合参数，是更小且可证伪的变量。

由于 `_07` 没有保留可提交的逐样本 Top-20 私有排名，本地不能预先声称目标
Chunk 一定存在于候选中。若某一路没有候选，本变量必须回退，并由未来配对
dev Gate 如实失败，而不是扩大候选或调参制造通过。

## 复用评估

### 仓库与既有项目

优先复用：

- `OnlineVersionRrfRetriever` 的 PostgreSQL READY/owner 路由；
- `RankedChunk` 与现有排名验证；
- 当前 ES/Milvus 每路召回和完整 RRF 顺序；
- 已有默认关闭、观察和失败回退模式。

已检索 `zhiyan-paper-reading-agent`、`zhiyan-data-quality-center`、
`zhiyan-patent-drafting-agent` 和既有知识库远程后端，没有发现满足当前
owner/版本/双路 RRF 合同的分组 Top-K 选择器。

### 上游组件

| 组件 | 结论 | 原因 |
|---|---|---|
| [Elasticsearch RRF retriever](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion) | 不采用 | 能融合 ES 子检索器，但不能在仓库的 ES+Milvus 联合 RRF 后保证文档覆盖 |
| [Milvus Grouping Search](https://milvus.io/docs/grouping-search.md) | 不采用 | 只约束单个 Milvus ANN 结果；当前是版本级 Collection 加外部 ES/Milvus 融合 |
| [Haystack DocumentJoiner](https://docs.haystack.deepset.ai/docs/documentjoiner) | 不采用 | 复用了 RRF/合并概念，但不提供当前精确的两条授权路由 Top-3 合同 |
| [LangChain MMR](https://reference.langchain.com/python/langchain-core/vectorstores/utils/maximal_marginal_relevance) | 不采用 | 需要候选向量和 `lambda_mult`，优化语义多样性但不保证 document_id 覆盖 |

结论是：不新增依赖，不引入框架；复用仓库现有窄合同，实现一个确定性选择器。

后续新增非平凡能力都必须先检查本仓库、既有项目和维护中的上游组件，并记录
“直接复用、窄适配或不采用”的结论。第三方组件不能接管 PostgreSQL 事实源、
ACL、READY、统一身份或清理合同。

## 冻结合同

### 唯一变量

- 配置：`evaluation/phase3/bilateral-comparison-route-coverage-top3-v1.json`
- 配置 SHA-256：`bdf7b0616812362966189e5ebaf374d705f4537a6e3e06a99efc6b480209a9d0`
- 开关：`PHASE3_COMPARISON_ROUTE_COVERAGE_ENABLED`
- 默认：`false`
- 适用：比较标记 + 恰好两个授权 READY 文档路由 + `top_k=3`
- 选择：两路各取原 RRF 最高候选，再按原 RRF 顺序补足
- 分数：原 RRF 分数不变
- 回退：`FALLBACK_TO_ORIGINAL_RRF_TOP3`

### 保持不变

- PostgreSQL READY/owner 前置；
- 持久化 Document/Version/Chunk 身份校验；
- ES/Milvus 每路并行召回；
- `candidate_k=20`；
- RRF `k=60`；
- Top-3；
- Reranker 关闭；
- 不增加 ES、Milvus、Embedding 或 LLM 调用；
- 不读取 `test/Acceptance`；
- 300 ms 性能 Gate 独立。

## 本地验收

- 配置字段、变量 ID、默认关闭和固定边界严格校验；
- 两路候选各保留一个，选中项仍按原 RRF 相对顺序输出；
- 原 Top-3 已覆盖两路时保持不变；
- 非比较、非两路、非 Top-3、候选不足、越界候选或异常均回退；
- 选择不能扩张 RRF 候选，最终排名重新编号且分数/载荷保持；
- 默认不注入选择器时，现有在线路径回归保持通过；
- 观察只记录枚举、计数、是否改变和耗时，不记录问题或候选正文。

## 远程 Gate 与结果

本 Gate 没有复制原 1300 行 runner，而是以冻结实验规格参数化既有组件：

- 私有输入包构建器和既有 ZIP/Manifest 身份；
- 隔离 owner 的三文档 READY 生命周期；
- Control `0/4` 停止规则、冻结 4 个 dev 与固定 15 题；
- 报告 SHA、HEAD、Run ID、配置和目标身份的独立裁决；
- 9 个清理任务、READY 失败关闭与删除后 403；
- 同一个 Windows PowerShell 5.1 用户入口。

用户既有项目中没有更强的 owner-scoped READY/清理证明 runner。Ragas 的实验
抽象与 MLflow 的评测数据/跟踪能力可管理通用实验，但不能证明本仓库的
PostgreSQL 事实、ACL、版本身份、ES/Milvus 清理和删除后 403；MLflow 还会
引入新的跟踪服务/数据存储。因此本 Gate 不新增依赖或服务。

Treatment 只开启本变量，查询拆分保持关闭。质量阈值沿用严格双侧 Top-3、
Recall@3、nDCG@3、固定 15 题和非目标不退化；选择器 P95 上限 `5 ms`，
增量检索 P95 上限 `50 ms`。实际选择器 P95 为 `0.049995 ms`，增量检索
P95 为 `-26.963305 ms`，非目标没有退化，但这些通过项不能覆盖目标质量与
固定 Canary 的硬失败。

运行报告使用
`phase3_comparison_route_coverage_paired_dev_report_v1`，必须证明四个目标
Treatment 均为 `APPLIED`；裁决使用
`phase3_comparison_route_coverage_dev_adjudication_v1`。入口和完整命令见
`deploy/remote/phase3-comparison-validation/README.md`。报告与裁决写入后，
PowerShell 脱敏汇总曾因完整报告不含可选 `primary_error_code` 而在严格模式
报错；这发生在证据落盘和清理完成之后，不影响质量裁决。本地修复复用同一
脚本并增加缺失安全的 JSON 属性读取，不要求重跑质量。该 Gate 前后均未读取
`test/Acceptance`，也未判定 300 ms SLO。
