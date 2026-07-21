# Current Phase

## Status

`STAGE_0 / MEMBER_A_CONSUMER_COMPLETE / MEMBER_B_PENDING`

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
- 成员 A 的授权过滤、确定性检索、Fake LLM、Evidence、Citation 和 `NO_EVIDENCE` 已通过 25 项测试。

## Current boundary

当前没有外部阻塞。V1 是成员 A 确认的初始基线；成员 B 可在实现中提出兼容性补充。样本文献只能用于本地工程验证，PDF 本体不得提交。

## Next gate

1. 成员 B 完成 [Issue #4](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/4) 的 PDF 到 `ChunkRecordV1`；
2. 使用成员 B 的输出替换测试 Fixture，不修改成员 A 的合同消费逻辑；
3. 通过 [Issue #5](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/5) 完成一次集中联调；
4. 验证回答、拒答、越权阻断和引用页码；
5. 最小链路通过后关闭 M0 并进入下一阶段。

## Prohibited shortcuts

- 不把父级知识库整理目录整体初始化为 Git 仓库；
- 不上传现有知识库数据、PDF、数据库、模型、运行时和本地配置；
- 不用即时通讯压缩包代替 GitHub 中的版本化源码交付；
- 不在安全和权属审查前将仓库切换为公有。
