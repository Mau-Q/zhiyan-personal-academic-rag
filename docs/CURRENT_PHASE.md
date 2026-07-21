# Current Phase

## Status

`M0_COMPLETE / REPOSITORY_HARNESS_READY / M1_SQLITE_FTS5_BASELINE_READY / MEMBER_B_REMOTE_PENDING`

Phase ID：`m1-sqlite-fts5-baseline-ready`

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

## 输入

- 基线：`main` 上已通过的仓库 Harness 与简化 Git 流程；
- 已实现能力：本地 PDF 到 Answer API、公开 Fixture 评测、本地三论文词项重叠基线和 SQLite FTS5/BM25 持久化检索基线；
- 未完成能力：成员 B 远程准备、真实 Elasticsearch、Milvus 和模型接入；
- 本阶段固定合同、授权、题集、页码、`top_k` 和 Fake LLM，只新增 SQLite FTS5/BM25 这一项检索变量。

## 验收

- `python3 scripts/validate_harness_contract.py` 必须通过；
- `make test` 必须覆盖合同、入库、检索、RAG、API、评测和仓库 Harness；
- 本地三论文 Harness 必须通过 15/15，且三类结果分别达到 9/9、3/3、3/3；
- `make sqlite-fts-fixture-smoke` 必须通过 6/6；
- `git diff --check` 必须通过；
- 不得出现被跟踪的 `runtime/`、PDF、`.env`、数据或存储目录；
- 仓库状态、能力清单和本文件必须一致。

## Git

- 默认分支：`main`；
- 当前 Repository Harness 提交从 `agent/add-repository-harness` 快进到 `main`；
- 成员 A 普通低风险任务通过本地门禁后直接 push `main`；
- 成员 B 远程任务和高风险变更继续通过 PR；
- 推送后本地 `main` 必须与 `origin/main` 指向同一提交；仅在 CI 配置、依赖、跨平台、高风险变更或异常状态时检查 GitHub Actions。

## Current boundary

当前仓库 Harness 已建立，负责约束阶段、范围、验证和交付；RAG 评测 Harness 只负责用例运行。本地 SQLite FTS5/BM25 是已验证的真实持久化检索后端，但执行边界仍为 `LOCAL_API_SQLITE_FTS5_FAKE_LLM`。它不证明 Elasticsearch、Milvus、向量检索、远程部署或真实模型已完成。PDF、真实 Chunk、私有问题集、SQLite 索引和运行报告不得提交。

## Next gate

1. 成员 B 按 [Issue #9](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/9) 完成远程准备；
2. 远程拉取同一 `main` 提交运行全量测试、Fixture API 和 Fixture Harness；
3. 成员 A 固定当前本地三论文题集、页码、`top_k` 和 SQLite BM25 结果，下一阶段只新增一种向量检索；
4. 用同一题集比较词项重叠、SQLite BM25、向量、混合检索和重排，不一次改变多个变量；
5. 真实模型接入放在检索证据链稳定之后，单独评估答案正确性与引用一致性。

## Prohibited shortcuts

- 不把父级知识库整理目录整体初始化为 Git 仓库；
- 不上传现有知识库数据、PDF、数据库、模型、运行时和本地配置；
- 不用即时通讯压缩包代替 GitHub 中的版本化源码交付；
- 不在安全和权属审查前将仓库切换为公有。
