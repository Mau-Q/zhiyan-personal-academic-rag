# 本地真实向量与 RRF 混合检索基线

## 结论

成员 A 已在不等待远程主机的情况下完成真实本地向量检索和 RRF 混合检索。固定输入仍为同一 3 篇论文、316 个 Chunk、15 题、人工目标页、`top_k=3`、既有 ACL 和 Fake LLM；本阶段只改变检索后端。

| 检索后端 | 总结果 | 可回答 | 无证据 | 越权 | 结论 |
|---|---:|---:|---:|---:|---|
| 词项重叠 | 15/15 | 9/9 | 3/3 | 3/3 | 原始基线 |
| SQLite FTS5/BM25 | 15/15 | 9/9 | 3/3 | 3/3 | 持久化词项基线 |
| BGE-M3 精确余弦 | 12/15 | 6/9 | 3/3 | 3/3 | 真实向量基线，不单独晋级 |
| SQLite BM25 + BGE-M3 RRF | 15/15 | 9/9 | 3/3 | 3/3 | 本地混合基线通过 |

RRF 恢复了向量单路遗漏，但没有超过现有 BM25 在 15 题 Canary 上的结果。因此当前重排决策为 `DEFER_RERANK`：先扩大分层评测集，只有出现可复现的排序缺口且重排带来净增益时再接入。

## 冻结输入与模型身份

- Chunk 来源 SHA-256：`2bc8cb4aab38e800954c0a32faafc7053c359d7fe0165c634a95eb1b96b2b4ff`；
- Chunk 数：`316`；
- Embedding 服务：本机 Ollama；
- 模型：`bge-m3:latest`；
- 模型 digest：`7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`；
- 维度：`1024`；
- Passage 模板：`section_path_newline_text_v1`；
- Query 模板：`raw_question_v1`；
- 存储：SQLite 中的 L2 归一化 little-endian float32；
- 相似度：精确余弦，不使用近似索引；
- 向量阈值：`0.50`；
- RRF：候选数 `20`、`k=60`、最终 `top_k=3`。

索引保存模型名称和 digest、向量维度、模板、源 Chunk 指纹与数量。任一身份漂移都会在 API 启动或查询前失败关闭，不能用旧向量配新模型或新 Chunk。

## 阈值证据

在不设阈值的诊断运行中：

- 3 个无证据问题的最高相似度分别为 `0.368800`、`0.425643`、`0.360973`；
- 9 个可回答目标页中的最低目标相似度为 `0.585648`；
- `0.50` 位于当前 Canary 的明确间隔内，既阻断 3 个无证据误召回，又不删除目标页候选。

该阈值只作为当前固定 Canary 的本地基线，不是生产阈值。扩大语料和评测集后必须重新校准。

## 向量单路失败分析

向量单路的 3 个失败不是模型或服务错误，而是目标页落在第 `4`、`4`、`8` 名，超出固定 `top_k=3`。未修改题目、目标页或 `top_k` 来制造通过。RRF 使用 SQLite BM25 与向量各自前 20 个授权候选，按 `1 / (60 + rank)` 融合后恢复 15/15。

## 接口和执行边界

评测/API 支持以下后端：

- `lexical_overlap`；
- `sqlite_fts5`；
- `local_vector`；
- `local_rrf`。

向量与混合后端分别要求 `--vector-index`；混合后端还要求 `--index` 指向 SQLite FTS5 索引。配置项固定暴露 `embedding_model`、`vector_min_score`、`candidate_k` 和 `rrf_k`。ACL 在任何候选进入 Evidence 前执行；客户端仍只能收窄服务端授权范围。

真实向量不等于真实生成模型。响应分别携带：

- `LOCAL_REAL_VECTOR_FAKE_LLM` / `LOCAL_REAL_VECTOR_ONLY`；
- `LOCAL_RRF_HYBRID_FAKE_LLM` / `LOCAL_RRF_HYBRID_ONLY`。

## 可执行验证

先确保本机 Ollama 已安装 `bge-m3:latest`，再运行：

```bash
make vector-fixture-smoke
make rrf-fixture-smoke
```

两条公开 Fixture 冒烟均为 6/6。真实 PDF、Chunk、问题集、索引和完整报告只保存在被 Git 忽略的 `runtime/evaluation/local-3-paper-v1/`。

## 下一门禁

1. 把 15 题继续保留为快速 Canary；
2. 近期先建立默认 80 条风险驱动工程集并运行排序指标；原方案 200～500 条规模仅在正式验收时恢复；
3. 等成员 B 提供远程资源盘点后，再确定 BGE-M3 服务方式和 Milvus 索引方案；
4. 不根据本地精确余弦结果宣称 Milvus、远程 Embedding、生产阈值或并发目标完成。
