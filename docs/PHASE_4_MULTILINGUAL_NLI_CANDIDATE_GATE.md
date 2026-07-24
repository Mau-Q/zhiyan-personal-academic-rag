# Phase 4 多语言 NLI 候选 Gate

## 结论

本地已完成固定多语言 NLI Cross-Encoder 的窄适配和 RTX 4090 用户执行入口，
状态为 `LOCAL_IMPLEMENTATION_READY_REMOTE_RTX4090_NOT_RUN`。Mac 只用 Fake
Scorer 验证合同、指标算术和失败关闭；真实模型不在 Mac 加载。

本 Gate 复用 `sentence-transformers.CrossEncoder`、既有 CUDA 12.6/PyTorch
环境、冻结私有 `dev` 包和 Claim–Evidence 输入身份，不新增框架、依赖或第二套
在线 RAG 链路。

## 冻结模型与输入

- 模型：`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`；
- revision：`b5113eb38ab63efdd7f280f8c144ea8b13f978ce`；
- snapshot SHA-256：
  `7e973b42bf69d9475c065d4deb04745659badf94ce054fd1de0f9cc1caeeafd5`；
- 输入方向固定为 Evidence=`premise`、Claim=`hypothesis`；
- `max_length=512`、`batch_size=16`、标签顺序固定为
  `entailment / neutral / contradiction`；
- 远程目标固定为 Windows PowerShell 5.1、RTX 4090、CUDA 12.6；
- 输入只读 `dev`：21 条 AI 辅助 `SUPPORTED`、1 条
  `PARTIALLY_SUPPORTED`，以及人工终审谱系中的 225 个正例 Claim。

## 当前能判断什么

远程诊断只判断两个正例保留率是否均达到 `0.85`。一个 Claim 绑定多个支持
Chunk 时，只要任意一个 Evidence–Claim pair 判为 entailment，就记为正例保留。

当前没有经过人工裁决的负例，所以 Precision、负例拒绝率和人机一致率均不可测。
AI 辅助候选不晋升为真值。即使两个正例保留率通过，也只允许进入后续人工裁决
Gate，不允许改变默认 `AUDIT_ONLY`，更不允许开启在线硬裁决。

## 入口与边界

本地可重复验证由单元测试覆盖 Fake Scorer、配置漂移、输入方向、正例分组和
PowerShell 行为合同。远程入口及完整用户命令见
`deploy/remote/phase4-nli-validation/README.md`。

远程脚本核验公开仓库提交、tracked worktree、私有输入哈希、候选哈希、配置
哈希、GPU、PyTorch/CUDA、模型 revision 和 snapshot，最终只输出脱敏 JSON。
组件延迟只表示 16 pair NLI scoring，不是在线 RAG 或 300 ms 检索性能结论。

知识库接入、前端、演示、远程服务操作、`test/Acceptance` 和在线策略变更均不在
本 Gate。
