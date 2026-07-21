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
