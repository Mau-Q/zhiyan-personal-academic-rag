# SSE Events V1

首个实现优先提供非流式接口；流式实现必须复用同一回答语义，并遵循以下事件合同。

## 事件

| Event | 次数 | 负载要求 |
|---|---:|---|
| `meta` | 1 | `request_id`、`trace_id`、合同版本 |
| `evidence` | 0..N | 完整 Evidence；必须早于引用它的 `citation` |
| `delta` | 0..N | 仅包含新增回答文本，不包含证据或私有推理过程 |
| `citation` | 0..N | 完整 Citation；只能引用本次已发送 Evidence |
| `done` | 1 | 完整 `RagAnswerV1` 终态对象 |
| `error` | 0..1 | `ErrorV1`；出现后连接终止，不再发送 `done` |

## 顺序

```text
meta -> evidence* -> (delta | citation)* -> done
meta -> error
```

断线重连、慢消费和事件 ID 策略在流式实现开始前补充兼容性合同；阶段 0 不假定自动续传。
