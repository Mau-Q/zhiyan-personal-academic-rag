# Changelog

本文件只记录仓库中已经提交的工程变化；远程运行、正式验收和人工评测结果仍以
`docs/CURRENT_PHASE.md`、版本化 Runbook 与脱敏证据为准。

## Unreleased

No changes yet.

## 0.1.0 — 2026-08-30

### Reliability and security hardening

- 让 HTTP `ErrorV1.request_id` 对每次 403/422 等错误响应唯一，同时保持正常回答的
  确定性 `request_id/trace_id` replay identity。
- 增加恶意问题和 Evidence 的消息边界回归：不可信内容只能进入固定的 `user` message，
  不会由主机代码转换为额外的 `system` 或其他 Chat message。
- 为应用自行创建的 Embedding Provider 增加 FastAPI lifespan 清理；索引/模型身份校验
  初始化失败时也执行清理。外部注入的 Provider 仍由调用方管理。

### Performance evidence

- 保留 Ollama HTTP/1.1 最多两条连接的有界复用实现。
- Windows RTX 4090 固定 30 样本 V1 Gate 的 Run 16/17 均通过：combined P95 分别为
  `287.73689 ms` 和 `292.114209 ms`。
- Run 16/17 只证明固定样本 Gate 在对应远程运行中的通过，不证明生产容量、正式
  Acceptance 或所有负载下的 SLO；300 ms 性能债和容量验证边界仍单独记录。

### Compatibility boundary

- 本轮未改变公开 API Schema、Prompt 身份、默认 RRF、candidate top-20、final top-3、
  ACL、READY、Citation、EvidenceSet `AUDIT_ONLY` 或失败关闭语义。
- 未新增运行时依赖、跨请求缓存、真实数据或远程服务；NLI/LLM Judge、前端、Agent API
  和正式用户验收继续后置。

## Release notes policy

`v0.1.0` 是一个公开的工程基线 Tag，不是 production-ready 声明。后续变化先进入
`Unreleased`，再经过本地门禁、公开材料审查和适用的远程/验收证据后发布。许可证见
[`LICENSE`](LICENSE)；第三方归属见 [`docs/THIRD_PARTY_NOTICES.md`](docs/THIRD_PARTY_NOTICES.md)。
