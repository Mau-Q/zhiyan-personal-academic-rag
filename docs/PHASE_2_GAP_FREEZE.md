# 阶段 2 差距冻结与最小真实生成 Gate

## 1. 依据与单变量边界

本 Gate 对照最高方案第 10.3 节，只改变生成边界。检索继续复用已有实现和证据，不修改 ES/Milvus Mapping、Embedding、候选数、向量阈值、RRF `k=60` 或最终 `top_k=3`，也不引入新的基础设施或依赖。

| 能力 | 冻结判断 | 本 Gate 是否改变 |
|---|---|---|
| Hybrid | ES+Milvus RRF 已实现；远程 15 题为 14/15，与 ES 持平，未晋级默认；175 题不为追求满分继续调参 | 否 |
| Reranker | 尚未接入固定 Cross-Encoder；现有 Baseline 没有稳定排序增益依据，决策保持 `DEFER_RERANK` | 否 |
| Evidence/引用 | 已有结构化 Evidence/Citation；ACL、READY、活动版本、Chunk 身份和页码由检索与事实源先行校验 | 只增加模型引用编号校验 |
| Fake LLM | 所有既有入口默认仍是 Fake，原 warning 和测试不变 | 新增显式注入的真实生成器，不静默替换默认路径 |
| Claim 支持度 | 确定性 Claim–Evidence 语义支持属于阶段 4；阶段 2 不用模型自评冒充 | 否 |

因此，“Hybrid 已比较”“Reranker 已作延期决策”“真实 Reranker 已验证”是三个不同结论。第三项仍未完成，不能由前两项替代。

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

同提交的模型选型 v3 因冲突用例没有逐字出现“差异/不一致/冲突”而报告 `KEEP_LLAMA3_2`，但两次诊断均包含 `12周`、`16周` 与引用 `[1][2]`，生成、身份和禁词门禁全部通过。v4 只把该假阴性改为“两项冲突值 + 两条来源引用”的结构门禁；不修改模型、Prompt、Schema、解码或检索，必须独立远程重跑后再确认最终晋级决策。

## 4. 阶段 2 剩余差距

- 以修正后的 v4 结构语义门禁重跑固定四题模型选型，保留 v3 假阴性原始报告；
- 在冻结的指定文档与普通学术问答样本上记录真实生成、引用、版本和定位结果；
- 如要满足“固定 Reranker 增益验证”的字面退出条件，需先出现可测排序缺口，再单独接入一个 Cross-Encoder 做保留/回退实验；当前不得与生成变量一起引入；
- Claim 语义支持、冲突处理、正式 MinIO、OCR 和目标规模性能继续由各自后续 Gate 跟踪。

阶段 2 因此仍为 `IN_PROGRESS/PARTIAL`。llama3.2 与 Qwen 的远程 READY 真实生成闭环均已完成；Qwen 最终晋级仍待 v4 固定四题远程结果。后续不把它与 Reranker、MinIO/OCR 或性能变量混合。
