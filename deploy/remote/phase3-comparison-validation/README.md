# 阶段 3 双侧比较配对 dev Gate

目标平台是用户维护的 Windows 主机上的 Windows PowerShell 5.1。本目录只提供
用户运行入口；本地实现 Gate 不连接远程主机、不启动或重启服务。

## 判定边界

该入口只判定冻结的
`BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1`：

- 先用相同的三篇 PDF 建立隔离 owner 下的三个临时 READY 版本；
- 验证 PostgreSQL owner/READY、文档版本、316 个持久化 Chunk 与
  `section_parent_child_v1` 冻结身份一致；
- 保持每路候选 20、RRF `k=60`、质量判定 Top-3、Reranker 关闭；
- 先运行原问题 Control。若四个目标问题不再是 `0/4` 双侧命中，立即停止
  Treatment 并以 `CONTROL_BASELINE_MISMATCH` 关闭；
- 再运行唯一变量 Treatment，判定目标增益、非目标 answerable dev 不退化、
  dev no-evidence、固定 15 题、拆分 P95 和增量检索 P95；
- 报告写入前将三个版本置为 INACTIVE，完成 ES、Milvus、运行时快照共 9 个
  清理任务，并证明删除后 Answer API 返回 403。
- 完整报告写入实际 Git HEAD 和 Run ID；随后由独立裁决器用报告 SHA-256
  重新验证身份、指标算术、清理和 holdout 隔离。
- 冻结配置身份按 LF 规范化字节计算；Windows `core.autocrlf=true` 产生的纯
  CRLF 检出可回放为同一 SHA，内容变化、BOM 或孤立 CR 仍失败关闭。

非目标 `nDCG@10` 使用同一候选 20 内的评测诊断 Top-10，不改变产品/API
Top-3。输入包只含 `dev`、冻结 Chunk、固定 Canary 和三篇 PDF；不含或读取
`test`、`acceptance`。入口不调用生成模型，不启用 Cross-Encoder。

该 Gate 只看相对增量成本。阶段 2 留下的绝对 300 ms 性能债仍是独立 Gate；
无论本次结果如何，都不能解释为 300 ms SLO、生产性能、默认启用或阶段 3
完成。

## 1. Mac：生成并核对私有输入包

在包含私有 `runtime/` 资产的本地仓库运行：

```text
make phase3-comparison-dev-package PHASE3_PAPER_2601="/private/dev/2601.03260.pdf" PHASE3_PAPER_2602="/private/dev/2602.11409.pdf" PHASE3_PAPER_2603="/private/dev/2603.04915.pdf"
shasum -a 256 runtime/handoffs/phase3-comparison-paired-dev-input-v1.zip
unzip -p runtime/handoffs/phase3-comparison-paired-dev-input-v1.zip manifest.json | shasum -a 256
```

记录命令输出的 ZIP SHA-256 和 manifest SHA-256。ZIP 位于忽略的 `runtime/`，
不得提交；三个 PDF 路径必须由用户在准备真实 dev 运行时显式提供，构建器不会
读取任何 Acceptance 套件或查找隐含路径。使用既有安全文件传输方式将 ZIP
交给 Windows 用户。

## 2. Windows：`_07` 已完成，不得复跑

`phase3_comparison_dev_20260723_07` 已在提交
`ff370b512f88b7d847fa17f080946aab4050048c` 上完成完整 Control/Treatment，
稳定结果为 `QUALITY_OR_COST_THRESHOLD_NOT_MET`：

- Control/Treatment 对四个目标均为双侧 Top-3 命中 `0/4`；
- Recall@3 无增益，`nDCG@3` 下降 `0.017739`；
- 固定 15 题为 `14/15`，Control/Treatment 边界不完全一致；
- 增量检索 P95 `24.101115 ms`、拆分 P95 `0.12922 ms`，成本门禁通过；
- 清理 9/9、READY 失败关闭和删除后 403 通过，无需恢复。

报告 SHA-256：
`3810CE9228F7CE9C65B5BE0E031F1F5CA6A471FA665BF5D8C12A6E7CAC6E01390`。
裁决 SHA-256：
`99530D236B8CA50B53DE18557C9D43C7BCC63695A3C98FC9DBA889B33CDAA036`。
裁决为 `KEEP_COMPARISON_DECOMPOSITION_DISABLED`。

当前没有获准执行的新 Windows Run ID 或 PowerShell 命令。不得复用 `_07`，
不得调参重跑，不得进入 `test/acceptance`。下一节点必须先在 Mac 上基于冻结
dev 证据选择并冻结一个新的单一变量，形成独立本地提交和新的版本化运行入口。

## 3. 停止规则

- Git 有 tracked 改动、HEAD 不等于 `origin/main`、输入身份漂移：不运行。
- Canary 数据库存在其他 `PENDING/RETRY/RUNNING` 清理任务：在任何新入库前
  失败关闭；本 Gate 不领取其他 owner 的清理任务。
- Control 不复现 `0/4`：不运行 Treatment。
- READY/ACL/版本/Chunk 身份无法证明：403 或失败关闭。
- 任一质量、不退化、固定 15 题或增量预算未达标：结果为 FAIL，不调参重跑。
- 清理或删除后 403 证明不完整：最终结果强制为 FAIL。
- 不得用 `test` 或 `acceptance` 调参，不得修改候选数、RRF、Embedding、
  Chunk、Reranker、缓存或默认开关制造通过。
