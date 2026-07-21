# Current Phase

## Status

`SOURCE_PHASE_0_IN_PROGRESS / REPOSITORY_HARNESS_READY / REPO_M0_COMPLETE / M1_LOCAL_RRF_BASELINE_READY / RISK_BASED_TESTING_READY / MEMBER_B_REMOTE_PENDING`

Phase ID：`source-phase0-foundation-in-progress`

## Completed

- 建立独立源码仓库目录；
- 建立源码、数据、密钥和运行时边界；
- 建立私有优先、审查后公开的仓库策略；
- 记录双人离线/在线并行开发边界；
- 创建 Private GitHub 仓库：<https://github.com/Mau-Q/zhiyan-personal-academic-rag>；
- 推送并建立远程 `main` 基线；
- 仓库所有者确定负责成员 A 的在线链路；
- 第二位成员 `chouyyds-blip` 已接受邀请；
- 从本地语料筛选 8 篇 PDF，并只提交元数据、页数和 SHA-256；
- 建立三个静态合同、RAG Answer、Trace、错误码、SSE 和契约测试草案；
- [PR #1](https://github.com/Mau-Q/zhiyan-personal-academic-rag/pull/1) 已由成员 A 确认并 Squash Merge，GitHub Actions 契约检查通过；
- 创建 [M0 里程碑](https://github.com/Mau-Q/zhiyan-personal-academic-rag/milestone/1)和 Issue #2～#5；
- [PR #6](https://github.com/Mau-Q/zhiyan-personal-academic-rag/pull/6) 已由成员 A 直接合并，[Issue #3](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/3) 已关闭；
- [PR #8](https://github.com/Mau-Q/zhiyan-personal-academic-rag/pull/8) 已由成员 A 在 CI 通过后直接合并，[Issue #7](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/7) 已关闭；
- 成员 A 的授权过滤、确定性检索、Fake LLM、Evidence、Citation、`NO_EVIDENCE` 和非流式 Answer API 已通过 33 项测试；
- 本地真实 HTTP 冒烟已覆盖 `200/COMPLETED`、`200/NO_EVIDENCE` 和 `403/RAG_FORBIDDEN_SCOPE`。
- 分工已调整：成员 A 负责完整本地核心链路，成员 B 负责远程主机准备和部署验证；
- [Issue #4](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/4) 已调整为成员 A 的 PDF 到 `ChunkRecordV1` 任务；
- 已创建成员 B 的 [Issue #9](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/9)，且远程准备不阻塞 M0；
- 本地入库、合同、检索、RAG 和 API 共 43 项测试通过；
- TRACER PDF 的 SHA-256 与样本清单一致，生成 63 个稳定 Chunk，覆盖第 1～10 页，12 个 Chunk 跨页；
- 真实 PDF 重复入库输出字节一致，63 条合同和相邻链接校验通过；
- 真实 PDF Chunk 已通过 HTTP 验证 `COMPLETED`、`NO_EVIDENCE` 和 403 越权阻断。
- [PR #10](https://github.com/Mau-Q/zhiyan-personal-academic-rag/pull/10) 已在 CI 通过后直接合并；
- [Issue #4](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/4) 和 [Issue #5](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/5) 已关闭；
- M0 里程碑已关闭，5 个任务全部完成，无开放任务。
- 建立 M1 薄评测 Harness，直接调用现有 Answer API，不复制检索或回答逻辑；
- 建立 6 个版本化 Fixture 基线，覆盖可回答、无证据和越权三类结果；
- Harness 输出机器可读报告和严格退出码，并显式保留 `LOCAL_API_FAKE_LLM` 边界。
- 加入评测测试后，合同、入库、检索、RAG、API 和评测共 48 项测试通过。
- 建立仓库级 Harness：入口、长期护栏、产品决策、执行合同、机器状态和只读校验器；
- 明确仓库 Harness 与 RAG 评测 Harness 的职责边界。
- 加入仓库 Harness 与 Git 流程测试后，全仓共 54 项测试通过。
- 简化 Git 流程：成员 A 普通低风险任务本地门禁通过后直接推送 `main`，高风险和成员 B 任务保留 PR。
- 完成本地三论文摄取：TRACER、SciNet 和 EVMbench 的 PDF 身份校验与解析均通过，共生成 316 个 Chunk；
- 人工完成 15 题本地评测集，覆盖 9 个目标页可回答题、3 个无证据题和 3 个越权请求；
- 词项检索基线首轮通过 15/15，分类结果为 `ANSWERABLE 9/9`、`NO_EVIDENCE 3/3`、`FORBIDDEN 3/3`；
- 三论文题集、PDF、Chunk、页面渲染和报告只进入被忽略的 `runtime/`，仓库仅记录脱敏方法与汇总结果。
- 再次简化成员 A 的普通低风险流程：本地 Harness、受影响测试和 diff 检查后直推，仅核对远程 SHA；Actions 改为条件检查。
- 接入本地持久化 SQLite FTS5/BM25 索引，固定 Porter 分词、OR 查询和 `2.0,1.0` 列权重；
- 索引绑定源 Chunk SHA-256 和数量，配置或来源漂移时失效关闭；
- SQLite 检索继续复用既有授权判断，未授权、跨租户和失效 Chunk 不得进入 Evidence；
- 新增公开 SQLite Fixture 冒烟入口和检索、API、评测测试；
- 三论文同题集首轮 14/15，经词形和停用词诊断后在不改题目、页码或 `top_k` 的情况下达到 15/15。
- 确认《个人学术空间 RAG 问答系统建设与测试方案》为最高层需求、目标架构和验收依据；
- 建立 12 项需求追踪和方案阶段 0～5 完成度映射；
- 明确仓库 `M0/M1` 为内部工程里程碑，当前最高方案阶段 0 仍为 `IN_PROGRESS`；
- 将 3 论文 15 题定位为快速工程 Canary，不代替 200～500 条初始评测和 800～1500 条正式验收规模。
- 使用本机 Ollama `bge-m3:latest` 为同一 316 个 Chunk 建立 1024 维真实向量索引，固定模型 digest、源 Chunk 指纹、模板、维度和归一化身份；
- 冻结当前 Canary 的向量阈值 `0.50`：无证据最高分 `0.425643`，可回答目标最低分 `0.585648`；
- 固定同一 15 题运行向量单路，结果为 12/15，其中可回答 6/9、无证据 3/3、越权 3/3，未修改题目、页码或 `top_k=3` 制造通过；
- 实现 SQLite BM25 + BGE-M3 的本地 RRF，固定候选数 20、`k=60`，同一 15 题达到 15/15；
- 固化 `lexical_overlap`、`sqlite_fts5`、`local_vector`、`local_rrf` 后端选择，新增模型/索引漂移失败关闭、ACL、API、评测和公开 Fixture 测试；
- 由于 RRF 未超过既有 BM25 的 15/15，重排状态为 `DEFER_RERANK`，等待扩展评测出现可测排序缺口后再判断。
- 按最高方案建立正式检索评测 V1：目标 500 条，固定 `dev/test/acceptance=60/20/20`，`online_hard_cases` 独立管理；
- 新增 Manifest、样本、独立标注/仲裁和排名结果合同，固定 0～3 级相关性、泄漏组、Acceptance 盲测和 SHA-256 身份；
- 新增正式集校验器与 Recall/Precision/MRR/nDCG、无答案、越权和延迟指标，多后端报告只输出差值、不自动宣布胜者；
- 公开 4 条合成 Fixture 仅证明合同和工具可执行，校验结果保持 `NOT_LOCK_READY`，不计入正式 500 条或 15 题 Canary。
- 用户批准后续阶段采用风险驱动的最小充分测试，并澄清保留 500 题规模，只降低人工评审复杂度；
- GPT 可承担全部候选生成、低风险初标和回归；低风险 `dev/test` 人工抽检 10%～20%，Acceptance 单人确认；
- 修正评审门禁：低风险样本可停在单 GPT 初标或一致双评审，不再要求每题仲裁；
- 冲突才由人工仲裁，专业高难题才专家复核；原方案双人工标注口径继续单独记为未完成。
- 新增 500 题工作区初始化器，验证真实 `ChunkRecordV1`、拒绝失效/重复 Chunk 和非空目录覆盖；
- 已冻结三论文 316 Chunk 源快照：Chunk SHA-256 为 `f7eb7e4a6c7820abde5523dca906df1d1a052e2e3b2174887781531295c7a282`；
- 已在被忽略的 `runtime/evaluation/formal-retrieval-v1/` 初始化目标 500 的工作区，并保持私有题目、标注和运行报告不进入 Git；
- 固定 500 题的拆分、题型、语言、查询形态、难度与可回答性配额，生成 500 个确定性槽位和 50 个内部容错分组；
- 新增 Qwen3.7-Plus 并发执行器，默认 20 路并发，强制关闭思考、JSON 输出、自动重试和断点续跑；
- Qwen3.7-Plus 已以 20 路并发完成 500/500 个原始候选，失败 0；全部为 `enable_thinking=false`、`finish_reason=stop`，且无 reasoning 内容；
- 生成共消耗 1,177,007 Token；结果包含 3 个重复组、4 个多余重复题面；
- 两轮定向修复共覆盖 7 个确定性语义错误，并保留原始响应和修复响应的完整谱系；
- 新增候选最终化工具，规范化题型、路由、引用、Chunk 元数据和无证据边界；500/500 条均通过正式 `EvaluationItemV1` 草稿合同，题面唯一数为 500；
- 25 个 `CONFLICTING_EVIDENCE` 候选保留为定向人工复核集，不由同一生成模型自行宣布冲突成立；
- 使用同一本机 BGE-M3 对题面与参考答案进行语义筛查，形成 443 个泄漏组；原拆分 24 个跨组冲突通过按组移动 30 题消除，最终仍为 `300/100/100`；
- 正式工作区已回填 500 个 `GPT_ASSISTED` items 与 500 条带模型、Prompt、温度和响应谱系的 Qwen 标注，Manifest 为 `ANNOTATION`；
- 当前正式校验结构、题量、配额和泄漏均通过，但 `engineering_ready=false / lock_ready=false`：100 条 Acceptance、25 条冲突、50 条 hard/standards、75 条无证据/越权/安全题尚未完成人工确认；四类合并去重为 213 题，其中 75 题同时覆盖 362 条低风险 `dev/test` 的 20.7%，无需再单独增加抽检题量。
- 已生成一个去重风险复核包，不拆成人工批次：213 条只读证据队列和 213 条预填但保持 `PENDING` 的决策模板；ZIP 含 README、SHA-256 清单和汇总，压缩包完整性与成员边界已验证；
- 复核包按 `P0/P1/P2=50/126/37` 排序，50 条要求领域专家、163 条要求普通人工复核；当前真实进度保持 `0/213`，未把空模板计作人工结果。
- 用户将 Token 成本设为后续全部流程的首要约束，并允许必要时降低质量；该决策以 PD-019 固化，原 500 题和最高方案人工缺口继续单独保留；
- 返回的 213 条决策全部来自 `ai.gpt-5.6-thinking.independent-review`，内部覆盖、标签哈希、结果与专家字段一致，但明确不构成人工签署；工程路径采用其 155 条确认与 40 条修正，18 条拒绝题直接排除且不消耗 Token 重生成；
- 已派生 482 题 Token 约束工程集，40 条修正全部通过 `EvaluationItemV1`，拆分为 `dev/test/acceptance=296/97/89`，430 个泄漏组均未跨拆分；无证据题占比降为 8.09%，作为已接受质量下降明确记录；
- 482 题集状态为 `TOKEN_CONSTRAINED_ENGINEERING_CORPUS_READY`，但 `human_review_count=0 / engineering_ready=false / lock_ready=false`，不得替代原 500 题正式兼容集或最高方案验收。

## 输入

- 最高依据：《个人学术空间 RAG 问答系统建设与测试方案》，身份与差距见 `docs/REQUIREMENTS_TRACEABILITY.md`；
- 仓库基线：`main` 上已通过的仓库 Harness 与简化 Git 流程；
- 已实现能力：本地 PDF 到 Answer API、公开 Fixture、三论文四路检索基线、原方案兼容合同/指标框架和风险驱动测试策略；
- 未完成能力：风险驱动人工确认、原方案双人工标注、正式范围/SLO、成员 B 远程准备、PostgreSQL、真实 Elasticsearch、Milvus、真实生成模型和远程模型服务；
- 下一工作直接使用 482 题 Token 约束集运行词项、BM25、向量和 RRF 对比，不再等待人工或重生成 18 题；只在比较显示稳定排序缺口时考虑重排。

## 验收

- `python3 scripts/validate_harness_contract.py` 必须通过；
- `make test` 必须覆盖合同、入库、检索、RAG、API、评测和仓库 Harness；
- 本地三论文 Harness 必须通过 15/15，且三类结果分别达到 9/9、3/3、3/3；
- `make sqlite-fts-fixture-smoke` 必须通过 6/6；
- `make vector-fixture-smoke` 和 `make rrf-fixture-smoke` 必须分别通过 6/6；
- 本地三论文向量基线必须如实记录 12/15，RRF 必须通过 15/15；
- `make formal-evaluation-fixture` 必须通过，且公开 4 条 Fixture 必须保持 `engineering_ready=false / lock_ready=false`；
- `python3 scripts/export_evaluation_contracts.py --check` 必须通过；
- GPT 标注必须携带模型身份、Prompt 版本和温度，且不得担任仲裁或专家；
- 一致低风险题不得因流程惯性强制增加仲裁，Acceptance 与高风险题不得取消人工复核；
- `git diff --check` 必须通过；
- 不得出现被跟踪的 `runtime/`、PDF、`.env`、数据或存储目录；
- 仓库状态、能力清单和本文件必须一致。
- 最高方案文件名、`2074` 行与 SHA-256 必须在需求追踪和机器状态中一致；
- 不得将仓库 `M0_COMPLETE`、15 题 Canary 或 Fake LLM 写成最高方案阶段 0/2 已完成。

## Git

- 默认分支：`main`；
- 当前 Repository Harness 提交从 `agent/add-repository-harness` 快进到 `main`；
- 成员 A 普通低风险任务通过本地门禁后直接 push `main`；
- 成员 B 远程任务和高风险变更继续通过 PR；
- 推送后本地 `main` 必须与 `origin/main` 指向同一提交；仅在 CI 配置、依赖、跨平台、高风险变更或异常状态时检查 GitHub Actions。

## Current boundary

当前仓库 Harness 已与最高方案建立需求映射。总体仍处于最高方案阶段 0，仓库 M0、本地 RRF M1 和评测工具只是已验证的子基线。当前最宽本地问答执行边界仍为 `LOCAL_API_RRF_HYBRID_FAKE_LLM`；近期评测执行边界为 `TOKEN_CONSTRAINED_ITEMS_482 / EXTERNAL_AI_AUDIT_213 / EDITED_40 / EXCLUDED_18 / HUMAN_REVIEW_0`，原 500 题与原方案执行边界仍为 `GPT_ASSISTED_500_HUMAN_PENDING / SOURCE_FORMAL_DOUBLE_HUMAN_PENDING`。它们不证明风险人工门禁、原方案双人工口径、PostgreSQL、Elasticsearch、Milvus、远程部署、真实 RAG 生成模型或生产参数已完成。PDF、真实 Chunk、私有问题集、标注记录、索引和运行报告不得提交。

## Next gate

1. **共享范围与评测线：** 原 500 题保留；482 题 Token 约束集已由第二模型审计派生，不再等待人工或重生成拒绝题；
2. **A 本地工程线：** 直接运行 482 题四路工程对比，不在没有证据增益时接入重排；
3. **B 远程基础设施线：** 按 Issue #9 完成主机盘点，拉取同一 `main` 运行全量测试和 Fixture 冒烟；
4. B 的基线通过后，按 PostgreSQL、Elasticsearch、Milvus、模型服务逐项建立真实状态，不同时切换多个基础设施变量；
5. A 已完成同一 Canary 的词项、SQLite BM25、向量和混合检索比较；真实 LLM 仍放在扩展评测和远程检索证据链稳定后单独接入；
6. GPT 辅助 500 题只用于近期工程决策；只有恢复原方案双人工验收口径，并让范围、正式评测、真实 ES/Milvus 基线和模型资源选型都形成证据后，才能按最高方案关闭阶段 0。

## Prohibited shortcuts

- 不把父级知识库整理目录整体初始化为 Git 仓库；
- 不上传现有知识库数据、PDF、数据库、模型、运行时和本地配置；
- 不用即时通讯压缩包代替 GitHub 中的版本化源码交付；
- 不在安全和权属审查前将仓库切换为公有。
