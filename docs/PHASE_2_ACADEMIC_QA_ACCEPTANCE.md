# 阶段 2 固定普通科研问答验收包

## 1. Gate 边界

本 Gate 复用既有三论文人工定位题集，固定选择 3 篇指定 PDF、每篇 3 个普通科研问题，共 9 题。问题和 PDF 只进入被忽略的 `runtime/` 私有包；Git 只保存 Case ID、源摘要、模型身份和检索冻结边界。

生成固定为 `qwen3:14b@bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`、`think=false` 和 `academic-evidence-answer-v1`。检索继续使用 PostgreSQL READY + ES/Milvus RRF，保持 `candidate_k=20 / rrf_k=60 / top_k=3`；不改变 Hybrid 远程 Canary `14/15` 未超过 ES `14/15` 的结论，不引入 Reranker、MinIO、OCR 或性能变量。

## 2. 私有包与执行门禁

选择策略位于 `evaluation/generation/phase2-academic-qa-acceptance-v1.json`。`scripts/prepare_phase2_academic_qa_package.py` 只接受摘要匹配的题集、论文清单和 PDF，输出确定性 ZIP、Manifest、逐文档 suite 与 `SHA256SUMS`。公开的 `package-report.json` 不保存问题、回答、Evidence 正文或本机绝对路径。

`scripts/run_stage1_remote_canary.py` 的可选 suite 模式要求同时提供 suite 文件与冻结 SHA-256，并且必须启用固定真实生成模型。每个问题执行两次 Answer API 调用并验证：

- PostgreSQL READY 范围只返回当前 `document_id/document_version_id`；
- 真实生成成功且引用编号经过现有确定性映射校验；
- Evidence 页码与人工目标页范围重叠；
- 两次调用均通过且 Citation 集合一致，答案字节一致只作观测；
- 文档失效后 Answer API 返回 403，ES、Milvus 和运行快照三路清理成功。

位置或版本门禁失败时，失败报告只补充已公开的 Case ID、`initial/replay` 阶段、人工目标页范围和实际 Evidence 页范围；仍不输出问题、回答、Evidence 正文、文档/版本标识或对象路径。该诊断只用于区分冻结目标错误与真实 Top-3 召回缺口，不改变模型、Prompt、检索参数或通过条件。

## 3. 当前证据与未完成项

本地私有包为 3 篇文档、9 个问题，状态 `READY_FOR_USER_REMOTE_EXECUTION`；ZIP SHA-256 为 `333051B2D8A929829CC32F89374CBFAEA28956B560D02A33D3873FC101F820B8`，Manifest SHA-256 为 `A1E0C455154394E1EA08C77E924625CC004D1758EC91E56ABA7342D4FA5DA3B2`。运行实例位于被忽略的 `runtime/phases/source-phase2-academic-qa-acceptance-local/input/`。

首次远程逐文档执行中，第 1 篇的 3/3 问已通过真实生成、引用稳定回放、定位、三路清理和删除后 403；第 2 篇以 `ACADEMIC_QA_LOCATION_GATE_FAILED` 真实失败，第 3 篇因失败即停尚未执行。因此当前结论是 `1/3 DOCUMENTS PASS / DOCUMENT 2 LOCATION DIAGNOSTIC PENDING / DOCUMENT 3 NOT RUN`，不得写成 9 题通过。

下一次同 Run ID 恢复只采集第 2 篇失败 Case 的脱敏页码诊断。先判断人工目标页冻结是否正确；若正确，则把结果保留为固定 Top-3 召回缺口，再进入独立 Reranker 决策，不为通过而修改问题、页码或检索参数。
