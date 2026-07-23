# 阶段 2 差距冻结与最小真实生成 Gate

## 1. 依据与单变量边界

本 Gate 对照最高方案第 10.3 节，只改变生成边界。检索继续复用已有实现和证据，不修改 ES/Milvus Mapping、Embedding、候选数、向量阈值、RRF `k=60` 或最终 `top_k=3`，也不引入新的基础设施或依赖。

| 能力 | 冻结判断 | 本 Gate 是否改变 |
|---|---|---|
| Hybrid | ES+Milvus RRF 已实现；远程 15 题为 14/15，与 ES 持平，未晋级默认；175 题不为追求满分继续调参 | 否 |
| Reranker | 已以固定 `bge-reranker-v2-m3` 重排冻结 `local_rrf` 前 20 候选；本地 `test=100` 质量门和目标 RTX 4090 组件 P95 均通过；READY/ACL 与 RRF 后的可选在线窄适配器已本地实现，但默认路由未改变 | 在线实现不改召回、融合或生成；Windows 组合 P95 仍是独立 Gate |
| Evidence/引用 | 已有结构化 Evidence/Citation；ACL、READY、活动版本、Chunk 身份和页码由检索与事实源先行校验 | 只增加模型引用编号校验 |
| Fake LLM | 所有既有入口默认仍是 Fake，原 warning 和测试不变 | 新增显式注入的真实生成器，不静默替换默认路径 |
| Claim 支持度 | 确定性 Claim–Evidence 语义支持属于阶段 4；阶段 2 不用模型自评冒充 | 否 |

因此，“Hybrid 已比较”“Reranker 组件质量与目标硬件成本已通过”
“受控在线实现已本地完成”“已经默认启用并满足组合 P95”是四个不同结论。
前三项已有对应证据，最后一项仍需 Windows 独立运行 Gate，不能由
预计算候选上的 pair-scoring P95 或本地单元测试替代。

## 2. 最小真实生成闭环

新增的真实生成器位于授权检索之后：

```text
PostgreSQL READY/owner/版本路由
→ ES + Milvus RRF Evidence
→ 固定 Ollama 生成模型
→ 结构化 claims + citation_ids
→ 服务端组装 [n]
→ 引用编号存在性校验
→ COMPLETED 或 DEGRADED 证据卡
```

首个远程 READY 基线的生成身份冻结为：

- Provider：`ollama`；
- 模型：`llama3.2:latest`；
- 模型 SHA-256：`a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`；
- Prompt：`academic-evidence-answer-v1`；
- Prompt SHA-256：`796bf2fad94a92584d604479fb921bd98e72e4b97ecc09d6e49eaa2c0c71df71`；
- 解码：`temperature=0.0`、`seed=42`、`num_predict=384`、`num_ctx=8192`、`think=false`；
- 输出：JSON Schema 约束的 `claims[].text + claims[].citation_ids`，最终引用编号由服务端组装。

独立模型选型 Gate 已将阶段 2 候选晋级为 `qwen3:14b@bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`；Prompt、Schema 和解码保持相同，llama3.2 保留为已有 READY 证据的回退基线。

模型摘要漂移、模型不可用、JSON/Claim 结构非法、无引用或引用越界时，模型答案不得进入响应，API 返回 `DEGRADED` 和已验证 Evidence 卡。无 Evidence 时返回 `NO_EVIDENCE`，不调用生成模型。既有 Fake 路径只有在未注入真实生成器时使用，并继续携带原有 Fake 边界。

## 3. 本地运行证据

执行：

```bash
make real-generation-canary
```

本地真实模型对公开 Fixture Evidence 的结果为：

- 两次同输入回答字节一致；
- `COMPLETED`，引用编号通过存在性校验；
- 无证据问题为 `NO_EVIDENCE`，模型未调用；
- 越权文档范围返回 `403 RAG_FORBIDDEN_SCOPE`；
- 运行报告只保存模型/Prompt/解码身份、回答哈希和布尔门禁，位于被忽略的 `runtime/phases/source-phase2-real-generation-local-gate/canary.json`。

公开 Fixture 的真实模型 Canary 证明生成变量可运行，但不冒充远程 PostgreSQL/ES/Milvus 实跑。源码已把同一生成器注入点接在 `online_remote_rrf` 返回的 READY Evidence 之后，并由专项测试证明生成器不能先于在线检索和权限门禁消费内容。

远程恢复闭环已由用户在提交 `91aca5a` 完成：同一冻结模型摘要消费 PostgreSQL READY + ES/Milvus RRF 返回的 3 条 Evidence，Answer API 为 `COMPLETED`，引用编号校验与两次稳定回放通过；随后删除后 403、ES/Milvus/运行快照 3 项清理通过。脱敏报告 SHA-256 为 `E2231FADABB368209F976B2BAB99F4E1D841ACB3053C45A07B1ADDC7B386E937`，稳定错误码为 `NONE`，报告不含回答或 Chunk 正文。

Qwen READY 首次运行以 `PERSISTED_SNAPSHOT_ANSWER_HTTP_FAILED` 失败；同 Run ID 恢复已越过该边界并进入生成，稳定分类最终定位为 `REAL_GENERATION_INITIAL_OLLAMA_ANSWER_JSON_INVALID`。显式 `think=false` 后，用户在提交 `43dc5b4` 以原 Run ID 完成 retry3：PostgreSQL READY + ES/Milvus RRF 返回 3 条 Evidence，Qwen Answer API `COMPLETED`，身份摘要、引用编号、两次稳定回放、删除后 403 和三路清理均通过，字节回放本次也一致；报告 SHA-256 为 `0CB1B569D8A782FC526266E1A7193EF6299B66D5DBC72DCC989FDB951B8A1160`，稳定错误码为 `NONE`。

同提交的模型选型 v3 因冲突用例没有逐字出现“差异/不一致/冲突”而报告 `KEEP_LLAMA3_2`，但两次诊断均包含 `12周`、`16周` 与引用 `[1][2]`，生成、身份和禁词门禁全部通过。v4 只把该假阴性改为“两项冲突值 + 两条来源引用”的结构门禁；不修改模型、Prompt、Schema、解码或检索。用户在提交 `063236a` 完成远程 v4：Qwen `4/4`、llama3.2 `3/4`，结果 `PASS / PROMOTE_QWEN3_14B / NONE`，报告 SHA-256 为 `E031B1B4532571850FD4527D4930E80A3C144074DBB55F8055A54A51EDB7E038`。v3 原始假阴性报告继续保留。

## 4. 阶段 2 剩余差距

- 3 篇指定文档、9 个普通学术问答样本已完成远程 v2 验收：3 篇各 `3/3`、合计 `9/9` 通过真实生成、引用、版本、定位、三路清理和删除后 403；第 3 篇最终报告 SHA-256 为 `3C106423AB3575B11B3B0142A66F19A2C949B8BAED3457F1BCA101A9931302FA`；
- 固定 Cross-Encoder 已在冻结 `test=100` 上完成本地质量验证：`nDCG@10` 相对提升 `15.5331%`、`Precision@5 +0.02`，四个关键类型不退化；目标 Windows RTX 4090 复跑保持相同质量和身份，Reranker 阶段 `P50=169.3867 ms / P95=188.22683 ms`，稳定错误码为 `NONE`；
- 受控在线窄适配器已本地实现：PostgreSQL READY/ACL 和 ES/Milvus RRF 先返回并重验至多 20 个候选，Reranker 只排序并输出前 3；标题/模型/分数故障回退同一批已授权 RRF，身份漂移仍失败关闭；
- 下一独立 Gate 在 Windows RTX 4090 上以至少 30 个样本验证无回退、无候选扩张和包含 READY 路由、召回、融合、重排的组合 `P95 <= 300 ms`，不与生成、Embedding、RRF 参数变化混合；通过前默认路由不变；
- Claim 语义支持、冲突处理、正式 MinIO、OCR 和目标规模性能继续由各自后续 Gate 跟踪。

阶段 2 因此仍为 `IN_PROGRESS/PARTIAL`。llama3.2 与 Qwen 的远程 READY
真实生成闭环、Qwen 最终晋级、固定普通科研问答远程 `9/9`、固定
Reranker 的本地质量门、目标硬件组件 P95 和受控在线本地实现均已完成；
Windows 组合检索 P95 与是否改变默认路由仍未完成。后续不把它与
MinIO/OCR、通用性能或生成变量混合。
