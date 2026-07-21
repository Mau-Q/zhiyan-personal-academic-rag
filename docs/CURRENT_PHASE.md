# Current Phase

## Status

`STAGE_0 / CONTRACTS_DRAFTED / REVIEW_PENDING`

## Completed

- 建立独立源码仓库目录；
- 建立源码、数据、密钥和运行时边界；
- 建立私有优先、审查后公开的仓库策略；
- 记录双人离线/在线并行开发边界；
- 创建 Private GitHub 仓库：<https://github.com/Mau-Q/zhiyan-personal-academic-rag>；
- 推送并建立远程 `main` 基线；
- 仓库所有者确定负责成员 A 的在线链路；
- 第二位成员已由仓库所有者邀请；
- 从本地语料筛选 8 篇 PDF，并只提交元数据、页数和 SHA-256；
- 建立三个静态合同、RAG Answer、Trace、错误码、SSE 和契约测试草案。

## Pending input

第二位成员需接受邀请，并与成员 A 共同评审 V1 合同。样本文献只能用于本地工程验证，PDF 本体不得提交。

## Next gate

1. 通过 Draft PR 评审 V1 合同；
2. GitHub Actions 契约测试通过；
3. 双方分别实现一个最小合同消费者并验证同一 Fixture；
4. 合并合同后进入阶段 1 两条链路并行开发；
5. 在首个里程碑进行一次集中联调。

## Prohibited shortcuts

- 不把父级知识库整理目录整体初始化为 Git 仓库；
- 不上传现有知识库数据、PDF、数据库、模型、运行时和本地配置；
- 不用即时通讯压缩包代替 GitHub 中的版本化源码交付；
- 不在安全和权属审查前将仓库切换为公有。
