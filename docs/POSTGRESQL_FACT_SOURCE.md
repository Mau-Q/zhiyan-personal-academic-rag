# PostgreSQL 最小事实源

## 当前边界

阶段 1 的第一个本地实现已建立 PostgreSQL Schema、延迟加载的 `psycopg` 适配器和独立测试。PostgreSQL 是 `owner_id`、文档映射、内容版本、生命周期与入库任务的唯一事实源；Elasticsearch 和 Milvus 仍然是可重建派生索引。

当前只证明源码、SQL 迁移和失效关闭语义在本地可执行。远程 PostgreSQL 18.4 尚未应用该迁移，未可宣称阶段 1 事实源已远程验收。

## 已实现的硬约束

- `document_id` 全局唯一，`(owner_id, paper_id)` 联合唯一；
- `owner_id/paper_id/document_id/source_type` 由数据库触发器阻止原地修改；
- 相同内容快照和解析版本重放时返回同一 `document_version_id`；
- 版本和入库任务在同一事务内绑定；任务按 `(owner_id, idempotency_key)` 幂等，同一 Key 不得换绑版本或内容；
- 生命周期使用修订号 Compare-and-Swap，陈旧并发更新失效关闭；
- `PROCESSING` 允许通过新修订号记录解析和 Chunk 进度，但不因局部完成变为可检索；
- 索引失败状态与任务失败在同一事务内提交，双索引成功后的 `READY` 与任务 `SUCCEEDED` 也原子提交；
- 解析、Chunk 和向量时间齐全，且 ES/Milvus 均为 `READY` 时才能进入 `READY`；
- 删除、撤权或过期版本先进入终态 `INACTIVE`；在线查询始终带 `owner_id AND is_active=true`。

## 仓库入口

- SQL：`backend/storage/migrations/0001_fact_source.sql`；
- 迁移器：`python -m backend.storage.migrate`；
- 仓储适配器：`backend/storage/postgres.py`；
- 双索引生命周期协调：`backend/ingestion/index_lifecycle.py`；
- Elasticsearch 隐藏版本索引写入器：`backend/ingestion/elasticsearch_writer.py`；
- 运行时模型：`backend/storage/models.py`；
- 本地门禁：`make storage-test`。

## 由用户执行的远程迁移

远程主机操作由用户亲自执行。必须先确认远程仓库提交与待验证提交一致，再在 PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[postgres]"
$secureDsn = Read-Host -Prompt "DATABASE_URL" -AsSecureString
$dsnPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureDsn)
try {
    $env:DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($dsnPointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($dsnPointer)
}
.\.venv\Scripts\python.exe -m backend.storage.migrate
Remove-Item Env:DATABASE_URL
.\.venv\Scripts\python.exe -m unittest discover -s tests/storage -p "test_*.py" -v
```

迁移器只输出 `APPLIED` 或 `UNCHANGED`，不输出 DSN。已应用的迁移如果与仓库 SHA-256 不同会直接失败，不会覆盖旧 Schema。用户应将原始命令输出返回给开发侧，不得回传密码、DSN、IP 或 `.env` 内容。

## 后续门禁

1. 用户在隔离的远程 PostgreSQL 上应用迁移并返回脱敏输出；
2. 在远程 PostgreSQL 上复测本地已完成的持久化 PDF 准备编排；
3. 在远程 Elasticsearch 复测本地隐藏版本索引写入器，并实现 Milvus 版本写入器和持久化清理队列；
4. 将在线 Answer API 切换到 PostgreSQL READY 可见性门禁；
5. 完成单侧失败补偿与删除/撤权先失效、再异步物理清理的远程故障验证。
