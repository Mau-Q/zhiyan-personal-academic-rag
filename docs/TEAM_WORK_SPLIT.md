# 双人并行分工与交付边界

## 1. 当前目标

当前优先完成一条可在普通本地电脑独立运行、可审计、可重复的最小链路：

```text
本地 PDF
→ 文本、章节和页码解析
→ ChunkRecordV1
→ 授权过滤与确定性检索
→ 非流式 Answer API
→ COMPLETED 或 NO_EVIDENCE
→ Evidence、Citation 和 PDF 页码
```

远程主机准备与本地核心代码并行，但不作为本地 M0 的前置条件。

## 2. 成员 A

成员 A 负责完整的本地核心链路：

- PDF 文本解析、解析质量门禁和 SHA-256 身份校验；
- 本地显式切分策略和稳定 Chunk ID；
- `ChunkRecordV1` 适配、页码范围、父子关系和相邻 Chunk 链接；
- 授权过滤、检索、Answer API、拒答、Evidence 和 Citation；
- 本地真实 PDF 联调、自动测试、CI 和核心代码合并；
- 冻结合同及跨模块集成决策。

对应 GitHub 任务：

- [Issue #4：本地 PDF 到 ChunkRecordV1](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/4)
- [Issue #5：单篇论文回答、拒答与引用联调](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/5)

## 3. 成员 B

成员 B 负责远程环境和部署验证：

- 操作系统、CPU、内存、磁盘、GPU、驱动和 CUDA 盘点；
- Git、Python、Docker、Docker Compose 和 NVIDIA Container Toolkit 检查；
- 远程部署目录、仓库拉取和版本同步；
- PostgreSQL、Elasticsearch、Milvus、模型服务的真实可用状态记录；
- 端口、防火墙、监听范围和密钥保存边界；
- 本地链路合并后，在远程拉取同一提交运行测试和 Fixture API 冒烟；
- 维护 `docs/REMOTE_HOST_READINESS.md`。

对应 GitHub 任务：

- [Issue #9：远程主机准备与部署验证](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/9)

## 4. 文件所有权

| 范围 | 主要负责人 |
|---|---|
| `backend/ingestion/`、`backend/retrieval/`、`backend/rag/`、`backend/api/` | 成员 A |
| `tests/ingestion/`、`tests/retrieval/`、`tests/rag/`、`tests/api/` | 成员 A |
| `deploy/`、远程检查脚本、`docs/REMOTE_HOST_READINESS.md` | 成员 B |
| `contracts/`、`tests/contracts/` | 冻结共享边界，破坏性变更必须先说明 |

成员 A 的普通低风险模块不强制 PR 或互审。合同破坏性变更、安全边界变化、远程公网暴露、真实数据处理和大型跨模块改动必须先确认并走 PR。

## 5. Git 交付

- 成员 A 从最新 `main` 实施普通低风险任务，本地门禁通过后可直接 commit 并 push `main`；
- 成员 B 从最新 `main` 建立功能分支，通过 GitHub PR 交付远程任务；
- 只提交自己负责范围内的源码、测试和文档；
- 不使用即时通讯压缩包交付源码；
- 直推后检查 GitHub Actions，失败时新增修复提交；
- 不提交 PDF、`.env`、密钥、IP 凭据、数据库、索引、模型权重和运行目录。

## 6. 集成顺序

1. 成员 A 在本地完成 PDF 到 Answer API；
2. 本地测试和真实 PDF 冒烟通过后合并到 `main`；
3. 成员 B 在远程拉取同一 `main` 提交；
4. 成员 B 先运行相同测试和 Fixture API，不立即接真实基础设施；
5. 远程基线通过后，再分别建立数据库、检索基础设施和模型接入任务。
