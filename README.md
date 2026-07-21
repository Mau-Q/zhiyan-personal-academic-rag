# 智研个人学术空间 RAG 问答系统

本仓库用于建设面向个人论文、个人文献库、研究目录及授权公共知识库的证据约束型 RAG 问答系统。

系统必须完成以下可审计链路：

```text
授权文献范围
→ PDF 入库与版本管理
→ 章节、页码和 Chunk
→ Elasticsearch + Milvus 混合检索
→ 融合、去重和重排
→ 证据上下文
→ 受证据约束的生成
→ 引用校验或证据不足拒答
→ PDF 原文定位
→ Trace、反馈和评测闭环
```

## 当前状态

当前总体状态为 `SOURCE_PHASE_0_IN_PROGRESS / REPO_M0_COMPLETE / M1_LOCAL_RRF_BASELINE_READY / RISK_BASED_TESTING_READY / REMOTE_RETRIEVAL_BASELINE_READY`。仓库已形成本地 PDF 到非流式 Answer API 的可审计最小链路，完成本地 BGE-M3/RRF 与 500 题四路检索基线；远程 PostgreSQL、Elasticsearch、Milvus 和 BGE-M3 已完成受限回环工程冒烟。真实应用适配器、正式索引 Schema、生成模型、性能验收和原方案人工口径仍未完成。

- GitHub：<https://github.com/Mau-Q/zhiyan-personal-academic-rag>
- 最高方案追踪：[`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md)
- 下一门禁：[`docs/CURRENT_PHASE.md`](docs/CURRENT_PHASE.md)
- 仓库 M0 范围：[`docs/STAGE_0_SCOPE.md`](docs/STAGE_0_SCOPE.md)
- 双人分工：[`docs/TEAM_WORK_SPLIT.md`](docs/TEAM_WORK_SPLIT.md)
- 合同入口：[`contracts/README.md`](contracts/README.md)
- 仓库 Harness 入口：[`AGENTS.md`](AGENTS.md)
- 薄评测 Harness：[`docs/EVALUATION_HARNESS.md`](docs/EVALUATION_HARNESS.md)
- SQLite FTS5/BM25：[`docs/SQLITE_FTS_RETRIEVAL.md`](docs/SQLITE_FTS_RETRIEVAL.md)
- 本地向量与 RRF：[`docs/LOCAL_VECTOR_RRF_RETRIEVAL.md`](docs/LOCAL_VECTOR_RRF_RETRIEVAL.md)
- 正式检索评测 V1：[`docs/FORMAL_RETRIEVAL_EVALUATION_V1.md`](docs/FORMAL_RETRIEVAL_EVALUATION_V1.md)
- 风险驱动测试策略：[`docs/RISK_BASED_TESTING_STRATEGY.md`](docs/RISK_BASED_TESTING_STRATEGY.md)

## 双人开发边界

- 成员 A：PDF 入库、本地检索、RAG 回答和核心系统集成；
- 成员 B：远程主机准备、部署验证和后续基础设施状态核验；
- 双方通过 GitHub 提交和同一 `main` 版本交接，远程工作不阻塞本地最小链路。

## 仓库边界

本仓库只保存源码、合同、测试、配置样例和可公开 Fixture。以下内容不得提交：

- 真实密钥和 `.env`；
- 私有论文、用户上传文件和未授权数据；
- PostgreSQL dump、live data 和索引目录；
- 模型权重、虚拟环境、依赖缓存和运行日志；
- 当前知识库整理目录中的大型压缩包和 4090 混合部署包。

详细规则见 [`docs/REPOSITORY_POLICY.md`](docs/REPOSITORY_POLICY.md)。

## 合同验证

本地需要 Python 3.11+ 和 `jsonschema`：

```bash
python3 -m pip install 'jsonschema>=4.23,<5'
make contract-test
```

验证只读取仓库内的 Schema、示例和人工 Fixture，不访问远程模型或生产数据。

## 成员 A 在线 Fixture 消费者

```bash
python3 -m backend.rag.fixture_consumer \
  --question "How are candidates combined before reranking?"
```

该命令只运行授权过滤、确定性词项检索和 Fake LLM 证据拼装。输出明确包含 `FIXTURE_ONLY_FAKE_LLM`，不能作为真实模型或真实索引效果。完整说明见 [`docs/ONLINE_FIXTURE_CONSUMER.md`](docs/ONLINE_FIXTURE_CONSUMER.md)。

## 本地 PDF 入库

```bash
python3 -m backend.ingestion.cli \
  --pdf /local/path/paper.pdf \
  --document-id doc_local_001 \
  --tenant-id tenant_fixture \
  --visibility private \
  --library-scope-id lib_fixture \
  --strategy section_parent_child_v1 \
  --output /tmp/chunks-v1.json
```

该命令只处理有文本层的本地 PDF，不调用网络、OCR、远程模型、数据库或向量库。完整边界见 [`docs/LOCAL_PDF_INGESTION.md`](docs/LOCAL_PDF_INGESTION.md)。

真实 TRACER PDF 的本地解析与 Answer API 结果见 [`docs/LOCAL_PDF_CANARY.md`](docs/LOCAL_PDF_CANARY.md)。仓库只记录身份、命令和验收结论，不保存 PDF 或真实 Chunk 输出。

## 仓库 Harness

```bash
python3 scripts/validate_harness_contract.py
```

仓库 Harness 固化当前阶段、产品决策、执行边界和完成门禁。`AGENTS.md` 是成员与自动化工具的入口，`machine/` 保存机器可读状态，具体阶段运行结果只写入被忽略的 `runtime/phases/`。架构说明见 [`docs/HARNESS_ARCHITECTURE.md`](docs/HARNESS_ARCHITECTURE.md)。

## M1 薄评测 Harness

```bash
make evaluation-smoke
```

该命令用版本化 JSONL 用例调用现有 RAG Answer API，并把机器可读报告写入被 Git 忽略的 `runtime/evaluation/`。当前公开基线只验证 Fixture/Fake LLM 下的状态、证据页码和权限边界；真实三篇论文问题集保留在本地。完整说明见 [`docs/EVALUATION_HARNESS.md`](docs/EVALUATION_HARNESS.md)。

## SQLite FTS5/BM25

```bash
make sqlite-fts-fixture-smoke
```

该命令使用标准库 `sqlite3` 建立持久化 FTS5 索引，并通过现有 Answer API 和评测 Harness 验证授权、Evidence、拒答和越权阻断。索引写入被忽略的 `runtime/`；答案仍为 Fake LLM。实现与三论文结果见 [`docs/SQLITE_FTS_RETRIEVAL.md`](docs/SQLITE_FTS_RETRIEVAL.md)。

## 非流式 RAG API

```bash
source .venv/bin/activate
uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

当前只提供 `POST /api/v1/rag/answers`，使用服务端 Fixture 授权范围，客户端只能通过 `document_ids` 收窄范围。安装、请求和错误响应见 [`docs/RAG_API_QUICKSTART.md`](docs/RAG_API_QUICKSTART.md)。

## 计划目录

```text
backend/
├── contracts/
├── ingestion/
├── storage/
├── indexing/
├── retrieval/
├── rag/
├── api/
└── evaluation/
frontend/
deploy/
docs/
tests/
```

## 许可证

公开许可证尚未确定。在完成代码归属、第三方依赖和竞赛公开规则审查前，本仓库保持私有，不授予仓库访问者超出适用法律默认范围的使用许可。
