# Phase 4 Claim–Evidence Core Gate

## 结论

本 Gate 把比赛项目的核心生成链路从“引用编号存在”推进到“每条结构化
Claim 都经过绑定 Evidence 的确定性核验”。它是本地核心能力，不包含前端、
知识库接入、演示入口、远程部署或 `test/Acceptance` 验收。

Gate 状态为
`LOCAL_CORE_READY_ONLINE_HARD_JUDGMENT_DEFERRED`。这表示核心代码与公开
Fixture/单元测试已就绪；不表示通用语义蕴含已经解决，也不表示最高方案
阶段 4 已完成。

## 复用决策

| 候选 | 接口/依赖 | 许可边界 | 决策与收益 |
|---|---|---|---|
| 本仓库 Ollama 结构化输出 | `claims[].text + citation_ids`；零新增依赖 | 本仓库现有私有源码 | 直接复用，避免再次做不稳定的答案 Claim 切分 |
| 本仓库 Evidence/Citation | 已授权 `EvidenceV1` 与位置编号；零新增依赖 | 本仓库现有私有源码 | 直接复用，继续继承 owner/READY/版本/页码链路 |
| 用户既有 reading-agent 可靠性 Guard | 高风险限定词、数字锚点、核心词重合的算法模式 | 私有项目，未作为第三方包再分发 | 只窄适配确定性规则，不复制其 LangGraph、Schema、模型网关或产品运行时 |
| `sentence-transformers.CrossEncoder` | 已有可选 Reranker 依赖 | 组件与模型许可分别受上游约束 | 不把相关性分数冒充 Claim 蕴含；如需 NLI，必须另选 NLI 训练模型并走独立离线 Gate |
| Ragas / Haystack Faithfulness | 需要额外框架和 LLM/评测执行 | 若以后引入需重新核对上游版本和许可 | 仅保留为后续离线对照候选，不进入当前在线硬裁决 |

因此当前最小复用方案是：保留现有生成 JSON，新增一个无外部依赖的窄
`verify_claim_evidence(claims, evidence)` 接口，再由现有
`apply_real_generation` 负责保留、降级和引用收缩。

## 确定性边界

当前检查覆盖：

- Claim 必须绑定本次请求内的 Evidence；
- Claim 中的数字必须能在绑定 Evidence 中找到；
- 因果、全称、比较、首次/唯一/最优等高风险语言必须在 Evidence 中出现
  对应关系标记；
- 普通事实至少通过英文内容词或中文二元组的核心重合检查；
- 同一单位的多条绑定 Evidence 出现不同数值时，回答必须明确披露冲突并
  同时给出至少两个冲突值；
- 纯“证据不足/未提供/无法确定”限制语可以安全保留，但状态不冒充
  `SUPPORTED`；
- 多 Claim 回答只删除不通过的 Claim；仍有可信 Claim 时形成显式部分回答，
  全部不通过时降级为 Evidence 卡片。

这些规则只证明确定性锚点、关系标记和引用绑定，不证明完整语义蕴含。
文本冲突、同义改写和隐含关系若无法被规则证明，当前失败关闭；不调用模型
自评来补造确定性结论。

## 核心合同

- `GeneratedClaim` 保存结构化 Claim 与 Evidence 位置；
- `ClaimSupportStatus` 为 `SUPPORTED / CONFLICTING_EVIDENCE /
  INSUFFICIENT_EVIDENCE / UNSUPPORTED`；
- `ClaimEvidenceReport` 提供保留 Claim、引用完整率、无依据主张率和部分回答
  判定；
- `apply_real_generation` 只渲染保留 Claim，并把 Citation 收缩到实际使用的
  Evidence；
- 全部 Claim 不通过或结构化 Claim 缺失时，保持原 Evidence 并
  `DEGRADED`，不输出模型自由文本。

## 验证与未完成项

公开测试覆盖正常支持、虚构数字、显式数值冲突、冲突遗漏、安全限制语、
部分回答、全量失败关闭、真实生成适配器和在线 READY API。`test/Acceptance`
未读取、未运行。

后续只保留一个大的校准 Gate：在独立 `dev` Claim–Evidence 人工标签上测
引用完整率、无依据主张率、误杀率与人工一致率，再决定规则是否能进入在线
硬裁决。知识库接入、前端和演示均由其他责任边界处理。
