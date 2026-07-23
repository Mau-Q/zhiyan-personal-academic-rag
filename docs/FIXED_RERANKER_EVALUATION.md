# 固定 Cross-Encoder Reranker 评测

## 1. Gate 边界

本 Gate 只增加固定 Reranker，不修改：

- 500 题工程集及其 `dev/test/acceptance=300/100/100` 拆分；
- 316 个源 Chunk 及相关性标签；
- BGE-M3 Embedding、SQLite/向量召回、RRF、候选数或 `k=60`；
- Qwen、Prompt、生成 Schema、ACL、READY 或在线版本路由。

质量决策只使用冻结的 `test=100`，不计算 Acceptance 指标，也不根据
`dev` 或中间结果调模型。Reranker 只重排每题已有的前 20 个
`local_rrf` 候选，不能增加候选、扩大授权范围或改变
`NO_EVIDENCE/FORBIDDEN` 决定。

## 2. 复用边界

模型加载、分词、Batch 推理和 MPS/CUDA 设备执行复用
`sentence-transformers.CrossEncoder`。仓库继续负责：

- 模型 revision、snapshot SHA-256 和输入模板身份；
- 冻结候选、Chunk/文档身份和候选集合不扩张；
- 排名合同、nDCG、Precision、关键类型与 P95；
- 质量保留/回退和默认在线路由决策。

`sentence-transformers` 只位于 `reranker` 可选依赖，不进入基础安装。
Hugging Face 的 remote code 被显式禁用。

## 3. 冻结配置

本机质量配置见
`evaluation/reranker/fixed-cross-encoder-v1.json`：

- 模型：`BAAI/bge-reranker-v2-m3`；
- revision：`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`；
- snapshot SHA-256：
  `f9dd638f0b27b57667d99b01f83ca4dbb3c82983911a1ef31a4601c7b890eaec`；
- 输入：`question + title + section_path + Chunk text`；
- `max_length=512`，超长输入尾部截断；
- `batch_size=16`；
- 候选前 20，输出前 20；
- 指标：`nDCG@10`、`Precision@5`、关键类型和 P95。

保留条件在运行前冻结为：

1. `test nDCG@10` 相对 `local_rrf` 增益至少 8%；
2. `Precision@5` 不下降；
3. comparison、exact lookup、multi-hop、standards freshness 四类
   `nDCG@10` 回退均不超过 0.02。

## 4. 本地质量证据

MacBook Air M4、16 GB、MPS 的冻结 `test=100` 结果：

| 指标 | `local_rrf` | 固定 Reranker | 变化 |
|---|---:|---:|---:|
| `nDCG@10` | 0.647269 | 0.747810 | +0.100541， relative +15.5331% |
| `Precision@5` | 0.231111 | 0.251111 | +0.020000 |
| `Recall@10` | 0.812037 | 0.843519 | +0.031482 |
| `MRR@10` | 0.699365 | 0.834828 | +0.135463 |

四个关键类型均通过不退化门禁：

- comparison：`nDCG@10 +0.091513`；
- exact lookup：`+0.185397`；
- multi-hop：`+0.006447`；
- standards freshness：`+0.004421`。

运行共处理 100 题、1952 个 query-passage pair；31 对超过 512 token
并按冻结规则截断，最大观测长度 775 token。本机 Reranker 阶段
`P50=7734.334 ms / P95=11839.113 ms`，只证明 M4 本地执行成本，
不能冒充 RTX 4090 或生产 P95。

运行报告位于被忽略的
`runtime/evaluation/formal-retrieval-v1/ai-audited-engineering-v1/reranker-bge-v2-m3-v1/`：

- decision SHA-256：
  `1716fb0d19bef25ae127d84c930a391fe11ef2e9e9dda542070bb6435f37c301`；
- rankings SHA-256：
  `054c91b6df1939b7f1f5e831df3eafad2e5a5099f89bc41c203d7276d628ee86`；
- metrics SHA-256：
  `a6754415768cc4387c5ee9942226264fbc3a803cd04cc5d2932cdd8798b97b28`。

## 5. 目标硬件证据与组件去留

本地质量结论曾为
`RETAIN_FIXED_CROSS_ENCODER_PENDING_TARGET_HARDWARE_P95`。用户随后在
Windows RTX 4090 上以提交
`d31e992713ea60827a5084c456ec050d927e2187` 完成同一冻结 Gate：

- PyTorch `2.13.0+cu126`、CUDA `12.6`、NVIDIA GeForce RTX 4090，
  驱动 `591.86`；
- 模型 revision 与 snapshot SHA-256 和本地冻结身份一致；
- `test=100`、1952 个 pair、31 个截断 pair 与本地运行一致；
- `nDCG@10=0.747810`、相对增益 `15.5331%`、
  `Precision@5=0.251111`、增量 `+0.020000`，关键类型门禁通过；
- Reranker 阶段 `P50=169.3867 ms / P95=188.22683 ms`；
- `stable_error_code=NONE`；
- 脱敏 run-report SHA-256：
  `D010FED8CFDC8D477FE816BD3C7DB6647F406560827B433A15526ED77B97562C`；
- decision SHA-256：
  `FF0E3852D37A12A4485E899437EEFAA71DA4203CB2E27718434F762839D8DA9E`。

目标硬件证据满足固定组件的质量与可执行成本检查，组件决策收口为
`RETAIN_FIXED_CROSS_ENCODER_FOR_CONTROLLED_ONLINE_INTEGRATION`。
这不是“已在线启用”：本次 P95 只计预计算候选之后的 pair scoring，
不包含 PostgreSQL READY 路由、ES/Milvus 召回与 RRF。默认在线路由继续
保持不变；下一独立 Gate 才能把 Reranker 接在权限过滤和 RRF 候选之后，
并验证候选集合不扩张、失败关闭、回退和组合检索 P95。

Reranker 不负责无证据阈值、ACL 或拒答，因此现有正式工程集中的
no-answer/forbidden 检测缺口不被本次排序增益掩盖。

Windows 配置位于
`evaluation/reranker/fixed-cross-encoder-windows-rtx4090-v1.json`，
用户运行入口为
`deploy/remote/reranker-validation/run_fixed_reranker_gate.ps1`。
由于正式题目、标注、Chunk 和排名按合同不进入 Git，Mac 先运行
`make fixed-reranker-input-package`，生成被忽略的
`runtime/handoffs/fixed-reranker-input-v1.zip`。固定包 SHA-256 为
`4884a5a9f2101ef203a55b58e25c82f74ac7f035a074760af5fd103eb198e9fe`；
用户自行传到 Windows 后通过 `-InputPackagePath` 交给脚本。脚本先验证
整包摘要，再只向被忽略的 `runtime/` 解压，并逐文件复核五份输入摘要。

该脚本面向 Windows PowerShell 5.1；只在 Mac 推送成功且 Windows
检出同一 `origin/main` 后运行。脚本拒绝已跟踪或已暂存修改；未跟踪的
评审材料不会阻断本 Gate，因为模型与五份冻结输入仍须逐项通过 SHA-256
身份校验。目标运行时固定使用 PyTorch `2.13.0+cu126` 和官方
`https://download.pytorch.org/whl/cu126` 索引；脚本在模型运行前验证
`nvidia-smi`、CUDA 12.6、RTX 4090 和一次真实 CUDA 张量分配，并在
脱敏摘要中记录 PyTorch、CUDA、GPU 和驱动身份。模型权重、题目、Chunk、
排名和运行报告继续只保留在被忽略的 `runtime/`。

## 6. 受控在线集成

固定组件已通过窄适配器接入可选在线路径，但尚未晋级为默认路由：

```text
PostgreSQL READY/owner/版本解析与检索后重验
→ ES + Milvus RRF 前 20 个已授权候选
→ 固定 Cross-Encoder 重排
→ 前 3 个 Evidence
→ 既有 Answer 构建或生成
```

实现位于 `backend/retrieval/online_reranker.py`，在线编排位于
`backend/rag/online_consumer.py`。配置
`evaluation/reranker/online-fixed-cross-encoder-windows-rtx4090-v1.json`
继续固定同一模型、revision、snapshot、输入模板、`max_length=512` 和
`batch_size=16`。标题由服务端受信提供者按 `document_id` 注入，模型无权
读取或决定 owner、READY、活动版本或物理路由。

在线边界如下：

- Reranker 只能重新排列已经通过 owner/READY、持久化 Chunk 身份与检索后
  重验的候选，不能生成、补充或跨文档扩张候选；
- 标题不可用、模型加载/推理失败或分数非法时，显式回退同一批已授权 RRF
  候选，并记录稳定失败类别；
- owner、版本、文档、活动状态或 Chunk 身份无法证明时继续失败关闭，
  不允许借回退绕过权限和事实源；
- 未注入在线 Reranker 时行为与原默认路由完全相同。

Windows 综合门禁由
`deploy/remote/reranker-validation/run_online_reranker_gate.ps1` 执行。
它复用隔离的 Stage 1 生命周期 Canary，关闭真实生成以保持单变量，并以
冻结 3 题各重复 10 次取得至少 30 个样本。硬门禁要求全部为
`APPLIED`、候选不超过 20、输出不超过 3、无回退或候选扩张，且从
PostgreSQL READY 路由开始、包含 ES/Milvus 召回、RRF 与重排的组合
`P95 <= 300 ms`。即使性能或回退门禁失败，脚本也先完成 INACTIVE、
三路清理和删除后 403，再返回稳定错误码。

用户在 Windows RTX 4090 上执行首个受控在线运行
`online_reranker_20260723_01`。同一 Run ID 从初始 Answer 403 恢复后，
运行达到至少 30 个 `APPLIED`、无回退和无候选扩张的组合延迟判定，但以
`ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 失败。旧失败报告只保留稳定错误码，
没有保留具体 P50/P95，因此不能从该次运行反推或引用精确延迟。错误在
INACTIVE、三路清理和删除后 403 检查之后才返回，但旧报告同样没有把这些
关闭证据写入失败摘要。

随后只将每个 READY 路由的 ES 与 Milvus 两个只读召回并行执行；
PostgreSQL READY/ACL、检索后重验、`candidate_k=20`、RRF `k=60`、向量
阈值、固定模型和 `top_k=3` 均未改变。用户在提交 `fb54918` 以新 Run ID
`online_reranker_parallel_20260723_01` 完成远程复跑：30/30 为 `APPLIED`，
无回退、候选扩张或边界违规，三路清理与删除后 403 通过；但 base retrieval
`P50=309.47805 ms / P95=344.676365 ms`，Reranker
`P50=128.504 ms / P95=131.885375 ms`，combined
`P50=436.2064 ms / P95=472.190015 ms`，仍以
`ONLINE_RERANKER_COMBINED_P95_EXCEEDED` 失败。报告 SHA-256 为
`132DFFDECDAD02F9C5280FADFBD09B5AE100C1DB31FE07118BF97B6E0C1B2602`。

base retrieval 的 P95 已单独超过整个 300 ms 预算，因此继续只优化 Reranker
无法使组合门禁通过。随后只增加脱敏分段观测，不改任何检索结果或参数。
用户在提交 `3303bed1c6faead6980dc5246a9d0a0a06d1a751` 和 Run ID
`online_retrieval_profile_20260723_01` 上取得 30/30 `APPLIED`：
base retrieval `P50=287.5011 ms / P95=376.394385 ms`，Reranker
`P50=129.59815 ms / P95=132.456 ms`，combined
`P50=416.2398 ms / P95=504.71613 ms`。分段状态为 `PASS`，其中 READY
路由解析 `P95=145.48693 ms`、Query Embedding `P95=189.838925 ms`、
后端并行墙钟 `P95=214.176715 ms`，ES 总工作 `P95=35.634955 ms`、
Milvus ANN `P95=6.03377 ms`、RRF `P95=0.12001 ms`。三路清理与删除后
403 通过，报告 SHA-256 为
`235FE36A97B7F4E462AD502595CB0CF38C139022703B6C4EA1E93E19D3AC765B`。

最终结论为
`REMOTE_PROFILE_COMPLETE_COMBINED_P95_EXCEEDED_RRF_DEFAULT_RERANKER_OPTIONAL`。
默认在线路由继续保持原 RRF，固定 Reranker 仅保留为未默认启用的可选组件。
阶段 2 的质量、保留/回退决定与功能边界已经完成；推理与 READY 路由性能
硬化移入阶段 3 的独立 Gate，不能把该阶段结论写成 300 ms 已达标。
