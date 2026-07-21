# Repository Harness Entry

本文件适用于整个仓库。聊天记录不是长期项目状态；开始工作前必须从仓库内的权威文件恢复上下文。

## 必读顺序

1. [`machine/project_state.json`](machine/project_state.json)：当前阶段和执行边界；
2. [`docs/CURRENT_PHASE.md`](docs/CURRENT_PHASE.md)：本阶段输入、验收、Git 和下一门禁；
3. [`docs/PROJECT_GUARDRAILS.md`](docs/PROJECT_GUARDRAILS.md)：数据、安全、真实性和范围硬边界；
4. [`docs/PRODUCT_DECISIONS.md`](docs/PRODUCT_DECISIONS.md)：已接受的长期决策；
5. [`docs/EXECUTION_CONTRACT.md`](docs/EXECUTION_CONTRACT.md)：实施、验证和收尾规则；
6. [`machine/feature_list.json`](machine/feature_list.json)：能力完成度与证据路径；
7. 与任务直接相关的 `contracts/`、源码、测试和专题文档。

## 初始化

```bash
git status -sb
python3 scripts/validate_harness_contract.py
```

若 Harness 校验失败，先修复仓库状态或明确报告阻塞，不绕过校验继续扩大范围。

## 权威边界

- 用户当前明确指令决定本次任务目标，但不能把 Fixture、Fake、计划或未验证状态表述为真实完成；
- API、Schema、权限和错误语义以 `contracts/` 为准；
- 阶段状态以 `machine/project_state.json` 和 `docs/CURRENT_PHASE.md` 的一致交集为准；
- 长期决策以 `docs/PRODUCT_DECISIONS.md` 为准；
- README 是入口说明，不单独证明能力完成。

## 硬规则

- 不提交 PDF、真实 Chunk、私有题目、运行报告、密钥、数据库、索引、模型或本机绝对路径；
- 不把父级知识库目录当作本仓库根目录；
- 不在远程结果返回前声称远程主机、Elasticsearch、Milvus 或真实模型已可用；
- 不用评测 Harness 代替仓库 Harness，也不用仓库 Harness 证明 RAG 质量；
- 不同时引入多个真实基础设施变量；
- 成员 A 的普通低风险任务在本地 Harness、受影响测试和 diff 检查通过后可直接推送 `main`；
- 成员 B 的远程任务，以及合同破坏、安全边界、真实数据、公网暴露和大型跨模块变更必须走 PR 并先确认。

## 完成门禁

普通低风险任务至少执行：

```bash
python3 scripts/validate_harness_contract.py
# 运行与改动直接相关的测试目标；阶段、合同或跨模块变更运行 make test
git diff --check
```

阶段状态变化时同步更新 `docs/CURRENT_PHASE.md`、`machine/project_state.json` 和 `machine/feature_list.json`。具体运行证据写入被忽略的 `runtime/phases/<phase-id>/phase_result.json`，不得提交伪造的运行结果。

成员 A 直接推送后确认本地 `HEAD` 与 `origin/main` 一致。只有 CI 配置、依赖、跨平台、高风险变更，或本地门禁/远程状态异常时，GitHub Actions 才是必查项；失败时新增修复提交，不改写 `main` 历史。
