# 阶段 3 路由覆盖配对 dev Gate

> 目标平台：用户维护的 Windows 主机，Windows PowerShell 5.1。
> 本页保留已完成 Gate 的版本化证据与历史命令；旧 Run ID 已关闭。

本 Gate 只判定默认关闭的
`BILATERAL_COMPARISON_ROUTE_COVERAGE_TOP3_V1`。首个查询拆分变量的 `_01`～
`_07` 已历史关闭；本页的路由覆盖 Run ID 也已完成并关闭，均不得复跑或复用。

新 Run ID：

```text
phase3_comparison_route_coverage_dev_20260724_01
```

## 已完成结果

该 Run ID 已在提交 `28b8987641ebd2754c2676f144dfa3abf4cdc041` 上完成：

- 报告 `FAIL / QUALITY_OR_COST_THRESHOLD_NOT_MET`；
- 裁决 `KEEP_COMPARISON_ROUTE_COVERAGE_DISABLED`；
- 报告 SHA-256
  `C2758BE68E614D5E075595B34C2386FA200B7DE13358DF8DB5193CCAD69A6A19`；
- 裁决 SHA-256
  `7492DC7574A2176351DDEEBCDED80230D66216FA2C923BBB4713182945CE4797`；
- 选择器 4/4 `APPLIED`、3/4 改变 Top-3，但双侧命中、Recall@3 和 nDCG@3
  均无增益；
- 清理 9/9、READY 失败关闭、删除后 403，故无需恢复。

报告和裁决落盘后，旧提交的脱敏汇总访问了完整报告中不存在的可选
`primary_error_code`，在严格模式抛出 `PropertyNotFoundStrict`。这不影响上述
证据；当前脚本仅修复可选汇总字段读取。禁止用本页旧命令重跑质量。

首次 Windows 收口复核也没有通过：Python 29 项批次为 `1 failure / 3 errors`；
静态检查在参数默认绑定阶段取得空 `$PSScriptRoot`；手工相对路径解析没有取得
AST，后续 helper 检查级联失败；最后无条件打印的 `PASS` 无效。这些都是验证
清单缺陷，没有运行质量 Gate、服务或私有输入。

后续不再粘贴长验证逻辑。修复提交从 Mac 推送且 Windows 精确快进后，只运行
版本化的
`verify_phase3_comparison_closeout.ps1`。它使用显式根目录和绝对解析路径，
任一失败立即终止；不会执行旧质量入口或通用 Python 测试批次。

第二次复核已成功快进到提交 `79861c6`，随后因 Windows PowerShell 5.1
模块路径没有 `PSScriptAnalyzer 1.25.0` 而正确终止。无需在 Windows 安装模块：
PSScriptAnalyzer 只属于 Mac 提交前静态 Gate；当前 Windows 入口只依赖系统
内置 Parser 和严格模式行为检查。

```powershell
Set-Location 'C:\Users\Administrator\zhiyan-personal-academic-rag'

git status -sb
git fetch origin main
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
    throw 'Windows checkout could not fast-forward to origin/main.'
}

$ExpectedHeadCommit = (& git rev-parse origin/main).Trim()
& '.\deploy\remote\phase3-comparison-validation\verify_phase3_comparison_closeout.ps1' `
    -RepositoryRoot 'C:\Users\Administrator\zhiyan-personal-academic-rag' `
    -ExpectedHeadCommit $ExpectedHeadCommit
if ($LASTEXITCODE -ne 0) {
    throw 'Phase 3 closeout verification failed.'
}
```

## 判定边界

- 使用原 dev-only ZIP：105 条 `dev`、316 个冻结 Chunk、固定 15 题和三篇
  PDF；`test/Acceptance` 不在包内、不读取；
- 创建隔离 owner 的三个临时 READY 版本，验证 PostgreSQL owner/READY、
  文档版本、持久化 Chunk 与 ES/Milvus 路由身份；
- Control 使用原问题、候选 20、RRF `k=60`、Top-3；
- Control 若不能复现冻结四题的双侧 Top-3 `0/4`，停止 Treatment；
- Treatment 只注入路由覆盖选择器；查询拆分、Reranker 和两个默认开关均关闭；
- 四个目标 Treatment 都必须实际 `APPLIED`，再判定双侧命中、Recall@3、
  nDCG@3、非目标不退化、dev no-evidence 与固定 15 题；
- 选择器 P95 必须不高于 `5 ms`，增量检索 P95 不高于 `50 ms`；
- 报告落盘前必须完成三个版本失活、ES/Milvus/runtime snapshot 共 9 个清理
  任务、READY 失败关闭和删除后 Answer API 403；
- 独立裁决器重新验证报告 SHA-256、HEAD、Run ID、变量/配置/输入/目标身份、
  指标算术、清理和 holdout 隔离。

本 Gate 不判定 300 ms SLO。阶段 2 的 `504.71613 ms` 性能债保持独立。

## 冻结输入身份

```text
ZIP:
89EA5829EFD7C299E3FF51FDC5048E2D78D172BCDE1D320322813B95C1DFDADB

Manifest:
05C36A393A51A8AA705E17D1AC3895DF074B9273F8AF6BFAD06C9904C458C63F

Route coverage config:
BDF7B0616812362966189E5EBAF374D705F4537A6E3E06A99EFC6B480209A9D0

Target IDs:
3F6E132954A721DEA34BED26D75D4C2DF84F589F2AAB0C0323005B0CDFEBCCB8
```

## Mac：推送前核对

在仓库根目录运行：

```text
git status -sb
git log -1 --oneline
git push origin main
git status -sb
git rev-parse HEAD
git rev-parse origin/main
```

只有推送成功且最后两个 SHA 完全一致，才进入 Windows。

## 历史命令（禁止重跑）

以下命令仅保留为已执行 Gate 的版本化审计记录，不再授权执行。

```powershell
Set-Location 'C:\Users\Administrator\zhiyan-personal-academic-rag'

git status -sb
git fetch origin main
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
    throw 'Windows checkout could not fast-forward to origin/main.'
}

$headCommit = (& git rev-parse HEAD).Trim()
$originCommit = (& git rev-parse origin/main).Trim()
if ($headCommit -ne $originCommit) {
    throw 'Windows HEAD must equal origin/main.'
}

$PackagePath = (
    'C:\Users\Administrator\zhiyan-personal-academic-rag\' +
    'runtime\handoffs\phase3-comparison-paired-dev-input-v1.zip'
)
$ExpectedPackageSha256 = (
    '89EA5829EFD7C299E3FF51FDC5048E2D78D172BCDE1D320322813B95C1DFDADB'
)
$ExpectedManifestSha256 = (
    '05C36A393A51A8AA705E17D1AC3895DF074B9273F8AF6BFAD06C9904C458C63F'
)

& '.\deploy\remote\phase3-comparison-validation\run_phase3_comparison_paired_dev_gate.ps1' `
    -RepositoryRoot 'C:\Users\Administrator\zhiyan-personal-academic-rag' `
    -InputPackagePath $PackagePath `
    -ExpectedPackageSha256 $ExpectedPackageSha256 `
    -ExpectedManifestSha256 $ExpectedManifestSha256 `
    -RunId 'phase3_comparison_route_coverage_dev_20260724_01' `
    -VariableId 'BILATERAL_COMPARISON_ROUTE_COVERAGE_TOP3_V1'
```

脚本输出的是脱敏摘要；完整报告和裁决保留在被忽略的 `runtime/`。不要发送
密码、连接字符串、问题正文、Evidence 正文或 PDF。

## 红色终止后的下一步

1. 不调候选、RRF、阈值、选择器或固定题目；
2. 不复用 `phase3_comparison_route_coverage_dev_20260724_01`；
3. 先根据摘要区分输入/配置拒绝、Control 停止、在线组件失败、可信质量失败
   或清理失败；
4. 只有 `cleanup.status=PASS`、9/9、READY 失败关闭和删除后 403 同时成立，
   才认定无需恢复；
5. 清理不可信时，先运行版本固定的只读审计，再决定是否需要精确恢复；
6. 干净基础设施失败不解释为质量失败；可信质量 FAIL 才保持变量关闭并形成
   质量结论；
7. `test/Acceptance` 与 300 ms 性能 Gate 始终不在本次流程中。
