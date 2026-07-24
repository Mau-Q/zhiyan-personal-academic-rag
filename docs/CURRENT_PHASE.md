# Current Phase

## Status

`SOURCE_PHASE_0_COMPLETE / SOURCE_PHASE_1_COMPLETE / SOURCE_PHASE_2_COMPLETE_RRF_DEFAULT_RERANKER_OPTIONAL_PERFORMANCE_DEFERRED / SOURCE_PHASE_3_IN_PROGRESS_FIRST_TWO_VARIABLES_DEV_QUALITY_FAILED_DISABLED_TEST_SEALED / SOURCE_PHASE_4_PARTIAL_MULTI_EVIDENCE_SET_LOCAL_READY_AUDIT_ONLY_ONLINE_HARD_JUDGMENT_DEFERRED / REPOSITORY_HARNESS_READY / REPO_M0_COMPLETE / M1_LOCAL_RRF_BASELINE_READY / MVP_INITIAL_175_HUMAN_VALIDATED / MVP_175_REMOTE_SINGLE_BACKEND_BASELINES_COMPLETE / REMOTE_RETRIEVAL_BASELINE_READY / REMOTE_RRF_CANARY_COMPLETE_NO_GAIN / LOCAL_REAL_GENERATION_GATE_READY`

Phase ID：`phase4-multi-evidence-set-local-ready`

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
- 明确仓库 `M0/M1` 为内部工程里程碑；当时最高方案阶段 0 仍为 `IN_PROGRESS`，现已由独立范围与 Baseline 门禁完成收口；
- 将 3 论文 15 题定位为快速工程 Canary，不代替固定 175 题 MVP 初始集、约 500 条稳定迭代集和 800～1500 条正式验收集。
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
- 收到 213 条外部 AI 独立复核：`155 APPROVE_AS_IS / 40 EDIT_LABELS / 18 REJECT_ITEM`；已构建保持 500 题的检索专用工程集，40 项精确更正，18 项最小修复标记为 `DRAFT`；人工复核仍为 `0/213`。
- 已对 500 题完成词项、SQLite BM25、本地 BGE-M3 向量和 RRF 四路检索，每路 `500/500`；test 的 `nDCG@10` 依次为 `0.457569 / 0.502652 / 0.631910 / 0.647269`。
- dev 上向量 `nDCG@10=0.614514` 高于 RRF `0.607016`，test 上 RRF 反超约 `0.015359`；优势不稳定，暂不增加重排复杂度。
- 成员 B 的 PR #13 已合并：远端为 Windows 11 x64、64 GB 内存、RTX 4090 24 GB；Docker/Compose 可用，PostgreSQL 已运行，Elasticsearch、Milvus 和模型服务未部署。
- 远端在 `ff5993e` 通过 Harness 和 HTTP 冒烟；62 项测试通过、5 项因 Windows 无 `python3` 命令失败。仓库已改为子进程复用 `sys.executable`，等待 B 在最新 `main` 复测。
- 远端已拉取 `8b22e56`，Windows 子进程解释器和跨平台哈希问题修复后 evaluation 测试 `45/45` 通过；
- 远端盘点闭环：i7-12700K、64 GB、RTX 4090 24 GB、WSL2 与 Docker Desktop 可用，容量充足的数据盘可供检索持久化；
- PostgreSQL `18.4` 本机连接正常，HBA 仅允许回环认证；应用 Schema、ACL 真值和生命周期尚未接入；
- 原生 Windows Ollama `0.30.10` 的 BGE-M3 返回 1024 维向量并以 GPU 执行；
- Elasticsearch `9.4.3` 单节点工程基线通过中文 BM25、ACL 过滤和重启恢复；
- Milvus `2.6.18` standalone 工程基线通过 BGE-M3 写入、COSINE 搜索、ACL 过滤和完整重启恢复；
- Elasticsearch、Milvus、MinIO、Ollama 的宿主机端口均限制为回环监听，持久化数据放在容量充足的数据盘；
- 已固化脱敏 Compose 配置和远程检索基线文档；ES 与 Milvus 的 316 Chunk 重跑已完成，性能验收尚未开始。
- Elasticsearch BM25 适配器已实现：严格 Mapping、源身份、服务端 ACL、Bulk UTF-8、漂移失败关闭和 Answer API 边界测试通过；远程 Fixture 与 316 Chunk 索引通过，固定 15 题结果为 14/15（可回答 8/9、无证据 3/3、越权 3/3）。唯一未通过项检索到同一论文第 5 页的完整模式/评分正文，但冻结目标只接受第 2 页概览图，因此不修改题目、目标页或 `top_k=3` 制造通过。
- Milvus 向量适配器已实现：固定源 Chunk、Embedding 模型 digest、维度、COSINE、HNSW 工程参数和严格 Collection Schema；服务端 ACL 与应用侧二次授权、漂移失败关闭、Answer API 和评测 Harness Fixture 测试通过。远程 316 Chunk 固定 15 题结果为 12/15（可回答 6/9、无证据 3/3、越权 3/3），与本地精确向量基线一致；3 个缺失目标页如实保留，HNSW 参数仍是工程基线而非生产最终值。
- 固化 Elasticsearch/Milvus 共用的 `backend/rank/score/chunk` 候选接口和无密钥 `remote_retrieval_config_v1`；非法结果、分数和身份漂移失败关闭；
- 基于 ES 与 Milvus 单路失败互补的证据，实现最小 ES+Milvus RRF：双路候选 20、`k=60`、最终 `top_k=3`，不直接比较异构原始分数；本地 Fixture Answer API 与 Harness 已通过。
- 远程 15 题 RRF Canary 实跑为 14/15（可回答 8/9、无证据 3/3、越权 3/3），与 ES 单路持平；唯一失败仍为 `local3.answerable.evmbench.modes`，冻结目标第 2 页被融合后的同论文第 4/5 页证据挤出最终 Top-3。
- 由于最小远程 RRF 未超过 ES，保留适配器与真实失败，不调参、不晋级默认策略、不增加重排。
- 新增候选接口、配置、融合与 Harness 针对性测试后，全仓 142 项测试及 Harness 8 项检查通过。
- Makefile 已跨平台固定 `.venv/bin/python` 或 `.venv/Scripts/python.exe`；所有仓库门禁不再使用系统 `python3`，虚拟环境缺失时失败关闭，不会把依赖缺失误报为源码失败。
- 最高方案已同步上游为 725 行，SHA-256 为 `43fd5d4af4d38884c2449b9ff39fcee537cf27af5a7a700747a932be5f74dc78`；业务范围收敛为个人文献库，知识来源仅为上传论文和收藏后入个人库的论文，并将 175 题写为固定 MVP 初始资产。
- 已按固定策略从现有 500 题选出 175 题 MVP 初始队列：精确查找 30、单文档事实 50、语义改写 30、比较 20、证据边界 25、安全 20；`dev/test/acceptance=105/35/35`，175 个泄漏组互不重复。
- 人工决策模板的 175 个结论和 1050 个检查项全部保持 `PENDING`；当前真实进度为 `0/175`，未将 GPT 初标或外部 AI 审计计为人工校验。
- 新增 175 题策略、生成器和针对性测试后，全仓 145 项测试及 Harness 8 项检查通过。
- 外部 AI 预审文件已以 SHA-256 `bc808388007ed5e82d153cf8454a99e12a700e91a5fba52df9a9581a50fe576f` 单独保留，不直接改名冒充人工谱系。
- 评审者 `A` 已确认逐题复核 175 条，并以同一假名完成 4 条授权专家签署；最终结果为 `166 APPROVE_AS_IS / 9 EDIT_LABELS / 0 REJECT_ITEM`。
- 人工最终文件无 `PENDING`，175 条修订后标签全部通过 `EvaluationItemV1` 正式合同，SHA-256 为 `a428a8fc92cece0d1aaf7e31ce11377bec2791e146b64efdc9e2ef1279800986`。
- 新增显式人工/专家声明门禁和谱系保留测试后，全仓 147 项测试及 Harness 8 项检查通过。
- 已从同一冻结 175 题生成兼容现有远程 Harness 的 ES-only/Milvus-only 私有输入包；两路各 175 题，`dev/test/acceptance=105/35/35`，ZIP SHA-256 为 `636593badda13fb11558ead65ab8b3b3cedb50ac0449bbdeff4889787e319e0b`。
- 输入包仅复用已锁定的 316 Chunk、`top_k=3`、ES 索引和 Milvus/BGE-M3 配置；远程两路报告均已覆盖 175/175，且题号和类别与冻结输入完全一致。
- ES 严格整题通过 `85/175`：可回答 `84/138`、无证据 `1/17`、安全拒答 `0/20`，必需证据目标命中 `114/192`；报告 SHA-256 为 `f49cb929aaf5f42593b9b38dac4baaf92377a54d9ed754df7dae77af009ecaaf`。
- Milvus 严格整题通过 `109/175`：可回答 `109/138`、无证据 `0/17`、安全拒答 `0/20`，必需证据目标命中 `144/192`；报告 SHA-256 为 `22f83b144da2b607f7ec66abb4bbe64a4c978827c0a2456c8540f50fd9034433`。
- 两路整题同时通过 78 题、仅 ES 通过 7 题、仅 Milvus 通过 31 题、两路均未通过 59 题；在 138 道可回答合同中，仅 ES 通过 6 题，仅 Milvus 通过 31 题。
- Milvus 是当前更强的单路召回基线，但两路都暴露无证据校准和安全策略层缺口；这两类失败不冒充纯召回失败。
- 由于远程 RRF Canary 已证明融合未超过 ES，且本次 Top-3 互补严重倾向 Milvus，当前不跑 175 题 RRF、不调融合参数，保留既有适配器。
- 新增三策略 Baseline 针对性测试后，全仓 154 项测试及 Harness 8 项检查通过。
- 完成三论文三种 Chunk 同源受控 Baseline：`fixed_boundary_v1` 产生 279 个 Chunk，`paragraph_sentence_v1` 与 `section_parent_child_v1` 各产生 316 个 Chunk；每种策略 SQLite BM25 均为 15/15、BGE-M3 均为 12/15，安全和无证据类均为 6/6；报告 SHA-256 为 `6edac6b48e80d160d5b32de87eec38d193e5060873cfbab2e99d4d13b18121c3`。
- 三种 Chunk 策略总体持平；固定边界与结构化策略各有一道独有命中/漏召回，不换默认策略、不调参、不引入重排。
- 冻结阶段 0 单用户范围与阶段 1 验收目标：500 篇论文标称规模、1000 篇验证上界、持续 0.2 QPS、问答并发 2、入库并发 1；MVP 复用单台既有 4090 主机，不新增硬件或外部 API 预算。
- 冻结检索 P95 300 ms、P99 500 ms、TTFT P95 3 s、完整回答 P95 10 s、端到端 P99 15 s 及权限/引用硬门禁；这些是待阶段 1 实测的目标，不是当前达标结果。
- 范围/资源/SLO 子门禁完成；方案阶段 0 仍需冻结数据身份适配和上游生命周期目标语义。
- 新增范围/资源/SLO 机器门禁后，全仓 155 项测试及 Harness 9 项检查通过。
- 冻结 `DocumentIdentityV1`、`DocumentVersionLifecycleV1` 和机器策略：映射按 `owner_id` 隔离，`document_id` 与 `(owner_id, paper_id)` 分别唯一，内容变化创建新 `document_version_id`。
- 冻结生命周期状态机与 READY 硬门禁：解析、Chunk、ES 和 Milvus 必须全部完成，删除/过期版本先在 PostgreSQL 失效，再清缓存并异步清理索引。
- 数据身份与生命周期合同新增 3 项语义测试后，全仓 158 项测试及 Harness 9 项检查通过；方案阶段 0 完成，当前进入阶段 1。
- 完成阶段 1 第一个本地实现：PostgreSQL Schema、版本化迁移器、`owner_id` 事实源适配器、幂等入库任务和生命周期 Compare-and-Swap；远程 PostgreSQL 尚未应用迁移。
- 后续远程主机操作改由用户亲自执行；代理准备脚本和完整命令，根据用户返回的脱敏原始输出判定。
- 新增 15 项 PostgreSQL 事实源专项测试后，全仓 173 项测试及 Harness 9 项检查通过。
- 完成本地持久化 PDF 准备编排：先校验 PDF 身份，再按 `owner_id` 建立映射，原子绑定内容版本与幂等任务，将 PostgreSQL `document_version_id` 适配到 `ChunkRecordV1.version_id`。
- 持久化准备产生的 Chunk 在双索引完成前固定 `is_active=false`；解析失败和 `REVIEW` 状态已记录稳定任务错误，同一请求可重放恢复。
- 新增 7 项持久化摄取测试与 2 项事实源进度/原子绑定测试后，全仓 182 项测试及 Harness 9 项检查通过。
- 完成本地双索引生命周期协调：逐侧暂存并核对源身份，单侧失败记录稳定任务错误并补偿为非活动，两路成功后原子提交 `READY + SUCCEEDED`。
- 完成删除、撤权和过期的失效顺序：先提交 PostgreSQL `INACTIVE`，再失效查询可见性并安排 ES/Milvus 异步物理清理；远程写入器和持久化清理队列尚未接入。
- 新增 7 项双索引协调测试与 2 项事实源原子结果测试后，全仓 191 项测试及 Harness 9 项检查通过。
- 完成 Elasticsearch 隐藏版本索引写入器：确定性物理索引名不暴露原始 owner/version，暂存、补写、激活、失活和删除均按版本身份核验；不创建在线 Alias。
- 新增 7 项 Elasticsearch 版本写入器测试与 1 项传输存在性测试后，全仓 199 项测试及 Harness 9 项检查通过。
- 完成 Milvus 脱离在线路由的版本 Collection 写入器：确定性名称不暴露原始 owner/version，Collection 描述绑定源 Chunk、Embedding 模型、维度和完整向量指纹；完整重放不重复向量化，部分写只补缺失行。
- 新增 7 项 Milvus 版本写入器测试与 1 项传输生命周期测试后，全仓 207 项测试及 Harness 9 项检查通过。
- 完成失效后物理清理闭环：只有 PostgreSQL `INACTIVE` 版本可以幂等入队；Worker 使用租约和 `SKIP LOCKED` 领取任务，恢复过期租约，按稳定错误码和有界指数退避重试，并调用身份固定的 ES/Milvus 版本删除接口。物理对象已经不存在按幂等成功处理，任何下游失败都不会重新激活事实源。
- 完成本地在线 READY 可见性闭环：PostgreSQL 约束同一 owner/document 只有一个活动版本；Answer API 从服务端鉴权 owner 解析 `READY` 文档版本，逐版本核验确定性 ES Index、Milvus Collection、模型和活动 Chunk，再跨多版本统一 RRF。任何事实源、路由或候选身份无法证明时沿现有 403 合同失败关闭。
- 完成阶段 1 本地集成对账门禁：对指定 owner/document 精确核对 PostgreSQL `READY`、源快照身份、ES 物理 Index 和 Milvus 物理 Collection，任一侧缺失或漂移整体失败关闭；固定 `make stage1-local-canary` 覆盖 50 项相关闭环测试。
- 形成一次性远程验证包：用户在隔离远程主机按版本化清单执行迁移、双索引发布、READY 对账、删除失效、两个物理清理任务和单侧失败重放；报告不包含凭据、PDF/Chunk 正文或端点。
- 用户已在远程提交 `5de784c` 执行阶段 1 基础设施 Canary：PostgreSQL 三个迁移首次 `APPLIED`、重放 `UNCHANGED`，合成 PDF 生成 4 个 Chunk，PostgreSQL `READY` 与 ES/Milvus 物理路由对账 `PASS`，删除后两个清理任务成功且在线不可见。
- 同一远程 Canary 已验证单侧失败恢复：暂时使 Embedding 端点不可达后脚本以 `IndexLifecycleError` 和退出码 1 失败，PostgreSQL 查询证明版本未进入 `READY`；恢复端点并使用相同 Run ID 重放后整体 `PASS`，不停止稳定服务。
- 远程脱敏报告 SHA-256：成功闭环 `D824BB4848050B20E4CB747BEC8F56D9B2F703F22991F06DAC89B912DF865DA0`，预期失败 `2AE22BBEA0E59FEB578129630916FDDD2672708BEC7BBB47A4DB57B8C42EAEF1`，同 ID 恢复 `5E365EE3D1B2B50A57B73DA3C9D003033FA18701209EBA9424B4E8AB593A66A7`；远程工作树干净，凭据已从 PowerShell 环境清除，报告保留在被忽略的 `runtime/`。
- 完成本地 PDF/Chunk 运行存储：`filesystem_v1` 以不透明确定性键原子保存并重开校验 PDF，PostgreSQL `0004` 注册对象定位和不可变 Chunk 快照，重放核对完整快照指纹；不新增依赖、不把 PDF 字节写入 PostgreSQL。
- 完成持久化快照 Answer API 闭环：在线模式不再加载 Fixture Chunk/Scope，只按 PostgreSQL READY 版本加载 Chunk，并在检索后重验事实源；失效后返回 403，ES、Milvus 和运行快照三项物理清理共用持久租约、重试与恢复。
- 远程 v2 首次运行在 PDF 对象注册处以 SQLSTATE `2201B` 失败，未进入 ES/Milvus 发布；根因是 `0004` 的对象键正则使用 PostgreSQL 不支持的 `{0,511}` 重复上限。本地追加 `0005` 迁移，以长度检查加无上界字符集正则修复，并保留 `0004` 校验和不变。
- 应用 `0005` 后，同一远程 Run ID 已完成 PDF/4 Chunk 持久化和 ES/Milvus `READY`，Answer 门禁暴露暂存态 `is_active=false` 指纹与 PostgreSQL READY 投影 `is_active=true` 被误判为内容漂移。本地已让 ES/Milvus 分离校验“暂存源指纹”和“在线活动载荷”，并支持同一 Run ID 从既有 READY 快照继续 Answer、失效和三路清理，不重建索引。
- 用户在远程提交 `72d71d2` 使用原 Run ID 完成 v2 恢复：PDF 对象重开、4 个 PostgreSQL Chunk、ES/Milvus READY 对账、持久化快照 Answer API `COMPLETED` 与 3 条 Evidence、删除后 403、ES/Milvus/运行快照三项清理全部通过；报告 SHA-256 为 `6B2AB3BAAD55AE8FA506C0D1FD7A310D9EF3A3833A93E33DD1A2D8A0938A9D8C`，凭据变量已清除。
- 最高方案阶段 1 的退出条件已满足：owner 发布阻断、ES/Milvus ID 与版本对账、删除/失效不可召回、上游时间戳与版本追踪、单侧失败不误报 READY 均有本地合同和远程运行证据。正式 MinIO、OCR 和目标规模性能仍是未完成需求，但不属于第 10.2 节列出的阶段 1 退出条件。
- 已对照最高方案第 10.3 节冻结阶段 2 差距：Hybrid 已实现但远程 Canary 无增益，Reranker 保持 `DEFER_RERANK` 且不冒充真实模型验证，引用/ACL/版本/定位门禁与 Claim 语义支持边界分开记账。
- 已接入可选的真实 Ollama 生成器，不改变现有 Fake 默认路径和 RAG Answer 公共合同；生成器只消费检索后 Evidence，模型摘要、Prompt 和解码固定，模型漂移、非法 JSON、无引用或引用越界均失败关闭为 `DEGRADED` 证据卡。
- 本机 `llama3.2:latest@a80c4f17acd5...b8b72` 真实模型 Canary 已通过：两次回答稳定、引用编号有效、无证据不调用模型、越权范围保持 403；执行边界为公开 Fixture Evidence，不冒充远程 PostgreSQL/ES/Milvus 实跑。
- 用户在远程提交 `91aca5a` 使用同一冻结模型摘要完成 READY 真实生成恢复闭环：PostgreSQL READY + ES/Milvus RRF 返回 3 条 Evidence，Answer API `COMPLETED`、引用编号校验和两次稳定回放均通过；随后删除后 403 与 ES/Milvus/运行快照 3 项清理通过，稳定错误码为 `NONE`。脱敏报告 SHA-256 为 `E2231FADABB368209F976B2BAB99F4E1D841ACB3053C45A07B1ADDC7B386E937`，报告未保存回答或 Chunk 正文。
- 已冻结独立模型选型 Harness：回退基线为 `llama3.2:latest@a80c4f17...b8b72`，唯一候选为 `qwen3:14b@bdbd181c...debe8`；两者直接调用同一 Ollama API，复用同一 Prompt、Schema、解码和四组公开中文科研 Evidence，不连接或修改检索基础设施。
- 模型选型 v1 的“证据不足”用例被过窄短语表误判；v2 保留原 Evidence/Prompt/模型，只补充等价拒答措辞，并将字节一致降为观测项、两次确定性门禁均通过作为稳定性条件。用户已在提交 `ebb12c4` 完成远程 v2：Qwen `4/4`、llama3.2 `2/4`，结果 `PASS / PROMOTE_QWEN3_14B / NONE`，脱敏报告 SHA-256 为 `21C27EAE18848962FC25A879AC620F989F4DD9690C6EB67A10236BE71DAF788B`。
- READY Canary 的真实生成稳定回放同步采用相同边界：两次 Answer API 调用必须分别完成引用门禁并返回相同 Citation 集合；答案是否逐字一致单独记录为 `generation_byte_stable_replay`，不作为自然语言模型硬门禁。
- Qwen READY 首次远程运行以 `PERSISTED_SNAPSHOT_ANSWER_HTTP_FAILED` 停在 Answer API；同 Run ID 恢复后已进入真实生成，但以 `REAL_GENERATION_INITIAL_FAILED_CLOSED` 失败关闭，尚未执行失效和三路清理。该结果证明问题不是缺少 Ollama API 配置，但原统一错误码无法区分传输、响应 JSON、答案 JSON、Schema 或引用失败。
- 生成器现为上述失败类别携带固定 allowlist 代码；远程 Canary 仅观察并输出该代码，不保存异常正文、模型回答、Prompt 或 Evidence，也不改变对外 Answer API 的 `DEGRADED`、warning 和 Schema。
- Qwen READY `retry2` 将具体失败定位为 `REAL_GENERATION_INITIAL_OLLAMA_ANSWER_JSON_INVALID`。依据 Ollama Qwen3 thinking API 边界，后续只显式冻结 `think=false`，避免默认 thinking 在 `num_predict=384` 内挤占最终结构化回答；模型摘要、Prompt、Schema、其他解码项和检索均未改变。
- 用户在提交 `43dc5b4` 完成 Qwen READY retry3：PostgreSQL READY + ES/Milvus RRF 返回 3 条 Evidence，Answer API `COMPLETED`，固定模型摘要、`think=false`、引用、两次稳定回放、删除后 403 和三路清理均通过，报告 SHA-256 为 `0CB1B569D8A782FC526266E1A7193EF6299B66D5DBC72DCC989FDB951B8A1160`，稳定错误码为 `NONE`。
- 同提交的选型 v3 为 `PASS / KEEP_LLAMA3_2`：Qwen `3/4`、llama3.2 `2/4`，报告 SHA-256 为 `64C4A7C741D5DC624D501165A129400D98DF66845F43BFC57D964AA9CD2B3C4E`。唯一失败是冲突用例的表面词检查；两次诊断均已包含 `12周`、`16周`、引用 `[1][2]`，身份和禁词门禁通过。v4 只将其改为冲突值与来源引用的结构门禁，不改生成或检索变量。
- 用户在提交 `063236a` 完成远程 v4：Qwen `4/4`、llama3.2 `3/4`，结果为 `PASS / PROMOTE_QWEN3_14B / NONE`；`think=false` 且检索参数未改变，报告 SHA-256 为 `E031B1B4532571850FD4527D4930E80A3C144074DBB55F8055A54A51EDB7E038`。Qwen 最终晋级，llama3.2 保留为回退；v3 假阴性报告不覆盖。
- 阶段 2 固定普通科研问答验收包已完成远程 v2 验收：复用既有三论文人工定位题集，固定 3 篇 PDF、每篇 3 题，共 9 题；生成固定 Qwen 摘要与 `think=false`，检索参数保持不变。3 篇文档各 `3/3`、合计 `9/9` 通过真实生成、引用集合稳定回放、页码定位、三路清理和删除后 403；最终第 3 篇报告 SHA-256 为 `3C106423AB3575B11B3B0142A66F19A2C949B8BAED3457F1BCA101A9931302FA`。自然语言答案字节一致仅作观测，本次为 `false`，不影响确定性引用与安全硬门禁。
- 固定 Cross-Encoder 已复用 `sentence-transformers.CrossEncoder` 与 `BAAI/bge-reranker-v2-m3@953dc6f6...d41e`，只重排冻结 `local_rrf` 前 20 候选并以 `test=100` 作决策，不读取 Acceptance 指标；`nDCG@10` 从 `0.647269` 提升到 `0.747810`（相对 `+15.5331%`），`Precision@5` 从 `0.231111` 提升到 `0.251111`，四个关键类型均未越过 0.02 回退线。用户在提交 `d31e992` 的 Windows RTX 4090 上保持相同模型/snapshot/输入身份，取得 pair-scoring `P50=169.3867 ms / P95=188.22683 ms`，稳定错误码为 `NONE`；组件决定为 `RETAIN_FIXED_CROSS_ENCODER_FOR_CONTROLLED_ONLINE_INTEGRATION`，默认在线路由尚未改变。
- 受控在线 Reranker 窄适配器已本地实现：现有 PostgreSQL READY/owner、持久化 Chunk 身份和检索后重验保持前置，ES/Milvus RRF 最多返回 20 个已授权候选，固定 Cross-Encoder 只排序并输出前 3；标题/模型/分数故障显式回退同一批 RRF，身份漂移仍失败关闭。用户在提交 `fb54918` 完成 ES/Milvus 并行远程复跑：30/30 `APPLIED`、无回退/扩张/越界、三路清理与删除后 403 通过，但 base retrieval `P95=344.676365 ms`、Reranker `P95=131.885375 ms`、combined `P95=472.190015 ms`，报告 SHA-256 为 `132DFFDECDAD02F9C5280FADFBD09B5AE100C1DB31FE07118BF97B6E0C1B2602`。默认路由继续保持原 RRF；当前本地只增加基础召回分段观测，等待远程归因。
- 用户随后在提交 `3303bed` 和 Run ID `online_retrieval_profile_20260723_01` 完成 Windows 分段归因：30/30 `APPLIED`，分段状态 `PASS`，base retrieval `P95=376.394385 ms`、Reranker `P95=132.456 ms`、combined `P95=504.71613 ms`；主要成本为 Query Embedding `P95=189.838925 ms` 和 READY 路由解析 `P95=145.48693 ms`，ES 总工作 `P95=35.634955 ms`、Milvus ANN `P95=6.03377 ms`、RRF `P95=0.12001 ms`。三路清理和删除后 403 通过，报告 SHA-256 为 `235FE36A97B7F4E462AD502595CB0CF38C139022703B6C4EA1E93E19D3AC765B`。
- 阶段 2 现按最高方案第 10.3 节完成：Hybrid 对比、固定 Reranker 增益与保留/回退决定、引用/ACL/版本/定位硬门禁和普通学术问答稳定回放均已完成。默认继续使用原 RRF，固定 Reranker 保留为非默认可选组件；300 ms 性能未通过，作为显式性能债进入阶段 3 独立 Gate，不冒充生产性能验收。
- 阶段 3 入口已冻结，并完成唯一变量 `BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1` 的默认关闭本地实现候选：4 个冻结 `dev` 的 Control 原问题保持 `4/4`、Treatment 确定性规划 `4/4`，120 次纯拆分本地 P95 为 `0.016271 ms`；隔离三文档在线 runner、私有 dev 输入包和 Windows PowerShell 5.1 用户入口已通过本地契约/静态检查。该本地实现时点尚未运行真实在线配对检索，故当时不写成质量增益或不退化通过。`test/acceptance` 保持封存，固定 Reranker 和默认 RRF 不变。
- 阶段 3 配对 dev 报告的独立裁决入口已准备：报告必须绑定实际 Git HEAD、Run ID 和 SHA-256，并重新验证输入/配置/目标身份、指标算术、9 路清理、删除后 403 与 holdout 隔离；PASS 只形成默认关闭的 dev 候选草案，不能自动解封 `test`。
- 首次 Windows Run ID `phase3_comparison_dev_20260723_01` 在连接服务前因 `core.autocrlf=true` 把冻结 JSON 检出为 CRLF 而被拒绝；报告 SHA-256 为 `AC081A26FD331F00659BE3E950537A9B22D46E75C1F3303B1BFEFBD7D7706827`，裁决 SHA-256 为 `EB0CE6F786963B65E859496405F4F12018C93AB43015B0E759D306141B1714F6`。该尝试没有运行在线 Control/Treatment、没有写入基础设施，也不是质量证据；运行器现只将纯 CRLF 规范化为 LF 后核对原冻结 SHA，内容漂移仍失败关闭，等待新提交和新 Run ID 重试。
- 第二次 Windows Run ID `phase3_comparison_dev_20260723_02` 在提交 `ac1e5994f8e35648750d912b9a778c2a46682c3c` 上通过配置身份后以 `CLEANUP_PROOF_FAILED` 结束；报告 SHA-256 为 `423D736D496BE0AFA1CC06A90E3402B060C519F74C17D9C4939E31A50304E276`，裁决 SHA-256 为 `74A599288445F1C2267F892A81B5F6B8BD3D5002D4A67E6BE6700645D3516981`，错误码为 `REPORT_CLEANUP_PROOF_INVALID`。旧通用异常路径没有保留主失败或清理阶段，`identity=null`，因此该报告既不是质量证据，也不能证明隔离 owner 已清理。
- 运行器现分别保留 `primary_error_code`、清理阶段、已观察/成功任务数与稳定阶段错误；版本固定的 Windows PowerShell 5.1 审计入口只在 PostgreSQL `READ ONLY` 事务中查询 `_02` owner 的版本、入库任务、三路清理任务、Chunk/PDF 快照聚合及全局非终态清理任务计数，不暴露其他 owner、不直接查询 ES/Milvus、不修改数据、不重启服务、不读取 `test/acceptance`。审计返回 `CLEAN` 前禁止新质量 Run ID；残留只能进入独立恢复 Gate。
- `_02` 只读审计已返回 `FAIL / RESIDUAL_REQUIRES_RECOVERY_GATE`：3 个版本全部 `INACTIVE`，3 个入库任务终态，9 个清理任务全部 `PENDING/attempt=0`，全局非终态任务正好也是这 9 个，仍有 316 Chunk 和 3 PDF；审计 SHA-256 为 `A3FBDDC29ACAAAB0E72EDCD889F14A198F238F523A08588D5D486765999498CF`。因此没有 READY 泄漏，但物理清理未执行。
- 精确恢复入口已准备：变更前重验完整残留身份，只让既有持久化 Worker 最多领取这 9 个任务，完成后要求 9 个 `SUCCEEDED`、全局非终态/Chunk/PDF 清零并自动运行只读事后审计；不运行质量、test、Acceptance 或性能，不重启服务，不允许手工删除。
- 用户已在提交 `64ef344daa5382d0b043ff444300963fb076c068` 完成 `_02` 精确恢复：9/9 `SUCCEEDED`，Chunk `316→0`、PDF `3→0`、全局非终态 `9→0`；恢复报告 SHA-256 为 `E9A9566ECFEDE9C30310F9831D8EBF22249CB5081EDA69BA6F7DEA48E26CB8FA`，事后只读审计 `PASS/CLEAN`，SHA-256 为 `F3C12A2F2F7C4D8E0F75EE8DB7B483B44C6509CF65FA0F0EE03779E296252790`。本次没有运行质量、test、Acceptance 或性能，允许以全新 Run ID 重试同一冻结质量 Gate。
- 第三次 Windows Run ID `phase3_comparison_dev_20260723_03` 在提交 `3a77484020f57aca27e6fa4b6d48cd1d81260982` 上于 Control/Treatment 指标前失败关闭：清理阶段 `VERIFY_QUEUE_SCOPE`、错误 `CLEANUP_QUEUE_SCOPE_PROOF_FAILED`；报告 SHA-256 为 `A45EF2F9F030FEB6AAED05DECB33A019CFA7920FAF6E1F1ABEB7189C242E339EC`。只读审计确认 3 个版本全部 `INACTIVE`、9 个三路任务全部 `PENDING/attempt=0`、316 Chunk、3 PDF，且全局非终态正好只有这 9 个；审计 SHA-256 为 `E9430BE17811C60116630F718C182A3FFD0A12FFD83F753EBB5FDFBA0420112B`。
- 根因已定位为运行器 `_active_cleanup_scope` 在 psycopg `dict_row` 连接上按元组解包行，实际得到列名而非 owner/version/backend 值，导致正确的 9 任务队列被错误拒绝。当时先用独立 Gate 绑定 `_03` 与审计 SHA 完成精确恢复，未在恢复 Gate 中修改运行器。
- 用户已在提交 `c9c3705d70de7cb43812a8cd8a6a585da6eebcd9` 完成 `_03` 精确恢复：9/9 `SUCCEEDED`，Chunk/PDF/全局非终态均为 0；恢复报告 SHA-256 为 `94A10A54FFB6B326740E093DB97D148891FD44898E7BC077E25FA4385B780CDB`，事后审计 `PASS/CLEAN`，SHA-256 为 `FFD2E805B857DF1D4D7E256A00BF09B15992261A4A31960C7A2D55B8D504DBAB`。质量、test、Acceptance、性能均未运行。
- 独立运行器修复现将 psycopg 行按 `owner_id`、`document_version_id`、`backend` 显式取值，并在报告/脱敏 summary 中记录 `primary_stage` 与 `primary_error_code`；没有改变任何质量变量或默认路径。
- 第四次 Windows Run ID `phase3_comparison_dev_20260723_04` 在提交 `b92e9ffa1d576aeef83dd028a28df09bf601d52e` 上进入 `RUN_CONTROL` 后以通用 `PHASE3_GATE_FAILED` 失败，Control/Treatment 指标均未形成；报告 SHA-256 为 `2CA305DCD16820DE4EB28863097F58C53AD5F9D678604C5251A65DE70B2AA47C`，裁决 SHA-256 为 `B49BF9079ED3C9C7C2019A4E4836CDB9677DEA07955675D6BFE1CDCE25E4A4BF`。报告同时证明清理 9/9、READY 失败关闭和删除后 403，故无需恢复；比较拆分保持关闭，test/Acceptance 未读取。
- 当前独立诊断加固只将异常类型链映射为 PostgreSQL READY、ES、Embedding、Milvus、在线 Scope/可见性、结果规范化或未分类等固定错误码，并把 Control 检索与指标计算分为 `RUN_CONTROL` / `SCORE_CONTROL`；不输出异常文本、不新增请求、不改变检索或质量变量。
- 第五次 Windows Run ID `phase3_comparison_dev_20260723_05` 在提交 `a669702b24880269a130f8e249126b30e17a2972` 上于 `RUN_CONTROL` 返回 `ONLINE_MILVUS_ROUTE_FAILED`；报告 SHA-256 为 `19A92545D6E87408462BDC38A72E3F4F69B5AA03EDCAAED19400116AAFBA4CD4`，裁决 SHA-256 为 `F8F72C59278A2A7EFB13B9B5917EAB596779372E4B159677A32B7538B82A9A2D`。Control/Treatment 指标均未形成；清理 9/9、READY 失败关闭和删除后 403 继续通过，无需恢复。比较拆分保持关闭，test/Acceptance 未读取，性能 Gate 未运行。
- 当前独立诊断只在既有 Milvus 搜索调用内部标注 `ROUTE_IDENTITY / QUERY_EMBEDDING / ANN_SEARCH / RESPONSE_CONTRACT` 四个稳定失败阶段，并由 Gate runner 映射为固定码；不新增请求、不输出异常文本、不改变 Milvus/Embedding 调用、默认 RRF 或质量变量。
- 第六次 Windows Run ID `phase3_comparison_dev_20260723_06` 在提交 `4771fe39ade2039a3251a6f8699a99fd1fb69b4d` 上于 `RUN_CONTROL` 返回 `ONLINE_MILVUS_ROUTE_IDENTITY_FAILED`；报告 SHA-256 为 `FCBD2B472E21AD5554FB3EBB0389CDE649FDFE80C4036C8BCC64A194FC4F70CB`，裁决 SHA-256 为 `A43F13F6E06F3D0C1B9ABA405529A31A82B754477292220D9EAC831CDCC6B779D`。Control/Treatment 指标仍未形成；清理 9/9、READY 失败关闭和删除后 403 通过，无需恢复。比较拆分保持关闭，test/Acceptance 未读取，性能 Gate 未运行。
- 当前独立修复只更正版本化 Milvus 集合的在线身份计数证明：不再把可能滞后的 collection stats 行数当作精确逻辑实体数，改为一次只返回 `chunk_id` 的逻辑快照，校验数量、唯一性和既有版本路由身份；provider、source fingerprint、schema、READY/owner 和完整版本行校验仍保留。未改变 ANN、Embedding、默认 RRF、比较变量、候选、阈值或 holdout。
- 第七次 Windows Run ID `phase3_comparison_dev_20260723_07` 在提交 `ff370b512f88b7d847fa17f080946aab4050048c` 上完成完整 Control/Treatment，报告以 `QUALITY_OR_COST_THRESHOLD_NOT_MET` 可信失败：四个冻结目标的 Control/Treatment 双侧 Top-3 命中均为 `0/4`，Recall@3 无增益，`nDCG@3` 下降 `0.017739`；固定 15 题为 `14/15` 且两分支边界不完全一致。报告 SHA-256 为 `3810CE9228F7CE9C65B5BE0E031F1F5CA6A471FA665BF5D8C12A6E7CAC6E01390`，裁决 SHA-256 为 `99530D236B8CA50B53DE18557C9D43C7BCC63695A3C98FC9DBA889B33CDAA036`，决定保持比较拆分关闭。
- `_07` 同时证明身份违规为 0、非目标 answerable 与 dev no-evidence 不退化、增量检索 P95 `24.101115 ms <= 50 ms`、拆分 P95 `0.12922 ms <= 5 ms`；这些通过项不能覆盖目标质量与固定 Canary 失败。清理 9/9、READY 失败关闭和删除后 403 通过，无需恢复；`test/Acceptance` 未读取，300 ms 性能 Gate 未运行。
- 完成阶段 3 第二个主要变量的复用评估、合同与默认关闭本地实现。现有项目和维护中的 Elasticsearch RRF、Milvus Grouping Search、Haystack DocumentJoiner、LangChain MMR 均不能直接满足融合后两条授权文档路由的 Top-3 覆盖合同；决定不新增依赖，复用现有 READY 路由、`RankedChunk` 和完整 RRF 顺序。
- `BILATERAL_COMPARISON_ROUTE_COVERAGE_TOP3_V1` 只在比较标记、恰好两个授权 READY 路由和 Top-3 下生效：两路各保留最高 RRF 候选，再按原顺序补足；分数、候选 20、RRF `k=60`、请求数和默认链路不变，任何不满足或异常回退原 RRF Top-3。该本地实现本身未运行在线 dev，不能写成质量增益。
- 第二变量的完整远程配对 dev Gate 直接参数化复用了既有私有输入包、隔离 owner 三文档 READY 生命周期、Control `0/4` 停止规则、独立裁决、9 路清理和 Windows PowerShell 5.1 入口；没有复制第二套 runner，也没有引入 Ragas、MLflow 或新服务。
- 用户已在提交 `28b8987641ebd2754c2676f144dfa3abf4cdc041` 运行 `phase3_comparison_route_coverage_dev_20260724_01`。选择器 4/4 `APPLIED`、3/4 改变 Top-3，但 Control/Treatment 双侧命中仍同为 `0/4`，宏观 Recall@3 同为 `0.145833`、nDCG@3 同为 `0.220967`，增益均为 0；固定 15 题为 `14/15`。报告 SHA-256 为 `C2758BE68E614D5E075595B34C2386FA200B7DE13358DF8DB5193CCAD69A6A19`，裁决 SHA-256 为 `7492DC7574A2176351DDEEBCDED80230D66216FA2C923BBB4713182945CE4797`，决定保持路由覆盖关闭。
- `_01` 同时证明身份违规为 0、关键非目标 Recall@3/nDCG@10 均不退化、选择器 P95 `0.049995 ms`、清理 9/9、READY 失败关闭和删除后 403；因此这是可信质量失败，无需恢复且不得重跑。报告和裁决落盘后，Windows PowerShell 汇总层因完整报告省略可选 `primary_error_code` 而在严格模式报错；该外层错误不影响既有报告、裁决或清理证明，本地仅将脱敏汇总字段改为缺失安全读取，不要求质量重跑。
- 用户首次复核该汇总修复时，验证清单自身失败：29 个 Python 测试为 `1 failure / 3 errors`，`check_powershell.ps1` 在 Windows PowerShell 5.1 参数默认绑定阶段取得空 `$PSScriptRoot`，手工 `ParseFile` 又使用相对路径而没有取得 AST，后续 helper/行为检查级联失败；末尾无条件打印的 `PASS` 无效。本地现将路径初始化移出参数默认值，并提供失败即停的版本化 Windows PowerShell 5.1 收口验证脚本，只验证提交、静态合同、绝对路径解析和可选字段行为，不运行质量 Gate、服务、私有输入或通用 Python 测试批次。
- 第二次 Windows 收口复核已精确快进到 `79861c6`，版本化脚本正确失败关闭，唯一错误为 Windows PowerShell 5.1 找不到 `PSScriptAnalyzer 1.25.0`；仍未运行质量、服务或私有输入。PSScriptAnalyzer 保持为 Mac 提交前静态 Gate，Windows 入口不安装外部模块，只运行系统内置 Parser 的绝对路径语法解析和严格模式 helper 行为检查。
- 用户已确认提交 `7764f3e0416706b98c5ea8d131a5525bc7f96f2e` 的版本化 Windows PowerShell 5.1 收口验证成功：系统内置 Parser 和严格模式 helper 行为均通过，且未运行质量、服务或私有输入。汇总修复的跨平台验证至此 `PASS_COMPLETE`，无需再次复核；路由覆盖质量失败、默认关闭、无需恢复、holdout 封存和独立性能债均不变。
- 比赛增强的下一个主 Gate 已完成轮子评估：直接复用本仓库 `claims[].text + citation_ids` 与授权 Evidence/Citation，窄适配用户既有 reading-agent 的确定性可靠性模式；现有相关性 Cross-Encoder 不作为蕴含器，Ragas/Haystack 只保留为后续离线评测候选，因此没有新增依赖、框架或服务。
- 本地 Claim–Evidence 核心现可校验请求内引用、数字锚点、高风险关系、核心重合和同单位数值冲突披露；支持安全限制语、删除无依据 Claim 后的显式部分回答，以及全部失败时保留 Evidence 卡片的 `DEGRADED`。公开 Answer Schema 与冻结 Prompt 身份均未改变。
- 该能力只达到 `LOCAL_CORE_READY_ONLINE_HARD_JUDGMENT_DEFERRED`：不包含知识库接入、前端、演示或远程运行，未读取 `test/Acceptance`，也不把确定性词面检查写成通用语义蕴含。最高方案阶段 3 仍为 `IN_PROGRESS`，阶段 4 仅记为 `PARTIAL`。
- `phase4-claim-evidence-candidate-intake-complete` 已原样接收成员 B PR #15 的三份候选资产并通过冻结私有 `dev` 对账：失败归因 `105/105`，Claim–Evidence `30/30`，关系为 `SUPPORTED=21 / PARTIALLY_SUPPORTED=1 / NOT_APPLICABLE=8`，`INPUT_MISSING=0`。评审者明确为 `member-b-ai-assisted`，候选未经过人工裁决，不晋升为最终真值。
- 现有确定性轮子在 21 条候选 `SUPPORTED` 上只保留 6 条，在人工终审谱系 225 个正例上只保留 110 条；这只证明高误杀风险，不产生 Precision、负例拒绝率或人工一致率。默认生成因此改为 `AUDIT_ONLY`，显式 enforcement 仅供测试和未来候选，在线硬裁决继续关闭。
- 已固定多语言 NLI 候选轮子 `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` 的 revision、snapshot、Evidence-premise/Claim-hypothesis 模板、标签顺序和正例保留门槛；Mac 仅以 Fake Scorer 完成合同测试，真实模型未在 Mac 运行。
- Windows PowerShell 5.1 RTX 4090 Gate 已形成可信质量失败：21 条候选 supported 仅保留 `9/21=0.428571`，225 个终审谱系正例仅保留 `124/225=0.551111`，均低于 `0.85`；组件 P95 为 `64.03166 ms`，质量失败不能由延迟通过覆盖。报告 SHA-256 为 `6f266edc0fa57b933260f3996585a53ac2dac065c13f472f7c8d1c5f94c7cf1e`，默认 `AUDIT_ONLY` 与在线硬裁决关闭不变。
- 首次 Windows NLI 尝试确认私有 ZIP 哈希正确，但在模型加载前因 tracked JSON 的 CRLF 检出被原始字节哈希误拒绝为 `NLI_CONFIG_HASH_DRIFT`。本地已复用 Phase 3 的 LF 规范化身份：tracked JSON/CSV 接受等价 CRLF，BOM、孤立 CR 和内容变化仍拒绝；私有 ZIP/JSONL 继续严格原始字节哈希。本次没有模型或质量结果。
- 私有诊断复跑在提交 `71c9f042c09b9d60e7922450a03714c41808eecc` 上完成，247/247 哈希 pair key、标签、概率和长度合同通过，预测 SHA-256 为 `c86747974470ecb4e6834de997a2ed649a3f8573f740ad7b5989ebcf56228b3a`。候选 supported 同语言保留 `6/7`，中文 Claim 对非中文 Evidence 仅 `3/14`；终审谱系同语言 `65/89`，跨语言 `59/136`。单/双 Chunk 接近且截断仅 7 个 group，诊断为模型跨语言与学术排版/领域失效为主，严格 NLI 标签语义未建立为次要问题。
- Codex 私有语义诊断完整复核 12 条候选漏判，其中 11 条 Evidence 直接表达 Claim、1 条标签口径可能偏宽；另一个 12 条高置信分层样本中 10 条直接蕴含、2 条上下文依赖或偏宽。该结果明确标为 AI 辅助诊断而非人工 NLI 金标，不得用于自动改写数据或估计总体标签错误率。
- Phase 4 Multi-Evidence Evidence Set 主 Gate 已完成：直接复用结构化 Claim、`citation_ids`、授权 Evidence/Citation 与 `claim_evidence.py`，一个 Claim 可形成一个或多个 Evidence 的确定性集合；集合级校验 owner、活动 document/version/chunk 身份、数值、单位、比较对象、限定条件和冲突，输出 `SUPPORTED_BY_EVIDENCE_SET / PARTIALLY_SUPPORTED / CONFLICTING_EVIDENCE / INSUFFICIENT_EVIDENCE`。
- 原绑定不足时，只允许从同一请求内加入同文档、同活动版本、双向邻接的最多一个 Chunk；加入必须提升确定性支持或冲突结论，并明确保持检索相关性分数不读、不改。默认继续 `AUDIT_ONLY`，不自动删除 Claim；公开 Answer/Evidence/Citation/Prompt、默认 RRF/Reranker 和 300 ms 性能债不变。

## 输入

- 最高依据：《个人学术空间 RAG 问答系统建设与测试方案》，身份与差距见 `docs/REQUIREMENTS_TRACEABILITY.md`；
- 仓库基线：`main` 上已通过的仓库 Harness 与简化 Git 流程；
- 已实现能力：本地 PDF 到 Answer API、公开 Fixture、三论文四路检索基线、原方案兼容合同/指标框架和风险驱动测试策略；
- 未完成能力：阶段 3 首个比较拆分变量和第二个路由覆盖变量均已在可信在线 dev Gate 失败并保持关闭；阶段 4 已接收 AI 辅助候选二审但尚缺人工裁决的正负 Claim–Chunk 真值，在线硬裁决关闭；正式 MinIO 适配、OCR、目标规模性能验收、知识库接入、前端和演示均不在当前责任边界；固定 Reranker 在当前 300 ms SLO 下不默认启用；
- 远程部署拓扑及 ES/Milvus/RRF 固定 Canary 已形成工程证据；结果接口、配置和最小 RRF 已完成，RRF 14/15 未超过 ES 14/15，不继续增加检索复杂度。

## 验收

- `make harness-validate` 必须通过，且必须由 Makefile 强制使用项目 `.venv`；
- `make storage-test` 必须覆盖迁移校验、owner scope、幂等映射、任务绑定、READY 双索引门禁、索引结果原子提交、并发修订号以及清理任务租约/重试状态；
- `make ingestion-test` 必须覆盖持久化重放、owner 隔离、幂等 Key 换内容阻断、解析失败恢复、ES/Milvus 版本索引补写与身份/载荷/向量漂移阻断、双索引单侧失败补偿和持久化物理清理恢复；
- `make retrieval-test` 必须覆盖 Elasticsearch 200/404 存在性判定、Milvus 版本生命周期传输和失败关闭；
- `make test` 必须覆盖合同、入库、检索、RAG、API、评测和仓库 Harness；
- 本地三论文 Harness 必须通过 15/15，且三类结果分别达到 9/9、3/3、3/3；
- `make sqlite-fts-fixture-smoke` 必须通过 6/6；
- `make vector-fixture-smoke` 和 `make rrf-fixture-smoke` 必须分别通过 6/6；
- 本地三论文向量基线必须如实记录 12/15，RRF 必须通过 15/15；
- `make formal-evaluation-fixture` 必须通过，且公开 4 条 Fixture 必须保持 `engineering_ready=false / lock_ready=false`；
- `make evaluation-contract-check` 必须通过；
- GPT 标注必须携带模型身份、Prompt 版本和温度，且不得担任仲裁或专家；
- 一致低风险题不得因流程惯性强制增加仲裁，Acceptance 与高风险题不得取消人工复核；
- `git diff --check` 必须通过；
- 不得出现被跟踪的 `runtime/`、PDF、`.env`、数据或存储目录；
- 仓库状态、能力清单和本文件必须一致。
- 最高方案文件名、`725` 行与 SHA-256 必须在需求追踪和机器状态中一致；
- `machine/phase_zero_scope_resource_slo.json` 必须通过仓库 Harness，且冻结目标不得写成已实测 SLO；
- 数据身份/生命周期合同必须通过 JSON Schema 与失败关闭语义测试；
- 不得将本地协调协议写成远程 PostgreSQL、真实 ES/Milvus 写入、持久化物理清理或在线权限切换已完成，不得将 Fake LLM 写成最高方案阶段 2 已完成。
- `make real-generation-canary` 必须使用固定模型摘要和 Prompt/解码配置，覆盖稳定回放、引用编号、`NO_EVIDENCE` 不调用模型与 403；公开 Fixture 结果不得写成远程 READY 实跑。
- `machine/phase3_entry_freeze.json` 必须保持入口时点的 4 个唯一 `dev` ID、单变量、`test/acceptance` 封存和独立性能债；`machine/phase3_comparison_dev_gate.json` 必须如实记录 `_07` 的在线 dev 失败、干净清理与关闭决定，不得出现 `test/acceptance` 结果。
- `machine/phase3_comparison_route_coverage_gate.json` 必须保持第二变量可信质量失败、默认关闭、无新依赖/请求、原候选与 RRF 分数、`test/Acceptance` 封存、旧 Run ID 不可复用和独立 300 ms Gate。
- `machine/phase4_claim_evidence_core_gate.json` 必须保持零新增依赖、公开 Answer Schema/Prompt 不变、确定性检查不冒充语义蕴含、全部无依据 Claim 失败关闭，以及知识库/前端/演示/远程/holdout 排除边界。
- `machine/phase4_multilingual_nli_candidate_gate.json` 必须保持 Mac Fake Scorer、远程 RTX 4090 用户运行、正例保留诊断、无人工负例不可测 Precision，以及在线硬裁决关闭边界。

## Git

- 默认分支：`main`；
- 当前 Repository Harness 提交从 `agent/add-repository-harness` 快进到 `main`；
- 成员 A 普通低风险任务通过本地门禁后建立独立本地提交；只有用户显式授权时才 push；
- 远程主机操作由用户按版本化清单亲自执行；高风险源码变更继续通过 PR；
- 用户显式授权推送后，本地 `main` 必须与 `origin/main` 指向同一提交；未授权时如实报告领先提交数。仅在 CI 配置、依赖、跨平台、高风险变更或异常状态时检查 GitHub Actions。

## Current boundary

最高方案阶段 0、阶段 1、阶段 2 已完成；阶段 3 仍为 `IN_PROGRESS`，阶段 4 为 `PARTIAL_MULTI_EVIDENCE_SET_LOCAL_READY`。两个阶段 3 变量均因无目标质量增益保持关闭；当前仓库节点为 `phase4-multi-evidence-set-local-ready`。确定性 EvidenceSet 已覆盖单/多 Evidence、身份、部分支持、冲突和最多一个同版本邻块，但只处于 `AUDIT_ONLY`，不冒充语义蕴含或人工金标。固定多语言 NLI 的质量失败和数据/模型诊断保持原结论，当前模型继续拒绝且不复跑或调门槛。当前评测边界为 `PHASE3_FIRST_TWO_VARIABLES_FAILED_DISABLED / PHASE4_MULTI_EVIDENCE_SET_LOCAL_READY_AUDIT_ONLY_NLI_REJECTED / TEST_ACCEPTANCE_NOT_READ_NOT_RUN`。默认 RRF、Reranker 关闭、查询拆分关闭、路由覆盖关闭和 300 ms 独立性能债均不变。

## Next gate

1. **本 Gate 已收口：** 不继续细分或调参 Multi-Evidence EvidenceSet；它保持本地 `AUDIT_ONLY`，不自动删除 Claim；
2. **NLI 分支停止：** 当前模型不再复跑、调阈值或用预测回写数据；只有未来明确选择语义 Judge 且先具备严格 pair-level 人工正负金标时才重新评估；
3. **下一比赛增强另选主变量：** 应选择能直接增加可展示 RAG 价值且不依赖知识库接入、前端或新人工金标的完整 Gate；
4. **债务分离：** `test/Acceptance` 继续封存，默认 RRF、Reranker、在线硬裁决和 300 ms 独立性能债保持不变。

## Prohibited shortcuts

- 不把父级知识库整理目录整体初始化为 Git 仓库；
- 不上传现有知识库数据、PDF、数据库、模型、运行时和本地配置；
- 不用即时通讯压缩包代替 GitHub 中的版本化源码交付；
- 仓库已由用户切换为公有；后续仍不得提交私有问题、Claim/Evidence 正文、PDF、运行时、凭据或本机路径。
