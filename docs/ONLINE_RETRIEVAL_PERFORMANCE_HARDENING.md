# 在线检索性能硬化记录

## 1. 当前结论

当前状态：`LOCAL_HARDENING_IMPLEMENTED_REMOTE_300MS_GATE_PENDING`。

本轮继续只处理仓库内部可以独立完成的在线检索执行层优化。已知 Windows 远程
Run 11 的 `combined P95=310.283465 ms` 仍高于目标 `300 ms`；因此不能把本地
变更或 Run 11 写成 300 ms 已达标。

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

Milvus 路由校验先并行取得 Collection 描述和 Embedding 模型身份；在描述确认
`chunk_count` 后，以最多 `chunk_count + 1` 的上界读取完整逻辑行快照，再按原顺序
执行相同的字段、向量指纹、数量和 active 状态校验。这个上界仍能识别多余行，且
不会放宽任何写入、生命周期、身份或失败关闭语义；它只避免在线验证向 Milvus
请求一个远大于实际版本大小的通用行数上限。

### 2.7 同请求复用已验证路由证明

READY 物理校验完成后，会把本次请求内已经验证的 ES/Milvus identity metadata
传给后端搜索。后端仍对 PostgreSQL Chunk snapshot 做本地 source fingerprint 和
数量核对，但不重复发起同一物理路由的 identity/model/逻辑行验证请求；如果证明
缺失则自动回退完整后端校验。证明不跨请求缓存，检索后 PostgreSQL revalidation
和候选身份检查保持不变。

### 2.8 Reranker Batch-20 受控性能变体

保留原冻结 V1 配置（`batch_size=16`）不变，新增仅供独立性能实验使用的 V2
配置（`batch_size=20`）。由于在线候选上限固定为 20，V2 使一次完整候选集进入
一个 Cross-Encoder forward batch；模型 ID、revision、snapshot、输入模板、
`max_length=512`、候选上限、RRF、ACL 和失败回退均不变。V2 不是默认路由，也
不覆盖 V1 的质量证据，必须使用新的 Run ID 在目标 Windows RTX 4090 上重新验证。

### 2.9 Ollama 单查询轻量端点

对不超过 2048 个字符的单条查询，Embedding provider 使用同一 Ollama 模型的
`/api/embeddings` 单输入接口；批量输入和更长文本继续使用 `/api/embed`，保留
`truncate=true`。两条接口都显式发送顶层 `keep_alive="10m"`，只约束模型驻留
时间，不改变模型、查询文本、向量维度或索引身份。下游 Milvus/本地向量路径仍
执行既有 L2 归一化；超长输入不走单输入快路径，避免改变既有截断语义。该变更
尚待新的远程 Run 验证。

### 2.10 READY 后 Chunk snapshot 预热

PostgreSQL 已确认精确 owner、READY 和请求范围后，在线检索会把对应的
`document_version_id` 交给一个短生命周期的只读预热任务，在 ES/Milvus 物理路由
校验期间加载 Chunk snapshot。物理路由返回后仍按原逻辑核对版本集合、Chunk ID
唯一性、ACL、来源指纹和后续 PostgreSQL revalidation；预热失败或结果不一致仍
失败关闭。该变化只重叠等待时间，不建立跨请求缓存，也不改变 READY、候选边界、
RRF 或证据语义，远程 Run 12 未证明其独立稳定收益。

### 2.11 有界 Milvus 在线逻辑行读取

Run 12 的 Milvus 物理校验工作仍接近 READY 物理校验墙钟，因此本轮只改变在线
读取的请求上界：先取得并验证 Collection 元数据，再以 `chunk_count + 1` 作为
逻辑行查询 `limit`。返回的仍是完整字段，仍执行 owner/document/version、Chunk
唯一性、payload、向量、Embedding 指纹和 active 状态校验；`+1` 保留了发现多余
实体的能力。该变更不使用跨请求缓存、不跳过模型身份或 PostgreSQL revalidation，
等待目标 Windows 上的单变量复测。

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
- 原有检索、API、Reranker 和阶段 Gate 合同回归；
- V1 冻结配置与 V2 Batch-20 配置的模型/候选身份一致性；
- Ollama 短单查询、长单查询和批量查询的端点选择与响应校验；
- READY 版本回调先于物理路由校验，以及 Chunk snapshot 预热结果的完整消费。

这些是代码与合同证据，不是远程性能证据。Run 11 已对 READY 后 Chunk snapshot
预热进行了远程验证，但 `310.283465 ms` 仍高于 `300 ms`，且单次运行不能证明
稳定收益；后续如继续优化，仍需先在本地对 Ollama、READY/Milvus 和 Query Embedding
做分段 profiling，并一次只选择一个变量。

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
Milvus 路由校验、Embedding 尾部等待和组合 Reranker 预算。

随后用户在提交 `b2cff12b502b82d1c6a7636c647d7cb96bfc9c26`、Run ID
`online_retrieval_hardening_04` 上完成 30/30 `APPLIED` 观测。阶段合同仍为 `PASS`，
`base retrieval P95=211.641675 ms`、`combined P95=341.631065 ms`、Reranker
P95 为 `132.96753 ms`；READY 物理校验墙钟 P95 降至 `118.789225 ms`，Milvus
物理校验工作降至 `117.81636 ms`，后端并行墙钟为 `101.249855 ms`。清理 3/3、
删除后 403、无 fallback/扩张/候选越界均通过；300 ms 仍未达标。

随后用户在提交 `30fc0c27ba64a8cd1f1b40be1b759c3afb3d5754`、Run ID
`online_retrieval_hardening_05` 上完成 30/30 `APPLIED` 观测。阶段合同仍为 `PASS`，
`base retrieval P50/P95=177.5275/187.45609 ms`，
`combined P50/P95=307.26725/317.61022 ms`，Reranker P95 为 `132.521785 ms`。Query Embedding
P95 为 `179.00355 ms`，READY 物理校验墙钟 P95 为 `119.039845 ms`，Milvus
物理校验工作 P95 为 `117.98263 ms`，后端并行墙钟 P95 为 `82.82814 ms`。
清理 3/3、删除后 403、无 fallback/扩张/候选越界均通过；仍因
`ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 未通过 300 ms。

Run 06 使用 V2 Batch-20 配置完成 30/30 `APPLIED`，但未形成性能收益：
`base P50/P95=171.1937/195.881911 ms`，
`combined P50/P95=304.8259/324.23998 ms`，Reranker P95 为 `135.93435 ms`；相比 Run 05，
combined P95 反而上升，V2 不晋级。阶段合同、清理 3/3、删除后 403、无
fallback/扩张/候选越界均通过。该结果仍以 `ONLINE_RERANKER_COMBINED_P95_EXCEEDED`
失败，V1 保持冻结。

Run 07 的首次有效远程结果为 30/30 `APPLIED`，
`base P50/P95=155.2553/169.782839 ms`，`combined P50/P95=285.78895/300.160535 ms`，Reranker P95
为 `132.60169 ms`，Query Embedding P95 为 `161.194215 ms`。清理 3/3、删除后
403、无 fallback/扩张/候选越界和分段状态均通过，但严格 P95 门禁失败。

Run 08 在同一提交、同一 V1 配置下完成 30/30 `APPLIED`，
`base P50/P95=154.38905/173.3739 ms`，`combined P50/P95=285.13485/305.54851 ms`，Reranker
P95 为 `133.28295 ms`，Query Embedding P95 为 `164.994689 ms`。清理 3/3、
删除后 403、无 fallback/扩张/候选越界和分段状态均通过；该结果仍以
`ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 失败。Run 07 与 Run 08 的差异说明
当前组合尾延迟仍有波动，不能以 Run 07 的近似值声称稳定达标。第一次误用已完成
清理的 Run 07 重跑只得到无指标的通用 `ValueError`，不计入性能结果。

Run 09 在提交 `9f77d9a6b6ce498b863ceaf58f4ae1c062070316`、同一 V1 配置下完成
30/30 `APPLIED`，`base P50/P95=156.46445/170.65502 ms`，
`combined P50/P95=286.3625/301.03561 ms`，Reranker P95 为 `132.019835 ms`，
Query Embedding P95 为 `162.108379 ms`。清理 3/3、删除后 403、无 fallback/扩张/
候选越界和分段状态均通过；仍因 `ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 失败。

Run 10 在同一提交、同一 V1 配置下完成 30/30 `APPLIED`，
`base P50/P95=159.0704/180.381485 ms`，
`combined P50/P95=288.27255/319.39854 ms`，Reranker P95 为 `134.309035 ms`，
Query Embedding P95 为 `171.749935 ms`。清理 3/3、删除后 403、无 fallback/扩张/
候选越界和分段状态均通过；仍因 `ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 失败。
Run 09 与 Run 10 均未证明 `keep_alive="10m"` 的独立收益，当前只保留为待验证的
驻留策略，不改变默认 RRF 或 V1 冻结配置。

Run 11 在提交 `72e1e4ddc257a0f56d67ea726113642f44fc8004`、同一 V1 配置下完成
30/30 `APPLIED`，`base P50/P95=151.086499/180.419535 ms`，
`combined P50/P95=280.38975/310.283465 ms`，Reranker P95 为 `131.83538 ms`，
Query Embedding P95 为 `169.90922 ms`。READY route resolution P95 为 `112.600355 ms`，
物理验证墙钟 P95 为 `111.041285 ms`，Chunk snapshot P95 为 `111.744975 ms`；
清理 3/3、删除后 403、无 fallback/扩张/候选越界和分段状态均通过，但仍因
`ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 失败。相比 Run 10 的 combined P95 有下降，
但单次结果不足以证明 READY 后预热的独立收益，不能晋级为默认优化。

Run 12 在同一提交、同一 V1 配置下完成 30/30 `APPLIED`，
`base P50/P95=161.8413/195.848285 ms`，
`combined P50/P95=291.86095/326.252255 ms`，Reranker P95 为 `132.92608 ms`，
Query Embedding P95 为 `186.120074 ms`。READY route resolution P95 为 `114.18532 ms`，
物理验证墙钟 P95 为 `112.69045 ms`，Milvus 物理校验工作 P95 为 `111.678 ms`，
Chunk snapshot P95 为 `113.4019 ms`，后端并行墙钟 P95 为 `91.94626 ms`；清理
3/3、删除后 403、无 fallback/扩张/候选越界和分段状态均通过，但仍因
`ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 失败。相比 Run 11，combined P95 上升约
`15.97 ms`，因此现有预热收益不稳定，不能把该结果归因于某一项既有硬化。

Run 13 在提交 `ca5a399e2fa6172ff7322a59b35e66ea98fbece7`、同一 V1 配置下完成
30/30 `APPLIED`，`base P50/P95=154.2442/171.33452 ms`，
`combined P50/P95=283.85435/302.983085 ms`，Reranker P95 为 `132.81631 ms`，
Query Embedding P95 为 `162.41544 ms`。READY route resolution P95 为 `111.34351 ms`，
READY PostgreSQL lookup P95 为 `0.747805 ms`，物理验证墙钟 P95 为 `110.057155 ms`，
ES 物理校验工作 P95 为 `93.904575 ms`，Milvus 物理校验工作 P95 为 `108.48885 ms`，
Chunk snapshot P95 为 `110.669265 ms`，ES total work P95 为 `8.759165 ms`，Milvus
总工作 P95 为 `7.739835 ms`，后端并行墙钟 P95 为 `68.3716 ms`，READY revalidation
P95 为 `1.06041 ms`，RRF P95 为 `0.099675 ms`。清理 3/3、删除后 403、无
fallback/扩张/候选越界和分段状态均通过，但仍因
`ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 失败。相比 Run 12，combined P95 下降
`23.26917 ms`、base P95 下降 `24.513765 ms`，但仍超出 300 ms `2.983085 ms`；
报告 SHA-256 为 `323D765FBEBE23C8CC1D3B509698E7D366A73CE3EEB34AC99F3F5D9AFA92E02F`。
该结果支持有界 Milvus 逻辑行读取具有正向观测，但单次结果不足以证明稳定收益或晋级默认
路径。V1 Batch-16、默认 RRF、ACL、READY、向量身份和失败关闭语义保持不变。随后在同一
提交、同一 V1 配置下完成确认性 Run 14：30/30 `APPLIED`，
`base P50/P95=150.7967/178.04327 ms`，
`combined P50/P95=280.4708/309.49054 ms`，Reranker P95 为 `133.246075 ms`，
Query Embedding P95 为 `168.735645 ms`。READY route resolution P95 为 `113.32768 ms`，
READY PostgreSQL lookup P95 为 `0.734876 ms`，物理验证墙钟 P95 为 `111.88934 ms`，
ES 物理校验工作 P95 为 `95.913135 ms`，Milvus 物理校验工作 P95 为 `109.545291 ms`，
Chunk snapshot P95 为 `112.596415 ms`，ES validation/query/total work P95 为
`1.457475/7.91732/9.28996 ms`，Milvus validation/query-embedding/ANN/total work P95
为 `1.559585/168.735645/6.48632/8.083165 ms`，后端并行墙钟 P95 为 `82.487035 ms`，
READY revalidation P95 为 `0.97465 ms`，RRF P95 为 `0.11742 ms`，retriever total P95
为 `177.84161 ms`。清理 3/3、删除后 403、无 fallback/扩张/候选越界和分段状态均通过，
但仍因 `ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 失败；报告 SHA-256 为
`21155ADC74729F37150327D3AEA5F80F4664F7653183845F6A151A6A16064AB7`。
Run 13 的 `302.983085 ms` 与 Run 14 的 `309.49054 ms` 均未稳定低于 300 ms，说明当前
安全边界内的有界 Milvus 读取不足以收敛性能债。保留该语义不变的硬化，不再追加当前冻结
边界内的微优化；后续转入真实 Demo/界面/README 工作流，所有展示必须明确标注该性能债。

## 5. 明确未处理的事项

- 正式 Acceptance、真实用户评价和生产运维仍需要相应外部参与或独立工作流；
- 本轮没有更换模型、放宽阈值、减少候选、引入重复问题缓存、修改默认 RRF 或修改冻结 V1 配置；V2 Batch-20 仅作失败的隔离实验；
- 本轮没有重开 Phase 3 排序优化、查询拆分、路由覆盖、NLI 或阶段 5；
- Ollama 单查询轻量端点、显式模型驻留、READY 后 Chunk snapshot 预热与有界 Milvus
  在线逻辑行读取均已获得有限远程观测，但 Run 13/14 的 combined P95 分别为
  `302.983085/309.49054 ms`，未通过稳定 300 ms 性能门禁；当前性能债保持 deferred，
  不再在冻结边界内追加微优化。本轮没有运行真实生成或正式 Acceptance，Mac 只根据用户
  提供的脱敏摘要判断远程性能。
