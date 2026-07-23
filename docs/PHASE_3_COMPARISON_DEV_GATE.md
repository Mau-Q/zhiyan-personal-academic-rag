# 阶段 3 双侧比较 dev 质量 Gate

## 1. 当前结论

`BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1` 的本地实现候选与冻结配置已完成，
方案阶段 3 由 `NOT_STARTED` 进入 `IN_PROGRESS`。本地结论仅为
`USER_RUNNER_READY_AWAITING_PAIRED_ONLINE_DEV`：

- 默认开关仍为 `false`，未改变默认 RRF；
- 4 个冻结 `dev` 样本的 Control 均保持原问题，Treatment 规划均为
  `APPLIED`；
- 私有 dev 输入包构建器、隔离三文档在线 runner 和 Windows PowerShell 5.1
  用户运行入口已完成本地契约测试与静态检查；首次 Windows 尝试在连接服务前
  因 `core.autocrlf=true` 造成的纯 CRLF 配置字节漂移被拒绝；
- 远程报告的 SHA-256、Git HEAD、Run ID、指标算术、清理与 holdout 隔离
  裁决器已准备；首次拒绝报告已按哈希保留，但不构成在线质量证据；
- 尚未运行真实 PostgreSQL READY + ES/Milvus + RRF 配对回放，因此没有
  检索质量增益、关键类不退化或 300 ms 通过结论；
- `test` 与 `acceptance` 均未读取、未运行。

机器状态见 `machine/phase3_comparison_dev_gate.json`，实现决策见 `PD-040`，
用户运行入口决策见 `PD-041`。
报告裁决边界见 `machine/phase3_comparison_report_intake.json`、`PD-042` 和
跨平台配置身份决策 `PD-043`。

## 2. 单变量实现

实现位于 `backend/retrieval/comparison_decomposition.py`，配置位于
`evaluation/phase3/bilateral-comparison-query-decomposition-v1.json`。
在线检索器只增加一个可选的 route-query planner 注入点：

1. PostgreSQL 先完成 owner 与 READY 路由解析；
2. planner 只接收原问题和已经授权的文档 ID；
3. 只有恰好两个路由、存在稳定身份别名且比较结构可证明时，才为每条路由
   生成一个文档侧查询；
4. 任一条件不成立、输出不完整或 planner 异常时，两条路由继续使用原问题；
5. 每条路由原有的一次 ES 和一次 Milvus 请求、候选 20、RRF `k=60`、
   最终 Top-3 与持久化身份校验均不改变。

配置中的论文简称、完整标题和 arXiv ID 是绑定到文档 ID 的身份元数据，不是
新的授权来源。实现不读取样本 ID、答案、Claim、相关性、候选、Chunk、页码或
运行报告，不调用 LLM，也不硬编码四个目标问题。在线执行时必须把冻结来源
文档 ID 全量、唯一地映射到 PostgreSQL 已解析的 owner-scoped 运行时文档 ID；
映射缺失、重复或多余时拒绝构造 planner。

配置身份 SHA 使用 LF 规范化后的 UTF-8 字节计算。Windows `core.autocrlf=true`
产生的纯 CRLF 工作树与冻结 LF 文件等价；孤立 CR、BOM 或任何内容变化均不被
规范化掩盖，仍以 `COMPARISON_CONFIG_IDENTITY_MISMATCH` 失败关闭。冻结配置
内容和 SHA-256 没有改变。

## 3. 允许的确定性结构

V1 只处理两种可解释结构：

- 两个文档身份都出现在同一比较句中：按身份锚点保留各自描述，并把比较维度
  作为两侧共享文本；
- 仅一侧被明确命名，但问题由“同时、另外、另一方面”等固定转折分成两段：
  命名段归入该文档，转折前未命名段归入另一已授权文档。

文档出现顺序不等于路由顺序；映射必须由身份锚点决定。结构不满足上述规则时
回退原问题，不扩大为通用查询改写、多查询、比较任务拆解或多跳规划。

## 4. 本地 dev 规划证据

私有输入仍位于被忽略的 `runtime/`，仓库只记录身份和汇总：

| 项目 | 结果 |
|---|---:|
| dev 输入 SHA-256 | `13b7ddfb0185ba03f251664366d5ab28a0cae64adda9ef9a57da563be0ae2c6e` |
| 配置 SHA-256 | `87b969a1b0f006c3406ab01a24837c5ff129d08bedd0b2460a57122f9d0b0f2b` |
| Control 原问题保持 | `4/4` |
| Treatment 规划应用 | `4/4` |
| 拆分延迟样本 | `120` |
| 本地拆分 P95 | `0.016271 ms` |
| 预算 | `P95 <= 5 ms` |
| 私有报告 SHA-256 | `4b56fffc65685b315edcf1703a22c0493fcab2b9d6fa977123f70ae10c5a70d3` |

运行入口：

```text
make phase3-comparison-dev-plan
```

报告只保存问题和路由查询的 SHA-256、字符数、状态和延迟，不保存问题或拆分后
文本。本地 P95 只证明纯转换成本，不替代 Windows 在线检索增量延迟。

## 5. 未完成的同一质量 Gate

下一节点仍属于首个失败类型质量 Gate，不另起能力变量。用户入口位于
`deploy/remote/phase3-comparison-validation/`，使用隔离 owner 创建三篇论文的
临时 READY 版本；固定数据准备和清理不是第二个质量变量：

1. 在同一 READY/owner、文档版本、Chunk、ES/Milvus、Embedding、候选和 RRF
   配置上先运行原问题 Control；
2. Control 若不能复现四题 Top-3 双侧失衡，停止并重新审查入口；
3. 仅打开 `PHASE3_COMPARISON_DECOMPOSITION_ENABLED` 运行 Treatment；
4. 判定入口冻结中的目标增益、关键类不退化、身份违规、固定 15 题 Canary
   和增量成本；
5. 将配置、dev 决策和候选提交冻结后，才允许一次性进入 `test`。

首次 Windows Run ID `phase3_comparison_dev_20260723_01` 在服务连接和数据写入
前被拒绝：报告 SHA-256 为
`AC081A26FD331F00659BE3E950537A9B22D46E75C1F3303B1BFEFBD7D7706827`，
裁决 SHA-256 为
`EB0CE6F786963B65E859496405F4F12018C93AB43015B0E759D306141B1714F6`。
冻结 LF 配置 SHA-256 为
`87B969A1B0F006C3406AB01A24837C5FF129D08BEDD0B2460A57122F9D0B0F2B`，
Windows CRLF 工作树 SHA-256 为
`491509223178E63BAFA7EBECDFC4F0A2EFEDD6A1FCD6FDD935476966423F9889`；
该差异已由相同内容的 CRLF 本地回放复现。它不证明
真实在线质量、清理或性能，重试必须使用新提交与新 Run ID。运行器只有在
316 个冻结 Chunk 与运行时持久化 Chunk 全量一一对应、三篇 READY
对账通过后才运行 Control；最终必须完成 9 个清理任务、READY 对账失败关闭和
删除后 Answer API 403。非目标 `nDCG@10` 只使用原候选 20 内的评测诊断
Top-10，产品/API Top-3 不改变。

## 6. 远程结果回收与裁决

Windows runner 现在把实际 Git HEAD 和 Run ID 写入完整报告。PowerShell 入口在
报告落盘后计算 SHA-256，并调用
`scripts/adjudicate_phase3_comparison_paired_dev_report.py` 独立复核：

1. 报告 SHA-256、HEAD、Run ID、输入 Manifest、配置和目标 ID 必须同时匹配；
2. `test/acceptance` 必须都是 `NOT_READ_NOT_RUN`，报告不得给出 300 ms SLO
   结论；
3. PASS 报告的目标增益、不退化、固定 15 题、成本必须重新验算且相互一致；
4. 无论质量结论如何，3 个版本、9 个清理任务、READY 失败关闭和删除后 403
   都是报告可采信的前提；
5. 远程 PASS 只生成
   `DEV_CANDIDATE_PASS_AWAITING_FREEZE_COMMIT`，默认开关仍为 `false`，
   `test` 仍需新的冻结提交和独立 Gate；
6. 远程 FAIL 或报告不可采信时都保持比较拆分关闭。

当前裁决器保留一次连接服务前的真实拒绝证据；在线配对 dev 仍未运行。

## 7. 不能合并的边界

本地实现、公开测试和 dev 规划检查可以合并为一个提交；真实配对 dev 回放可在
后续执行节点补齐。但以下门禁不能用同一次改动合并判定：

- 封存 `test` 的一次性评估；
- 需要另行明确授权的 Acceptance；
- 阶段 2 携带的 300 ms 独立性能 Gate。

原因不是流程形式，而是要保持训练/评估隔离和单变量因果归因。质量变量通过也
不代表生产性能、300 ms SLO、默认启用或阶段 3 完成。
