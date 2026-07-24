# 最高方案需求追踪

## 1. 最高依据身份

项目的最高层需求、目标架构和验收依据为：

- 文件名：`个人学术空间RAG问答系统建设与测试方案_副本.md`；
- 标题：《个人学术空间 RAG 问答系统建设与测试方案》；
- 当前已核对行数：`725`；
- SHA-256：`43fd5d4af4d38884c2449b9ff39fcee537cf27af5a7a700747a932be5f74dc78`；
- 覆盖范围：第 1～10 章，包括目标、架构、数据治理、在线链路、测试、API、可观测性、部署和阶段 0～5。

原文件由项目文档目录管理，不在源码仓库重复保存。仓库只记录身份、需求映射和实施证据，避免两份正文漂移。原文变更后，必须重新计算哈希并审查本文档。

## 2. 权威层级

1. 当前用户的明确指令；
2. 上述最高方案；
3. 本需求追踪、产品决策和当前阶段文档；
4. 仓库 Harness、执行合同和版本化 API 合同；
5. 代码、测试、运行报告和其他说明。

Harness 负责约束“怎么开发和证明”，不得缩小、改写或替代最高方案的最终建设与验收目标。

## 3. 阶段命名对齐

- `方案阶段 0～5`：最高方案第 10 章定义的项目阶段，用于判断最终建设完成度；
- `仓库 M0/M1`：GitHub 中已使用的内部工程里程碑，只证明某个窄范围实现和门禁通过；
- `仓库 M0_COMPLETE` 不等于 `方案阶段 0 COMPLETE`；
- `方案阶段 0/1/2 COMPLETE`：评测 Baseline 与范围、数据与索引最小闭环、基础 RAG MVP 的 Hybrid/Reranker 决策、硬门禁和稳定回放均已完成；当前仍为 `方案阶段 3 IN_PROGRESS`，同时阶段 4 的本地 Claim–Evidence 核心达到 `PARTIAL`。阶段 2 的完成不代表 300 ms 或生产性能验收通过，阶段 4 本地核心也不代表人工校准或在线硬裁决完成。

## 4. 需求追踪矩阵

| ID | 最高方案要求 | 当前状态 | 已有证据 | 关键缺口 |
|---|---|---|---|---|
| SR-01 | 冻结个人库知识源、用户范围、语料量、并发、硬件预算和 SLO | `COMPLETE` | `machine/phase_zero_scope_resource_slo.json`：500 篇标称/1000 篇验证上界、0.2 QPS、问答并发 2、入库并发 1、单台既有主机预算及阶段 1 SLO；`docs/PHASE_0_SCOPE_RESOURCE_SLO.md` | 数值已冻结为阶段 1 验收目标，但目标规模性能、真实 LLM 延迟和 PostgreSQL `owner_id` 生命周期仍待实测，不冒充已达标 |
| SR-02 | PostgreSQL 作为 `owner_id`、主键适配和生命周期唯一事实源 | `COMPLETE` | `backend/storage/` 已实现 owner-scoped 映射、幂等版本/任务、生命周期 CAS、单活动版本、不可变 Chunk 快照和三路清理租约；远程 `0001`～`0005` 与 v2 READY/删除闭环通过 | 目标规模性能与运维告警仍由 SR-12 跟踪，不否定本项事实源合同完成 |
| SR-03 | PDF/OCR、章节页码、三种 Chunk Baseline、版本和幂等入库 | `PARTIAL` | 三种切片策略已完成同源对比；远程 `filesystem_v1` PDF 对象重开、PostgreSQL Chunk 快照、重放恢复和 INACTIVE 后清理闭环已通过 | OCR 与正式 MinIO 应用适配未完成，不把 MVP 文件对象后端冒充最终架构 |
| SR-04 | Elasticsearch 论文级和 Chunk 级 BM25 | `PARTIAL` | 远程 ES 9.4.3；316 Chunk Canary 14/15；175 题 85/175；版本写入器、READY 持久化 Answer API 和删除清理均远程通过 | 中文分词选型和目标规模性能基线未完成 |
| SR-05 | Milvus + BGE-M3 语义检索及版本一致性 | `PARTIAL` | 远程 Milvus 2.6.18 + BGE-M3；316 Chunk Canary 12/15；175 题 109/175；版本 Collection、READY 持久化 Answer API 和删除清理均远程通过 | 目标规模性能基线未完成；不以远程 500 题或调参作为当前门禁 |
| SR-06 | 基础规范化和最小路由；改写、多查询和多跳按失败后置 | `PARTIAL` | API 问题输入合同与默认检索链路；`machine/phase3_entry_freeze.json` 冻结 4 个双文档比较失衡 `dev` 样本；`_07` 证明查询拆分无增益，路由覆盖 `_01` 证明选择改变仍无 Recall@3/nDCG@3 或双侧命中增益，两个变量均保持关闭 | 两个 dev 变量均未通过，不能进入 `test`；不得调参重跑或扩大为通用改写、多查询、多跳，下一主 Gate 需重新选择能直接改善目标 Evidence 的高价值假设 |
| SR-07 | ES/Milvus 并行、RRF、去重、多样性、Cross-Encoder 重排 | `PARTIAL` | 本地 SQLite BM25 + BGE-M3 RRF 15/15；远程 RRF Canary 14/15；固定 BGE Reranker 将 `nDCG@10` 从 `0.647269` 提升到 `0.747810`、`Precision@5 +0.02`，RTX 4090 pair-scoring `P95=188.22683 ms`；最终 Windows 分段 Gate 30/30 应用且安全/清理通过，base `P95=376.394385 ms`、combined `P95=504.71613 ms`，主要成本为 Query Embedding `P95=189.838925 ms` 与 READY 路由解析 `P95=145.48693 ms` | 默认明确保持原 RRF，固定 Reranker 仅为可选组件；300 ms 性能债、去重/多样性和扩展消融进入阶段 3 独立 Gate，不放宽 SLO |
| SR-08 | 证据上下文、真实 LLM、强制引用、校验与拒答 | `PARTIAL` | Evidence/Citation、`NO_EVIDENCE`；llama3.2 与 Qwen 已通过远程真实生成闭环和 3 文档 9 题；`backend/rag/claim_evidence.py` 已接入确定性锚点；成员 B 的 105 条失败归因和 30 题 AI 辅助候选二审已通过格式、身份和私有输入对账，21 条候选支持关系中当前规则只保留 6 条，因此默认改为 audit-only | 候选二审没有经过人工裁决，不计算 Precision 或人工一致率；需先形成人工裁决正负关系，再比较固定多语言 NLI 或既有本地 LLM 离线 Judge，在线硬裁决保持关闭 |
| SR-09 | 问答 API、SSE、内部 Evidence 合同和鉴权原文定位 | `PARTIAL` | 非流式 Answer API、SSE 文件合同、PDF 页码 | SSE 运行、独立 Evidence 消费和鉴权预览未实现；对外 Agent Evidence API 保持后置 |
| SR-10 | Trace、反馈、指标、告警和运营闭环 | `PARTIAL` | Trace 合同与评测报告结构 | 持久化、反馈 API、看板、告警和难例回流未实现 |
| SR-11 | 固定 175 题 MVP 初始集、约 500 条稳定迭代集、800～1500 条正式验收集 | `PARTIAL` | 175 题已按 `105/35/35` 拆分完成人工校验，166 条原样通过、9 条修订、4 条专家签署；ES 85/175、Milvus 109/175；500 题四路工程结果保留；阶段 3 入口仅使用 4 个 `dev` ID，`test/acceptance` 保持封存 | 无证据校准和安全策略层缺口需分流；阶段 3 的 `test` 只能在实现和 dev 决策冻结后一次性使用，Acceptance 需另行授权；800～1500 条正式独立盲测尚未进入 |
| SR-12 | 性能、容量、故障、安全、灰度和回滚 | `PARTIAL` | 本地单元/合同/权限边界测试；远程已验证 Embedding 单侧不可达时不进入 READY，同 Run ID 恢复后双索引对账与物理清理成功 | 目标规模压测、更完整的故障矩阵、专项安全、灰度和发布回滚未验收 |

`COMPLETE`、`PARTIAL`、`NOT_STARTED` 均按最高方案的完整口径判断，不用仓库内部里程碑结果替代。

## 5. 方案阶段完成度

| 方案阶段 | 当前判断 | 说明 | 后移边界 |
|---|---|---|---|
| 阶段 0：范围与 Baseline | `COMPLETE` | 175 题人工校验、ES/Milvus 同集单路 Baseline、三种 Chunk 受控 Baseline、单用户范围/资源/SLO 及数据身份/生命周期目标合同均已冻结 | 冻结目标不等于运行时达标 |
| 阶段 1：数据与索引最小闭环 | `COMPLETE` | 远程 v2 已通过 PDF/Chunk 持久化、owner/版本 READY 对账、ES/Milvus 在线 Evidence、同 Run ID 恢复、删除后 403 和三路清理；报告 SHA-256 `6B2AB3BAAD55AE8FA506C0D1FD7A310D9EF3A3833A93E33DD1A2D8A0938A9D8C` | 正式 MinIO、OCR 和目标规模性能不属于阶段 1 退出条件 |
| 阶段 2：基础 RAG MVP | `COMPLETE` | 非流式 API、Evidence、拒答、远程 RRF Canary、llama3.2/Qwen READY 真实生成闭环、模型选型和 3 文档 9 题 v2 均通过；固定 BGE Reranker 的增益、目标硬件成本和在线边界已验证，最终决定为原 RRF 默认、Reranker 可选且不默认启用 | Windows 分段 Gate 的 combined `P95=504.71613 ms` 未通过 300 ms；这是显式后移的性能债，不写成 SLO 或生产验收完成 |
| 阶段 3：针对失败类型增强 | `IN_PROGRESS` | 首个查询拆分变量和第二个路由覆盖变量均已完成可信在线 dev 比较并保持关闭；第二变量虽在 4/4 目标上生效、3/4 改变选择，但 Control/Treatment 仍同为双侧 `0/4`，Recall@3 与 nDCG@3 增益均为 0 | `_01` 清理 9/9、READY 失败关闭和删除后 403 均通过，无需恢复且不得复用；`test/acceptance` 继续封存，300 ms 性能 Gate 独立。下一节点须先重新选择一个高价值主 Gate，不继续细分或调参重跑失败变量 |
| 阶段 4：Claim–Evidence 可靠性 | `PARTIAL` | 已复用结构化 Claim 与授权 Evidence建立确定性核心；成员 B 的 105/30 AI 辅助候选资产已接收并对账，候选支持保留率 `6/21` 与人工终审正例保留率 `110/225` 证明现有词法规则高误杀，默认改为 audit-only | 候选不是人工裁决真值，Precision、负例拒绝率和人工一致率仍不可测；人工裁决和离线语义候选比较未完成，不启用在线 NLI/LLM 硬裁决 |
| 阶段 5：复杂科研问答与复用 | `NOT_STARTED` | 暂未完成比较、多跳、时效问答与 Agent Evidence API | 进入前需满足 MVP、权限委托、审计与运维条件 |

## 6. 当前工作门禁

方案阶段 2 的收口门禁为：

1. **已完成本地 Gate：** 第 10.3 节差距已冻结；固定本机模型、Prompt 和解码的真实生成 Canary 已通过，且不修改检索；
2. **已完成远程 Gate：** 用户在提交 `91aca5a` 复用 PostgreSQL READY + ES/Milvus RRF Evidence 完成同一真实生成配置的稳定回放、引用门禁、删除后 403 和三路清理；
3. **已完成模型选型 Gate：** 固定 Evidence/Prompt/解码比较 `qwen3:14b` 与 `llama3.2:latest`，远程 v2 以 `4/4` 对 `2/4` 决定 `PROMOTE_QWEN3_14B`；
4. **已完成远程 Qwen Gate：** 冻结摘要的 Qwen 已完成真实生成、引用、ACL、版本、删除后 403 和三路清理闭环；
5. **已完成学术问答 Gate：** v2 三篇各 `3/3`、合计 `9/9` 远程通过；最终第 3 篇报告 SHA-256 `3C106423AB3575B11B3B0142A66F19A2C949B8BAED3457F1BCA101A9931302FA`，原 HTTP 失败报告继续保留；
6. **已完成本地 Reranker 质量 Gate：** 冻结 `test=100` 上 `nDCG@10` 相对提升 `15.5331%`、`Precision@5 +0.02`，四个关键类型门禁通过；M4 P95 只作本地观测；
7. **已完成目标硬件 Reranker Gate：** 用户在提交 `d31e992` 的 Windows RTX 4090 上复用相同 revision、snapshot、输入模板、Batch Size 和冻结输入，质量门保持通过，pair-scoring `P50=169.3867 ms / P95=188.22683 ms`，稳定错误码为 `NONE`，组件决定保留进入受控在线集成；
8. **已完成受控在线本地 Gate：** 固定 Reranker 只接在 PostgreSQL READY/ACL、持久化身份重验与 ES/Milvus RRF 之后；最多重排 20 个已授权候选并输出前 3，标题/模型/分数故障回退同一批 RRF，身份漂移失败关闭；
9. **已完成并行在线远程 Gate：** Windows RTX 4090 取得 30/30 `APPLIED`、无回退/扩张/越界、三路清理和删除后 403；base `P95=344.676365 ms`、Reranker `P95=131.885375 ms`、combined `P95=472.190015 ms`，固定 Reranker 不默认启用；
10. **已完成远程归因 Gate：** 提交 `3303bed` 上 30/30 `APPLIED`，分段状态 `PASS`；base `P95=376.394385 ms`、Reranker `P95=132.456 ms`、combined `P95=504.71613 ms`，主要成本为 Query Embedding 与 READY 路由解析；三路清理、删除后 403 通过，报告 SHA-256 `235FE36A97B7F4E462AD502595CB0CF38C139022703B6C4EA1E93E19D3AC765B`；
11. **已完成阶段决策：** 依据最高方案第 10.3 节，Hybrid 对比、Reranker 增益和保留/回退决定、引用/ACL/版本/定位硬门禁与稳定回放均满足退出条件；阶段 2 完成，原 RRF 保持默认，固定 Reranker 非默认，性能债后移。

阶段 3 已在入口冻结后完成默认关闭的本地实现候选：
`docs/PHASE_3_COMPARISON_DEV_GATE.md` 与
`machine/phase3_comparison_dev_gate.json` 证明 Control 原问题保持 `4/4`、
Treatment 确定性规划 `4/4`，且纯拆分本地 P95 低于 `5 ms`。该证据没有运行
真实 PostgreSQL READY + ES/Milvus + RRF，不证明目标增益或不退化，不改变
默认 RRF，也未读取 `test/acceptance`；方案阶段 3 因实现已开始而为
`IN_PROGRESS`。`deploy/remote/phase3-comparison-validation/` 已补齐用户运行
入口，并冻结隔离三文档 READY、Control 停止规则、316 Chunk 身份一一对应、
9 个清理任务与删除后 403；其本地静态通过仍不等于 Windows 在线结果或
300 ms SLO 通过。`machine/phase3_comparison_report_intake.json` 进一步冻结
报告 SHA-256、实际 Git HEAD、Run ID、指标算术与 holdout 隔离的独立裁决；
首次 Windows 报告在服务连接前因 `core.autocrlf=true` 的纯 CRLF 配置字节差异
被拒绝；第二次报告
`423D736D496BE0AFA1CC06A90E3402B060C519F74C17D9C4939E31A50304E276`
通过配置身份后以 `CLEANUP_PROOF_FAILED` 结束，裁决为
`REPORT_CLEANUP_PROOF_INVALID`。旧报告没有保留主失败与具体清理阶段，因此不能
证明质量或隔离 owner 已清理。运行器现分别输出主失败和清理阶段；版本固定的
只读审计只查询 PostgreSQL owner 范围，检查版本失活、三路持久化清理终态、
Chunk/PDF 快照清零以及全局非终态清理任务计数。在该审计返回 `CLEAN` 前不得
启动新质量 Run ID。提交 `740393a7897a7ed9bdff747acfcd27dfa0667ddd` 上的
审计返回 `RESIDUAL_REQUIRES_RECOVERY_GATE`：3 个版本全部 `INACTIVE`，但 ES、
Milvus、runtime snapshot 各 3 个任务均为 `PENDING`，仍有 316 Chunk 和 3 PDF
对象；审计 SHA-256 为
`A3FBDDC29ACAAAB0E72EDCD889F14A198F238F523A08588D5D486765999498CF`。
恢复入口只处理这 9 个既有任务，并在完成后重新运行只读审计。用户在提交
`64ef344daa5382d0b043ff444300963fb076c068` 上取得 9/9 `SUCCEEDED`、
Chunk/PDF/全局非终态均为 0；恢复报告 SHA-256
`E9A9566ECFEDE9C30310F9831D8EBF22249CB5081EDA69BA6F7DEA48E26CB8FA`，
事后审计 `PASS/CLEAN`，SHA-256
`F3C12A2F2F7C4D8E0F75EE8DB7B483B44C6509CF65FA0F0EE03779E296252790`。
该结果不补造 `_02` 质量证据，只允许以新 Run ID 重试同一 dev Gate；PASS 分支
仍只形成默认关闭的候选草案。

第三次 Run ID `phase3_comparison_dev_20260723_03` 未形成质量指标；报告
SHA-256 `A45EF2F9F030FEB6AAED05DECB33A019CFA7920FAF6E1F1ABEB7189C242E339EC`
在清理 `VERIFY_QUEUE_SCOPE` 阶段失败。只读审计 SHA-256
`E9430BE17811C60116630F718C182A3FFD0A12FFD83F753EBB5FDFBA0420112B`
确认 3 个版本全部 `INACTIVE`、9 个三路任务全部 `PENDING/attempt=0`、
316 Chunk、3 PDF，且全局非终态正好是这 9 个。根因是 psycopg `dict_row`
被错误按元组解包，队列真实值未参与比较。当时先用独立 Gate 绑定该审计完成
精确恢复，没有在恢复 Gate 中修运行器或重跑质量。

用户随后在提交 `c9c3705d70de7cb43812a8cd8a6a585da6eebcd9` 完成 `_03`
精确恢复：恢复 SHA-256
`94A10A54FFB6B326740E093DB97D148891FD44898E7BC077E25FA4385B780CDB`，
事后审计 `PASS/CLEAN`，SHA-256
`FFD2E805B857DF1D4D7E256A00BF09B15992261A4A31960C7A2D55B8D504DBAB`。
当前独立修复只更正 mapping 行读取并补充脱敏主阶段，不改变质量变量；允许在
新提交和新 Run ID 上重试，仍不解封 `test/acceptance` 或性能 Gate。

第四次 Run ID `phase3_comparison_dev_20260723_04` 在提交
`b92e9ffa1d576aeef83dd028a28df09bf601d52e` 上于 `RUN_CONTROL` 失败，
报告 SHA-256
`2CA305DCD16820DE4EB28863097F58C53AD5F9D678604C5251A65DE70B2AA47C`，
裁决 SHA-256
`B49BF9079ED3C9C7C2019A4E4836CDB9677DEA07955675D6BFE1CDCE25E4A4BF`。
Control/Treatment 指标均未形成，但清理 9/9、READY 失败关闭和删除后 403
通过，不需要恢复。下一独立诊断变更只细分 Control 检索/评分子阶段，并将异常
类型链映射为固定组件码；不输出异常文本、不增加请求、不改变默认 RRF、质量
变量、test/Acceptance 或性能 Gate。

第五次 Run ID `phase3_comparison_dev_20260723_05` 在提交
`a669702b24880269a130f8e249126b30e17a2972` 上于 `RUN_CONTROL` 以
`ONLINE_MILVUS_ROUTE_FAILED` 失败。报告 SHA-256
`19A92545D6E87408462BDC38A72E3F4F69B5AA03EDCAAED19400116AAFBA4CD4`，
裁决 SHA-256
`F8F72C59278A2A7EFB13B9B5917EAB596779372E4B159677A32B7538B82A9A2D`。
Control/Treatment 指标仍未形成，但清理 9/9、READY 失败关闭和删除后 403
通过，无需恢复。该证据只能定位到 Milvus 路径，不能证明具体根因或质量结果；
下一独立诊断只将既有 Milvus 搜索拆为路由身份、查询向量、ANN 调用和响应合同
四个固定阶段，不新增探测请求或改变检索行为。

第六次 Run ID `phase3_comparison_dev_20260723_06` 在提交
`4771fe39ade2039a3251a6f8699a99fd1fb69b4d` 上于 `RUN_CONTROL` 以
`ONLINE_MILVUS_ROUTE_IDENTITY_FAILED` 失败。报告 SHA-256
`FCBD2B472E21AD5554FB3EBB0389CDE649FDFE80C4036C8BCC64A194FC4F70CB`，
裁决 SHA-256
`A43F13F6E06F3D0C1B9ABA405529A31A82B754477292220D9EAC831CDCC6B779D`。
Control/Treatment 指标仍未形成，但清理 9/9、READY 失败关闭和删除后 403
通过，无需恢复。独立修复只把版本集合的精确计数证明从可能滞后的 collection
stats 改为逻辑主键快照；既有 READY/owner、完整版本行、活动状态、向量、
provider、source fingerprint 和 schema 校验不放宽，ANN、RRF 与质量变量不变。

第七次 Run ID `phase3_comparison_dev_20260723_07` 在提交
`ff370b512f88b7d847fa17f080946aab4050048c` 上完成完整 Control/Treatment，
稳定结果为 `QUALITY_OR_COST_THRESHOLD_NOT_MET`。Control 与 Treatment 的四个
冻结目标均为双侧 Top-3 命中 `0/4`，宏观 Recall@3 绝对增益为 `0`，
`nDCG@3` 绝对增益为 `-0.017739`；固定 15 题为 `14/15`，且两分支边界不完全
一致。非目标 answerable、dev no-evidence 与增量成本没有退化，但不能抵消目标
增益和固定 Canary 硬门禁失败。报告 SHA-256
`3810CE9228F7CE9C65B5BE0E031F1F5CA6A471FA665BF5D8C12A6E7CAC6E01390`，
裁决 SHA-256
`99530D236B8CA50B53DE18557C9D43C7BCC63695A3C98FC9DBA889B33CDAA036`，
决定为 `KEEP_COMPARISON_DECOMPOSITION_DISABLED`。清理 9/9、READY 失败关闭
与删除后 403 通过，无需恢复；`test/Acceptance` 未读取，300 ms Gate 未运行。

Phase 4 的比赛增强现新增固定多语言 NLI 候选，但未形成远程质量结果。模型固定为
`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` revision
`b5113eb38ab63efdd7f280f8c144ea8b13f978ce`，只以 Evidence 为 premise、
Claim 为 hypothesis 做离线正例保留诊断。Mac 仅运行 Fake Scorer；真实模型只由
用户在 Windows PowerShell 5.1 RTX 4090 入口运行。当前没有人工裁决负例，因此
Precision、负例拒绝率和人机一致率不可测；候选通过也不改变 `AUDIT_ONLY` 或
在线硬裁决。知识库接入、前端、演示和 `test/Acceptance` 继续排除。

首次 Windows NLI 尝试在模型加载前因 tracked 配置的等价 CRLF 检出被原始字节
SHA-256 拒绝，没有形成质量结果。跨平台身份现与 Phase 3 已验证规则一致：
tracked JSON/CSV 以 LF 规范化文本字节计算身份，纯 LF 与等价 CRLF 接受，BOM、
孤立 CR 和内容漂移拒绝；私有 ZIP/JSONL 仍使用原始字节 SHA-256。修复不改变
模型、输入、门槛、默认 `AUDIT_ONLY` 或 holdout。

修复后 RTX 4090 报告 SHA-256
`6f266edc0fa57b933260f3996585a53ac2dac065c13f472f7c8d1c5f94c7cf1e`
通过合同复核：候选 supported 保留 `9/21`，终审谱系正例保留 `124/225`，
均低于 `0.85`；组件 P95 `64.03166 ms` 只证明性能可用，不能覆盖质量失败。
NLI 硬裁决候选因此拒绝，默认 `AUDIT_ONLY` 不变。下一诊断只允许在同一冻结
模型/输入上导出不含正文与原始 ID 的哈希键级预测，用于本地区分数据口径与模型
能力，不读取 `test/Acceptance`。
