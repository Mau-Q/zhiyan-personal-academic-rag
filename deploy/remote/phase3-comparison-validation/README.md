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

## 2. Windows：仅在 Mac 推送成功后运行

`phase3_comparison_dev_20260723_05` 已越过入库、READY 和 Chunk 身份校验，
但在 `RUN_CONTROL` 以 `ONLINE_MILVUS_ROUTE_FAILED` 失败，未形成 Control 或
Treatment 指标。报告 SHA-256 为
`19A92545D6E87408462BDC38A72E3F4F69B5AA03EDCAAED19400116AAFBA4CD4`，
裁决 SHA-256 为
`F8F72C59278A2A7EFB13B9B5917EAB596779372E4B159677A32B7538B82A9A2D`。
清理 9/9、READY 失败关闭和删除后 403 均通过，无需恢复 Gate。

本次独立诊断加固只把既有 Milvus 搜索细分为路由身份、查询向量、ANN 调用和
响应合同四个固定阶段；不输出异常文本、不增加请求、不改默认 RRF、比较变量
或检索参数。诊断提交推送后，使用全新 Run ID `_06` 重试同一 dev Gate。

先确保服务已经由用户正常维护并可通过本机环回端口访问。脚本不会安装依赖、
启动容器或重启服务。输入 ZIP 已位于仓库忽略目录
`runtime\handoffs`。在仓库根目录完整运行：

```text
Set-Location 'C:\Users\Administrator\zhiyan-personal-academic-rag'

git status -sb
git pull --ff-only origin main
git rev-parse HEAD

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

if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
    throw "输入包不存在：$PackagePath"
}
$ActualPackageSha256 = (
    Get-FileHash -LiteralPath $PackagePath -Algorithm SHA256
).Hash
if ($ActualPackageSha256 -ne $ExpectedPackageSha256) {
    throw "输入包 SHA-256 不匹配：$ActualPackageSha256"
}

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass `
    -File '.\deploy\remote\phase3-comparison-validation\run_phase3_comparison_paired_dev_gate.ps1' `
    -InputPackagePath $PackagePath `
    -ExpectedPackageSha256 $ExpectedPackageSha256 `
    -ExpectedManifestSha256 $ExpectedManifestSha256 `
    -RunId 'phase3_comparison_dev_20260723_06'
```

如未设置 `DATABASE_URL`，脚本以安全提示读取 PostgreSQL 密码，并在结束时删除
临时环境变量。`ELASTICSEARCH_URL`、`MILVUS_URI`、`OLLAMA_URL` 和
`DATABASE_URL` 均由 Python runner 强制为 loopback。脚本结束时也删除由它
解压的临时输入目录，原始 ZIP 不受影响。

任何红色终止都停止并回传当前 JSON summary，不要调整参数重跑。summary 中
的 `primary_stage` 与固定组件级 `primary_error_code` 用于定位质量步骤之前
的失败；不得回传原始异常消息。

只回传终端输出的 JSON summary、裁决文件和两个文件的 SHA-256；不要回传输入
ZIP、问题文本、证据文本、路径、连接串或密码。完整报告保存在
`runtime/phase3-comparison-paired-dev-<RUN_ID>-report.json`，裁决文件保存在
同目录命名空间下的 `...-adjudication.json`，均不提交。裁决 PASS 也只表示
默认关闭的 dev 候选可以进入冻结提交，不会自动解封 `test`。

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
