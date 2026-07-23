# Product Decisions

| ID | 状态 | 决策 | 影响 |
|---|---|---|---|
| PD-001 | ACCEPTED | 本地优先完成可审计 RAG 链路 | 远程基础设施不是本地 M0/M1 的前置条件 |
| PD-002 | ACCEPTED | 合同优先，授权过滤失败关闭 | API、Schema、错误码和权限语义不得由实现临时扩宽 |
| PD-003 | ACCEPTED | GitHub 是源码交付来源 | 不使用即时通讯压缩包作为最终版源码 |
| PD-004 | ACCEPTED | 仓库保持 Private，公开需单独过门禁 | 当前无开源许可，不默认授予再分发权利 |
| PD-005 | SUPERSEDED_BY_PD-027_AND_PD-030 | 成员 A 负责本地核心，成员 B 负责远程准备 | 远程操作现由用户亲自执行；成员 B 改为通过独立 PR 准备离线评测候选标签 |
| PD-006 | SUPERSEDED_BY_PD-011 | 成员 A 普通低风险任务通过本地门禁后直接推送 `main` | 直推决策保留，固定检查 CI 的部分由 PD-011 替代 |
| PD-007 | ACCEPTED | Fixture/Fake 与真实索引、真实模型严格分离 | 评测和演示输出必须携带执行边界 |
| PD-008 | ACCEPTED | 仓库 Harness 与 RAG 评测 Harness 分离 | 前者约束开发过程，后者比较问答结果 |
| PD-009 | ACCEPTED | 真实基础设施逐项接入、逐项验收 | 不在一个 PR 同时切换数据库、检索和模型 |
| PD-010 | ACCEPTED | 成员 B 远程任务和高风险变更保留 PR | 合同破坏、安全、真实数据、公网暴露和大型跨模块变更不得直推 |
| PD-011 | SUPERSEDED_BY_PD-028 | 普通低风险直推以本地 Harness、受影响测试、diff 检查和远程 SHA 一致为完成门禁 | 本地门禁和条件检查 Actions 的原则保留；默认推送规则由 PD-028 替代 |
| PD-012 | ACCEPTED | 《个人学术空间 RAG 问答系统建设与测试方案》是最高层需求、目标架构和验收依据 | 仓库必须维护身份哈希和需求追踪，Harness 不得缩小最高方案范围 |
| PD-013 | ACCEPTED | 最高方案阶段 0～5 与仓库内部 M0/M1 分开记录 | 作出决策时方案阶段 0 为 `IN_PROGRESS`；仓库 `M0_COMPLETE` 只证明最小工程链路，后续阶段变化另记新决策 |
| PD-014 | SUPERSEDED_BY_PD-022 | 3 论文 15 题保留为固定工程 Canary，不替代 200～500 条初始评测和 800～1500 条正式验收规模 | Canary 定位保留；初始集规模和层级由 PD-022 替代 |
| PD-015 | ACCEPTED | 本地 BGE-M3 精确余弦使用 `0.50` Canary 阈值，SQLite BM25 与向量按候选 20、`k=60` 做 RRF；当前暂缓重排 | 参数只用于固定本地基线，生产阈值和 ANN 参数等待扩展评测与远程资源；没有证据增益不增加重排复杂度 |
| PD-016 | SUPERSEDED_BY_PD-017 | 正式检索评测 V1 目标固定为 500 条，`dev/test/acceptance=60/20/20`，使用泄漏组、双人独立标注、仲裁和专家复核 | 保留原方案兼容框架，不再作为近期工程推进的强制门禁 |
| PD-017 | SUPERSEDED_BY_PD-018 | 后续阶段采用风险驱动的最小充分测试；默认建立 80 题工程基线 | 用户澄清降复杂度针对人工评审流程，不降低 500 题覆盖规模 |
| PD-018 | SUPERSEDED_BY_PD-022 | 保留 500 题，GPT 承担候选生成和低风险初标；低风险 `dev/test` 人工抽检 10%～20%，Acceptance 单人确认，冲突才仲裁，专业高难题才专家复核 | 500 题继续作为工程候选池/稳定迭代证据，不再充当 MVP 初始人工校验集 |
| PD-019 | ACCEPTED | 固化 ES/Milvus 带名次与原始分数的共用候选接口和无密钥配置；基于固定 Canary 失败完全互补的证据实现最小远程 RRF | 融合只使用名次，不直接比较 BM25/COSINE 原始分数；本地 Fixture 就绪不等于远程 RRF Canary 完成 |
| PD-020 | ACCEPTED | 仓库门禁统一由 Makefile 强制使用项目 `.venv`，禁止静默回退到系统 Python | macOS 使用 `.venv/bin/python`，Windows 使用 `.venv/Scripts/python.exe`；虚拟环境缺失时明确失败 |
| PD-021 | ACCEPTED | 远程 ES+Milvus RRF Canary 为 14/15，与 ES 单路持平；保留已验证适配器，不调参、不晋级默认策略、不增加重排 | Top-3 候选并集互补未转化为融合后净增益；唯一失败和冻结目标按真实结果保留 |
| PD-022 | SUPERSEDED_BY_PD-023 | 按旧版最高方案将评测分为 150～250 条人工校验 MVP 初始集、约 500 条稳定迭代集和 800～1500 条正式验收集；MVP 从现有 500 题候选池确定性选出 175 条 | 人工谱系边界保留；初始集规模和当前门禁由 PD-023 替代 |
| PD-023 | ACCEPTED | 最新最高方案只覆盖上传/收藏后进入个人库的论文，以 `owner_id` 为目标权限核心，并将 175 题固定为 MVP 初始资产 | 175 题人工校验及 ES/Milvus 单路 Baseline 已完成；当时阶段 0 的剩余项是三种 Chunk Baseline 和范围/资源/SLO 收口，不跑 175 题 RRF、不增加重排或真实 LLM |
| PD-024 | ACCEPTED | 三种 Chunk 策略在同一三论文、15 题、`top_k=3`、SQLite BM25 和 BGE-M3 配置下完成受控对比 | 每种策略 BM25 15/15、BGE-M3 12/15，且失败集存在互换；不宣布胜者、不切换默认、不调参或引入重排 |
| PD-025 | ACCEPTED | 阶段 0 冻结单用户个人库的 500 篇标称/1000 篇验证上界、0.2 QPS、问答并发 2、入库并发 1、单台既有主机预算及后续 SLO 目标 | 范围/资源/SLO 子门禁完成；冻结值是待验证目标，不冒充目标规模性能、真实 LLM 延迟或 PostgreSQL 生命周期已达标；当时阶段 0 仍需冻结数据身份与生命周期语义 |
| PD-026 | ACCEPTED | `paper_id ↔ document_id` 映射按 `owner_id` 隔离并显式存储；内容变化创建不可复用的 `document_version_id`；只有解析、Chunk、ES、Milvus 全部就绪且未删除/过期的版本才能 `READY` | 阶段 0 完成并进入阶段 1；现有 V1 字段保持兼容，PostgreSQL 表、适配器、索引对账和失效清理留在阶段 1 实现 |
| PD-027 | ACCEPTED | 后续远程主机迁移、部署和验证改由用户亲自操作 | 代理准备版本化脚本和完整命令，只根据用户返回的脱敏原始输出判定；不再以成员 B 执行作为后续门禁 |
| PD-028 | ACCEPTED | “下一步/进行/继续”默认完成一个端到端本地门禁并建立独立本地提交；只有用户显式授权时才推送 | 同一门禁内不重复确认；一次只改变一个主要边界；远程节点、破坏性动作、重大分叉、合同破坏或无关脏改动时停止自动推进；Actions 继续按风险条件检查 |
| PD-029 | ACCEPTED | 阶段 1 在线路由以 PostgreSQL `READY` 解析每个文档版本的确定性 ES Index 与 Milvus Collection，不把外部 Alias 作为第二事实源 | ES Alias 可聚合多个 Index，但 Milvus Alias 只能指向一个 Collection；多文档请求按每版本双路召回后统一 RRF，任何 PostgreSQL、身份、活动状态或物理路由无法证明时失败关闭 |
| PD-030 | ACCEPTED | 成员 B 在阶段 1 期间只通过独立 Draft PR 准备阶段 2～4 的 `dev` 评测候选标签，不再操作远程主机或修改核心链路 | 首个任务固定为 105 题失败归因和 30 题 Claim–Evidence 第二审；只提交 ID 与枚举，不接触 `test/acceptance`，PR 不自动成为最终真值或阶段完成证据 |
| PD-031 | ACCEPTED | 阶段 1 MVP 使用可替换的 `filesystem_v1` 私有对象根目录保存 PDF，PostgreSQL 保存对象定位与不可变 Chunk 快照；正式 MinIO 适配保持独立 | 不新增对象存储 SDK 依赖，不把 PDF 字节塞入 PostgreSQL，也不把 Milvus 自带 MinIO 冒充应用对象存储；在线 Answer API 只消费 PostgreSQL READY 版本的持久化 Chunk 快照 |
| PD-032 | ACCEPTED | 固定 Reranker 复用 `sentence-transformers.CrossEncoder`，仓库继续控制模型/snapshot 身份、冻结候选、指标和去留；本地 `test=100` 质量门通过但默认路由不变 | 只在目标 Windows RTX 4090 复用同一配置完成 P95 后作最终启用/回退；不得同时调 Embedding、RRF、候选、Prompt 或生成模型 |
| PD-033 | ACCEPTED | 通用组件通过窄适配器逐项复用，不引入第二套业务事实或全栈 RAG 主链 | PyMilvus 已采用；Elasticsearch helper、Docling、OpenTelemetry、Ragas 和 Alembic 按 `docs/COMPONENT_REUSE_ROADMAP.md` 的独立触发条件后置，Temporal 和全栈框架当前不接管核心链路 |

新增或改变已接受决策时，必须记录新 ID 或明确替代关系，不能只在聊天中覆盖本文件。
