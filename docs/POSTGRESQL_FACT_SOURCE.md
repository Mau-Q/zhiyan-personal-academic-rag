# PostgreSQL 最小事实源

## 当前边界

阶段 1 已建立 PostgreSQL Schema、延迟加载的 `psycopg` 适配器和独立测试。PostgreSQL 是 `owner_id`、文档映射、内容版本、Chunk 快照、生命周期与入库/清理任务的唯一事实源；PDF 字节保存在独立对象根目录，Elasticsearch 和 Milvus 仍然是可重建派生索引。

远程 PostgreSQL 18.4 已通过 `0001`～`0003` 迁移和基础设施生命周期 Canary。新增 `0004_runtime_snapshots.sql`、持久化 Chunk 在线加载和 Answer API v2 Canary 目前只有本地证据，等待用户远程应用和实跑。

## 已实现的硬约束

- `document_id` 全局唯一，`(owner_id, paper_id)` 联合唯一；
- `owner_id/paper_id/document_id/source_type` 由数据库触发器阻止原地修改；
- 相同内容快照和解析版本重放时返回同一 `document_version_id`；
- 版本和入库任务在同一事务内绑定；任务按 `(owner_id, idempotency_key)` 幂等，同一 Key 不得换绑版本或内容；
- 生命周期使用修订号 Compare-and-Swap，陈旧并发更新失效关闭；
- `PROCESSING` 允许通过新修订号记录解析和 Chunk 进度，但不因局部完成变为可检索；
- 索引失败状态与任务失败在同一事务内提交，双索引成功后的 `READY` 与任务 `SUCCEEDED` 也原子提交；
- 解析、Chunk 和向量时间齐全，且 ES/Milvus 均为 `READY` 时才能进入 `READY`；
- 删除、撤权或过期版本先进入终态 `INACTIVE`；在线查询始终带 `owner_id AND is_active=true`；
- 同一 owner/document 最多一个活动版本；在线解析显式要求 PostgreSQL `READY`、双索引 `READY`、未删除且未过期。
- PDF 对象注册和 Chunk 行按版本不可变；重放必须得到完全相同的对象身份和 Chunk 快照；
- 在线 Answer API 只按 PostgreSQL 已解析的 READY 版本加载 Chunk，不读取 Fixture；
- 运行快照物理删除只有在版本已 `INACTIVE` 后才允许，并与 ES/Milvus 共用持久清理租约、重试和恢复机制。

## 仓库入口

- SQL：`backend/storage/migrations/0001_fact_source.sql`；
- 清理队列迁移：`backend/storage/migrations/0002_cleanup_queue.sql`；
- 在线唯一活动版本迁移：`backend/storage/migrations/0003_online_ready_visibility.sql`；
- PDF 对象注册与 Chunk 快照迁移：`backend/storage/migrations/0004_runtime_snapshots.sql`；
- PDF 对象后端：`backend/storage/pdf_objects.py`；
- 迁移器：`python -m backend.storage.migrate`；
- 仓储适配器：`backend/storage/postgres.py`；
- 双索引生命周期协调：`backend/ingestion/index_lifecycle.py`；
- Elasticsearch 隐藏版本索引写入器：`backend/ingestion/elasticsearch_writer.py`；
- Milvus 脱离在线路由的版本写入器：`backend/ingestion/milvus_writer.py`；
- 持久化物理清理调度与 Worker：`backend/ingestion/cleanup.py`；
- PostgreSQL READY 在线路由：`backend/retrieval/online.py`；
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

用户在隔离远程主机应用 `0004`，再运行版本化 Stage 1 v2 Canary。必须同时返回：迁移 `APPLIED/UNCHANGED`、PDF 对象重开、Chunk 快照指纹、Answer API `COMPLETED` 与 Evidence、删除后 Answer API 403、ES/Milvus/运行快照三项清理成功。报告只返回脱敏身份和哈希，不返回 PDF/Chunk 正文、对象根目录或连接信息。
