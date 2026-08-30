# 简历级技术案例：可追溯的个人学术空间 RAG 核心

> 本文用于简历、技术面试和项目介绍。所有数字只覆盖文中列出的冻结输入与 Gate，
> 不应扩展为生产容量、正式用户验收或通用问答质量结论。

## 一句话项目描述

这个项目面向个人论文库，构建了一条 owner-scoped、版本化、可引用、可拒答、可清理的
RAG 核心链路：PostgreSQL 维护 READY/ACL 事实，Elasticsearch 与 Milvus 并行召回，
RRF 负责融合；真实模型只消费完成身份重验的 Evidence，文档删除后阻断旧证据继续可见。

## 可直接用于简历的中文表述

- 设计并实现个人学术文献 RAG 核心：以 PostgreSQL owner/READY 为事实源，接入
  Elasticsearch BM25、Milvus/BGE-M3、rank-only RRF（candidate top-20、`k=60`、
  final top-3）和 Citation/Evidence 审计，形成可重放、可失败关闭的在线链路。
- 为 PDF/Chunk、不可变 document version 和双索引 READY 定义统一身份；删除时先将
  PostgreSQL 版本置为 `INACTIVE`，再清理 Elasticsearch、Milvus 和 runtime snapshot，
  防止索引残留重新暴露已撤权证据。
- 在 Windows RTX 4090 固定 30 样本在线 Gate 中定位延迟瓶颈：单共享 Ollama HTTP/1.1
  连接限制了 Query Embedding 与 READY 身份校验的重叠；改为最多两条连接的线程安全有界池，
  在不引入跨请求缓存、不改变检索参数的前提下，将 combined P95 从 Run 15 的
  `364.802135 ms` 降至 Run 16/17 的 `287.73689/292.114209 ms`。
- 加固服务可靠性：错误响应使用唯一 `request_id`，正常回答保留确定性 replay identity；
  恶意问题/Evidence 不会改变 Chat message role；应用自行创建的 Embedding Provider
  在关闭和初始化失败时清理。

## English resume bullets

- Built an owner-scoped academic RAG core with PostgreSQL READY/ACL truth, parallel
  Elasticsearch BM25 and Milvus/BGE-M3 retrieval, rank-only RRF, citation traceability,
  fail-closed refusal, and post-deletion physical cleanup.
- Designed immutable document/version/chunk identity checks so generated answers consume
  only authorized Evidence revalidated against the active READY route; preserved
  `candidate_top_k=20`, RRF `k=60`, and final top-3 boundaries.
- Diagnosed online latency on a Windows RTX 4090 Gate and replaced a serialized shared
  Ollama HTTP/1.1 connection with a bounded two-connection pool; fixed-input combined P95
  improved from `364.802135 ms` to `287.73689/292.114209 ms` across two confirmation runs.
- Added reliability guards for unique HTTP error correlation IDs, deterministic replay IDs for
  successful answers, untrusted prompt-message boundaries, and application-owned provider
  shutdown cleanup without changing the public API schema.

## 技术面试叙事

### 问题

普通 RAG Demo 容易把“索引中存在”当成“用户可以访问”，把模型输出当成答案真值，或在
删除文档后仍返回旧索引内容。本项目首先解决身份、权限、版本和生命周期一致性，再讨论
召回和生成质量。

### 关键设计

1. **事实源单一：** PostgreSQL 决定 owner、活动版本和 READY；ES/Milvus 只提供可重建的
   检索结构。
2. **证据最小化：** 生成模型只接收当前请求内、通过 ACL/READY 和候选身份重验的 Evidence。
3. **故障分类：** 合法范围无证据返回 `NO_EVIDENCE`；越权/失活/未就绪返回 403；生成或
   Citation 门禁失败保留证据卡并返回 `DEGRADED`。
4. **可逆实验：** Reranker 为可选非默认组件；RRF、候选边界、缓存边界和失败语义不因
   单次质量或性能结果被悄然改变。

### 性能实验的工程判断

Run 15 使用单共享连接。Query Embedding 本身较快，但 READY 物理验证的墙钟时间上升，
说明连接复用可能串行化了原本可以重叠的请求。后续只把连接池上限改为 2，端点、模型、
输入、缓存边界和错误语义均保持不变。Run 16/17 连续通过固定 `300 ms` combined P95
Gate，因此保留该实现；这两次结果仍不等于生产容量或正式 SLO 证明，也不值得继续做同
一变量的无信息重跑。

## 证据边界

- Run 15/16/17 是固定输入、固定配置的远程性能实验；Run 16/17 的通过结论只覆盖该
  Gate，不覆盖生产容量、长时间稳定性或完整用户 Acceptance。
- 远程服务和 RTX 4090 结果来自版本化 Windows 执行清单与脱敏报告；仓库只保存方法、
  汇总和身份，不保存 PDF、真实 Chunk、私有题目、凭据或运行报告正文。
- Claim–Evidence/Multi-Evidence 当前主要是确定性 `AUDIT_ONLY`；没有将其表述为人工金标、
  通用 NLI 或在线硬裁决。
- OCR、正式 MinIO、完整生产运维、容量验证、真实用户评价和阶段 5 复杂问答仍不属于
  当前完成范围。

## 关联材料

- 当前阶段与证据：[`CURRENT_PHASE.md`](CURRENT_PHASE.md)
- 在线性能硬化：[`ONLINE_RETRIEVAL_PERFORMANCE_HARDENING.md`](ONLINE_RETRIEVAL_PERFORMANCE_HARDENING.md)
- API 快速开始：[`RAG_API_QUICKSTART.md`](RAG_API_QUICKSTART.md)
- 变更记录：[`../CHANGELOG.md`](../CHANGELOG.md)
