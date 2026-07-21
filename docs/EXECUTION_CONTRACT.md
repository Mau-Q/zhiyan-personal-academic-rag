# Execution Contract

## 1. 初始化

1. 确认仓库根目录和 Git 状态；
2. 按 `AGENTS.md` 读取当前状态与边界；
3. 运行 `python3 scripts/validate_harness_contract.py`；
4. 区分用户要的是检查、诊断、实现还是部署。

## 2. 实施

- 先复用现有合同、模块和测试入口；
- 只修改完成当前目标需要的文件；
- Fixture、真实数据、本地运行和远程运行保持可辨识；
- 新能力必须同时提供最小测试和操作说明；
- 阶段外想法记录为下一门禁，不顺手实施。

## 3. 验证

最低门禁：

```bash
python3 scripts/validate_harness_contract.py
make test
git diff --check
```

按风险增加真实 PDF、HTTP、远程或安全验证。缺少某个工具时必须区分“环境未安装”和“源码失败”。

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
- 直推后的 GitHub Actions 是复验门禁，失败时新增修复提交，不 force push；
- 收尾时确认本地 `main` 与 `origin/main` 一致。

## 6. 完成定义

只有代码、合同、测试、文档、机器状态和可执行证据互相一致时，才能把阶段标记为完成。计划、模板和未执行命令不属于完成证据。
