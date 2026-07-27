# 智研个人学术空间 RAG 使用与操作手册

> 面向对象：第一次接触本仓库的体验者、开发协作者和验收人员
> 推荐环境：macOS 或 Linux、Python 3.11+、Git、`curl`
> 当前公开入口：本地非流式 Answer API（Fixture 检索 + Fake LLM）

## 1. 先确认你要做什么

| 目标 | 从哪里开始 | 会不会连接真实服务 |
|---|---|---|
| 5 分钟体验 API | 按本文第 3～5 节操作 | 不会 |
| 验证本地源码 | 按本文第 6 节操作 | 默认不会 |
| 阅读接口和字段合同 | 查看 `http://127.0.0.1:8000/docs` 或 `contracts/` | 不会 |
| 运行真实 PostgreSQL、ES、Milvus、PDF 入库或模型 Gate | 先阅读第 8 节，再使用指定的版本化清单 | 会，且可能写入隔离数据 |

第一次使用时，请先完成公开 Fixture 演示。不要从远程部署、真实 PDF 或私有评测
开始。

## 2. 这份手册能证明什么

按本文完成公开演示，可以确认：

- Python 环境和仓库依赖可用；
- Answer API 能启动；
- 请求和响应符合当前接口结构；
- 可回答、无证据和越权三种基本语义可观察；
- 客户端指定的文档范围不能扩大服务端授权范围。

它不能证明：

- PostgreSQL、Elasticsearch、Milvus 或真实模型当前在线；
- Fixture 回答具有真实检索或生成质量；
- 检索 P95 已达到 `300 ms`；
- 当前项目已经达到生产发布标准；
- `warnings` 中带 `FIXTURE` 或 `FAKE_LLM` 的结果是真实业务证据。

## 3. 获取源码

从 GitHub 新建工作目录：

```bash
git clone https://github.com/Mau-Q/zhiyan-personal-academic-rag.git
cd zhiyan-personal-academic-rag
git status -sb
```

如果源码由同事直接交付，请先进入包含 `README.md`、`Makefile`、`backend/` 和
`contracts/` 的仓库根目录，再确认：

```bash
git rev-parse --show-toplevel
git rev-parse HEAD
git status -sb
```

如果 `git status` 显示已有本地修改，不要擅自删除、覆盖或重置；先向交付者确认
这些修改是否需要保留。

## 4. 创建本地环境

### 4.1 检查 Python

```bash
python3 --version
```

版本必须为 Python 3.11 或更高。

### 4.2 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install '.[dev,server]'
```

安装完成后检查：

```bash
.venv/bin/python -c "import fastapi, uvicorn; print('environment ready')"
```

看到 `environment ready` 表示公开演示所需依赖已就绪。

说明：

- 仓库 `Makefile` 强制使用 `.venv/bin/python`，不会回退到系统 Python；
- 公开 Fixture 演示不需要 `.env`、API Key、数据库或模型；
- `.env.example` 只是非密钥字段示例，不表示程序会自动加载 `.env`；
- 不要把真实密码、完整连接串或 API Key 写进命令、文档、截图或 Git。

## 5. 运行 5 分钟公开演示

### 5.1 启动 API

在仓库根目录打开终端 A：

```bash
.venv/bin/python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

看到以下含义相同的日志即可：

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

服务只绑定本机回环地址 `127.0.0.1`。不要为了演示改成 `0.0.0.0` 或直接暴露到
公网。

### 5.2 检查接口是否可访问

在终端 B 执行：

```bash
curl -fsS http://127.0.0.1:8000/openapi.json >/dev/null
```

命令无输出且退出码为 0，表示接口描述可访问。也可以在浏览器打开：

- Swagger UI：<http://127.0.0.1:8000/docs>
- OpenAPI：<http://127.0.0.1:8000/openapi.json>

### 5.3 场景一：正常回答

```bash
curl -sS http://127.0.0.1:8000/api/v1/rag/answers \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "How are candidates combined before reranking?",
    "document_ids": ["doc_fixture_001"],
    "stream": false
  }'
```

预期结果：

- HTTP 状态为 `200`；
- 响应中的 `status` 为 `COMPLETED`；
- `evidence` 和 `citations` 非空；
- `warnings` 包含 `FIXTURE_ONLY_FAKE_LLM`。

最后一项是必要的真实性标记：本例使用公开 Fixture 和 Fake LLM，不能作为真实
论文检索或真实模型质量证据。

### 5.4 场景二：证据不足

```bash
curl -sS http://127.0.0.1:8000/api/v1/rag/answers \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "What is the measured ocean temperature?",
    "document_ids": ["doc_fixture_001"],
    "stream": false
  }'
```

预期结果：

- HTTP 状态仍为 `200`；
- `status` 为 `NO_EVIDENCE`；
- `evidence` 和 `citations` 为空；
- 回答明确说明当前授权范围内证据不足。

`NO_EVIDENCE` 是正常业务结果，不是服务异常。

### 5.5 场景三：越权请求

```bash
curl -sS http://127.0.0.1:8000/api/v1/rag/answers \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "quantum entanglement",
    "document_ids": ["doc_fixture_private_other_tenant"],
    "stream": false
  }'
```

预期结果：

- HTTP 状态为 `403`；
- `code` 为 `RAG_FORBIDDEN_SCOPE`；
- `retryable` 为 `false`。

客户端传入 `document_ids` 只能缩小服务端授权范围，不能扩大权限。

### 5.6 停止服务

回到终端 A，按 `Control-C`。看到服务关闭日志后，本次演示结束。

## 6. 本地验证

### 6.1 只验证公开 API

适合第一次安装后的快速检查：

```bash
make harness-validate
make api-test
git diff --check
```

### 6.2 完整本地回归

适合修改代码或交付前：

```bash
make harness-validate
make test
make powershell-check
git diff --check
```

注意：

- `make test` 会运行完整本地测试，但不会证明远程基础设施当前可用；
- `make powershell-check` 需要本机安装 `pwsh`，它只做 Windows PowerShell
  5.1 兼容性解析和静态检查；
- Mac 上的静态检查不能替代目标 Windows 环境中的最终运行验证；
- 如果只完成 `make api-test`，交付说明中必须写“仅验证 API 相关测试”，不能写成
  “全仓测试通过”。

## 7. 请求和结果怎么判断

### 7.1 请求字段

| 字段 | 必填 | 规则 |
|---|---|---|
| `question` | 是 | 去除首尾空格后长度为 1～4000 |
| `document_ids` | 是 | 文档 ID 数组；不能重复；空数组表示使用服务端已授权范围 |
| `stream` | 是 | 当前只能是 `false` |

服务端拒绝额外字段。重复 `document_ids`、空问题、`stream=true` 或结构错误会返回
HTTP `422` 和 `RAG_INVALID_REQUEST`。

### 7.2 常见响应

| HTTP | 状态或错误码 | 含义 | 操作者动作 |
|---|---|---|---|
| `200` | `COMPLETED` | 已形成回答 | 检查 Evidence、Citation 和 `warnings` |
| `200` | `NO_EVIDENCE` | 授权范围内证据不足 | 不要当作程序故障重试 |
| `200` | `DEGRADED` | 只能形成受限或部分结果 | 阅读 `warnings`，不要隐藏降级 |
| `403` | `RAG_FORBIDDEN_SCOPE` | 请求包含未授权文档 | 修正调用方范围，不要绕过 ACL |
| `422` | `RAG_INVALID_REQUEST` | 请求结构不合法 | 按合同修正字段 |

判断结果时不要只看 HTTP `200`。至少同时检查：

1. `status`；
2. `evidence`；
3. `citations`；
4. `warnings`；
5. 使用的是 Fixture、Fake、真实检索还是实际模型。

## 8. 真实基础设施操作

真实链路可能涉及 PostgreSQL、Elasticsearch、Milvus、Embedding、真实生成、私有
PDF 和清理任务。它不是本手册的默认演示路径，也不能通过修改几个环境变量就视为
部署完成。

只有同时满足以下条件时，才进入真实 Gate：

1. 已确定要验证的具体 Gate 和审核过的 Git commit；
2. 使用隔离 owner、索引、Collection、Run ID 和私有运行目录；
3. 所有服务只绑定目标主机的回环地址；
4. 输入 PDF、问题集和配置的 SHA-256 已独立确认；
5. 操作者理解 Gate 会创建数据，并确认其清理与失败恢复步骤；
6. 只返回脱敏报告，不返回密钥、完整连接串、私有正文或本机路径。

远程 Stage 1 的权威入口是
[Stage 1 Remote Validation Package](../deploy/remote/stage1-validation/README.md)。
该清单面向仓库所有者在隔离的 Windows 主机上执行，并以 Windows PowerShell
5.1 为兼容基线。不要从聊天记录、旧截图或手工拼接命令替代版本化清单。

如果真实 Gate 失败：

- 立即保留原始错误码、Run ID、commit 和脱敏报告；
- 不修改输入、阈值或默认算法来制造通过；
- 不重启稳定服务来模拟或掩盖故障；
- 有残留时先走对应恢复 Gate，清理完成前不创建新的质量 Run；
- 不把 Fixture、Fake 或历史报告写成“当前远程服务可用”。

## 9. 常见问题

### `Project virtualenv is missing`

原因：仓库根目录缺少 `.venv`，或命令不在仓库根目录运行。

处理：

```bash
pwd
python3 -m venv .venv
.venv/bin/python -m pip install '.[dev,server]'
```

### `No module named uvicorn` 或 `No module named fastapi`

原因：依赖没有安装到仓库 `.venv`。

处理：

```bash
.venv/bin/python -m pip install '.[dev,server]'
```

不要用系统 `pip` 和仓库 `.venv` 混装。

### 端口 `8000` 已被占用

换一个本机端口，例如：

```bash
.venv/bin/python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8001
```

随后把请求地址中的 `8000` 同步改成 `8001`。

### 返回 `FIXTURE_ONLY_FAKE_LLM`

这是公开演示的预期边界，不是安装错误。它提醒操作者当前结果不能代表真实检索或
模型质量。

### 返回 `NO_EVIDENCE`

先检查问题是否能被当前授权 Fixture 支持。不要删除拒答逻辑，也不要把无关 Chunk
强行作为证据。

### 返回 `403`

检查 `document_ids`。客户端不能请求服务端范围之外的文档；不要通过改 Fixture
ACL 来“修好”越权用例。

### `make powershell-check` 找不到 `pwsh`

公开 API 演示仍可单独完成，但完整仓库静态门禁尚未通过。安装满足仓库门禁的
PowerShell 环境后再运行；交付前不要省略或伪报结果。

### 真实 ES、Milvus、PostgreSQL 或模型连接失败

停止当前真实 Gate，并按对应版本化清单定位。不要把服务地址改成公网地址，不要在
聊天或 Issue 中粘贴完整连接串，也不要用 Fixture 结果代替真实失败。

## 10. 交给下一位操作者前

交付说明至少包含：

- 仓库地址和准确 commit SHA；
- 操作系统、Python 版本和本次使用的命令；
- 实际通过的测试目标，不扩大为未运行的 Gate；
- API 使用的检索后端和生成边界；
- `COMPLETED`、`NO_EVIDENCE`、`403` 是否按预期出现；
- 是否存在 `FIXTURE`、`FAKE_LLM`、`DEGRADED` 或其他警告；
- 是否存在未提交修改；
- 若涉及真实 Gate，只附脱敏报告哈希和允许返回的摘要。

交付前建议执行：

```bash
git status -sb
git rev-parse HEAD
make harness-validate
make api-test
git diff --check
```

不要交付或提交：

- `.env`、API Key、密码和完整连接串；
- 私有 PDF、真实 Chunk、私有题目和未脱敏报告；
- `runtime/`、日志、数据库、索引、模型或 `.venv`；
- 带个人绝对路径的截图、配置或文档。

## 11. 继续阅读

- [项目首页](../README.md)：项目能力、阶段和边界摘要
- [RAG API 快速开始](RAG_API_QUICKSTART.md)：API 后端和注入方式
- [API 与数据合同](../contracts/README.md)：稳定字段、Schema 和错误码
- [项目完整技术文档](PROJECT_DOCUMENTATION.md)：架构、生命周期、评测与限制
- [当前阶段](CURRENT_PHASE.md)：动态状态、历史 Gate 和下一边界
- [仓库规则](../AGENTS.md)：开发、验证和完成门禁
- [仓库与数据策略](REPOSITORY_POLICY.md)：允许和禁止提交的内容
