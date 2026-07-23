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

## 5. 当前决策

本地质量结论为
`RETAIN_FIXED_CROSS_ENCODER_PENDING_TARGET_HARDWARE_P95`：

- 质量三道门全部通过；
- 默认在线路由暂不改变；
- Reranker 不负责无证据阈值、ACL 或拒答，因此现有正式工程集中的
  no-answer/forbidden 检测缺口不被本次排序增益掩盖；
- 在目标 Windows RTX 4090 上复用同一模型、revision、输入模板、
  `max_length=512`、`batch_size=16` 和 `test=100`，记录 P95 后再作
  最终启用或回退决定。

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
