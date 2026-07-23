[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$PythonPath = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
$OutputDirectory = Join-Path $RepositoryRoot 'runtime\evaluation\formal-retrieval-v1\ai-audited-engineering-v1\reranker-bge-v2-m3-windows-rtx4090-v1'

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Project Python is missing at $PythonPath"
}

Push-Location $RepositoryRoot
try {
    $dirtyPaths = @(& git status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw 'git status failed.'
    }
    if ($dirtyPaths.Count -ne 0) {
        throw 'Remote repository must be clean before the Reranker Gate.'
    }

    & git fetch origin main
    if ($LASTEXITCODE -ne 0) {
        throw 'git fetch origin main failed.'
    }
    $headCommit = (& git rev-parse HEAD).Trim()
    $originCommit = (& git rev-parse origin/main).Trim()
    if ($LASTEXITCODE -ne 0 -or $headCommit -ne $originCommit) {
        throw 'Remote HEAD must equal origin/main before the Reranker Gate.'
    }

    & $PythonPath -m pip install -e '.[reranker]'
    if ($LASTEXITCODE -ne 0) {
        throw 'Installing the optional Reranker dependencies failed.'
    }

    & $PythonPath -c "import torch; assert torch.cuda.is_available(), 'CUDA is unavailable'; print(torch.cuda.get_device_name(0))"
    if ($LASTEXITCODE -ne 0) {
        throw 'CUDA preflight failed.'
    }

    $arguments = @(
        'scripts/run_fixed_reranker_gate.py',
        '--manifest',
        'runtime/evaluation/formal-retrieval-v1/ai-audited-engineering-v1/manifest.json',
        '--chunks',
        'runtime/evaluation/mvp-175-remote-baseline-input-v1/chunks-v1.json',
        '--candidates',
        'runtime/evaluation/formal-retrieval-v1/ai-audited-engineering-v1/rankings-v1/local_rrf.jsonl',
        '--document-catalog',
        'fixtures/sample-corpus-v1.json',
        '--config',
        'evaluation/reranker/fixed-cross-encoder-windows-rtx4090-v1.json',
        '--output-dir',
        $OutputDirectory
    )
    & $PythonPath @arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Fixed Reranker Gate failed.'
    }

    $runReportPath = Join-Path $OutputDirectory 'run-report.json'
    $decisionPath = Join-Path $OutputDirectory 'decision.json'
    $runReport = Get-Content -LiteralPath $runReportPath -Raw | ConvertFrom-Json
    $decision = Get-Content -LiteralPath $decisionPath -Raw | ConvertFrom-Json

    if ($runReport.item_count -ne 100) {
        throw 'Reranker Gate did not cover the frozen 100-question test split.'
    }
    if ($runReport.model.revision -ne '953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e') {
        throw 'Reranker model revision drifted.'
    }
    if ($runReport.model.snapshot_sha256 -ne 'f9dd638f0b27b57667d99b01f83ca4dbb3c82983911a1ef31a4601c7b890eaec') {
        throw 'Reranker model snapshot digest drifted.'
    }
    $expectedInputs = [ordered]@{
        config = 'e4b9e927da6411a0b152c4019ed6fd8a827f71dfa3bf14a2b934451383ac7383'
        manifest = 'b1a3d2aa7a40e38c28818b1b712ccdf14a05eeeaa87826545e0d102d2f400207'
        chunks = 'f7eb7e4a6c7820abde5523dca906df1d1a052e2e3b2174887781531295c7a282'
        candidates = '777b41c3e2544badcb9ed6fb7208f4556f4a989286a2373ebad5a59028bbc7f5'
        document_catalog = '64d453d915ee822766b44a7bec5ab9f031d957532a85bc529e4d1f849bd9c2fb'
    }
    foreach ($inputName in $expectedInputs.Keys) {
        if ($runReport.input_sha256.$inputName -ne $expectedInputs[$inputName]) {
            throw "Reranker frozen input digest drifted: $inputName"
        }
    }
    if ($runReport.truncated_pair_count -ne 31) {
        throw 'Reranker tokenization or truncation count drifted.'
    }

    $summary = [ordered]@{
        schema_version = 'fixed_cross_encoder_remote_summary_v1'
        head_commit = $headCommit
        model_revision = $runReport.model.revision
        model_snapshot_sha256 = $runReport.model.snapshot_sha256
        item_count = $runReport.item_count
        pair_count = $runReport.pair_count
        truncated_pair_count = $runReport.truncated_pair_count
        ndcg_at_10 = $decision.quality.reranker_ndcg_at_10
        relative_ndcg_at_10_gain = $decision.quality.relative_ndcg_at_10_gain
        precision_at_5 = $decision.quality.reranker_precision_at_5
        precision_at_5_delta = $decision.quality.precision_at_5_delta
        critical_gate_passed = $decision.quality.critical_gate_passed
        reranker_latency_ms_p50 = $decision.latency.reranker_latency_ms_p50
        reranker_latency_ms_p95 = $decision.latency.reranker_latency_ms_p95
        quality_decision = $decision.decision
        run_report_sha256 = (Get-FileHash -LiteralPath $runReportPath -Algorithm SHA256).Hash
        decision_sha256 = (Get-FileHash -LiteralPath $decisionPath -Algorithm SHA256).Hash
        stable_error_code = 'NONE'
    }
    $summary | ConvertTo-Json -Depth 4
}
finally {
    Pop-Location
}
