# 成员 A：在线 Fixture 消费者

## 目标

该消费者用于证明在线链路可以直接消费冻结的 `AuthorizedScopeV1`、`ChunkRecordV1` 和 `RagAnswerV1`。它不连接 Elasticsearch、Milvus、远程 4090 或生产数据库。

## 运行

```bash
python3 -m backend.rag.fixture_consumer \
  --question "How are candidates combined before reranking?"
```

无证据示例：

```bash
python3 -m backend.rag.fixture_consumer \
  --question "What is the measured ocean temperature?"
```

## 授权规则

1. `is_active` 必须为 `true`；
2. `public` 需要 `include_public=true`；
3. `tenant` 需要租户一致，并受请求中显式文档/文献库范围约束；
4. `private` 需要租户一致，并命中 `document_ids` 或 `library_ids`；
5. 当前 `ChunkRecordV1` 没有目录字段，只有 `folder_ids` 的范围会拒绝检索；真实授权层必须先把目录展开为文档 ID；
6. 未知可见性、缺失字段、失效版本和越权 Chunk 均不进入候选。

## 检索与生成边界

- 检索只使用问题与 `section_path + text` 的确定性词项交集；
- 排序使用“匹配词项数降序、`chunk_id` 升序”；
- Fake LLM 只拼装已召回 Chunk 的原文，不补充模型知识；
- 回答通过 `FIXTURE_ONLY_FAKE_LLM` 明确标记测试来源；
- 零候选返回 `NO_EVIDENCE`，不会读取越权 Chunk 或编造答案。

## 验证

```bash
make test
```

该实现只用于阶段 0 合同消费和成员 A 的在线链路起步，不代表真实检索质量基线。
