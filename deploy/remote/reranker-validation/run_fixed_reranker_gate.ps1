[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$InputPackagePath
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Join-Path -Path $PSScriptRoot -ChildPath '..\..\..'
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$PythonPath = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
$OutputDirectory = Join-Path $RepositoryRoot 'runtime\evaluation\formal-retrieval-v1\ai-audited-engineering-v1\reranker-bge-v2-m3-windows-rtx4090-v1'
$TorchPackage = 'torch==2.13.0+cu126'
$TorchIndexUrl = 'https://download.pytorch.org/whl/cu126'
$InputPackageSha256 = '4884a5a9f2101ef203a55b58e25c82f74ac7f035a074760af5fd103eb198e9fe'
$ExpectedPrivateInputs = [ordered]@{
    'runtime\evaluation\formal-retrieval-v1\ai-audited-engineering-v1\annotations-v1.jsonl' = '9a6f66e2709fc2d7a91cb332de62ec01c30563e44df2efad3458c9ecede8cb68'
    'runtime\evaluation\formal-retrieval-v1\ai-audited-engineering-v1\items-v1.jsonl' = '940e5b8c8d00d9f70626e65e34fdfce6bac6ec7ab681b8d2b08794976b94d5d4'
    'runtime\evaluation\formal-retrieval-v1\ai-audited-engineering-v1\manifest.json' = 'b1a3d2aa7a40e38c28818b1b712ccdf14a05eeeaa87826545e0d102d2f400207'
    'runtime\evaluation\formal-retrieval-v1\ai-audited-engineering-v1\rankings-v1\local_rrf.jsonl' = '777b41c3e2544badcb9ed6fb7208f4556f4a989286a2373ebad5a59028bbc7f5'
    'runtime\evaluation\mvp-175-remote-baseline-input-v1\chunks-v1.json' = 'f7eb7e4a6c7820abde5523dca906df1d1a052e2e3b2174887781531295c7a282'
}

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Project Python is missing at $PythonPath"
}

Push-Location $RepositoryRoot
try {
    $dirtyPaths = @(& git status --porcelain --untracked-files=no)
    if ($LASTEXITCODE -ne 0) {
        throw 'git status failed.'
    }
    if ($dirtyPaths.Count -ne 0) {
        throw 'Remote repository must have no tracked or staged changes before the Reranker Gate.'
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

    $privateInputsReady = $true
    foreach ($relativePath in $ExpectedPrivateInputs.Keys) {
        $privateInputPath = Join-Path -Path $RepositoryRoot -ChildPath $relativePath
        if (-not (Test-Path -LiteralPath $privateInputPath -PathType Leaf)) {
            $privateInputsReady = $false
            break
        }
        $privateInputSha256 = (Get-FileHash -LiteralPath $privateInputPath -Algorithm SHA256).Hash
        if ($privateInputSha256 -ne $ExpectedPrivateInputs[$relativePath]) {
            $privateInputsReady = $false
            break
        }
    }

    $inputSource = 'PREEXISTING_VERIFIED_RUNTIME'
    if (-not $privateInputsReady) {
        if ([string]::IsNullOrWhiteSpace($InputPackagePath)) {
            throw 'Frozen Reranker inputs are missing or drifted. Transfer the private input package and pass -InputPackagePath.'
        }
        $resolvedInputPackage = (Resolve-Path -LiteralPath $InputPackagePath).Path
        $actualPackageSha256 = (Get-FileHash -LiteralPath $resolvedInputPackage -Algorithm SHA256).Hash
        if ($actualPackageSha256 -ne $InputPackageSha256) {
            throw 'Frozen Reranker input package digest drifted.'
        }
        Expand-Archive -LiteralPath $resolvedInputPackage -DestinationPath $RepositoryRoot -Force
        $inputSource = 'VERIFIED_PRIVATE_PACKAGE'
    }

    foreach ($relativePath in $ExpectedPrivateInputs.Keys) {
        $privateInputPath = Join-Path -Path $RepositoryRoot -ChildPath $relativePath
        if (-not (Test-Path -LiteralPath $privateInputPath -PathType Leaf)) {
            throw "Frozen Reranker input is missing after package import: $relativePath"
        }
        $privateInputSha256 = (Get-FileHash -LiteralPath $privateInputPath -Algorithm SHA256).Hash
        if ($privateInputSha256 -ne $ExpectedPrivateInputs[$relativePath]) {
            throw "Frozen Reranker input digest drifted after package import: $relativePath"
        }
    }

    $nvidiaSmi = Get-Command -Name 'nvidia-smi.exe' -ErrorAction SilentlyContinue
    if ($null -eq $nvidiaSmi) {
        throw 'NVIDIA driver preflight failed: nvidia-smi.exe is unavailable.'
    }
    $nvidiaInfo = @(
        & $nvidiaSmi.Source '--query-gpu=index,name,driver_version' '--format=csv,noheader'
    )
    if ($LASTEXITCODE -ne 0 -or $nvidiaInfo.Count -eq 0) {
        throw 'NVIDIA driver preflight failed.'
    }

    & $PythonPath -m pip install --force-reinstall --no-deps $TorchPackage --index-url $TorchIndexUrl
    if ($LASTEXITCODE -ne 0) {
        throw 'Installing the pinned CUDA PyTorch wheel failed.'
    }

    & $PythonPath -m pip install -e '.[reranker]'
    if ($LASTEXITCODE -ne 0) {
        throw 'Installing the optional Reranker dependencies failed.'
    }
    & $PythonPath -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw 'Reranker dependency consistency check failed.'
    }

    $cudaProbe = "import json, torch; assert torch.__version__ == '2.13.0+cu126', 'PyTorch build drifted'; assert torch.version.cuda == '12.6', 'CUDA runtime drifted'; assert torch.cuda.is_available(), 'CUDA is unavailable'; gpu_name = torch.cuda.get_device_name(0); assert 'RTX 4090' in gpu_name, 'Target GPU is not RTX 4090'; tensor = torch.ones(1, device='cuda'); torch.cuda.synchronize(); print(json.dumps({'torch_version': torch.__version__, 'cuda_runtime': torch.version.cuda, 'gpu_name': gpu_name}, sort_keys=True))"
    $cudaInfoJson = & $PythonPath -c $cudaProbe
    if ($LASTEXITCODE -ne 0) {
        throw 'CUDA preflight failed.'
    }
    $cudaInfo = $cudaInfoJson | ConvertFrom-Json

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
        input_source = $inputSource
        input_package_sha256 = $InputPackageSha256
        torch_version = $cudaInfo.torch_version
        cuda_runtime = $cudaInfo.cuda_runtime
        gpu_name = $cudaInfo.gpu_name
        nvidia_smi = ($nvidiaInfo -join '; ')
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
