# 阶段 0 合同

本目录是成员 A 与成员 B 的静态交接边界。实现代码不得重新定义这些字段的含义。

## 当前版本

- `ChunkRecordV1`：成员 B 产出，成员 A 消费；
- `AuthorizedScopeV1`：服务端计算的授权范围；
- `IndexVersionV1`：可被在线查询链路消费的索引版本；
- `RagAnswerV1`：非流式回答、证据、引用和拒答结果；
- `TraceV1`：不包含模型私有推理过程的阶段追踪记录；
- `openapi.json`：首个非流式问答接口和错误响应；
- `sse-events.md`：后续流式接口的事件和顺序合同；
- `error-codes.md`：首批稳定错误码。
- 正式检索评测：Manifest、样本、独立标注/仲裁记录和检索排名结果合同。

正式评测 JSON Schema 由 `scripts/export_evaluation_contracts.py` 从运行时 Pydantic 模型导出，并用 `--check` 防止漂移。合同和合成 Fixture 就绪不代表真实 500 条人工评测集已经完成。

## 变更规则

1. 兼容性增加只能使用可选字段，并补充示例与契约测试；
2. 字段删除、重命名或语义变化必须发布新主版本；
3. 合同变更先修改 Schema、示例和测试，再修改实现；
4. `READY`、ACL、引用定位和证据不足拒答属于阻断性边界，不允许静默降级；
5. `tests/contracts/` 通过后才能合并合同变更。

## 本地验证

```bash
make contract-test
python3 scripts/export_evaluation_contracts.py --check
```
