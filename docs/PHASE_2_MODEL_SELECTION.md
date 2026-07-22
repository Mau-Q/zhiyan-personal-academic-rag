# 阶段 2 固定生成模型选型 Gate

## 目标与边界

本 Gate 把 `qwen3:14b` 作为预期升级候选，把已通过远程 READY 闭环的 `llama3.2:latest` 作为回退基线。它只验证生成模型变量，不重新入库，不连接 PostgreSQL、Elasticsearch 或 Milvus，也不修改 RRF、候选数或 `top_k`。

Gate 直接复用 `OllamaGenerationProvider` 的 `/api/tags` 身份检查和 `/api/chat` 结构化生成。两个模型使用完全相同的：

- Prompt：`academic-evidence-answer-v1`；
- Prompt SHA-256：`796bf2fad94a92584d604479fb921bd98e72e4b97ecc09d6e49eaa2c0c71df71`；
- JSON Schema：`claims[].text + claims[].citation_ids`；
- 解码：`temperature=0.0`、`seed=42`、`num_predict=384`、`num_ctx=8192`、`think=false`；
- 四组公开合成中文科研 Evidence，基础用例规范化 SHA-256：`2ddec2697294ef98bacae7e01fd49a382235dad506b6a22b93b7b4d789ac176f`；
- v3 评测套件规范化 SHA-256：`85d639796aed211ea0f778fdadd791933a80f6374dd7b81e0a1b765429df2331`。

## 冻结模型

| 角色 | 模型 | Ollama digest |
|---|---|---|
| 回退基线 | `llama3.2:latest` | `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` |
| 预期升级候选 | `qwen3:14b` | `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8` |

摘要不匹配时提供器失败关闭，不得修改冻结摘要制造通过。本 Gate 不增加第二个候选。

## 晋级规则

每个模型对四类固定问题各生成两次：方法与样本、数值比较、冲突证据、证据不足。自动门禁检查：

1. 两次调用均完成且模型身份一致；
2. 两次回答分别通过相同的引用、必须回答点和禁止主张检查；
3. 必需 Evidence 引用编号全部存在；
4. 固定必须回答点出现，禁止主张不出现；
5. 回答正文不写入报告，只保存 SHA-256；
6. 两次答案是否字节一致单独记录为观测项，不作为选型硬门禁；
7. 调用耗时与 Token 只记录，当前没有冻结性能阈值，也不参与晋级决定。

候选四题全部通过时报告 `PROMOTE_QWEN3_14B`；任何确定性硬门禁未通过时报告 `KEEP_LLAMA3_2`。模型请求未完整执行时报告失败，不作选型决定。这里不建设匿名 A/B 平台，也不把本 Gate 冒充正式 Acceptance 人工验收。

v1 首次远程运行暴露了评测器假失败：`qwen3:14b` 对证据不足问题两次诊断回答完全一致，均为“提供的证据中没有提及本研究的资助机构”，引用 `[1]` 正确且没有外推；v1 固定短语表漏掉“没有提及/未提及”。v2 保留 v1 基础 Evidence 和原始运行证据，只以版本化覆盖补充等价拒答措辞，并把稳定性定义修正为“两次均通过相同确定性门禁”。

## 远程 v2 结果与决策

用户在 Windows 远程主机对提交 `ebb12c410fa93102b2a28cdc0bae3f33cc11ea9d` 执行冻结 v2 Gate，结果为 `PASS / PROMOTE_QWEN3_14B`：

- `qwen3:14b`：硬门禁通过，`4/4`；
- `llama3.2:latest`：硬门禁未通过，`2/4`；
- 候选资格：`true`；
- 稳定错误码：`NONE`；
- 脱敏报告 SHA-256：`21C27EAE18848962FC25A879AC620F989F4DD9690C6EB67A10236BE71DAF788B`。

因此阶段 2 的冻结生成模型晋级为 `qwen3:14b@bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`，`llama3.2:latest` 保留为已有远程 READY 证据的回退基线。本报告只证明固定公开 Evidence/Prompt 的模型选型，不证明 Qwen 已通过 PostgreSQL READY + ES/Milvus RRF 端到端闭环；后者必须使用新 Run ID 独立验证。

Qwen READY 的稳定分类进一步定位为 `REAL_GENERATION_INITIAL_OLLAMA_ANSWER_JSON_INVALID`。Ollama 对 Qwen3 的 API 默认启用 thinking；此前冻结配置没有显式发送 `think`，真实长 Evidence 下最终回答在固定 `num_predict=384` 内未形成完整 JSON。v3 只把该隐式默认冻结为 `think=false`，不修改模型摘要、Prompt、Schema、温度、Seed、Token 上限或检索。

用户在提交 `43dc5b4b5aae9ea7e2d16660ed3e75a3e6d07344` 执行 v3 后，报告为 `PASS / KEEP_LLAMA3_2`：Qwen `3/4`、llama3.2 `2/4`，报告 SHA-256 为 `64C4A7C741D5DC624D501165A129400D98DF66845F43BFC57D964AA9CD2B3C4E`。唯一失败用例为 `zh.evidence.conflict`；两次生成均完成并包含 `12周`、`16周`、引用 `[1][2]`，身份和禁词门禁通过，只因答案未逐字出现“差异/不一致/冲突”而失败。这是固定词面门禁假阴性，不是事实、引用或模型执行回归。

v4 因此把冲突用例冻结为结构语义门禁：两个互斥时间点和两条来源引用必须同时存在，仍保留禁词、身份、两次独立门禁与回答哈希；不要求某个表面连接词。基础 Evidence、问题、模型、Prompt、Schema、解码和检索均不改变。v3 原始结果继续保留，v4 必须形成新的远程报告，不得覆盖旧报告。

## 远程 v4 最终结果

用户在 Windows 远程主机对提交 `063236aa30ee7140a85bd5c7c305e4a0918dfc23` 执行 v4，结果为 `PASS / PROMOTE_QWEN3_14B`：

- `qwen3:14b`：硬门禁通过，`4/4`；
- `llama3.2:latest`：硬门禁未通过，`3/4`；
- 候选资格：`true`；
- `think=false`，检索参数未改变；
- 稳定错误码：`NONE`；
- 脱敏报告 SHA-256：`E031B1B4532571850FD4527D4930E80A3C144074DBB55F8055A54A51EDB7E038`。

因此最终生成模型保持晋级为 `qwen3:14b@bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`，`llama3.2:latest` 保留为回退模型。v3 的 `3/4 / KEEP_LLAMA3_2` 假阴性报告继续保留，不被 v4 覆盖。

## 运行

macOS/Linux 可执行：

```bash
make phase2-model-selection
```

Windows 可执行：

```powershell
.\.venv\Scripts\python.exe scripts\run_phase2_model_selection.py
```

默认报告位于被忽略的：

```text
runtime/phases/source-phase2-model-selection-qwen3-14b-v4/report.json
```

脚本只允许回环 Ollama URL 和 `runtime/` 下的新 JSON 报告；目标报告已存在时拒绝覆盖。返回证据只需要提交 SHA、完整脱敏报告、报告 SHA-256 和稳定错误码，不需要模型回答正文。
