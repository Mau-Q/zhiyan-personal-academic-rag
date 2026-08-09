# Competition Human Evaluation V1

## Worksheet

复制 `evaluation/templates/competition-human-evaluation-v1.csv`，由 Reviewer A 与
Reviewer B 独立填写，互不查看对方记录。问题、RAG Answer 与人工参考判断只从同一
次 `runtime/competition/v1/<run-id>/redacted-results.json` 和获准论文页面填入；不得
把历史 9/9 摘要当作本次答案，也不得把空模板计为评价。

枚举值由 `contracts/schemas/competition-human-evaluation-v1.schema.json` 冻结。
`critical_error_types` 多值时用 `|` 分隔，只允许：

- `ANSWER_CORRECT_CITATION_WRONG`
- `SHOULD_REFUSE_BUT_GENERATED`
- `CLAIM_NOT_SUPPORTED_BY_EVIDENCE`

时间字段按秒记录非负整数；没有计时就保持空白并报告不可用，不填 0 冒充实测。

## 双评审与仲裁

1. Reviewer A 独立评审全部三个场景并冻结自己的 CSV。
2. Reviewer B 独立评审同一运行的全部三个场景并冻结自己的 CSV。
3. 以 `scenario_id` 对齐，逐字段标出分歧；不得先用讨论改写独立记录。
4. 第三位仲裁者或两位评审共同复核授权论文 Evidence，填写最终行和
   `adjudication`，保留 A、B 原始行。
5. 最终材料同时保存两个独立文件、仲裁文件及各自 SHA-256。

## Agreement

对下列离散字段分别计算，不跨字段混成一个分数：

- `answer_correctness`
- `citation_correctness`
- `evidence_support_correctness`
- refusal correctness，定义为 `should_refuse == actual_refusal`

Percent agreement 为 `一致场景数 / 双方均给出适用值的场景数`。Cohen's kappa 仅对
双方均填写、枚举兼容且存在足够类别变化的离散字段计算：

```text
kappa = (observed_agreement - expected_agreement) / (1 - expected_agreement)
```

只有三个场景时，kappa 通常样本过少；分母为 0、只有单一类别、有效配对少于 2 或
任一方缺值时必须写 `NOT_COMPUTABLE`，不得报告统计显著性。连续时间、修订量和自由
文本不计算 kappa。仲裁结论不覆盖独立 agreement，只另行报告最终分布。

任一 critical error 都必须单列，不得被总体一致率或平均分抵消。EvidenceSet 输出
始终标注 `AUDIT_ONLY`：它不是人工语义 Gold，也不是自动消除幻觉的证明。
