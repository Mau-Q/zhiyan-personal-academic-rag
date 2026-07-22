# 远程主机准备与部署验证记录

> 当前远程操作人：用户。代理负责准备脚本、操作清单和结果判定。本文档只能记录脱敏状态，不得写入 IP、用户名、密码、Token、私钥或 `.env` 内容。

## 1. 状态值

- `CONFIRMED`：已执行命令并确认可用；
- `NOT_INSTALLED`：已确认未安装；
- `PERMISSION_REQUIRED`：缺少权限，尚未验证；
- `DEFERRED`：当前阶段不接入；
- `NOT_CHECKED`：尚未检查。

## 2. 主机资源

| 项目 | 状态 | 脱敏结果 | 验证命令 |
|---|---|---|---|
| 操作系统和架构 | `CONFIRMED` | Windows 11 x64，WSL2/Linux Docker Engine | PowerShell、`wsl --status`、`docker info` |
| CPU | `CONFIRMED` | Intel Core i7-12700K，12 核 20 线程 | `Get-CimInstance Win32_Processor` |
| 内存 | `CONFIRMED` | 约 64 GB | PowerShell 主机盘点 |
| 磁盘 | `CONFIRMED` | 数据盘约 927 GB，总余量约 400 GB；Docker/模型持久化不得新增到低余量盘 | `Get-Volume` |
| GPU | `CONFIRMED` | NVIDIA GeForce RTX 4090，24564 MiB | `nvidia-smi` |
| CUDA | `CONFIRMED` | 驱动兼容 13.1；`nvcc 11.3` | `nvidia-smi`、`nvcc --version` |

## 3. 基础工具

| 项目 | 状态 | 版本或说明 |
|---|---|---|
| Git | `CONFIRMED` | 2.40.0.windows.1 |
| Python 3.11+ | `CONFIRMED` | 3.11.15，仓库使用 `.venv` 的解释器 |
| Docker | `CONFIRMED` | Docker Desktop 4.38.0，Engine 27.5.1，linux/amd64 |
| Docker Compose | `CONFIRMED` | v2.32.4-desktop.1 |
| NVIDIA Container Toolkit | `DEFERRED` | 原生 Windows Ollama 已验证 GPU；当前不引入 GPU 容器变量 |

## 4. 可选基础设施

| 服务 | 状态 | 监听范围 | 当前动作 |
|---|---|---|---|
| PostgreSQL | `CONFIRMED` | 5432；HBA 仅允许回环认证 | 18.4 可连接，尚未接入应用 |
| Elasticsearch | `CONFIRMED` | `127.0.0.1:9200` | 9.4.3 工程基线通过 |
| Milvus | `CONFIRMED` | `127.0.0.1:19530/9091` | 2.6.18 standalone 工程基线通过 |
| 模型服务 | `CONFIRMED` | `127.0.0.1:11434` | Ollama 0.30.10 + BGE-M3 GPU 冒烟通过 |

## 5. 仓库与部署目录

- 仓库：<https://github.com/Mau-Q/zhiyan-personal-academic-rag>
- 部署目录：仅记录逻辑名称，不记录包含用户名的绝对路径；
- 拉取方式：GitHub `git clone` / `git pull --ff-only`；
- 当前验证提交：`8b22e56`；
- 工作树状态：验证时干净。

## 6. 远程验收

- [ ] 拉取指定 `main` 提交；
- [ ] 建立忽略的本地虚拟环境；
- [ ] 安装项目依赖；
- [ ] `make test` 全部通过；
- [ ] Fixture API 仅监听 `127.0.0.1` 或受控内网；
- [ ] `COMPLETED`、`NO_EVIDENCE`、403 越权三条 HTTP 冒烟通过；
- [ ] 输出和日志不含密钥、凭据、PDF 正文或本机绝对路径；
- [ ] 将验证日期、提交和结果更新到本文档并通过 PR 交付。

## 7. 禁止事项

- 不直接向公网开放数据库、向量库、模型或 API 端口；
- 不把真实凭据写入 Git、Issue、PR、截图或日志；
- 不上传 PDF、数据库、索引、模型权重和用户数据；
- 不在本地 M0 未合并前修改核心合同和入库实现；
- 不把“命令存在”当作服务已经可用，必须记录实际检查结果。

## 8. Windows 远程验证结果

- 验证提交：`ff5993e`
- 工作树：干净。
- 操作系统：Windows 11 x64。
- 内存：约 64 GB。
- GPU：NVIDIA GeForce RTX 4090，约 24 GB 显存。
- NVIDIA 驱动：`591.86`；驱动报告 CUDA 兼容版本 `13.1`。
- CUDA 编译器：`nvcc 11.3`。
- Git：`2.40.0.windows.1`，`CONFIRMED`。
- Python：`3.11.15`，`CONFIRMED`。
- Docker：`27.5.1`，Docker 守护进程可用，`CONFIRMED`。
- Docker Compose：`v2.32.4-desktop.1`，`CONFIRMED`。
- GNU Make：`NOT_INSTALLED`；Windows 主机使用 Makefile 对应的 Python unittest 命令执行测试。
- NVIDIA Container Toolkit：`DEFERRED`；当前为原生 Windows 主机，未接入 Linux/WSL2 GPU 容器运行时。
- PostgreSQL：`CONFIRMED`，已安装且运行；本阶段未连接或部署。
- Elasticsearch：`CONFIRMED`；9.4.3 单节点工程基线可用，尚未接入应用。
- Milvus：`CONFIRMED`；2.6.18 standalone 工程基线可用，尚未接入应用。
- 模型服务：`CONFIRMED`；Ollama `0.30.10` 已安装，BGE-M3 1024 维向量以 GPU 执行。
- 仓库 Harness：`CONFIRMED`，`8/8` 检查通过。
- Python 测试：Windows 子进程解释器问题已修复；最新提交的 evaluation 测试 `45/45` 通过。全仓最新 Windows 回归尚未重新执行，不用局部结果替代全量结论。
- Fixture API：`CONFIRMED`，仅监听 `127.0.0.1:8000`。
- HTTP 冒烟：`CONFIRMED`。
  - `COMPLETED`：HTTP `200`，返回 Evidence、Citation 和 `FIXTURE_ONLY_FAKE_LLM` 边界标识。
  - `NO_EVIDENCE`：HTTP `200`，`evidence=[]`。
  - 越权请求：HTTP `403`，`code=RAG_FORBIDDEN_SCOPE`，`retryable=false`。

## 9. 检索基础设施基线

- Elasticsearch `9.4.3`：单节点 `green`，中文 BM25、租户/用户过滤和重启持久化通过；
- Milvus `2.6.18`：1024 维 COSINE Collection、BGE-M3 写入、授权过滤搜索和完整重启恢复通过；
- 所有宿主机发布端口均限制为 `127.0.0.1`；
- Elasticsearch/Milvus 持久化数据放置于容量充足的数据盘；
- 详细边界与版本化配置见 `docs/REMOTE_RETRIEVAL_BASELINE.md`。
