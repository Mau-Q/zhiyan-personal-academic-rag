# 双人并行分工与交付边界

## 1. 当前目标

最高方案的“阶段 0：范围冻结与基线建立”已完成，当前进入阶段 1。仓库内部 M0 已完成下列可审计最小链路，但它不替代 PostgreSQL 事实源、幂等入库与双索引一致性闭环：

```text
本地 PDF
→ 文本、章节和页码解析
→ ChunkRecordV1
→ 授权过滤与确定性检索
→ 非流式 Answer API
→ COMPLETED 或 NO_EVIDENCE
→ Evidence、Citation 和 PDF 页码
```

远程主机已完成早期准备。后续迁移、部署和验证由用户亲自操作，代理负责准备版本化脚本、完整命令和结果判定。

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

## 3. 用户（远程操作人）

早期远程准备由成员 B 完成并已保留历史证据。从 PD-027 开始，用户负责亲自执行后续远程操作：

- 操作系统、CPU、内存、磁盘、GPU、驱动和 CUDA 盘点；
- Git、Python、Docker、Docker Compose 和 NVIDIA Container Toolkit 检查；
- 远程部署目录、仓库拉取和版本同步；
- PostgreSQL、Elasticsearch、Milvus、模型服务的真实可用状态记录；
- 端口、防火墙、监听范围和密钥保存边界；
- 按操作清单确认远程与本地待验收提交 SHA 一致；
- 在远程运行迁移、测试、Fixture API 冒烟和故障验证；
- 只返回脱敏原始输出，不回传密码、DSN、IP、Token 或 `.env`；
- 维护 `docs/REMOTE_HOST_READINESS.md`。

对应 GitHub 任务：

- [Issue #9：远程主机准备与部署验证](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/9)

## 4. 文件所有权

| 范围 | 主要负责人 |
|---|---|
| `backend/ingestion/`、`backend/retrieval/`、`backend/rag/`、`backend/api/` | 成员 A |
| `tests/ingestion/`、`tests/retrieval/`、`tests/rag/`、`tests/api/` | 成员 A |
| `deploy/`、远程检查脚本、`docs/REMOTE_HOST_READINESS.md` | 代理准备，用户执行 |
| `contracts/`、`tests/contracts/` | 冻结共享边界，破坏性变更必须先说明 |

成员 A 的普通低风险模块不强制 PR 或互审。合同破坏性变更、安全边界变化、远程公网暴露、真实数据处理和大型跨模块改动必须先确认并走 PR。

## 5. Git 交付

- 成员 A 从最新 `main` 实施普通低风险任务，本地 Harness、受影响测试和 diff 检查通过后可直接 commit 并 push `main`；
- 用户不在远程主机直接编辑源码；远程只拉取已审查的提交并执行版本化操作清单；
- 只提交自己负责范围内的源码、测试和文档；
- 不使用即时通讯压缩包交付源码；
- 普通低风险直推后核对本地与远程 SHA；CI 配置、依赖、跨平台、高风险变更或异常状态再检查 GitHub Actions；
- 不提交 PDF、`.env`、密钥、IP 凭据、数据库、索引、模型权重和运行目录。

## 6. 集成顺序

### 6.1 可并行的三条工作线

1. **A：本地检索与 RAG 工程线**
   - 先完成真实本地向量检索基线；
   - 用同一 3 论文 15 题 Canary 对比词项、SQLite BM25 和向量检索；
   - 再实现混合融合，有证据增益后才接重排；
   - 检索证据链稳定后，再单独接真实 LLM 与引用校验。

2. **用户：远程主机与基础设施线**
   - 盘点硬件、GPU/CUDA、Docker、端口和安全边界；
   - 拉取同一 `main` 运行 Harness、全量测试和 Fixture API；
   - 基线通过后按 PostgreSQL、Elasticsearch、Milvus、模型服务的顺序逐项接入；
   - 每项单独记录版本、资源、可用性、监听范围和性能基线。

3. **共享：范围与评测线**
   - 维护已冻结的首期知识源、目标语料量、峰值并发、SLO 和资源预算；
   - 保留 15 题作为快速 Canary，现有 500 题作为候选池和稳定迭代证据；
   - 175 题真实人工校验、同集 ES/Milvus 单路 Baseline、三种 Chunk 受控 Baseline、范围/资源/SLO 和数据身份/生命周期合同均已完成；下一步按合同实现阶段 1。

### 6.2 合流点

- 已完成的远程主机盘点继续作为部署约束；
- 代理在本地门禁通过后交付一次性完整命令，用户在同一提交上执行；
- 远程每接入一项真实基础设施，都用 A 的固定 Canary 和扩展评测集复测；
- PostgreSQL 身份事实源、幂等任务、双索引对账和删除/撤权闭环未实现前，不将最高方案阶段 1 标记为完成。
