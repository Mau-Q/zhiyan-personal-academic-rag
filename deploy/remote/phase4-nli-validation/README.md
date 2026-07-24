# Phase 4 multilingual NLI RTX 4090 Gate

这是 Windows PowerShell 5.1、用户操作的离线 `dev` 正例保留诊断。它不连接知识库或
RAG 服务，不读取 `test/Acceptance`，不改变在线 Claim–Evidence 策略。

前提：公开仓库 `main` 已拉到待验证提交且 tracked worktree 干净；私有输入 ZIP
仍由用户在主机上保管。脚本会核验 ZIP、内层 JSONL、候选 CSV、配置、CUDA
PyTorch、RTX 4090、模型 revision 和完整 snapshot 哈希。

先把私有 ZIP 放到仓库忽略目录
`runtime\handoffs\member-b-phase2-4-dev-review-input-v1\`，保留原文件名。然后在
仓库根目录执行：

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy\remote\phase4-nli-validation\run_phase4_multilingual_nli_gate.ps1 -RepositoryRoot $PWD.Path -InputPackagePath (Join-Path $PWD.Path 'runtime\handoffs\member-b-phase2-4-dev-review-input-v1\member-b-phase2-4-dev-review-input-v1.zip')`

最终仅回传脚本输出的脱敏 JSON。不要回传私有 JSONL、模型缓存或异常堆栈。
`quality_decision` 即使为候选通过，也只表示可以进入后续人工裁决的远程 NLI Gate，
绝不表示在线硬裁决已启用。
