# Current Phase

## Status

`REPOSITORY_BOOTSTRAP / LOCAL_COMPLETE / REMOTE_CREATION_PENDING_AUTH`

## Completed

- 建立独立源码仓库目录；
- 建立源码、数据、密钥和运行时边界；
- 建立私有优先、审查后公开的仓库策略；
- 记录双人离线/在线并行开发边界；
- 准备 Git 初始化所需基础文件。

## Current blocker

GitHub CLI 账号 `Mau-Q` 的现有令牌无效。远程私有仓库创建和首次推送必须在重新认证后执行。

## Next gate

1. 完成 `gh auth login -h github.com`；
2. 创建私有仓库 `zhiyan-personal-academic-rag`；
3. 推送本地 `main`；
4. 邀请第二位成员；
5. 建立首批 Issue 与 Milestone；
6. 冻结三个静态合同后进入阶段 0 实施。

## Prohibited shortcuts

- 不把 `/Users/rui/knowledge base` 整体初始化为 Git 仓库；
- 不上传现有知识库数据、PDF、数据库、模型、运行时和本地配置；
- 不用即时通讯压缩包代替 GitHub 中的版本化源码交付；
- 不在安全和权属审查前将仓库切换为公有。
