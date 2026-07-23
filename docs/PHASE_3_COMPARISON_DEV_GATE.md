# 阶段 3 双侧比较 dev 质量 Gate

## 1. 当前结论

`BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1` 的本地实现候选与冻结配置已完成，
方案阶段 3 由 `NOT_STARTED` 进入 `IN_PROGRESS`。当前结论为
`SEVENTH_ATTEMPT_DEV_QUALITY_FAILED_CLEAN_VARIABLE_REJECTED`：

- 默认开关仍为 `false`，未改变默认 RRF；
- 4 个冻结 `dev` 样本的 Control 均保持原问题，Treatment 规划均为
  `APPLIED`；
- 私有 dev 输入包构建器、隔离三文档在线 runner 和 Windows PowerShell 5.1
  用户运行入口已完成本地契约测试与静态检查；首次 Windows 尝试在连接服务前
  因 `core.autocrlf=true` 造成的纯 CRLF 配置字节漂移被拒绝；
- 远程报告的 SHA-256、Git HEAD、Run ID、指标算术、清理与 holdout 隔离
  裁决器已准备；三次拒绝报告均不构成在线质量证据；
- 第二次报告的通用清理异常遮蔽了主失败与具体阶段；运行器已改为同时保留
  `primary_error_code` 和分阶段清理错误，另有只读 PostgreSQL 残留审计入口；
- 只读审计确认的 9 个 `PENDING` 任务已由精确恢复入口全部处理成功，Chunk、
  PDF 与全局非终态任务均清零，事后审计为 `PASS/CLEAN`；
- 第三次运行在质量指标前因清理队列范围证明误判失败；`_03` 只读审计再次
  冻结 3 个 `INACTIVE` 版本、9 个 `PENDING/attempt=0` 任务、316 Chunk 和
  3 PDF，随后已由独立精确恢复清零；
- 第五次运行 `_05` 已返回 `RUN_CONTROL / ONLINE_MILVUS_ROUTE_FAILED`，并
  再次完成 9/9 清理、READY 失败关闭和删除后 403；该结果证明组件诊断生效，
  但仍没有 Control/Treatment 指标；
- 第六次运行 `_06` 已将故障收敛为
  `RUN_CONTROL / ONLINE_MILVUS_ROUTE_IDENTITY_FAILED`，并再次完成 9/9
  清理、READY 失败关闭和删除后 403；无需恢复，但仍没有质量指标；
- 第七次运行 `_07` 已完成真实 PostgreSQL READY + ES/Milvus + RRF 配对回放；
  Control/Treatment 对目标四题均为双侧 Top-3 命中 `0/4`，Recall@3 无增益、
  `nDCG@3 -0.017739`，固定 15 题 `14/15`，裁决保持变量关闭；
- `_07` 清理 9/9、READY 失败关闭和删除后 403 通过，无需恢复；非目标和增量
  成本门禁通过，但不构成目标质量通过或 300 ms 结论；
- `test` 与 `acceptance` 均未读取、未运行。

机器状态见 `machine/phase3_comparison_dev_gate.json`，实现决策见 `PD-040`，
用户运行入口决策见 `PD-041`。
报告裁决边界见 `machine/phase3_comparison_report_intake.json`、`PD-042` 和
跨平台配置身份决策 `PD-043`，清理审计边界见 `PD-044`。

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

## 5. 已完成的同一质量 Gate

首个失败类型质量 Gate 没有另起能力变量。用户入口位于
`deploy/remote/phase3-comparison-validation/`，使用隔离 owner 创建三篇论文的
临时 READY 版本；固定数据准备和清理不是第二个质量变量。实际执行遵守：

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

第二次 Windows Run ID `phase3_comparison_dev_20260723_02` 已通过 LF/CRLF
身份检查，但完整报告以 `CLEANUP_PROOF_FAILED` 结束，报告 SHA-256 为
`423D736D496BE0AFA1CC06A90E3402B060C519F74C17D9C4939E31A50304E276`，
裁决 SHA-256 为
`74A599288445F1C2267F892A81B5F6B8BD3D5002D4A67E6BE6700645D3516981`，
错误码为 `REPORT_CLEANUP_PROOF_INVALID`。该版本的通用异常路径只记录
`jobs_expected=9`，没有保留原始失败、清理阶段或可靠身份汇总；因此既不能判定
Control/Treatment，也不能证明隔离 owner 已清理。

在任何第三次质量运行前，必须先对 `_02` 执行只读残留审计。审计在 PostgreSQL
`READ ONLY` 事务内只按确定性 owner 查询聚合状态：无版本/任务/快照，或所有
版本 `INACTIVE`、每版本三路清理任务均 `SUCCEEDED`、Chunk/PDF 快照为零，且
全局没有会阻断下一隔离 Gate 的 `PENDING/RUNNING/RETRY` 清理任务，才返回
`CLEAN`。全局汇总不输出其他 owner 身份。审计不直接查询 ES/Milvus；物理删除
只解释为持久化任务成功与运行快照清零的组合证据。若返回残留，下一步是独立
恢复 Gate，不允许临时 SQL、手工删索引或直接复跑。

该审计已在提交 `740393a7897a7ed9bdff747acfcd27dfa0667ddd` 上执行，结果为
`FAIL / RESIDUAL_REQUIRES_RECOVERY_GATE`，SHA-256：
`A3FBDDC29ACAAAB0E72EDCD889F14A198F238F523A08588D5D486765999498CF`。
具体状态是 3 个 `INACTIVE` 版本、3 个已终态入库任务、9 个
`PENDING/attempt=0` 清理任务、316 Chunk 和 3 PDF；全局 9 个非终态任务就是
该 owner 的同一队列，没有其他 owner 混入。

恢复 Gate 只允许 `scripts/recover_phase3_comparison_cleanup.py` 调用既有
`PersistentIndexCleanupWorker`，最大领取 9 次。变更前再次核对上述完整身份和
计数；完成后必须是 9 个 `SUCCEEDED`、全局非终态为 0、Chunk/PDF 为 0，并由
原只读审计器生成独立事后报告。任何前置漂移、删除失败或事后审计失败都停止，
不得自动重试或进入质量 Gate。

用户已在提交 `64ef344daa5382d0b043ff444300963fb076c068` 完成该恢复：
9/9 `SUCCEEDED`，Chunk `316→0`、PDF `3→0`、全局非终态 `9→0`。恢复报告
SHA-256 为
`E9A9566ECFEDE9C30310F9831D8EBF22249CB5081EDA69BA6F7DEA48E26CB8FA`；
自动事后审计为 `PASS / CLEAN`，SHA-256 为
`F3C12A2F2F7C4D8E0F75EE8DB7B483B44C6509CF65FA0F0EE03779E296252790`。
本次没有运行质量、test、Acceptance 或性能 Gate。旧 `_02` 仍不可作为质量
证据；下一次只能使用全新 Run ID。

第三次 Windows Run ID `phase3_comparison_dev_20260723_03` 在提交
`3a77484020f57aca27e6fa4b6d48cd1d81260982` 上于质量指标前失败关闭。清理
阶段为 `VERIFY_QUEUE_SCOPE`，报告 SHA-256 为
`A45EF2F9F030FEB6AAED05DECB33A019CFA7920FAF6E1F1ABEB7189C242E339EC`。
只读审计 SHA-256
`E9430BE17811C60116630F718C182A3FFD0A12FFD83F753EBB5FDFBA0420112B`
确认残留与 `_02` 同构，且全局非终态正好只有该 owner 的 9 个任务。

根因是 `_active_cleanup_scope` 在 psycopg `dict_row` 连接上把行按元组解包，
得到列名而非实际值，从而把正确的 9 任务范围误判为不匹配。独立恢复 Gate
没有修复该运行器缺陷；恢复入口只把既有恢复器扩展到显式冻结的 `_03`，绑定
Run ID、确认词、审计 SHA 与完整前置计数。恢复完成并事后审计 `CLEAN` 后，
才进入当前独立运行器修复 Gate。

用户已在提交 `c9c3705d70de7cb43812a8cd8a6a585da6eebcd9` 完成 `_03`
恢复：9/9 `SUCCEEDED`，Chunk/PDF/全局非终态均为 0。恢复报告 SHA-256
`94A10A54FFB6B326740E093DB97D148891FD44898E7BC077E25FA4385B780CDB`；
事后审计 `PASS/CLEAN`，SHA-256
`FFD2E805B857DF1D4D7E256A00BF09B15992261A4A31960C7A2D55B8D504DBAB`。
随后独立修复只把 `_active_cleanup_scope` 改为显式 mapping key 取值，并记录
脱敏 `primary_stage`；质量变量、检索参数和 holdout 均未改变。

第四次 Windows Run ID `phase3_comparison_dev_20260723_04` 在提交
`b92e9ffa1d576aeef83dd028a28df09bf601d52e` 上越过入库、READY 和 Chunk
身份校验，但在 `RUN_CONTROL` 以通用 `PHASE3_GATE_FAILED` 失败，未形成完整
Control 指标。报告 SHA-256
`2CA305DCD16820DE4EB28863097F58C53AD5F9D678604C5251A65DE70B2AA47C`；
裁决 SHA-256
`B49BF9079ED3C9C7C2019A4E4836CDB9677DEA07955675D6BFE1CDCE25E4A4BF`。
清理 9/9、READY 失败关闭和删除后 403 均通过，因此无需恢复 Gate。

当前诊断加固只在 Gate runner 捕获在线检索异常后，遍历最多 8 层异常类型链，
将其映射到固定组件码。异常消息、问题、Evidence、路径和连接信息均不进入报告；
同时将 Control 检索与指标计算分为 `RUN_CONTROL` / `SCORE_CONTROL`。该变更
不增加网络请求，也不修改 `OnlineVersionRrfRetriever`、默认 RRF 或质量变量。

第五次 Windows Run ID `phase3_comparison_dev_20260723_05` 在提交
`a669702b24880269a130f8e249126b30e17a2972` 上返回
`RUN_CONTROL / ONLINE_MILVUS_ROUTE_FAILED`。报告 SHA-256
`19A92545D6E87408462BDC38A72E3F4F69B5AA03EDCAAED19400116AAFBA4CD4`，
裁决 SHA-256
`F8F72C59278A2A7EFB13B9B5917EAB596779372E4B159677A32B7538B82A9A2D`；
清理 9/9、READY 失败关闭和删除后 403 通过。该结果无需恢复，但只能证明
Milvus 路径失败，不能确定根因或形成质量结论。

当前阶段诊断通过 `MilvusSearchStageError` 在原失败因果链外只增加
`ROUTE_IDENTITY / QUERY_EMBEDDING / ANN_SEARCH / RESPONSE_CONTRACT` 四个
稳定阶段，并由 Gate runner 映射为固定错误码。它不增加探测或检索请求，不
改变 Milvus/Embedding 调用、候选 20、RRF `k=60`、Top-3、阈值或默认开关。

第六次 Windows Run ID `phase3_comparison_dev_20260723_06` 在提交
`4771fe39ade2039a3251a6f8699a99fd1fb69b4d` 上返回
`RUN_CONTROL / ONLINE_MILVUS_ROUTE_IDENTITY_FAILED`。报告 SHA-256
`FCBD2B472E21AD5554FB3EBB0389CDE649FDFE80C4036C8BCC64A194FC4F70CB`，
裁决 SHA-256
`A43F13F6E06F3D0C1B9ABA405529A31A82B754477292220D9EAC831CDCC6B779D`；
清理 9/9、READY 失败关闭和删除后 403 通过，无需恢复。

版本集合经过暂存和激活 `upsert` 后，通用检索器原先把
`get_collection_stats().row_count` 与冻结 Chunk 数作精确等式。该统计接口允许
尚在 stream 中的数据不计入统计，因此不适合作逐请求身份硬门；依据为
[Milvus 2.6 `get_collection_stats()` 官方接口说明](https://milvus.io/api-reference/pymilvus/v2.6.x/MilvusClient/Collections/get_collection_stats.md)。
当前修复只对
`milvus_version_writer_v1` 集合使用一次只返回 `chunk_id` 的逻辑快照，要求
数量和唯一性与元数据一致；版本 writer 在 READY 路由解析时执行的完整行、
活动状态与向量身份验证，以及检索端的 schema、owner/document/version、
provider 和 source fingerprint 校验均保留。此次未更改 ANN、Embedding、
默认 RRF、比较变量、候选 20、RRF `k=60`、Top-3、阈值或 holdout。

第七次 Windows Run ID `phase3_comparison_dev_20260723_07` 在提交
`ff370b512f88b7d847fa17f080946aab4050048c` 上越过全部身份、Control、
Treatment 和清理阶段，形成可信质量失败：

| 项目 | Control | Treatment | 绝对变化 |
|---|---:|---:|---:|
| 目标双侧 Top-3 命中 | `0/4` | `0/4` | `0` |
| 目标宏观 Recall@3 | `0.145833` | `0.145833` | `0` |
| 目标宏观 nDCG@3 | `0.220967` | `0.203228` | `-0.017739` |
| 非目标 Recall@3 | `0.622917` | `0.622917` | `0` |
| 非目标 nDCG@10 | `0.632761` | `0.632761` | `0` |

固定 15 题为 `14/15`，类别为 `8/9 answerable + 3/3 no-evidence +
3/3 forbidden`，Control/Treatment 边界不完全一致。增量检索 P95 为
`24.101115 ms <= 50 ms`，纯拆分 P95 为 `0.12922 ms <= 5 ms`；成本通过
不能抵消目标增益和固定 Canary 失败。报告 SHA-256 为
`3810CE9228F7CE9C65B5BE0E031F1F5CA6A471FA665BF5D8C12A6E7CAC6E01390`，
裁决 SHA-256 为
`99530D236B8CA50B53DE18557C9D43C7BCC63695A3C98FC9DBA889B33CDAA036`。
最终决定为 `KEEP_COMPARISON_DECOMPOSITION_DISABLED`。

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

当前裁决器保留前三次拒绝、第四次可信通用 FAIL、第五次可信 Milvus 路径
FAIL、第六次可信 Milvus 身份 FAIL，以及第七次完整可信质量 FAIL。`_07`
证明首个比较拆分变量不能晋级：不得调参、不得复用 Run ID、不得解封 `test`。
由于 9/9 清理、READY 失败关闭和删除后 403 均通过，本次不进入恢复 Gate。

## 7. 不能合并的边界

本地实现、公开测试和 dev 规划检查可以合并为一个提交；真实配对 dev 回放可在
后续执行节点补齐。但以下门禁不能用同一次改动合并判定：

- 封存 `test` 的一次性评估；
- 需要另行明确授权的 Acceptance；
- 阶段 2 携带的 300 ms 独立性能 Gate。

原因不是流程形式，而是要保持训练/评估隔离和单变量因果归因。质量变量通过也
不代表生产性能、300 ms SLO、默认启用或阶段 3 完成。
