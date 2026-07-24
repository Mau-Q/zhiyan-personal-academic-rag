# 智研个人学术空间 RAG

面向个人论文库的证据约束型 RAG 核心服务。项目以 PostgreSQL 保存文档身份、
授权范围和生命周期事实，以 Elasticsearch 与 Milvus 提供混合召回，并让生成、
引用、拒答和证据审计都能回到具体论文版本、页码与 Chunk。

仓库地址：<https://github.com/Mau-Q/zhiyan-personal-academic-rag>

## 已验证主链

```text
PDF / Chunk
→ PostgreSQL READY / owner ACL
→ Elasticsearch + Milvus
→ RRF
→ 真实生成
→ Citation
→ Multi-Evidence 审计
→ NO_EVIDENCE
→ 删除失效与 ES / Milvus / runtime 清理
```

这条链路已有版本化本地测试和用户执行的脱敏远程证据。它证明当前 RAG
核心可以按身份和权限失败关闭，不代表所有计划中的产品能力或生产 SLO 已完成。

## 当前阶段

| 最高方案阶段 | 状态 | 当前边界 |
|---|---|---|
| 阶段 0：范围与 Baseline | `COMPLETE` | 范围、资源、SLO 目标、数据身份和评测 Baseline 已冻结 |
| 阶段 1：数据与索引最小闭环 | `COMPLETE` | PDF/Chunk、PostgreSQL READY、ES/Milvus、删除和三路清理闭环已验证 |
| 阶段 2：基础 RAG MVP | `COMPLETE` | RRF、真实生成、Citation、拒答、ACL 与稳定回放已验证 |
| 阶段 3：失败类型增强 | `PARTIAL / WORKSTREAM_CLOSED_WITHOUT_PROMOTION` | 两个 V1 在冻结 `dev` 上未产生稳定净增益，均保持关闭 |
| 阶段 4：Claim–Evidence 可靠性 | `PARTIAL` | 确定性 Multi-Evidence 审计核心完成；语义 Judge 与在线硬裁决后置 |
| 阶段 5：复杂科研问答与复用 | `NOT_STARTED` | 不在当前仓库节点的交付范围 |

动态状态、历史 Gate 和精确证据以
[`docs/CURRENT_PHASE.md`](docs/CURRENT_PHASE.md) 与
[`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md)
为准，README 只保留稳定摘要。

## 默认决策

- 默认检索路径是 PostgreSQL `READY`/owner 前置校验后的 ES + Milvus
  rank-only RRF。
- 固定 Cross-Encoder Reranker 已保留为可选组件，但不默认启用。
- Multi-Evidence EvidenceSet 保持 `AUDIT_ONLY`，不自动删除 Claim，也不冒充
  人工真值或通用语义蕴含。
- 当前多语言 NLI 候选因真实质量 Gate 失败而拒绝，不进入在线硬裁决。
- 检索 P95 `300 ms` 是独立性能债；功能闭环完成不等于该 SLO 已通过。

## 已验证能力与真实边界

已验证：

- 带文本层 PDF 的确定性切片、版本身份、持久化快照和幂等重放；
- PostgreSQL 事实源、owner 隔离、双索引 `READY` 门禁和失败关闭；
- 真实 Elasticsearch BM25、Milvus/BGE-M3 与 ES + Milvus RRF；
- 冻结模型与配置下的真实 Qwen 生成、Citation 稳定映射和
  `NO_EVIDENCE` 不调用模型；
- 删除后不可召回、Answer API 返回 403，以及 ES、Milvus、runtime snapshot
  三路清理与恢复；
- 单/多 Evidence 的确定性身份、数字、单位、比较、限定和冲突审计。

边界：

- 公开 Fixture/Fake 路径只用于合同、权限和失败语义测试，不是当前真实能力的
  替代证据；
- 远程结论来自冻结提交上的用户执行与脱敏报告，不表示远程服务此刻持续在线；
- 确定性 EvidenceSet 不是人工裁决、NLI 金标或通用语义 Judge；
- 正式 MinIO、OCR、目标规模容量/性能、完整运维告警和生产发布回滚仍未验收。

## 最小开发与测试

需要 Python 3.11+。Makefile 强制使用仓库 `.venv`，不会回退到系统 Python：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev,server]'
```

提交前最小完整门禁：

```bash
make harness-validate
make test
make powershell-check
git diff --check
```

`make powershell-check` 需要本机 `pwsh`，只做 Windows PowerShell 5.1
兼容性解析和静态检查，不替代 Windows 行为验证。API 启动与请求示例见
[`docs/RAG_API_QUICKSTART.md`](docs/RAG_API_QUICKSTART.md)。

## 文档导航

- 当前阶段与下一门禁：[`docs/CURRENT_PHASE.md`](docs/CURRENT_PHASE.md)
- 最高方案需求追踪：[`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md)
- 长期产品决策：[`docs/PRODUCT_DECISIONS.md`](docs/PRODUCT_DECISIONS.md)
- 安全与真实性边界：[`docs/PROJECT_GUARDRAILS.md`](docs/PROJECT_GUARDRAILS.md)
- 实施和收尾规则：[`docs/EXECUTION_CONTRACT.md`](docs/EXECUTION_CONTRACT.md)
- API 与 Schema 合同：[`contracts/README.md`](contracts/README.md)
- PostgreSQL 事实源：[`docs/POSTGRESQL_FACT_SOURCE.md`](docs/POSTGRESQL_FACT_SOURCE.md)
- 阶段 2 收口：[`docs/PHASE_2_CLOSEOUT.md`](docs/PHASE_2_CLOSEOUT.md)
- Multi-Evidence Gate：[`docs/PHASE_4_MULTI_EVIDENCE_SET_GATE.md`](docs/PHASE_4_MULTI_EVIDENCE_SET_GATE.md)
- 仓库 Harness 入口：[`AGENTS.md`](AGENTS.md)

## 数据与仓库边界

Git 只保存源码、合同、测试、配置样例、公开 Fixture 和脱敏元数据。以下内容不得
进入版本历史：

- `.env`、API Key、数据库密码、连接串和签名凭据；
- 私有论文、用户 PDF、真实 Chunk、私有问题与未脱敏评测正文；
- PostgreSQL dump、SQLite live data、ES/Milvus/MinIO 数据目录；
- 模型权重、Embedding 缓存、虚拟环境和依赖缓存；
- `runtime/`、日志、Trace 正文、运行报告及本机绝对路径。

`.env.example` 只提供无密钥字段示例。完整规则见
[`docs/REPOSITORY_POLICY.md`](docs/REPOSITORY_POLICY.md)。

## 当前不负责

当前仓库节点不负责知识库接入、前端、演示、对外 Agent API、阶段 5
复杂科研问答，也不以 README 宣布这些能力完成。

## 许可证

仓库当前公开，但尚未添加项目级开源许可证。除适用法律默认允许的范围外，
不要据此假定代码已获复制、修改或分发授权；第三方依赖说明见
[`docs/THIRD_PARTY_NOTICES.md`](docs/THIRD_PARTY_NOTICES.md)。
