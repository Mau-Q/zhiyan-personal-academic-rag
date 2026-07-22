# M1 薄评测 Harness

## 目标

该 Harness 用同一组版本化问题调用现有 `POST /api/v1/rag/answers`，记录状态、证据文档、页码和错误码。它用于比较后续词项、向量、混合检索和重排方案，不实现新的检索器、模型服务或评测平台。

当前执行边界固定为 `LOCAL_API_FAKE_LLM`。通过只说明本地 API 的状态、权限和证据定位符合用例预期，不代表真实模型回答质量已经通过。

Harness 也支持 `--retrieval-backend sqlite_fts5 --index <path>`。此时报告边界为 `LOCAL_API_SQLITE_FTS5_FAKE_LLM`，用例必须要求对应警告，不能继续沿用 Fixture 警告制造虚假通过。

真实本地检索还支持：

- `--retrieval-backend local_vector --vector-index <path>`；
- `--retrieval-backend local_rrf --index <fts-path> --vector-index <vector-path>`；
- `--embedding-model`、`--vector-min-score`、`--candidate-k` 和 `--rrf-k` 显式进入报告配置。

远程 Elasticsearch BM25 使用 `--retrieval-backend elasticsearch_bm25`，并显式提供 `--elasticsearch-url` 与 `--elasticsearch-index`。报告边界为 `REMOTE_API_ELASTICSEARCH_BM25_FAKE_LLM`；它验证真实远程检索与 ACL，不代表真实生成模型质量。

远程 Milvus/BGE-M3 使用 `--retrieval-backend milvus_vector`，并显式提供 `--milvus-uri` 与 `--milvus-collection`。报告边界为 `REMOTE_API_MILVUS_BGE_M3_FAKE_LLM`；Collection、源 Chunk 和模型身份漂移时失败关闭。参数与命令见 [Milvus 向量检索适配器](MILVUS_RETRIEVAL.md)。

远程 ES + Milvus 最小 RRF 后端读取版本化配置，报告固定输出配置 Schema、Index、Collection、模型身份、阈值与 RRF 参数，详见 [Elasticsearch + Milvus 最小 RRF](REMOTE_RRF_RETRIEVAL.md)。

本地 BGE-M3 与 RRF 的固定三论文结果、模型 digest 和阈值依据见 [本地真实向量与 RRF 混合检索基线](LOCAL_VECTOR_RRF_RETRIEVAL.md)。

本文件描述的薄 Harness 继续服务于 6 条公开 Fixture 和 15 题工程 Canary。正式 500 条检索评测使用独立的版本化 Manifest、双标注谱系、泄漏检查和 Recall/MRR/nDCG 指标，见 [正式检索评测体系 V1](FORMAL_RETRIEVAL_EVALUATION_V1.md)。两者不能互相替代。

后续阶段按 [风险驱动测试策略](RISK_BASED_TESTING_STRATEGY.md) 运行受影响测试、固定 Canary 和 500 题 GPT 辅助基线；题量保持，人工评审只在 Acceptance、抽检、冲突和专业高难边界展开。

## 已提交基线

`evaluation/suites/fixture-smoke-v1.jsonl` 包含 6 个公开 Fixture 用例：

- 2 个 `ANSWERABLE`：检查 `COMPLETED`、目标文档和目标页；
- 3 个 `NO_EVIDENCE`：检查无关问题、越权内容和失效版本不会成为证据；
- 1 个 `FORBIDDEN`：检查客户端不能扩大服务端授权范围。

运行：

```bash
make evaluation-smoke
```

报告默认写入被 Git 忽略的 `runtime/evaluation/fixture-smoke-v1-report.json`。任一用例失败时进程返回 `1`，输入或 JSONL 结构错误时返回 `2`。Harness 还会拒绝类别和期望不一致的用例，例如把 `ANSWERABLE` 标成 `NO_EVIDENCE`，避免错误标注制造虚假通过。

也可以显式指定输入：

```bash
.venv/bin/python -m backend.evaluation.harness \
  --cases evaluation/suites/fixture-smoke-v1.jsonl \
  --chunks fixtures/chunks-v1.json \
  --scope fixtures/authorized-scope-v1.json \
  --output runtime/evaluation/report.json
```

## 本地三篇论文扩展

真实 PDF、生成的 Chunk 和真实问题集不提交。成员 A 在本地 `runtime/evaluation/` 建立 `local-3-paper-v1.jsonl`，沿用同一 JSONL 结构：

```json
{"case_id":"local.paper1.answerable.01","category":"ANSWERABLE","question":"问题文本","document_ids":["doc_local_001"],"expected":{"http_status":200,"answer_status":"COMPLETED","min_evidence_count":1,"required_evidence":[{"document_id":"doc_local_001","page_start":3,"page_end":4}],"required_warnings":["FIXTURE_ONLY_FAKE_LLM"]}}
```

第一批已完成 3 篇论文、15 题：每篇 3 个可回答问题，另外统一加入 3 个无证据问题和 3 个越权请求。题目由人工根据 PDF 页码编写，不能仅依据检索结果反向生成答案。

本地运行时把 `--chunks` 指向三篇论文合并后的 `ChunkRecordV1` JSON，把 `--scope` 指向本地授权范围。报告只进入 `runtime/`，不得提交问题对应的私有正文、Chunk 或绝对路径。

脱敏后的输入身份、方法和 15/15 分类结果见 [本地三论文词项检索评测基线](LOCAL_3_PAPER_EVALUATION.md)。

## 通过标准

- 公开 Fixture：6/6；
- 三类用例分别统计，不允许用总平均掩盖权限失败；
- 可回答题至少命中一个人工标注的目标文档与页码区间；
- 无证据题必须是 `NO_EVIDENCE` 且 Evidence 数量为 0；
- 越权请求必须是 HTTP 403 和 `RAG_FORBIDDEN_SCOPE`；
- 报告保留 `execution_boundary`，Fixture/Fake 结果不能表述为真实模型通过。
- 报告保留 `retrieval_backend`，不同检索器必须使用相同问题、页码和 `top_k` 才能比较。
