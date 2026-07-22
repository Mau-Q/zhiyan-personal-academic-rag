# 数据身份与生命周期 V1

## 身份映射

- PostgreSQL 是 `owner_id`、文档身份、版本和生命周期的唯一事实源；ES/Milvus 只是可重建索引。
- `paper_id` 保留上游物理主键语义，`document_id` 是 RAG/API 逻辑标识。二者不通过字符串规则互相推导，而是在 PostgreSQL 中显式映射。
- 映射按所有者隔离：`document_id` 全局唯一，`(owner_id, paper_id)` 联合唯一。任一方向查询都必须带服务端鉴权得到的 `owner_id`，避免公共论文被多个用户收藏时产生跨用户歧义。
- `owner_id`、`paper_id`、`document_id` 和 `source_type` 建立后不可修改；客户端不提供可信的所有者或物理主键。
- DOI、arXiv ID 等写入独立外部标识关系，不能替代 `paper_id ↔ document_id` 映射。

## 版本语义

- `document_version_id` 标识可引用的内容版本；内容变化创建新版本，历史版本 ID 不复用、不被静默覆盖。
- 现有 `ChunkRecordV1.version_id` 是运行时 legacy 字段。阶段 1 适配层将其解释为 `document_version_id`，本合同不破坏现有 V1 API 或 Chunk Schema。
- `chunk_id` 必须绑定文档版本、解析版本和稳定边界；新内容版本不得沿用旧 Chunk ID。

## 生命周期

| 状态 | 含义 | 可在线召回 |
|---|---|---|
| `REGISTERED` | PostgreSQL 已登记身份和版本 | 否 |
| `PROCESSING` | 正在解析、切片或写索引 | 否 |
| `REVIEW` | 解析质量或元数据需要确认 | 否 |
| `READY` | 解析、Chunk、ES 与 Milvus 均完成 | 是 |
| `FAILED` | 处理失败并记录稳定错误码 | 否 |
| `INACTIVE` | 删除、撤权或版本失效 | 否 |

`READY` 必须同时满足 `parse_finish_time`、`chunk_splitter_time`、`chunk_create_time`、`chunk_gen_time`、`vector_index_time` 已记录，ES Chunk 与 Milvus Vector 状态均为 `READY`，且 `delete_time`、`chunk_expire_time`、`failure_code` 为空。任何一侧索引未完成都不能进入 `READY`。

索引中的派生字段固定为：

```text
is_active = lifecycle_status == READY
            AND delete_time IS NULL
            AND chunk_expire_time IS NULL
```

删除、撤权或版本失效先在 PostgreSQL 提交 `INACTIVE`，随后使查询和缓存失效，最后异步物理清理 ES/Milvus。`INACTIVE` 对单个版本是终态；恢复或内容刷新创建新的 `document_version_id`。`last_access_time` 只用于访问统计，不参与 READY 或活动状态；`last_refresh_time` 变化触发新版本/索引刷新，不把旧索引状态反写为业务事实。

## 运行边界

本次只冻结 `DocumentIdentityV1`、`DocumentVersionLifecycleV1` 和机器策略，不创建数据库表、不迁移现有 Fixture、不接入远程 PostgreSQL。阶段 1 才实现持久化、幂等任务、索引状态对账与撤权失效，并通过目标规模验证后判断 SLO 是否达标。
