# 远程主机准备与部署验证记录

> 负责人：成员 B。本文档只能记录脱敏状态，不得写入 IP、用户名、密码、Token、私钥或 `.env` 内容。

## 1. 状态值

- `CONFIRMED`：已执行命令并确认可用；
- `NOT_INSTALLED`：已确认未安装；
- `PERMISSION_REQUIRED`：缺少权限，尚未验证；
- `DEFERRED`：当前阶段不接入；
- `NOT_CHECKED`：尚未检查。

## 2. 主机资源

| 项目 | 状态 | 脱敏结果 | 验证命令 |
|---|---|---|---|
| 操作系统和架构 | `NOT_CHECKED` |  | `uname -a` |
| CPU | `NOT_CHECKED` |  | `lscpu` |
| 内存 | `NOT_CHECKED` |  | `free -h` |
| 磁盘 | `NOT_CHECKED` |  | `df -h` |
| GPU | `NOT_CHECKED` |  | `nvidia-smi` |
| CUDA | `NOT_CHECKED` |  | `nvcc --version` |

## 3. 基础工具

| 项目 | 状态 | 版本或说明 |
|---|---|---|
| Git | `NOT_CHECKED` |  |
| Python 3.11+ | `NOT_CHECKED` |  |
| Docker | `NOT_CHECKED` |  |
| Docker Compose | `NOT_CHECKED` |  |
| NVIDIA Container Toolkit | `NOT_CHECKED` |  |

## 4. 可选基础设施

| 服务 | 状态 | 监听范围 | 当前动作 |
|---|---|---|---|
| PostgreSQL | `DEFERRED` | 未记录 | 仅检查，不部署 |
| Elasticsearch | `DEFERRED` | 未记录 | 仅检查，不部署 |
| Milvus | `DEFERRED` | 未记录 | 仅检查，不部署 |
| 模型服务 | `DEFERRED` | 未记录 | 仅检查，不调用 |

## 5. 仓库与部署目录

- 仓库：<https://github.com/Mau-Q/zhiyan-personal-academic-rag>
- 部署目录：仅记录逻辑名称，不记录包含用户名的绝对路径；
- 拉取方式：GitHub `git clone` / `git pull --ff-only`；
- 当前验证提交：`NOT_CHECKED`；
- 工作树状态：`NOT_CHECKED`。

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
- Elasticsearch：`NOT_INSTALLED`；未部署、未连接。
- Milvus：`NOT_INSTALLED`；未部署、未连接。
- 模型服务：`NOT_INSTALLED`；未部署、未连接。
- 仓库 Harness：`CONFIRMED`，`8/8` 检查通过。
- Python 测试：`62` 项通过；`5` 项未通过。原因是 Windows 环境没有 `python3` 命令，部分测试子进程返回退出码 `9009`；该问题未通过修改核心代码或安全配置绕过。
- Fixture API：`CONFIRMED`，仅监听 `127.0.0.1:8000`。
- HTTP 冒烟：`CONFIRMED`。
  - `COMPLETED`：HTTP `200`，返回 Evidence、Citation 和 `FIXTURE_ONLY_FAKE_LLM` 边界标识。
  - `NO_EVIDENCE`：HTTP `200`，`evidence=[]`。
  - 越权请求：HTTP `403`，`code=RAG_FORBIDDEN_SCOPE`，`retryable=false`。
