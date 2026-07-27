# 智研个人学术空间 RAG 操作指南

> 面向对象：项目使用者、开发协作者和技术评审人员
> 命令基线：除第 13 节引用的 Windows Runbook 外，命令均在仓库根目录执行
> 路径约定：先把 `<REPO_ROOT>`、`<PDF_PATH>`、`<CHUNKS_PATH>` 等占位符替换为本机真实值

## 1. 文档适用范围

### 1.1 当前可操作能力

| 层级 | 当前可执行入口 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| Fixture / Fake LLM | 默认 Answer API、Fixture Consumer、公开 Smoke | API 合同、ACL 收窄、Citation 结构、`NO_EVIDENCE` 和 403 | 真实 PDF、真实索引或真实模型质量 |
| 本地真实 PDF | `backend.ingestion.cli` | 带文本层 PDF 的身份校验、页码解析、确定性 Chunk | OCR、PostgreSQL READY、ES/Milvus 或真实生成 |
| 本地真实检索 | SQLite FTS5；可选 Ollama/BGE-M3 向量与 RRF | 对实际 Chunk 的本地持久检索 | 远程 Milvus、生产阈值或真实生成 |
| 本地真实生成 | `run_local_real_generation_canary.py` | Ollama 对公开 Fixture Evidence 的模型身份、引用和拒答边界 | 真实 PDF 或 PostgreSQL/ES/Milvus 在线链路 |
| 真实持久链路 | PostgreSQL 迁移和用户执行的 Stage 1 Canary | 隔离环境中的 PDF 快照、双索引 READY、问答、INACTIVE 和三路清理 | 长期在线产品服务或生产部署 |
| Windows 远程 Gate | `deploy/remote/` 下版本化 Runbook/脚本 | 指定提交、输入和环境上的一次真实 Gate | 远程服务此刻仍在线 |

### 1.2 不在本文范围的能力

- OCR、正式 MinIO 应用适配；
- 前端、知识库产品接入、Agent API、SSE 运行服务；
- 通用部署、后台常驻 Worker、运维看板、告警、灰度和回滚；
- 阶段 5 的复杂比较、多跳和时效问答；
- 把 EvidenceSet 当作人工真值、NLI 或在线硬裁决；
- 把历史远程报告当作当前服务健康检查。

### 1.3 系统结构概览

> **截图占位 01：系统总体架构图**
> 建议内容：PostgreSQL 事实源、ES/Milvus 双路检索、RRF、生成、Citation、
> EvidenceSet，以及 INACTIVE 后三路清理。
> 后续文件名：`01-system-architecture.png`

## 2. 环境要求

### 2.1 基础工具

| 工具 | 必需场景 | 当前要求 |
|---|---|---|
| Python | 所有 Python 入口 | 3.11 或更高 |
| `.venv` | 所有 Makefile 门禁 | 必须位于仓库根目录 |
| Git | 版本和工作区检查 | 使用当前审核提交 |
| Make | 仓库门禁和公开 Smoke | macOS/Linux/WSL2 常规使用 |
| `curl` | API/OpenAPI 检查 | 访问本机回环地址 |
| `pwsh` | `make powershell-check` | 只做 PowerShell 静态检查 |

### 2.2 外部服务按需启用

| 服务 | 何时需要 | 不需要的场景 |
|---|---|---|
| PostgreSQL | 迁移、持久身份、READY、清理队列 | Fixture、本地 PDF CLI、SQLite |
| Elasticsearch | 真实 BM25、双索引 READY、物理清理 | Fixture、SQLite |
| Milvus | 真实向量、双索引 READY、物理清理 | Fixture、SQLite、本地精确向量 |
| Ollama | 本地 BGE-M3 或真实生成 | Fixture、Fake LLM、SQLite |
| RTX 4090 | 指定远程性能/模型 Gate | 普通本地开发和合同测试 |

### 2.3 平台差异

- macOS、Linux 和 WSL2 使用 POSIX 命令及 `.venv/bin/python`。
- 原生 Windows 下 Makefile 会选择 `.venv/Scripts/python.exe`，但远程操作必须
  使用仓库内对应的 Windows PowerShell 5.1 Runbook。
- WSL2 和原生 Windows 是两个环境，不能共用同一个 `.venv`。
- Mac 上的 `pwsh` 解析通过不等于 Windows cmdlet、服务或 Docker 行为通过。

## 3. 获取仓库与初始化环境

### 3.1 进入并确认仓库

| 项目 | 内容 |
|---|---|
| 目的 | 确保命令运行在真正的源码仓库，而不是父级知识库目录 |
| 前置条件 | 已获得仓库工作副本 |
| 执行命令 | 见下方 |
| 预期结果 | 根目录包含 `AGENTS.md`、`Makefile`、`backend/`、`contracts/` |
| 失败时检查 | 检查 `<REPO_ROOT>` 是否指向 `05_个人学术空间RAG` |
| 数据影响 | 只读 |

```bash
cd <REPO_ROOT>
git rev-parse --show-toplevel
git rev-parse HEAD
git status -sb
```

如果工作区已有修改，不要执行重置或覆盖；先确认这些修改的归属。

### 3.2 创建虚拟环境

| 项目 | 内容 |
|---|---|
| 目的 | 建立 Makefile 强制使用的项目 Python 环境 |
| 前置条件 | Python 3.11+，位于仓库根目录 |
| 执行命令 | 见下方 |
| 预期结果 | 导入 FastAPI、Uvicorn、Pydantic 和 pypdf 成功 |
| 失败时检查 | Python 版本、网络、证书和磁盘空间 |
| 数据影响 | 创建被 Git 忽略的 `.venv/` |

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev,server]'
python -c "import fastapi, pydantic, pypdf, uvicorn; print('environment ready')"
```

只有需要真实持久链路时才安装额外依赖：

```bash
python -m pip install '.[postgres,milvus]'
```

Reranker 依赖更大，普通用户不要默认安装：

```bash
python -m pip install '.[reranker]'
```

### 3.3 环境变量与本地配置

| 项目 | 内容 |
|---|---|
| 目的 | 查看仓库允许的环境变量名称 |
| 前置条件 | 位于仓库根目录 |
| 执行命令 | `sed -n '1,120p' .env.example` |
| 预期结果 | 只看到空值样例，不包含真实密钥 |
| 失败时检查 | `.env.example` 是否存在 |
| 数据影响 | 只读 |

`.env.example` 仅是字段样例；默认 API 和多数脚本不会自动加载 `.env`。真实
`DATABASE_URL`、`MILVUS_TOKEN` 或模型凭据必须通过目标 Runbook 指定的安全方式
注入当前进程，不能写入文档、命令历史、截图或 Git。

## 4. 最小健康检查

### 4.1 仓库完整门禁

| 项目 | 内容 |
|---|---|
| 目的 | 验证仓库状态、全量本地测试和 PowerShell 静态合同 |
| 前置条件 | `.venv` 已安装开发依赖；`pwsh` 可用 |
| 执行命令 | 见下方，按顺序执行 |
| 预期结果 | Harness `PASS`、测试 `OK`、PowerShell 静态检查通过、diff 无空白错误 |
| 失败时检查 | 先处理第一条失败，不跳过 Harness 扩大执行范围 |
| 数据影响 | 测试可能写入被忽略的临时/runtime 文件；不应改动跟踪文件 |

```bash
make harness-validate
make test
make powershell-check
git diff --check
```

命令含义：

- `make harness-validate`：验证权威状态、内容安全和跟踪边界，不证明 RAG 质量。
- `make test`：运行 Harness、合同、存储、入库、检索、RAG、API、评测和验证测试。
- `make powershell-check`：解析并静态分析 `.ps1` 和 Markdown 中的 PowerShell
  代码块，不执行 Windows 行为。
- `git diff --check`：检查已跟踪差异；新文件提交前还要运行 staged diff 检查。

## 5. 启动 Answer API

### 5.1 启动默认 API

| 项目 | 内容 |
|---|---|
| 目的 | 启动公开 Fixture + 词项重叠 + Fake LLM 的非流式 API |
| 前置条件 | 已安装 `server` 依赖，端口 8000 未占用 |
| 执行命令 | 见下方 |
| 预期结果 | Uvicorn 监听 `127.0.0.1:8000` |
| 失败时检查 | `.venv`、Uvicorn、端口和当前目录 |
| 数据影响 | 不写业务数据；进程只读取公开 Fixture |

```bash
.venv/bin/python -m uvicorn backend.api.app:app \
  --host 127.0.0.1 \
  --port 8000
```

默认入口不是 PostgreSQL READY 服务，也不会连接 ES、Milvus 或真实模型。不要将
监听地址改为 `0.0.0.0` 暴露到公网。

### 5.2 健康检查和停止

| 项目 | 内容 |
|---|---|
| 目的 | 确认 FastAPI 已提供真实存在的 OpenAPI 和 Answer 路由 |
| 前置条件 | API 正在运行 |
| 执行命令 | 见下方 |
| 预期结果 | OpenAPI 请求退出码 0；浏览器可打开 `/docs` |
| 失败时检查 | 终端启动日志、端口、代理和 URL |
| 数据影响 | 只读 |

```bash
curl -fsS http://127.0.0.1:8000/openapi.json >/dev/null
curl -fsS http://127.0.0.1:8000/docs >/dev/null
```

当前仓库没有独立 `/health` 路由，不能在文档中编造。停止服务时回到启动终端按
`Control-C`。

## 6. Fixture / Fake LLM 验证

### 6.1 命令行消费者

| 项目 | 内容 |
|---|---|
| 目的 | 不启动 HTTP 服务，直接验证公开 Fixture 检索和回答结构 |
| 前置条件 | 基础依赖已安装 |
| 执行命令 | 见下方 |
| 预期结果 | `status=COMPLETED`，有 Evidence/Citation，警告含 Fake 边界 |
| 失败时检查 | Fixture 文件、问题文本、`.venv` |
| 数据影响 | 只读 |

```bash
.venv/bin/python -m backend.rag.fixture_consumer \
  --question "How are candidates combined before reranking?" \
  --scope fixtures/authorized-scope-v1.json \
  --chunks fixtures/chunks-v1.json \
  --top-k 3
```

### 6.2 HTTP 三类结果

| 项目 | 内容 |
|---|---|
| 目的 | 验证正常回答、证据不足和越权三种 HTTP 语义 |
| 前置条件 | 第 5 节默认 API 正在运行 |
| 执行命令 | 依次执行下方三个 `curl` |
| 预期结果 | 分别得到 200 `COMPLETED`、200 `NO_EVIDENCE`、403 `RAG_FORBIDDEN_SCOPE` |
| 失败时检查 | 请求 JSON、端口、Fixture ID、`stream=false` 和服务日志 |
| 数据影响 | 三个请求均只读 |

API 正常回答：

```bash
curl -sS http://127.0.0.1:8000/api/v1/rag/answers \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "How are candidates combined before reranking?",
    "document_ids": ["doc_fixture_001"],
    "stream": false
  }'
```

证据不足：

```bash
curl -sS http://127.0.0.1:8000/api/v1/rag/answers \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "What is the measured ocean temperature?",
    "document_ids": ["doc_fixture_001"],
    "stream": false
  }'
```

越权范围：

```bash
curl -sS http://127.0.0.1:8000/api/v1/rag/answers \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "quantum entanglement",
    "document_ids": ["doc_fixture_private_other_tenant"],
    "stream": false
  }'
```

| 场景 | 预期 HTTP | 预期状态/错误码 | 数据影响 |
|---|---:|---|---|
| 正常回答 | 200 | `COMPLETED`，`FIXTURE_ONLY_FAKE_LLM` | 只读 |
| 无证据 | 200 | `NO_EVIDENCE`，Evidence/Citation 为空 | 只读 |
| 越权 | 403 | `RAG_FORBIDDEN_SCOPE` | 只读 |

失败时先检查 JSON 字段。`stream` 当前只能是 `false`，`document_ids` 不能重复，
未知字段、空问题或 `stream=true` 返回 422 `RAG_INVALID_REQUEST`。

### 6.3 本地持久检索 Smoke

| 项目 | 内容 |
|---|---|
| 目的 | 验证 SQLite 真实本地索引，以及可选的真实向量/RRF 检索 |
| 前置条件 | SQLite 只需基础依赖；向量/RRF 需 Ollama 和 `bge-m3:latest` |
| 执行命令 | 见下方 |
| 预期结果 | 各公开 Smoke 为 6/6 |
| 失败时检查 | Ollama、模型身份、索引来源指纹和 runtime 写权限 |
| 数据影响 | 在 `runtime/evaluation/` 创建被忽略的索引和报告 |

```bash
make sqlite-fts-fixture-smoke
make vector-fixture-smoke
make rrf-fixture-smoke
```

三条路径的答案仍由 Fake LLM 拼装。真实 SQLite/向量检索不等于真实生成。

## 7. 本地 PDF 入库

### 7.1 能力边界

- 只支持具有可提取文本层的 PDF；
- 使用 `pypdf`，不联网、不调用 OCR、数据库、索引或模型；
- PDF SHA-256 可选但强烈建议提供；
- `FAILED` 必须停止；`REVIEW` 只有人工确认后才可显式允许；
- 相同 PDF 和配置应产生确定性版本/Chunk 身份；
- PDF 与 Chunk 输出必须放在仓库外或被忽略的 `runtime/`。

### 7.2 计算身份并执行转换

| 项目 | 内容 |
|---|---|
| 目的 | 把一份真实带文本层 PDF 转换为 `ChunkRecordV1` JSON 数组 |
| 前置条件 | 已确认授权、PDF 可读、输出目录不进入 Git |
| 执行命令 | 见下方；把 `<PDF_SHA256>` 替换为独立计算结果 |
| 预期结果 | `status=COMPLETED`、`parse_status=PASS`、`chunk_count>0` |
| 失败时检查 | SHA、文本层、输出目录、切片策略和合同字段 |
| 数据影响 | 读取 PDF，创建或覆盖 `<CHUNKS_PATH>` |

macOS 计算 SHA-256：

```bash
shasum -a 256 <PDF_PATH>
```

Linux/WSL2 计算 SHA-256：

```bash
sha256sum <PDF_PATH>
```

转换：

```bash
.venv/bin/python -m backend.ingestion.cli \
  --pdf <PDF_PATH> \
  --expected-sha256 <PDF_SHA256> \
  --document-id <DOCUMENT_ID> \
  --tenant-id <OWNER_ID> \
  --visibility private \
  --library-scope-id <LIBRARY_ID> \
  --strategy section_parent_child_v1 \
  --output <CHUNKS_PATH>
```

可选策略只有：

- `fixed_boundary_v1`
- `paragraph_sentence_v1`
- `section_parent_child_v1`

不要把 `--allow-parse-review` 当作自动修复。没有可用文本层时会以
`PARSE_QUALITY_GATE_BLOCKED` 停止；当前应更换输入或另走未来 OCR Gate。

### 7.3 用真实 PDF Chunk 做本地 SQLite 检索

先在被忽略的运行目录保存一份 `AuthorizedScopeV1`，例如 `<SCOPE_PATH>`：

```json
{
  "user_id": "<OWNER_ID>",
  "tenant_id": "<OWNER_ID>",
  "library_ids": ["<LIBRARY_ID>"],
  "folder_ids": [],
  "document_ids": [],
  "include_public": false,
  "acl_version": "local_operation_v1"
}
```

| 项目 | 内容 |
|---|---|
| 目的 | 为真实 PDF Chunk 建立本地 SQLite FTS5/BM25 索引并查询 |
| 前置条件 | `<CHUNKS_PATH>` 和 `<SCOPE_PATH>` 已准备且身份一致 |
| 执行命令 | 见下方 |
| 预期结果 | Build 成功；Query 只返回授权且活动的 Chunk |
| 失败时检查 | Chunk/SCOPE 指纹、tenant/library/document 身份、问题词项 |
| 数据影响 | 创建或覆盖 `<SQLITE_INDEX_PATH>` |

```bash
.venv/bin/python -m backend.retrieval.sqlite_fts build \
  --chunks <CHUNKS_PATH> \
  --output <SQLITE_INDEX_PATH>

.venv/bin/python -m backend.retrieval.sqlite_fts query \
  --index <SQLITE_INDEX_PATH> \
  --chunks <CHUNKS_PATH> \
  --scope <SCOPE_PATH> \
  --question "<QUESTION>" \
  --top-k 3
```

### 7.4 用现有应用工厂启动真实 Chunk + SQLite + Fake LLM API

仓库没有独立的“自定义 Chunk API 启动器”。下面命令只调用现有
`backend.api.app.create_app`，没有引入新功能：

| 项目 | 内容 |
|---|---|
| 目的 | 对实际 PDF Chunk 启动本地 SQLite Answer API |
| 前置条件 | 第 7.3 节三个文件存在；端口 8000 可用 |
| 执行命令 | 见下方 |
| 预期结果 | OpenAPI 可访问；回答带 `LOCAL_SQLITE_FTS5_FAKE_LLM` |
| 失败时检查 | 路径替换、索引来源指纹、SCOPE 身份和端口 |
| 数据影响 | 只读现有 Chunk/SCOPE/索引，不创建业务数据 |

```bash
.venv/bin/python -c 'from pathlib import Path; import uvicorn; from backend.api.app import create_app; uvicorn.run(create_app(chunks_path=Path("<CHUNKS_PATH>"), scope_path=Path("<SCOPE_PATH>"), retrieval_backend="sqlite_fts5", index_path=Path("<SQLITE_INDEX_PATH>")), host="127.0.0.1", port=8000)'
```

启动后沿用第 9 节请求，把 `document_ids` 替换为 `<DOCUMENT_ID>`。这条链使用真实
PDF、真实 SQLite 检索和 Fake LLM，不是 PostgreSQL/ES/Milvus 或真实生成。

## 8. PostgreSQL 与双索引入库

### 8.1 迁移 PostgreSQL

> [!CAUTION]
> 本节会修改目标 PostgreSQL Schema。只能在已授权、已备份或隔离的目标库执行。

| 项目 | 内容 |
|---|---|
| 目的 | 应用版本化迁移 `0001`～`0005` |
| 前置条件 | `postgres` 依赖；当前进程已安全提供 `DATABASE_URL` |
| 执行命令 | 见下方 |
| 预期结果 | 输出 `APPLIED` 或幂等重放时的 `UNCHANGED` |
| 失败时检查 | 连接、权限、回环限制和 migration checksum drift |
| 数据影响 | 创建/更新 PostgreSQL Schema 与迁移记录 |

```bash
.venv/bin/python -m backend.storage.migrate
```

迁移器不打印 DSN。已应用迁移与仓库字节不一致时会失败，不会覆盖旧迁移。

### 8.2 真实双索引 READY 的唯一完整入口

当前仓库没有面向普通产品用户的独立“持久入库”“切换 READY”“启动在线服务”
CLI。完整装配只存在于
[`scripts/run_stage1_remote_canary.py`](../scripts/run_stage1_remote_canary.py)
和用户执行的
[Stage 1 Remote Validation Package](../deploy/remote/stage1-validation/README.md)。

> [!WARNING]
> Stage 1 Canary 会在隔离 owner 下写入 PostgreSQL、ES、Milvus 和 runtime
> snapshot，随后执行 INACTIVE 和三路清理。它是验证 Gate，不是长期保留文档的
> 产品入库命令。

其真实前置条件包括：

- PostgreSQL、Elasticsearch、Milvus、Ollama 均为本机回环服务；
- 独立 PDF SHA-256、全新非敏感 Run ID；
- `DATABASE_URL` 和可选 `MILVUS_TOKEN` 仅存在于进程环境；
- 明确确认短语 `RUN_ISOLATED_STAGE1_CANARY`；
- 使用版本化 Runbook 中的 Windows PowerShell 5.1 命令，本文不复制。

成功报告必须至少显示：

- `status=PASS`
- `pdf_object_reopen_proven=true`
- `answer_api_status=COMPLETED`
- `answer_api_evidence_count>=1`
- `cleanup_jobs_succeeded=3`
- `runtime_snapshot_cleanup_proven=true`
- `inactive_visibility_proven=true`
- `inactive_answer_api_status=403`

### 8.3 组件 CLI 不等于 READY

仓库也提供单独的 ES/Milvus Build/Inspect/Query CLI，但它们只验证组件，不会在
PostgreSQL 中创建原子 READY：

| 项目 | 内容 |
|---|---|
| 目的 | 独立验证 ES 版本索引或 Milvus Collection 的构建和身份 |
| 前置条件 | 对应服务和依赖可用；名称全新；Chunk 身份已确认 |
| 执行命令 | 见下方两个组件示例 |
| 预期结果 | Build 成功，随后 Inspect 返回匹配的来源和配置身份 |
| 失败时检查 | 服务、URL/URI、名称冲突、Chunk 指纹、模型和维度 |
| 数据影响 | **高风险写操作**：创建真实 ES Index 或 Milvus Collection |

```bash
.venv/bin/python -m backend.retrieval.elasticsearch \
  --url http://127.0.0.1:9200 \
  --index <ES_INDEX> \
  build \
  --chunks <CHUNKS_PATH>

.venv/bin/python -m backend.retrieval.elasticsearch \
  --url http://127.0.0.1:9200 \
  --index <ES_INDEX> \
  inspect
```

```bash
.venv/bin/python -m backend.retrieval.milvus \
  --uri http://127.0.0.1:19530 \
  --collection <MILVUS_COLLECTION> \
  --model <EMBEDDING_MODEL> \
  --base-url http://127.0.0.1:11434 \
  build \
  --chunks <CHUNKS_PATH>

.venv/bin/python -m backend.retrieval.milvus \
  --uri http://127.0.0.1:19530 \
  --collection <MILVUS_COLLECTION> \
  --model <EMBEDDING_MODEL> \
  --base-url http://127.0.0.1:11434 \
  inspect
```

这些 Build 会创建真实索引/Collection；名称不得复用。单侧失败不能手工宣布
READY，也不能用另一侧成功掩盖。

## 9. 执行 RAG 问答

### 9.1 请求合同

| 字段 | 必需 | 当前规则 |
|---|---|---|
| `question` | 是 | 去空格后 1～4000 字符 |
| `document_ids` | 是 | 唯一 ID 数组；只能收窄服务端授权范围 |
| `stream` | 是 | 只能为 `false` |

`owner_id` 不由客户端 JSON 提供。Fixture 模式从服务端 Scope 获得授权；真实在线
模式必须由服务端可信鉴权上下文注入 `authenticated_owner_id`。

### 9.2 向已启动的 API 提问

| 项目 | 内容 |
|---|---|
| 目的 | 获取结构化 Answer、Evidence 和 Citation |
| 前置条件 | 已按第 5 节或 7.4 节启动对应 API |
| 执行命令 | 见下方 |
| 预期结果 | HTTP 200；有证据时 `COMPLETED`，无证据时 `NO_EVIDENCE` |
| 失败时检查 | URL、JSON、`document_ids`、服务端 Scope 和执行边界 |
| 数据影响 | 当前公开 API 请求只读 |

```bash
curl -sS http://127.0.0.1:8000/api/v1/rag/answers \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "<QUESTION>",
    "document_ids": ["<DOCUMENT_ID>"],
    "stream": false
  }'
```

真实 PostgreSQL READY API 没有独立的公共 Uvicorn 启动命令；它由 Stage 1 Canary
在进程内装配。不要把默认 `backend.api.app:app` 写成真实在线入口。

### 9.3 本地真实模型 Canary

| 项目 | 内容 |
|---|---|
| 目的 | 验证 Ollama 真实生成、引用、`NO_EVIDENCE` 不调用模型和 403 |
| 前置条件 | 本机 Ollama 已安装指定模型，模型 digest 已独立确认 |
| 执行命令 | 见下方 |
| 预期结果 | 报告 `status=PASS`，输出写入 `runtime/` |
| 失败时检查 | Ollama `/api/tags`、模型名称/digest、Prompt/JSON/Citation 错误码 |
| 数据影响 | 调用本机模型并写入被忽略的报告；Evidence 是公开 Fixture |

```bash
.venv/bin/python scripts/run_local_real_generation_canary.py \
  --model <MODEL_ID> \
  --expected-digest <MODEL_DIGEST> \
  --ollama-url http://127.0.0.1:11434 \
  --output runtime/phases/local-real-generation-operation/canary.json
```

不带参数的 `make real-generation-canary` 使用脚本当前默认模型身份。无论哪种
方式，该 Canary 都是“公开 Fixture Evidence + 真实 Ollama”，不是完整真实链路。

## 10. 检查回答与证据

按以下顺序检查，不要只看 HTTP 200：

| 检查项 | 正常表现 | 异常信号 |
|---|---|---|
| `status` | `COMPLETED`、`NO_EVIDENCE` 或显式 `DEGRADED` | 缺失、未知状态 |
| `evidence` | 有稳定 `chunk_id/document_id/version_id` 和页码 | 身份缺失、跨版本混入 |
| `citations` | `evidence_id` 可回指本次 Evidence | 越界、悬空或页码不一致 |
| `warnings` | 明确写出 Fixture/Fake/真实模型/降级边界 | 空泛或隐藏 Fake/降级 |
| ACL | 请求只能收窄授权范围 | 客户端 owner/tenant 被当成可信事实 |
| `NO_EVIDENCE` | Evidence/Citation 为空，真实模型不调用 | 空证据仍生成事实 |
| 403 | `RAG_FORBIDDEN_SCOPE` | 已失效或越权文档仍返回 Evidence |

执行边界识别示例：

- `FIXTURE_ONLY_FAKE_LLM`：Fixture 检索 + Fake LLM；
- `LOCAL_SQLITE_FTS5_FAKE_LLM`：实际 SQLite 检索 + Fake LLM；
- `LOCAL_REAL_VECTOR_FAKE_LLM`：实际向量检索 + Fake LLM；
- `LOCAL_RRF_HYBRID_FAKE_LLM`：实际本地 RRF + Fake LLM；
- `REAL_GENERATION_...`：已注入固定身份的真实生成器；仍要检查是否降级。

EvidenceSet 当前是内部确定性 `AUDIT_ONLY` 能力。公开 `RagAnswerV1` 没有独立
`audit_status` 字段，也没有 EvidenceSet CLI/API；四态结果
`SUPPORTED_BY_EVIDENCE_SET`、`PARTIALLY_SUPPORTED`、
`CONFLICTING_EVIDENCE`、`INSUFFICIENT_EVIDENCE` 目前通过
`verify_claim_evidence_sets` 和专项测试验证。不得在普通 API 响应中声称已看到
不存在的 Audit Status。

可运行的专项回归：

| 项目 | 内容 |
|---|---|
| 目的 | 验证回答构建、真实生成失败关闭及单/多 EvidenceSet 规则 |
| 前置条件 | `.venv` 已安装开发依赖 |
| 执行命令 | `make rag-test` |
| 预期结果 | RAG 专项测试全部 `OK` |
| 失败时检查 | 首个失败用例、Claim/Citation 身份和审计状态 |
| 数据影响 | 仅测试临时数据 |

```bash
make rag-test
```

## 11. 文档删除、失效与三路清理

### 11.1 当前真实顺序

1. PostgreSQL 先把版本切到终态 `INACTIVE`；
2. READY 路由立即不再返回该版本；
3. ES 与 Milvus 版本被标记为非活动；
4. 分别排入 ES、Milvus、`runtime_snapshot` 三个持久清理任务；
5. Worker 通过租约领取任务，成功记为 `SUCCEEDED`，失败进入有界重试；
6. runtime 清理先核验并删除 PDF 对象，再清除 PostgreSQL Chunk/对象注册；
7. 删除后的 Answer 请求返回 403。

### 11.2 可执行入口与缺口

仓库当前没有通用的 `DELETE /documents/...` API，也没有独立的删除或常驻
Cleanup Worker CLI。不要编造 `curl -X DELETE`，也不要手工删除数据库行、索引或
Collection。

| 项目 | 内容 |
|---|---|
| 目的 | 本地验证 INACTIVE、三路任务、重试和删除后 403 的代码合同 |
| 前置条件 | `.venv` 完整，外部真实服务不需要 |
| 执行命令 | 见下方 |
| 预期结果 | Stage 1 相关单元/集成测试全部 `OK` |
| 失败时检查 | 生命周期、清理队列、租约、Writer 身份和 READY 路由测试 |
| 数据影响 | 测试仅使用临时/模拟资源，不删除真实服务数据 |

```bash
make stage1-local-canary
```

真实删除和清理只在第 13 节的用户执行 Stage 1 Canary 中完成。检查脱敏报告：

- `inactive_visibility_proven=true`
- `inactive_answer_api_status=403`
- `cleanup_jobs_succeeded=3`
- `runtime_snapshot_cleanup_proven=true`

失败后保留同一 Run ID 和脱敏报告。进入 INACTIVE 前可按 Runbook 重放；进入
INACTIVE 后只恢复既有清理任务，不新建质量 Run，不手工通配删除。

## 12. 可选 Reranker

- 默认在线主链是 PostgreSQL READY/owner → ES + Milvus → rank-only RRF。
- 固定 Cross-Encoder 只可重排已有的最多 20 个授权 RRF 候选并输出前 3。
- 未注入 Reranker 时行为保持 RRF；标题、模型或分数失败时回退同一批 RRF
  候选，不能扩张候选或绕过 ACL。
- 当前没有面向普通用户的“启用 Reranker”服务开关或公共启动命令。
- `make online-reranker-test` 只验证代码合同，不代表远程性能。
- 历史组合 P95 为 `504.71613 ms`，未达到 `300 ms` 目标；因此 Reranker
  保持可选且不默认启用。

| 项目 | 内容 |
|---|---|
| 目的 | 验证可选在线 Reranker 的候选不扩张、回退和 READY 边界 |
| 前置条件 | `.venv` 已安装开发依赖；不需要真实模型或远程服务 |
| 执行命令 | `make online-reranker-test` |
| 预期结果 | 对应检索、API 和远程脚本合同测试全部 `OK` |
| 失败时检查 | 候选身份、回退原因、配置和 PowerShell 静态合同 |
| 数据影响 | 仅测试临时数据，不启用线上 Reranker |

组件与在线 Gate 入口分别见
[固定 Reranker 评测](FIXED_RERANKER_EVALUATION.md)和
[`deploy/remote/reranker-validation/`](../deploy/remote/reranker-validation/)。

## 13. 远程 Windows / RTX 4090 验证

### 13.1 执行责任

- 远程操作只由用户在目标 Windows 主机上手动执行；
- Codex 不连接、部署、重启或重配置远程服务；
- Windows 操作以 Windows PowerShell 5.1 为兼容基线；
- Mac 的 `make powershell-check` 只解析/静态分析，不替代 Windows 运行；
- 每次 Gate 必须绑定审核提交、输入 SHA-256 和全新非敏感 Run ID。

### 13.2 版本化入口

- Stage 1 完整链路：
  [Runbook](../deploy/remote/stage1-validation/README.md) /
  [Python Runner](../scripts/run_stage1_remote_canary.py)
- Reranker：
  [`run_fixed_reranker_gate.ps1`](../deploy/remote/reranker-validation/run_fixed_reranker_gate.ps1) /
  [`run_online_reranker_gate.ps1`](../deploy/remote/reranker-validation/run_online_reranker_gate.ps1)
- 阶段 3 比较：
  [Runbook](../deploy/remote/phase3-comparison-validation/README.md)
- 阶段 4 NLI 候选：
  [Runbook](../deploy/remote/phase4-nli-validation/README.md)

普通使用者只应执行 Stage 1 Runbook；其他 Gate 是冻结实验入口，不是日常产品操作。
历史报告只证明对应提交和输入上的一次运行，不表示 PostgreSQL、ES、Milvus、
Ollama 或 GPU 服务当前在线。

## 14. 常见故障排查

| 症状 | 可能原因 | 检查方法 | 处理方式 |
|---|---|---|---|
| `.venv` 不存在 | 未初始化或目录错误 | `pwd`；`test -x .venv/bin/python` | 回到 `<REPO_ROOT>`，按第 3.2 节创建 |
| Python 依赖未安装 | 使用系统 Python 或 extras 缺失 | `.venv/bin/python -m pip show fastapi` | 用 `.venv/bin/python -m pip install '.[dev,server]'` |
| 端口 8000 占用 | 旧 Uvicorn 或其他服务 | `lsof -nP -iTCP:8000 -sTCP:LISTEN` | 停止旧进程或改用其他本机端口 |
| PostgreSQL 连接失败 | DSN、服务、权限或非回环地址 | 确认变量存在但不要打印；运行迁移观察稳定错误 | 修复本机服务/凭据；不要把 DSN贴入日志 |
| ES 不可用 | 服务未启动、URL 错误 | `curl -fsS http://127.0.0.1:9200 >/dev/null` | 按目标 Runbook恢复回环服务，不改成公网 |
| Milvus 不可用 | 服务/依赖/Collection 错误 | 对 `<MILVUS_COLLECTION>` 运行 Milvus `inspect` | 核对服务、`pymilvus`、URI 和 Collection 身份 |
| Embedding/LLM 不可用 | Ollama 停止、模型缺失或 digest 漂移 | `curl -fsS http://127.0.0.1:11434/api/tags` | 启动本机 Ollama；核对模型名和 digest |
| 版本无法 READY | 解析/Chunk/向量时间不全、单侧索引失败或身份漂移 | 查看 Stage 1 稳定错误码和对账字段 | 保持 `PROCESSING/FAILED`，修复同一变量后按同 Run ID 重放 |
| Answer 返回 `NO_EVIDENCE` | 授权范围内无匹配证据或阈值阻断 | 检查 Scope、问题、Evidence 和检索边界 | 不调用模型硬补；修正范围或真实检索缺口 |
| Answer 返回 403 | 文档越权、未 READY、已 INACTIVE 或事实源不可证明 | 核对服务端 owner、`document_ids` 和版本状态 | 修正授权/状态；不能绕过 ACL |
| Citation 校验失败 | 引用越界、Evidence 身份漂移或页码不一致 | 对照本次 `evidence_id/chunk_id/version_id/pages` | 失败关闭；不能手工补造引用 |
| 清理任务未完成 | Worker 失败、租约/重试或物理服务不可达 | 看三个任务状态、attempt、稳定错误码和脱敏审计 | 恢复既有任务；禁止手工删行或通配删索引 |
| PowerShell 检查失败 | `pwsh`/PSScriptAnalyzer 缺失或代码块不兼容 | 运行 `make powershell-check` 看首个错误 | 修复环境或语法；Mac PASS 不冒充 Windows PASS |
| 私有数据被误跟踪 | 文件放错目录或 `.gitignore` 规则被绕过 | `git status --short`；使用第 15 节跟踪扫描 | 立即停止提交，移出跟踪区并做敏感历史评估 |

## 15. 数据与安全边界

### 15.1 禁止提交

- `.env`、API Key、数据库密码、完整连接串和签名凭据；
- 私有 PDF、真实 Chunk、私有问题、Claim/Evidence 正文；
- PostgreSQL dump、SQLite live data、ES/Milvus/MinIO 数据目录；
- 模型权重、Embedding 缓存、`.venv` 和依赖缓存；
- `runtime/`、日志、Trace 正文、完整运行报告；
- 本机绝对路径、私有 IP 和远程服务地址。

### 15.2 提交前边界检查

| 项目 | 内容 |
|---|---|
| 目的 | 确认任务只包含预期文档，未跟踪私有资产 |
| 前置条件 | 位于仓库根目录 |
| 执行命令 | 见下方 |
| 预期结果 | 只显示本次允许的文件；敏感模式扫描无输出 |
| 失败时检查 | `.gitignore`、staged 文件和历史提交 |
| 数据影响 | 只读 |

```bash
git status --short
git diff --check
git diff --cached --check
git ls-files | rg '(^|/)\.env$|\.pdf$|^runtime/|^data/|^logs/'
```

最后一条应无输出。`.env.example` 是允许的公开空值样例。远程回传只允许脱敏
状态、稳定错误码、计数和报告 SHA-256，不回传凭据、正文、路径或服务地址。

## 16. 完整操作检查清单

### 环境初始化

- [ ] 已进入 `<REPO_ROOT>`，确认仓库根目录和 commit SHA
- [ ] Python 版本为 3.11+
- [ ] `.venv` 创建完成并安装所需 extras
- [ ] 未把真实密钥写入 `.env.example`、命令历史或文档

### 本地测试

- [ ] `make harness-validate` 通过
- [ ] `make test` 通过
- [ ] `make powershell-check` 通过或明确记录未具备 `pwsh`
- [ ] `git diff --check` 通过

### 服务启动与 Fixture

- [ ] 默认 API 仅绑定 `127.0.0.1`
- [ ] `/openapi.json` 和 `/docs` 可访问
- [ ] Fixture 正常回答为 `COMPLETED`
- [ ] Fixture 无证据为 `NO_EVIDENCE`
- [ ] Fixture 越权为 403 `RAG_FORBIDDEN_SCOPE`
- [ ] 已明确记录 `FIXTURE_ONLY_FAKE_LLM`

### 本地 PDF 与检索

- [ ] PDF 已获授权并独立计算 SHA-256
- [ ] `parse_status=PASS`，未绕过 OCR/REVIEW 边界
- [ ] Chunk 输出位于仓库外或 `runtime/`
- [ ] Chunk、Scope、SQLite 索引身份一致
- [ ] 实际 PDF API 明确标记为 SQLite + Fake LLM

### 真实持久链路（仅在执行 Stage 1 时）

- [ ] 服务只绑定回环地址，使用隔离 owner/索引/Collection/Run ID
- [ ] PostgreSQL 迁移为 `APPLIED` 或 `UNCHANGED`
- [ ] PDF 对象和 Chunk 快照可重开/重放
- [ ] ES 与 Milvus 均核验后才进入 READY
- [ ] 正常问答有 Evidence/Citation
- [ ] `NO_EVIDENCE` 不调用真实模型
- [ ] 越权或失效文档返回 403
- [ ] 先 INACTIVE，再执行物理清理
- [ ] ES、Milvus、runtime snapshot 三项清理均 `SUCCEEDED`

### 工作区收尾

- [ ] 未跟踪 PDF、Chunk、runtime、数据库、索引、模型或 `.env`
- [ ] 文档内部链接和命令路径已验证
- [ ] staged diff 只包含本次任务文件
- [ ] 已记录实际运行的 Gate，不扩大结论
- [ ] 未经授权未 push









这是 Windows 验证主机上的本地 PostgreSQL，不是可直接从公网访问的数据库：

| 项目       | 值                       |
| ---------- | ------------------------ |
| 数据库类型 | PostgreSQL 18.4          |
| 主机       | 127.0.0.1                |
| 端口       | 5432                     |
| 数据库名   | zhiyan_stage1_canary     |
| 用户名     | zhiyan_stage1_canary_app |
| 密码       | admin                    |
| 连接范围   | Windows 验证主机本机回环 |
| 管理员名   | postgres                 |
| 管理员密码 | admin                    |
