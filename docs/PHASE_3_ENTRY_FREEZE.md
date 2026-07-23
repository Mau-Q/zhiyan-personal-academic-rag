# 阶段 3 入口冻结

## 1. Gate 结论

阶段 3 的第一个 Gate 只完成入口冻结，不实现增强。方案阶段 3 继续记为
`NOT_STARTED`，当前工程状态为
`source-phase3-entry-frozen-cross-document-imbalance`。

首个目标失败类型冻结为 `CROSS_DOCUMENT_IMBALANCE`：两文档比较题的
Top-3 只覆盖一侧相关文档。唯一允许进入下一 `dev` 实验的主要变量为
`BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1`。默认 PostgreSQL
READY/owner、持久化身份校验、ES/Milvus 并行召回与 RRF 均不改变，固定
Cross-Encoder 继续关闭。

机器可读冻结见 `machine/phase3_entry_freeze.json`，长期决策为
`PD-039`。

## 2. 证据边界

本 Gate 只读取已有私有运行资产中的 ID、split、枚举标签、Chunk 身份、
相关性等级和排名元数据，没有把问题、答案、Claim、Chunk 正文或运行报告
提交到 Git，也没有读取 `test` 或 `acceptance` 内容。

现有成员 B 人工失败归因 CSV 尚不存在，因此本 Gate 不冒充“105 题人工失败
归因完成”。目标集使用更窄的确定性筛选：

1. 来自 175 题人工校验资产的 `dev`；
2. 四题均为人工 `APPROVE_AS_IS`，问题范围、Answerability、相关性、
   Claim–Evidence 与引用检查全部通过；
3. 四题均为 `ANSWERABLE` 两文档比较题，两个文档各有 `relevance >= 2`
   的冻结 Chunk；
4. ES 和 Milvus 的 `dev` 单路严格结果均为失败；
5. 冻结本地 RRF Top-3 均只覆盖一侧相关文档；
6. 缺失侧相关 Chunk 在同一冻结本地 RRF Top-50 中仍未出现。

第 6 项说明这不是单纯把已有候选重新排序即可修复的近失误，因而不选择
Reranker 或文档多样性重排作为首变量。远程 ES/Milvus RRF 尚未在这四题上
形成同身份 `dev` 回放，因此下一质量 Gate 必须先生成原路径配对 control；
若 control 与本冻结的失败形态矛盾，立即停止并重新审查入口，不把本地 RRF
写成远程默认路径实测。

## 3. 目标失败集与身份

固定样本共 4 条，全部为 `dev`：

- `local3.assisted.0033`
- `local3.assisted.0304`
- `local3.assisted.0383`
- `local3.assisted.0387`

按上述顺序、每个 ID 后接换行的 SHA-256 为
`3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8`。

来源身份：

| 资产 | SHA-256 |
|---|---|
| 175 题人工最终决策 | `a428a8fc92cece0d1aaf7e31ce11377bec2791e146b64efdc9e2ef1279800986` |
| `dev` ID/枚举元数据 | `f107f98c3d7c0777c233e8b479384e7c2edd2470acb7f5ea9098d662f57b8f3b` |
| 工程评测 items | `940e5b8c8d00d9f70626e65e34fdfce6bac6ec7ab681b8d2b08794976b94d5d4` |
| 本地 RRF 排名 | `777b41c3e2544badcb9ed6fb7208f4556f4a989286a2373ebad5a59028bbc7f5` |
| ES `dev` 报告 | `149ea4a33edd65224c9da42224d731fc86c2562d9eff5cf573e212b81dd81935` |
| Milvus `dev` 报告 | `d57910711a09bfb09f30c261453633b0692349341a1257ca914f0506133177f5` |

任一身份不一致时不得用新资产覆盖本冻结结果；应建立新版本并重新作出
入口决策。

## 4. 基线与目标增益

当前可证明的基线只包括人工标签、本地 RRF 排名和远程单路结果：

| 指标 | 基线 |
|---|---:|
| 本地 RRF Top-3 严格双侧相关文档覆盖 | `0/4` |
| 本地 RRF Macro Recall@3 | `0.145833` |
| 本地 RRF Macro nDCG@3 | `0.270971` |
| 缺失侧相关 Chunk 出现在本地 RRF Top-50 | `0/4` |
| ES 严格通过 | `0/4` |
| Milvus 严格通过 | `0/4` |

下一 `dev` 质量实验必须采用同请求的原路径 control 与单变量 treatment
配对比较。最低目标：

- 严格双侧相关文档覆盖至少 `3/4`，且相对 control 绝对提升至少 `0.50`；
- Macro Recall@3 相对 control 绝对提升至少 `0.20`；
- Macro nDCG@3 相对 control 绝对提升至少 `0.10`。

达到目标只允许进入封存 `test` 的一次性评估，不代表线上默认启用、阶段 3
完成、Acceptance 通过或生产性能通过。

## 5. 唯一增强变量

`BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1` 的允许变化只有一项：

> 对恰好包含两个已授权文档路由且可确定为比较问题的请求，把两条文档路由
> 共同使用的原问题，替换为每条路由恰好一个确定性的“该文档侧子查询”。

后续实现必须是确定性纯转换，不调用 LLM，不读取样本 ID、答案、Claim、
相关性标签、候选、Chunk 或页码。它只能使用原问题及已通过 READY/owner
解析的两个文档身份。不能证明恰好两侧、任一子查询为空或转换失败时，使用
原问题走原 RRF 路径。

本变量必须保持：

- PostgreSQL READY/owner 前置和持久化文档、版本、Chunk 身份校验；
- 每条既有路由的 ES/Milvus 并行召回；
- `candidate_k=20`、`rrf_k=60`、最终 `top_k=3`；
- 固定 Reranker 关闭；
- Embedding 模型、Chunk、生成模型、Prompt 和解码不变。

不得同时改变 RRF 参数、候选数、Reranker、额外多查询、父子 Chunk、邻接
扩展、Chunk 策略、Embedding、生成或固定问题缓存。

## 6. 关键类别不退化线

下一质量 Gate 除目标集外必须满足：

- 非目标 `ANSWERABLE dev` 的 Recall@3 绝对下降不超过 `0.01`；
- 非目标 `ANSWERABLE dev` 的 nDCG@10 绝对下降不超过 `0.01`；
- `FORBIDDEN` 的决定与零候选边界逐条等同 control；
- `NO_EVIDENCE` 的决定和候选边界不得比 control 更差；
- owner、ACL、版本和 Chunk 身份违规为 `0`；
- 固定 15 题工程 Canary 保持 `15/15`。

任何安全或身份违规直接失败，不能用目标集增益抵消。

## 7. 延迟、Token 与运维预算

本质量变量的自身预算为：

- 确定性拆分逻辑 P95 不超过 `5 ms`；
- 相对 control 的检索 P95 增量不超过 `50 ms`；
- 每请求最多新增 1 次 Query Embedding；不新增 ES/Milvus 请求；
- 新增 LLM 调用为 `0`，新增生成 Token 为 `0`，生成上下文 Token 上限不变；
- 不新增服务、模型、索引、数据库迁移、密钥或运维进程。

绝对检索 `P95 <= 300 ms` 仍是未通过的硬门槛，只能由独立性能 Gate 判定。
质量变量即使通过上述增量预算，也不能据此宣称 300 ms 达标或默认启用。

## 8. 关闭、回滚与拆分隔离

预留开关为 `PHASE3_COMPARISON_DECOMPOSITION_ENABLED`，未来实现时默认
`false`。关闭开关即恢复原问题、原候选边界和原 RRF；因为不允许 Schema、
数据、索引或模型变更，回滚不需要迁移或数据清理。

评测隔离固定为：

- `dev`：只允许设计、调试和调参这一单变量；
- `test`：本 Gate 保持封存；实现、配置、dev 决策和候选提交全部冻结后，
  只允许一次性评估，不得反向调参；
- `acceptance`：继续封存，只有用户另行明确授权后才可进入；始终不得用于
  调参。

## 9. 独立性能携带 Gate

阶段 2 的 Windows 分段证据继续单独记录：

- base retrieval `P95=376.394385 ms`；
- Reranker `P95=132.456 ms`；
- combined `P95=504.71613 ms`；
- Query Embedding `P95=189.838925 ms`；
- READY 路由解析 `P95=145.48693 ms`；
- 报告 SHA-256
  `235FE36A97B7F4E462AD502595CB0CF38C139022703B6C4EA1E93E19D3AC765B`。

该性能债不得与首个失败类型增强同时实施。不得放宽 300 ms、移除 READY、
ACL 或身份重验、减少候选，或缓存固定问题制造通过。
