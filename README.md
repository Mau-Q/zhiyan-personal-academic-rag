# 智研个人学术空间 RAG 问答系统

本仓库用于建设面向个人论文、个人文献库、研究目录及授权公共知识库的证据约束型 RAG 问答系统。

系统必须完成以下可审计链路：

```text
授权文献范围
→ PDF 入库与版本管理
→ 章节、页码和 Chunk
→ Elasticsearch + Milvus 混合检索
→ 融合、去重和重排
→ 证据上下文
→ 受证据约束的生成
→ 引用校验或证据不足拒答
→ PDF 原文定位
→ Trace、反馈和评测闭环
```

## 当前状态

当前阶段为 `STAGE_0 / CONTRACTS_DRAFTED / REVIEW_PENDING`：成员 A 已确定，协作者已邀请，首批合同、Fixture 和本地样本文献清单已进入评审。

- GitHub：<https://github.com/Mau-Q/zhiyan-personal-academic-rag>
- 下一门禁：[`docs/CURRENT_PHASE.md`](docs/CURRENT_PHASE.md)
- 阶段 0 范围：[`docs/STAGE_0_SCOPE.md`](docs/STAGE_0_SCOPE.md)
- 合同入口：[`contracts/README.md`](contracts/README.md)

## 双人开发边界

- 成员 A：在线查询、RAG 回答和系统集成；
- 成员 B：离线入库、索引和基础设施；
- 双方通过 `ChunkRecordV1`、`AuthorizedScopeV1`、`IndexVersionV1` 三个版本化静态合同交接。

## 仓库边界

本仓库只保存源码、合同、测试、配置样例和可公开 Fixture。以下内容不得提交：

- 真实密钥和 `.env`；
- 私有论文、用户上传文件和未授权数据；
- PostgreSQL dump、live data 和索引目录；
- 模型权重、虚拟环境、依赖缓存和运行日志；
- 当前知识库整理目录中的大型压缩包和 4090 混合部署包。

详细规则见 [`docs/REPOSITORY_POLICY.md`](docs/REPOSITORY_POLICY.md)。

## 合同验证

本地需要 Python 3.11+ 和 `jsonschema`：

```bash
python3 -m pip install 'jsonschema>=4.23,<5'
make contract-test
```

验证只读取仓库内的 Schema、示例和人工 Fixture，不访问远程模型或生产数据。

## 计划目录

```text
backend/
├── contracts/
├── ingestion/
├── storage/
├── indexing/
├── retrieval/
├── rag/
├── api/
└── evaluation/
frontend/
deploy/
docs/
tests/
```

## 许可证

公开许可证尚未确定。在完成代码归属、第三方依赖和竞赛公开规则审查前，本仓库保持私有，不授予仓库访问者超出适用法律默认范围的使用许可。
