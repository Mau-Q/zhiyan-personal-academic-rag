# 本地三论文词项检索评测基线

## 结论

`local-3-paper-v1` 已在本地完成，结果为 15/15：9 个可回答用例、3 个无证据用例、3 个越权用例全部通过。该结果建立了可重复的词项检索和权限基线，但执行边界仍为 `LOCAL_API_FAKE_LLM`，不代表真实生成模型、向量检索或远程部署已经通过。

## 输入身份

| 文献 | arXiv | 页数 | Chunk 数 | SHA-256 |
|---|---|---:|---:|---|
| TRACER: Trajectory Risk Aggregation for Critical Episodes in Agentic Reasoning | `2602.11409` | 10 | 63 | `3e7e4628ffadc9183e85341b3a88050c3b58a06dec02926c8f2028b55879d6ea` |
| SciNet: Evaluating AI Agents in Relation-Aware Scientific Literature Retrieval | `2601.03260` | 18 | 111 | `d509e0891cedd235251940fa57880bd31721e08a22379d922cddd534f62dce70` |
| EVMbench: Evaluating AI Agents on Smart Contract Security | `2603.04915` | 32 | 142 | `ff3b39d94690de98cff09998c669b20333861d43b797ea000af812bc7f524dcf` |

三份 PDF 均与已提交语料清单中的页数和 SHA-256 一致，解析状态均为 `PASS`，合计生成 316 个 `ChunkRecordV1`。

## 方法

- 对三份 PDF 首页和 9 个目标证据页进行渲染抽检，确认版面、标题、正文和图表可读；
- 每篇人工编写 3 个可回答问题，并在运行时题集中标注目标文档与页码；
- 统一加入 3 个资料范围外问题和 3 个未授权文档请求；
- 使用现有 Answer API 和薄评测 Harness 运行，不复制检索、授权或回答逻辑；
- 首轮即通过 15/15，没有通过反复修改题目来适配检索结果。

## 结果

| 类别 | 通过/总数 | 强制条件 |
|---|---:|---|
| `ANSWERABLE` | 9/9 | HTTP 200、`COMPLETED`，且命中人工目标文档和页码 |
| `NO_EVIDENCE` | 3/3 | HTTP 200、`NO_EVIDENCE`，Evidence 为 0 |
| `FORBIDDEN` | 3/3 | HTTP 403、`RAG_FORBIDDEN_SCOPE` |

问题文本、PDF、Chunk、授权范围、页面渲染和完整报告只保存在被 Git 忽略的 `runtime/evaluation/local-3-paper-v1/`，不进入仓库历史。

## 可解释边界

当前检索器是授权范围内的确定性词项重叠基线，回答由 Fake LLM 消费者按 Evidence 拼装。因此本结果只能证明：本地真实 PDF 可入库，词项检索可定位人工目标页，拒答和越权阻断按合同工作。下一阶段可以固定同一份本地题集，分别替换为向量、混合检索和重排，以避免同时改变题集和算法。

## 三种 Chunk 受控 Baseline

使用同一三篇 PDF、同一 15 题及页码目标、同一授权范围、`top_k=3`、SQLite FTS5/BM25 和本地 `bge-m3:latest` 完成三种策略对比。BGE-M3 digest 为 `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`，向量阈值保持 `0.5`，未修改题目、目标页、切片参数或检索参数。

| 策略 | Chunk 数 | 长度中位数 | 跨页 Chunk | 父链接 Chunk | SQLite BM25 | BGE-M3 |
|---|---:|---:|---:|---:|---:|---:|
| `fixed_boundary_v1` | 279 | 1024 | 0 | 0 | 15/15 | 12/15 |
| `paragraph_sentence_v1` | 316 | 1002 | 56 | 0 | 15/15 | 12/15 |
| `section_parent_child_v1` | 316 | 1010 | 63 | 316 | 15/15 | 12/15 |

三组 BM25 均为可回答 9/9、无证据 3/3、越权 3/3。三组 BGE-M3 均为可回答 6/9、无证据 3/3、越权 3/3；`fixed_boundary_v1` 额外命中 SciNet review methods 但漏掉 TRACER ingredients，两种结构化策略恰好相反。因此当前小样本只证明策略间存在局部互换，不证明任一策略总体更好。

结论是保留三种可重放策略，不切换默认、不调参、不引入重排。完整 Chunk、索引和报告保留在被 Git 忽略的 `runtime/evaluation/local-3-paper-chunk-baseline-v1/`；汇总报告 SHA-256 为 `6edac6b48e80d160d5b32de87eec38d193e5060873cfbab2e99d4d13b18121c3`。
