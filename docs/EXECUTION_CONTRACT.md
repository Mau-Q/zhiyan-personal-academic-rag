# Execution Contract

## 1. 初始化

1. 确认仓库根目录和 Git 状态；
2. 按 `AGENTS.md` 读取当前状态与边界；
3. 运行 `make harness-validate`，由 Makefile 强制选择项目 `.venv`；
4. 区分用户要的是检查、诊断、实现还是部署。

## 2. 实施

- 先复用现有合同、模块和测试入口；
- 只修改完成当前目标需要的文件；
- Fixture、真实数据、本地运行和远程运行保持可辨识；
- 新能力必须同时提供最小测试；一次性操作命令在当次交互中一次性给全，每条命令分开编号和展示，不写入长期文档；
- 阶段外想法记录为下一门禁，不顺手实施。

## 3. 验证

验证按 `docs/RISK_BASED_TESTING_STRATEGY.md` 选择最小充分范围。普通低风险任务的最低门禁：

```bash
make harness-validate
# 运行受影响测试目标
git diff --check
```

仓库测试和 Harness 不得直接使用系统 `python3`。`.venv` 缺失时 Makefile 必须明确报错，不得静默降级。

阶段状态、合同、依赖、公共接口或跨模块代码变化时运行 `make test`；按风险增加固定 Canary、500 题 GPT 辅助基线、真实 PDF、HTTP、远程或安全验证。没有对应变量和失败信号时，不提前展开完整性能矩阵或大规模人工评审。缺少某个工具时必须区分“环境未安装”和“源码失败”。

## 4. 阶段结果

具体结果写入：

```text
runtime/phases/<phase-id>/phase_result.json
```

结构遵循 `machine/phase_result.schema.json`，参考 `machine/phase_result.template.json`。运行实例不进入 Git；不得填写未执行的命令、伪造 commit 或把脏工作区标成干净。

## 5. Git 收尾

- 成员 A 普通低风险任务：从最新 `main` 实施，只暂存本任务文件，门禁通过后 commit 并直接 push `main`；
- 成员 B 远程任务和高风险变更：从最新 `main` 建分支，通过 PR 交付；
- 高风险包括合同破坏、安全边界、真实数据、公网暴露和大型跨模块改动；
- 直推或 PR 前都必须审查 diff 并重跑门禁；
- 收尾时确认本地 `main` 与 `origin/main` 一致；
- 普通低风险直推不要求打开浏览器检查 Actions；CI 配置、依赖、跨平台、高风险变更，或本地门禁/远程状态异常时必须检查 Actions；
- Actions 失败时新增修复提交，不 force push。

## 6. 完成定义

只有代码、合同、测试、文档、机器状态和可执行证据互相一致时，才能把阶段标记为完成。计划、模板和未执行命令不属于完成证据。
