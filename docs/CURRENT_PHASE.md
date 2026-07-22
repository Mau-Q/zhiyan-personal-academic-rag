# Current Phase

## Status

`SOURCE_PHASE_0_COMPLETE / SOURCE_PHASE_1_IN_PROGRESS / REPOSITORY_HARNESS_READY / REPO_M0_COMPLETE / M1_LOCAL_RRF_BASELINE_READY / MVP_INITIAL_175_HUMAN_VALIDATED / MVP_175_REMOTE_SINGLE_BACKEND_BASELINES_COMPLETE / REMOTE_RETRIEVAL_BASELINE_READY / REMOTE_RRF_CANARY_COMPLETE_NO_GAIN`

Phase ID：`source-phase1-data-index-minimal-loop-in-progress`

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

## 输入

- 最高依据：《个人学术空间 RAG 问答系统建设与测试方案》，身份与差距见 `docs/REQUIREMENTS_TRACEABILITY.md`；
- 仓库基线：`main` 上已通过的仓库 Harness 与简化 Git 流程；
- 已实现能力：本地 PDF 到 Answer API、公开 Fixture、三论文四路检索基线、原方案兼容合同/指标框架和风险驱动测试策略；
- 未完成能力：远程 PostgreSQL 迁移与持久化 PDF 实跑、PDF/Chunk 运行存储、ES 版本写入远程复测、Milvus 版本写入器、持久化清理队列、在线 Alias/事实源权限门禁、目标规模性能验收、无证据校准、安全策略层和真实生成模型；
- 远程部署拓扑及 ES/Milvus/RRF 固定 Canary 已形成工程证据；结果接口、配置和最小 RRF 已完成，RRF 14/15 未超过 ES 14/15，不继续增加检索复杂度。

## 验收

- `make harness-validate` 必须通过，且必须由 Makefile 强制使用项目 `.venv`；
- `make storage-test` 必须覆盖迁移校验、owner scope、幂等映射、任务绑定、READY 双索引门禁、索引结果原子提交和并发修订号；
- `make ingestion-test` 必须覆盖持久化重放、owner 隔离、幂等 Key 换内容阻断、解析失败恢复、ES 隐藏版本索引补写/漂移阻断、双索引单侧失败补偿和先失效后清理；
- `make retrieval-test` 必须覆盖 Elasticsearch 200/404 存在性判定与非 404 失败关闭；
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

## Git

- 默认分支：`main`；
- 当前 Repository Harness 提交从 `agent/add-repository-harness` 快进到 `main`；
- 成员 A 普通低风险任务通过本地门禁后直接 push `main`；
- 远程主机操作由用户按版本化清单亲自执行；高风险源码变更继续通过 PR；
- 推送后本地 `main` 必须与 `origin/main` 指向同一提交；仅在 CI 配置、依赖、跨平台、高风险变更或异常状态时检查 GitHub Actions。

## Current boundary

最高方案阶段 0 已完成，当前进入阶段 1。当前最宽本地问答执行边界仍为 `LOCAL_API_RRF_HYBRID_FAKE_LLM`；评测执行边界为 `MVP_INITIAL_175_HUMAN_VALIDATED / ES_85_OF_175 / MILVUS_109_OF_175 / THREE_CHUNK_STRATEGIES_BM25_15_OF_15_VECTOR_12_OF_15_NO_WINNER / RRF_175_DEFERRED / ENGINEERING_ITEMS_500_FOUR_BACKENDS_COMPLETE / REMOTE_RRF_CANARY_14_OF_15_NO_GAIN`。PostgreSQL 最小事实源、持久化 PDF 准备、双索引生命周期协调和 ES 隐藏版本索引写入器已在本地就绪；远程迁移/实跑、Milvus 版本写入器、持久化清理队列、在线 Alias/事实源权限门禁、目标规模性能和真实生成模型尚未完成。运行时私有数据继续不进入 Git。

## Next gate

1. **PostgreSQL 最小事实源：** 本地 Schema、迁移器与适配器已完成；下一步由用户在隔离远程 PostgreSQL 应用迁移并返回脱敏证据；
2. **索引闭环：** 本地协调和 ES 隐藏版本索引写入器已完成；下一步实现 Milvus 版本写入器及持久化清理队列，再接在线 Alias/READY 路由；
3. **兼容迁移：** 持久化准备已将 `document_version_id/owner_id` 适配到 legacy Chunk 字段；在线 Answer API 仍待切换到 PostgreSQL READY 权限门禁；
4. **性能与复杂度：** 闭环完成后再按冻结规模验收性能；当前不跑 175 题 RRF、不增加重排或真实 LLM。

## Prohibited shortcuts

- 不把父级知识库整理目录整体初始化为 Git 仓库；
- 不上传现有知识库数据、PDF、数据库、模型、运行时和本地配置；
- 不用即时通讯压缩包代替 GitHub 中的版本化源码交付；
- 不在安全和权属审查前将仓库切换为公有。
