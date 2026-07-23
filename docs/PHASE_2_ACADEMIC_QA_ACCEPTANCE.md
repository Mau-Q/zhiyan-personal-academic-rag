# 阶段 2 固定普通科研问答验收包

## 1. Gate 边界

本 Gate 复用既有三论文人工定位题集，固定选择 3 篇指定 PDF、每篇 3 个普通科研问题，共 9 题。问题和 PDF 只进入被忽略的 `runtime/` 私有包；Git 只保存 Case ID、源摘要、模型身份和检索冻结边界。

生成固定为 `qwen3:14b@bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`、`think=false` 和 `academic-evidence-answer-v1`。检索继续使用 PostgreSQL READY + ES/Milvus RRF，保持 `candidate_k=20 / rrf_k=60 / top_k=3`；不改变 Hybrid 远程 Canary `14/15` 未超过 ES `14/15` 的结论，不引入 Reranker、MinIO、OCR 或性能变量。

## 2. 私有包与执行门禁

原始选择策略保留在 `evaluation/generation/phase2-academic-qa-acceptance-v1.json`；PDF 核验后的校正策略位于 `evaluation/generation/phase2-academic-qa-acceptance-v2.json`。`scripts/prepare_phase2_academic_qa_package.py` 只接受摘要匹配的题集、论文清单和 PDF，输出确定性 ZIP、Manifest、逐文档 suite 与 `SHA256SUMS`。v2 校正必须绑定原始页范围、白名单依据和仍覆盖原始页的扩展范围，不能静默替换历史标签。公开的 `package-report.json` 不保存问题、回答、Evidence 正文或本机绝对路径。

`scripts/run_stage1_remote_canary.py` 的可选 suite 模式要求同时提供 suite 文件与冻结 SHA-256，并且必须启用固定真实生成模型。每个问题执行两次 Answer API 调用并验证：

- PostgreSQL READY 范围只返回当前 `document_id/document_version_id`；
- 真实生成成功且引用编号经过现有确定性映射校验；
- Evidence 页码与人工目标页范围重叠；
- 两次调用均通过且 Citation 集合一致，答案字节一致只作观测；
- 文档失效后 Answer API 返回 403，ES、Milvus 和运行快照三路清理成功。

位置或版本门禁失败时，失败报告只补充已公开的 Case ID、`initial/replay` 阶段、人工目标页范围和实际 Evidence 页范围；仍不输出问题、回答、Evidence 正文、文档/版本标识或对象路径。该诊断只用于区分冻结目标错误与真实 Top-3 召回缺口，不改变模型、Prompt、检索参数或通过条件。

## 3. 远程证据与结论

原始 v1 私有包为 3 篇文档、9 个问题，ZIP SHA-256 为 `333051B2D8A929829CC32F89374CBFAEA28956B560D02A33D3873FC101F820B8`，Manifest SHA-256 为 `A1E0C455154394E1EA08C77E924625CC004D1758EC91E56ABA7342D4FA5DA3B2`。其首次远程逐文档执行中，第 1 篇的 3/3 问已通过真实生成、引用稳定回放、定位、三路清理和删除后 403；第 2 篇以 `ACADEMIC_QA_LOCATION_GATE_FAILED` 失败，第 3 篇因失败即停尚未执行。

同 Run ID 脱敏诊断定位到 `local3.answerable.tracer.ingredients`：原始目标只接受 PDF 第 3 页，实际 Top-3 Evidence 为第 1、2 页；诊断报告 SHA-256 为 `37B4345C0B16A34237EF90CE5037DCF798FE855ACAAA98798E4611D5D8CAB5D4`。PDF 文字与第 1～3 页渲染复核确认三项组成在第 1 页摘要/引言、第 2 页图和贡献说明、第 3 页方法概述均有有效表述。因此该结果是位置标签覆盖不完整导致的假阴性，不是已证实的召回缺口。

v2 只对该 Case 建立可追溯校正：保留来源范围第 3 页，将可接受范围扩为第 1～3 页；其余 8 个 Case、问题、PDF、模型、Prompt 和检索参数完全不变。新私有包状态为 `READY_FOR_USER_REMOTE_EXECUTION`，ZIP SHA-256 为 `CDCFA981ECA1BE2B7C06D97D42775A3EF9FA00F1E078C0BD5424A35336E95EED`，Manifest SHA-256 为 `A8DEE26281EE1C953D1024C2686FCA28E0D0195855CDDE81ED142E791618FD39`，位于被忽略的 `runtime/phases/source-phase2-academic-qa-acceptance-v2-local/input/`。

远程 v2 第 1、2 篇各 `3/3` 问通过：真实 Qwen 生成、引用集合稳定回放、定位、三路清理和删除后 403 均满足门禁，报告 SHA-256 分别为 `4FB08864CB22B611294CAD0159DF6DB60E7496D89D16ADA6819A8E94E4FB9FB1` 和 `F92F9989FC28A6807B298E45369CEC72755169ACC2882FD57582C66915177E9E`。

第 3 篇初次运行以 `PERSISTED_SNAPSHOT_ANSWER_HTTP_FAILED` 停止，失败报告 SHA-256 为 `6C01FFC7CA2D8EF4C97F4B6E58AC492DAEBE421F50B0479E12346E2E81EA99FC`；该失败证据不删除、不改写。随后在相同冻结边界下以新报告路径恢复，最终报告 SHA-256 `3C106423AB3575B11B3B0142A66F19A2C949B8BAED3457F1BCA101A9931302FA` 为 `PASS / NONE`，第 3 篇 `3/3`、全部文档 `3/3`、全部问题 `9/9` 通过。生成身份仍为 `qwen3:14b@bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`，`citation_stable_replay=true`，三路清理为 `3`，失效后 Answer API 为 `403`。

最终报告的 `byte_stable_replay_observed=false` 只表示两次自然语言答案字节不完全相同；两次调用各自均通过引用、位置、版本和安全硬门禁，Citation 集合稳定，因此不把字节差异误报为验收失败。远程学术问答验收 Gate 至此完成，且没有调整模型、Prompt、检索参数或基础设施。

为了不再盲目重试，远程 Canary 在保留原稳定错误码的同时，为 Answer API 非 200 报告新增 `answer_http_failure`：只包含 `initial/replay`、HTTP 状态和匹配 `^[A-Z][A-Z0-9_]{0,63}$` 的 API 错误码，不输出响应消息、问题、回答或 Evidence。
