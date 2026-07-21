# Error Codes V1

| Code | HTTP | Retryable | 含义 |
|---|---:|---|---|
| `RAG_INVALID_REQUEST` | 422 | false | 请求字段、长度或范围结构无效 |
| `RAG_FORBIDDEN_SCOPE` | 403 | false | 请求包含未授权文档或文献库 |
| `RAG_NO_EVIDENCE` | 200 | false | 授权范围内证据不足，返回结构化拒答 |
| `RAG_INDEX_NOT_READY` | 409 | true | 指定索引版本未达到 READY |
| `RAG_RETRIEVAL_TIMEOUT` | 504 | true | 检索阶段超过固定时限 |
| `RAG_RERANKER_UNAVAILABLE` | 200 | true | 重排不可用，回答必须标记 `DEGRADED` |
| `RAG_MODEL_UNAVAILABLE` | 503 | true | 生成模型不可用，未产出回答 |
| `RAG_CITATION_INVALID` | 500 | false | 引用无法映射到本次有效证据 |
| `RAG_INTERNAL_ERROR` | 500 | true | 未分类内部错误 |

`RAG_NO_EVIDENCE` 是正常业务结果，不是基础设施失败。任何降级都必须进入回答 `status`、`warnings` 和 Trace，不能伪装成完整成功。
