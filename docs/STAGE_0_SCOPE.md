# 阶段 0 范围与门禁

## 1. 目标

建立双方可以独立消费的 V1 合同，使成员 A 能基于确定性 Fixture 开发在线问答链路，成员 B 能基于本地 PDF 开发离线入库链路。

## 2. 已确定角色

- 成员 A：仓库所有者，负责在线查询、RAG Answer、引用/拒答和后续前端集成；
- 成员 B：已加入 GitHub，负责 PDF 解析、Chunk、索引和一致性；
- 双方共同维护 `contracts/` 和 `tests/contracts/`。

## 3. 首个 MVP

只验收一条完整、可审计的最小链路：

```text
单篇授权 PDF
-> 解析与页码映射
-> ChunkRecordV1
-> Fixture 或测试索引
-> 授权范围过滤
-> 检索与上下文
-> Fake LLM
-> COMPLETED 或 NO_EVIDENCE
-> 引用定位到原 PDF 页码
```

## 4. 本阶段非目标

- 不接入生产数据库或公网部署；
- 不依赖远程 4090 才能运行合同测试；
- 不建设微服务、多 Agent、复杂查询改写或多跳推理；
- 不上传 PDF、数据库、模型权重或真实用户数据；
- 不以模型生成内容作为检索证据；
- 不承诺 200～500 条正式评测集已完成。

## 5. 样本文献

`fixtures/sample-corpus-v1.json` 登记 8 篇已完成本地 PDF 可读性检查的 arXiv 文献。PDF 本体不进入 Git；清单中的 `redistribution_allowed=false` 是仓库交付边界，不是对论文版权状态的法律结论。

正式联调前，成员 B 应在本地逐项核对 SHA-256。哈希不匹配的文件不得沿用同一文档版本。

## 6. 完成门禁

- [x] 独立 Private 仓库和远程 `main` 已建立；
- [x] 双人角色已确定，协作者已邀请；
- [x] 三个静态合同具备 JSON Schema 和示例；
- [x] RAG Answer、Trace、错误码和 SSE V1 已形成文件；
- [x] 确定性 Chunk Fixture 已建立；
- [x] 8 篇本地联调 PDF 已登记，不上传原文件；
- [x] GitHub Actions 中契约测试通过；
- [x] 成员 A 确认初始 V1 基线并合并 PR #1；
- [ ] 成员 A 与成员 B 分别以自己的最小消费者验证同一 Fixture。

两名成员现在可以按同一基线并行实现。普通模块 PR 不强制互审；只有 `contracts/` 的破坏性变更或跨成员边界变化需要另一方确认。

## 7. GitHub 协作入口

- [Merged PR #1：阶段 0 合同基线](https://github.com/Mau-Q/zhiyan-personal-academic-rag/pull/1)
- [Milestone M0：合同冻结与最小链路](https://github.com/Mau-Q/zhiyan-personal-academic-rag/milestone/1)
- [Issue #2：共同合同评审](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/2)
- [Issue #3：成员 A 在线 Fixture 消费者](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/3)
- [Issue #4：成员 B PDF 到 ChunkRecordV1](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/4)
- [Issue #5：首次单篇论文集中联调](https://github.com/Mau-Q/zhiyan-personal-academic-rag/issues/5)
