# Current Phase

## Status

`M0_COMPLETE / LOCAL_PDF_RAG_COMPLETE / MEMBER_B_REMOTE_PENDING`

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

## Current boundary

当前本地 M0 已完成。远程主机、数据库、向量库和真实模型不是已完成链路的前置条件。样本文献只能用于本地工程验证，PDF 和生成的真实 Chunk 本体不得提交。

## Next gate

1. 成员 B 按 [Issue #9](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/9) 完成远程准备；
2. 远程拉取同一 `main` 提交运行 43 项测试和 Fixture API；
3. 成员 A 保持本地链路稳定，不在远程结果返回前引入真实基础设施；
4. 远程基线通过后，为真实索引、模型接入和评测分别建立下一阶段任务；
5. 数据库、向量库和模型接入分别验收，避免一次 PR 同时改变多个边界。

## Prohibited shortcuts

- 不把父级知识库整理目录整体初始化为 Git 仓库；
- 不上传现有知识库数据、PDF、数据库、模型、运行时和本地配置；
- 不用即时通讯压缩包代替 GitHub 中的版本化源码交付；
- 不在安全和权属审查前将仓库切换为公有。
