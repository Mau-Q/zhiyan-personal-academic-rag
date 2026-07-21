# Repository Harness Architecture

## 目的

仓库 Harness 让成员和自动化工具仅凭当前提交即可回答四个问题：现在处于什么阶段、允许改什么、怎样验证、什么证据才算完成。

它不实现 RAG 检索或质量评测。`backend/evaluation/` 是业务评测 Harness；本文件描述的是仓库治理 Harness。

## 四层结构

| 层 | 文件 | 职责 |
|---|---|---|
| 最高需求映射 | [`REQUIREMENTS_TRACEABILITY.md`](REQUIREMENTS_TRACEABILITY.md) | 记录最高方案身份、阶段口径、需求差距和下一门禁 |
| 入口 | [`AGENTS.md`](../AGENTS.md) | 阅读顺序、权威映射和硬规则 |
| 人类合同 | [`PROJECT_GUARDRAILS.md`](PROJECT_GUARDRAILS.md)、[`PRODUCT_DECISIONS.md`](PRODUCT_DECISIONS.md)、[`EXECUTION_CONTRACT.md`](EXECUTION_CONTRACT.md)、[`CURRENT_PHASE.md`](CURRENT_PHASE.md) | 长期约束与当前阶段 |
| 机器合同 | [`project_state.json`](../machine/project_state.json)、[`feature_list.json`](../machine/feature_list.json)、[`phase_result.schema.json`](../machine/phase_result.schema.json) | 状态、能力和结果结构 |
| 可执行门禁 | [`validate_harness_contract.py`](../scripts/validate_harness_contract.py)、[`tests/harness/`](../tests/harness/) | 一致性、路径、安全和回归校验 |

## 权威关系

- 建设目标、目标架构和最终验收冲突：最高方案优先，仓库通过 `REQUIREMENTS_TRACEABILITY.md` 记录对齐；
- 工作方式冲突：`AGENTS.md` 与执行合同优先于普通说明文档；
- 业务语义冲突：版本化 `contracts/` 优先于 README 和阶段叙述；
- 完成度冲突：机器状态与可执行证据必须同时支持，单独文字声明无效；
- 当前阶段与长期决策冲突：停止实施并修正权威文件，不选择对自己有利的一份继续。

## 状态流

```text
核对最高方案身份与需求映射
→ 读取仓库权威文件
→ 校验 Harness
→ 确定任务边界
→ 实施和测试
→ 写入本地 phase_result
→ 同步阶段状态
→ 低风险直推 main 或高风险 PR
```

`runtime/` 始终被 Git 忽略。阶段结果 Schema 和模板进入仓库，具体运行实例只留在本地或受控交付环境。
