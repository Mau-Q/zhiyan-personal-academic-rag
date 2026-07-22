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

生成身份冻结为：

- Provider：`ollama`；
- 模型：`llama3.2:latest`；
- 模型 SHA-256：`a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`；
- Prompt：`academic-evidence-answer-v1`；
- Prompt SHA-256：`796bf2fad94a92584d604479fb921bd98e72e4b97ecc09d6e49eaa2c0c71df71`；
- 解码：`temperature=0.0`、`seed=42`、`num_predict=384`、`num_ctx=8192`；
- 输出：JSON Schema 约束的 `claims[].text + claims[].citation_ids`，最终引用编号由服务端组装。

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

## 4. 阶段 2 剩余差距

- 在用户操作的远程环境中，用扩展后的隔离 Stage 1 Canary 和同一模型摘要，对 PostgreSQL READY + ES/Milvus RRF Evidence 完成两次稳定真实回放；报告只新增生成身份、回答哈希和引用门禁，不保存回答正文；
- 在冻结的指定文档与普通学术问答样本上记录真实生成、引用、版本和定位结果；
- 如要满足“固定 Reranker 增益验证”的字面退出条件，需先出现可测排序缺口，再单独接入一个 Cross-Encoder 做保留/回退实验；当前不得与生成变量一起引入；
- Claim 语义支持、冲突处理、正式 MinIO、OCR 和目标规模性能继续由各自后续 Gate 跟踪。

阶段 2 因此仍为 `IN_PROGRESS/PARTIAL`，本 Gate 只把“没有真实生成模型”推进为“本地真实生成已验证，远程 READY 闭环待用户执行”。
