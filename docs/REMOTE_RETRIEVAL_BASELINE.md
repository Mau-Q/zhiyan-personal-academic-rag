# 远程检索基础设施工程基线

## 边界

本基线证明单机远程环境中的 Elasticsearch、Milvus 和 BGE-M3 可运行、可持久化并执行带授权过滤的最小检索。Elasticsearch 与 Milvus 应用适配器均已完成 316 Chunk/15 题同源 Canary。它不证明生产安全配置完成、生产参数冻结或性能目标达成。

## 已验证拓扑

- 原生 Windows Ollama `0.30.10`：`bge-m3:latest`，1024 维，RTX 4090 GPU 执行；
- Docker Elasticsearch `9.4.3`：单节点、2 GB JVM、4 GB 容器上限；
- Docker Milvus `2.6.18`：官方 standalone 拓扑，依赖 etcd `3.5.25` 和 MinIO；
- 服务端口全部绑定 `127.0.0.1`；
- Docker 镜像层保留在 Docker Desktop 数据盘，Elasticsearch/Milvus 持久化目录放在容量充足的数据盘；
- PostgreSQL `18.4` 已在主机运行，但尚未接入应用。

## 版本化配置

- `deploy/remote/compose.elasticsearch.yml`
- `deploy/remote/compose.milvus.yml`

运行前由主机本地设置 `ZHIYAN_DATA_ROOT`。该变量不得写入 Git；仓库配置不得保存主机绝对路径。

当前远端容器由等价的逐项命令建立。不要在未安排维护窗口时用 Compose 强行接管或重建现有容器。

## 已执行的最小验证

### Elasticsearch

- `127.0.0.1:9200` 可用，单节点集群为 `green`；
- 创建 1 分片、0 副本的测试索引；
- 写入两个不同租户的测试文档；
- BM25 中文匹配与 `tenant_id + allowed_user_ids` 过滤只返回授权文档；
- 容器重启后索引仍有两条记录。

Windows PowerShell 5.1 发送非 ASCII JSON 时必须显式传入 UTF-8 字节，否则中文会被写为问号；响应终端显示乱码不等于服务端索引损坏。

### Milvus 与 BGE-M3

- Ollama 对两个输入返回 2 个 1024 维向量，模型以 `100% GPU` 运行；首次冷启动约 7.1 秒；
- 创建 COSINE、1024 维测试 Collection；
- 写入两个不同租户的 BGE-M3 向量；
- 向量搜索叠加租户和用户过滤后只返回授权实体；
- standalone、etcd 和 MinIO 完整重启后搜索结果仍存在。
- 应用适配器以 BGE-M3 1024 维、COSINE、HNSW 工程参数建立 316 Chunk Collection；
- 固定 15 题 Canary 为 `12/15`：`ANSWERABLE 6/9`、`NO_EVIDENCE 3/3`、`FORBIDDEN 3/3`，与本地精确向量基线一致；
- 3 个未通过项均为冻结目标页未进入返回证据：TRACER 目标第 6 页而命中第 7 页，SCINet 目标第 8 页而命中第 1/2/9 页，EVMbench 目标第 5 页而命中第 10/11 页；不修改目标页、阈值或参数制造通过。

## 当前未完成

- 500 题在真实 ES/Milvus 上的同源重跑；
- PostgreSQL 元数据/ACL 真值接入；
- Elasticsearch 隐藏版本索引写入器的远程复测，以及 READY 后在线 Alias/路由接入；
- Milvus 版本 Collection 写入器的远程复测，以及 READY 后在线 Collection 路由接入；
- 认证、TLS、备份、监控、并发和性能验收；
- 生产 HNSW/IVF、阈值、批大小和资源参数冻结；
- 真实生成 LLM 接入。

Elasticsearch/Milvus 候选接口与无密钥配置已固化。最小 ES+Milvus RRF 远程 15 题实跑为 `14/15`，与 ES 单路持平；唯一失败仍为 EVMbench 目标第 2 页未进入最终 Top-3。因此保留适配器和真实结果，不同时接入真实 LLM、重排、500 题远程全量或生产调参。
