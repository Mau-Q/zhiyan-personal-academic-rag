# Phase 4 Multi-Evidence Evidence Set 主 Gate

## 结论

本 Gate 在不改变公开 Answer、Evidence、Citation 或生成 Prompt 合同的前提下，
完成一个 Claim 对一个或多个 Evidence 的确定性 `EvidenceSet` 审计核心。状态为
`LOCAL_MULTI_EVIDENCE_SET_READY_AUDIT_ONLY`。

输出固定为：

- `SUPPORTED_BY_EVIDENCE_SET`；
- `PARTIALLY_SUPPORTED`；
- `CONFLICTING_EVIDENCE`；
- `INSUFFICIENT_EVIDENCE`。

该状态只证明本地确定性身份与锚点检查可执行，不冒充通用语义蕴含、人工金标、
在线硬裁决或最高方案阶段 4 完成。

## 复用与不采用

- 直接复用本仓库 `GeneratedClaim.text + citation_ids`，不重新切分生成结果；
- 直接复用请求内 Evidence/Citation 的位置绑定以及
  `claim_evidence.py` 的数字、单位、关系、限定词、核心重合与冲突检查；
- 窄适配 reading-agent 已验证的“部分支持保留边界”和“有界邻块”模式，只复用
  算法原则，不复制其 Pydantic、LLM Gateway、Planning 或运行时；
- 不引入 Ragas、Haystack、LangGraph 或新的 NLI/LLM 依赖。通用组件不能替代
  本仓库 owner、活动版本、document/version/chunk 身份与请求内引用合同。

## EvidenceSet 合同

`verify_claim_evidence_sets` 接收已经授权的请求内候选 Evidence、可信
`expected_owner_id`、每篇文档唯一活动版本映射和活动
`chunk_id → (document_id, version_id)` 身份快照。每条 Claim 首先按排序去重的
`citation_ids` 形成集合，并失败关闭校验：

- Evidence owner 必须与可信 owner 一致；
- Evidence 必须为活动状态，且 document/version 必须匹配活动版本映射；
- Chunk ID 必须合法且集合内唯一，并与活动身份快照精确一致；同一文档不得混入
  旧版本；
- Claim 数值必须存在，数值对应单位不得漂移；
- 因果、全称、比较对象、首次/唯一/最优及限定条件必须由集合证据建立；
- 同单位不同数值形成 `CONFLICTING_EVIDENCE`，不因 Claim 未披露冲突而隐藏；
- 多子句只有部分可证明时形成 `PARTIALLY_SUPPORTED`，全部无法证明时形成
  `INSUFFICIENT_EVIDENCE`。

## 邻块边界

只有原始绑定集合不能达到支持或冲突结论时，才检查同一请求内尚未绑定的候选。
候选必须满足：

1. 与某个已绑定 Chunk 同文档、同活动版本、同 owner；
2. `previous_chunk_id / next_chunk_id` 双向一致；
3. 加入后能把结论提升为支持或显式冲突。

满足时按请求内稳定顺序最多加入一个邻块，并记录
`SAME_DOCUMENT_VERSION_ADJACENT_EVIDENCE_ADDED` 与
`RETRIEVAL_SCORE_UNCHANGED`。实现不读取、不修改也不伪造相关性分数，不发起新
检索请求。

## 运行边界

- 默认继续 `AUDIT_ONLY`，不自动删除或改写 Claim；
- 原固定多语言 NLI 继续为已拒绝候选，不换模型、不调阈值、不复跑现有 dev、
  不回写数据；
- 无新框架、外部依赖、公共合同或 Prompt 变化；
- 未读取或运行 `test/Acceptance`；
- 不涉及知识库接入、前端、演示、Agent API、默认 RRF/Reranker 或 300 ms
  性能债。

## 验证

专项测试覆盖单 Evidence、多 Evidence、跨版本、越权、非活动版本、数值与单位
冲突、部分支持、比较对象与限定条件、最多一个同版本邻块及既有单 Evidence
回归。完整仓库回归、Harness、PowerShell 静态检查、diff 与敏感信息检查作为
本 Gate 的统一收口条件。
