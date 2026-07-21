# GitHub 仓库与交付策略

## 1. 仓库定位

- 仓库名称：`zhiyan-personal-academic-rag`
- 初始可见性：Private
- 默认分支：`main`

GitHub 是本项目源码、合同、测试、Issue、Pull Request、Tag 和 Release 的唯一可信来源。即时通讯工具只用于通知，不传递“最终版源码”。

## 2. 允许提交

- 后端、前端和部署源码；
- Schema、migration、ES Mapping 和 Milvus Collection 定义；
- API、事件、错误码和三个静态合同；
- 单元、契约、集成和评测代码；
- 不含真实论文内容的人工 Fixture；
- `.env.example`；
- 开发、部署、测试和验收文档；
- 可重复生成交付包的脚本。

## 3. 禁止提交

- `.env`、API Key、数据库密码和签名凭据；
- 私有 PDF、用户上传文件和未授权专业数据库内容；
- PostgreSQL dump、SQLite live data、ES/Milvus/MinIO 数据目录；
- 模型权重、Embedding 缓存和训练 checkpoint；
- `.venv`、`node_modules`、`.local_packages` 和平台二进制运行时；
- 日志、Trace 正文、私有问题和未脱敏评测数据；
- 当前大型整理目录及其原始 ZIP、知识库数据和 4090 部署包。

## 4. 分支与合并

- 成员 A 使用在线检索、RAG 和前端相关功能分支；
- 成员 B 使用入库、索引和部署相关功能分支；
- 每项任务建立独立分支和 Pull Request；
- 不直接向 `main` 推送业务实现；
- 每个 PR 包含测试结果和必要文档更新；
- `contracts/` 破坏性变更必须升级版本并由双方确认；
- 每个里程碑只进行一次集中联调。

## 5. 版本与交付

阶段版本使用语义化 Tag，例如：

```text
v0.1.0-contracts
v0.2.0-single-paper-mvp
v0.3.0-personal-library-mvp
v1.0.0
```

最终交付包含仓库地址、Release/Tag、commit SHA、部署说明、测试与验收报告，以及外部数据、模型、运行时清单和 SHA-256。

如需 ZIP，必须由脚本从干净 Tag 生成，不从个人工作目录手工打包。

## 6. 公开门禁

仓库初始保持私有。切换为 Public 前必须全部通过：

1. 竞赛、学校和团队规则允许公开；
2. 所有贡献者同意代码公开；
3. Git 历史中不存在密钥、密码、私有路径和内部地址；
4. 不含真实论文、数据库、模型和未授权第三方材料；
5. 完成第三方许可证清单与兼容性审查；
6. 选择并添加适当的开源许可证；
7. Secret、路径、版权和大文件扫描通过；
8. README 只描述已实现并验证的能力；
9. Fake、Fixture、降级和真实结果边界清楚；
10. 从干净 clone 完成构建和测试复验。
