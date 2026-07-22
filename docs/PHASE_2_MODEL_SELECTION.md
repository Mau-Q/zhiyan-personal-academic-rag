# 阶段 2 固定生成模型选型 Gate

## 目标与边界

本 Gate 把 `qwen3:14b` 作为预期升级候选，把已通过远程 READY 闭环的 `llama3.2:latest` 作为回退基线。它只验证生成模型变量，不重新入库，不连接 PostgreSQL、Elasticsearch 或 Milvus，也不修改 RRF、候选数或 `top_k`。

Gate 直接复用 `OllamaGenerationProvider` 的 `/api/tags` 身份检查和 `/api/chat` 结构化生成。两个模型使用完全相同的：

- Prompt：`academic-evidence-answer-v1`；
- Prompt SHA-256：`796bf2fad94a92584d604479fb921bd98e72e4b97ecc09d6e49eaa2c0c71df71`；
- JSON Schema：`claims[].text + claims[].citation_ids`；
- 解码：`temperature=0.0`、`seed=42`、`num_predict=384`、`num_ctx=8192`；
- 四组公开合成中文科研 Evidence，规范化 SHA-256：`2ddec2697294ef98bacae7e01fd49a382235dad506b6a22b93b7b4d789ac176f`。

## 冻结模型

| 角色 | 模型 | Ollama digest |
|---|---|---|
| 回退基线 | `llama3.2:latest` | `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` |
| 预期升级候选 | `qwen3:14b` | `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8` |

摘要不匹配时提供器失败关闭，不得修改冻结摘要制造通过。本 Gate 不增加第二个候选。

## 晋级规则

每个模型对四类固定问题各生成两次：方法与样本、数值比较、冲突证据、证据不足。自动门禁检查：

1. 两次调用均完成且模型身份一致；
2. 同模型同问题的答案字节稳定；
3. 必需 Evidence 引用编号全部存在；
4. 固定必须回答点出现，禁止主张不出现；
5. 回答正文不写入报告，只保存 SHA-256；
6. 调用耗时与 Token 只记录，当前没有冻结性能阈值，也不参与晋级决定。

候选四题全部通过时报告 `PROMOTE_QWEN3_14B`；任何确定性硬门禁未通过时报告 `KEEP_LLAMA3_2`。模型请求未完整执行时报告失败，不作选型决定。这里不建设匿名 A/B 平台，也不把本 Gate 冒充正式 Acceptance 人工验收。

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
runtime/phases/source-phase2-model-selection-qwen3-14b/report.json
```

脚本只允许回环 Ollama URL 和 `runtime/` 下的新 JSON 报告；目标报告已存在时拒绝覆盖。返回证据只需要提交 SHA、完整脱敏报告、报告 SHA-256 和稳定错误码，不需要模型回答正文。
