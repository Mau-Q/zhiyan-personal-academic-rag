[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [Parameter(Mandatory = $true)]
    [string]$InputPackagePath,
    [string]$ModelCachePath
)

# Target: Windows PowerShell 5.1 on the user-operated RTX 4090 host.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Join-Path -Path $PSScriptRoot -ChildPath '..\..\..'
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if ([string]::IsNullOrWhiteSpace($ModelCachePath)) {
    $ModelCachePath = Join-Path `
        -Path $RepositoryRoot `
        -ChildPath 'runtime\models\phase4-multilingual-nli'
}

$expectedPackageSha256 = 'EF3FC1288FD78CD886793959C886C0AC2CE62AB822D556FA8527EE7C58E53B18'
$expectedInputSha256 = '13B7DDFB0185BA03F251664366D5AB28A0CAE64ADDA9EF9A57DA563BE0AE2C6E'
$expectedConfigSha256 = '08722F95BDE2AF91C4138FD1E7E863B55F39F843DDE0290A84578B309D470C3E'
$expectedReviewSha256 = '0E17DBA081CDEF7EBBAA0CD101EE3B629F62ED65517CB295C1D9918F839AFD8C'
$expectedRevision = 'b5113eb38ab63efdd7f280f8c144ea8b13f978ce'
$expectedSnapshotSha256 = '7E973B42BF69D9475C065D4DEB04745659BADF94CE054FD1DE0F9CC1CAEEAFD5'
$expectedTorchVersion = '2.13.0+cu126'
$torchIndexUrl = 'https://download.pytorch.org/whl/cu126'
$inputMember = 'dev-claim-evidence-review-input-v1.jsonl'
$configPath = Join-Path `
    -Path $RepositoryRoot `
    -ChildPath 'evaluation\claim_evidence\phase4-multilingual-nli-rtx4090-v1.json'
$reviewPath = Join-Path `
    -Path $RepositoryRoot `
    -ChildPath 'evaluation\reviews\member_b\dev-claim-evidence-second-review-v1.csv'
$importDirectory = Join-Path `
    -Path $RepositoryRoot `
    -ChildPath 'runtime\handoffs\phase4-nli-dev-input-v1'
$privateInputPath = Join-Path -Path $importDirectory -ChildPath $inputMember
$outputDirectory = Join-Path `
    -Path $RepositoryRoot `
    -ChildPath 'runtime\phases\phase4-multilingual-nli-rtx4090-v1'
$reportPath = Join-Path -Path $outputDirectory -ChildPath 'report.json'
$runnerPath = Join-Path `
    -Path $RepositoryRoot `
    -ChildPath 'scripts\run_phase4_multilingual_nli_gate.py'

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    return (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash
}

function Get-LfCanonicalTextSha256 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    [byte[]]$payload = [System.IO.File]::ReadAllBytes($LiteralPath)
    $canonical = New-Object 'System.Collections.Generic.List[byte]'
    for ($index = 0; $index -lt $payload.Length; $index += 1) {
        if ($payload[$index] -ne 13) {
            $canonical.Add($payload[$index])
            continue
        }
        if (
            $index + 1 -ge $payload.Length -or
            $payload[$index + 1] -ne 10
        ) {
            throw 'NLI_TEXT_LINE_ENDING_INVALID'
        }
        $canonical.Add(10)
        $index += 1
    }
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $hasher.ComputeHash($canonical.ToArray())
    }
    finally {
        $hasher.Dispose()
    }
    return (
        [System.BitConverter]::ToString($digest).Replace('-', '')
    )
}

function Assert-FileHash {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [Parameter(Mandatory = $true)][string]$FailureCode
    )
    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) {
        throw $FailureCode
    }
    if ((Get-Sha256 -LiteralPath $LiteralPath) -ne $ExpectedSha256) {
        throw $FailureCode
    }
}

Push-Location $RepositoryRoot
try {
    $dirtyPaths = @(& git status --porcelain --untracked-files=no)
    if ($LASTEXITCODE -ne 0 -or $dirtyPaths.Count -ne 0) {
        throw 'NLI_TRACKED_WORKTREE_NOT_CLEAN'
    }
    & git fetch origin main
    if ($LASTEXITCODE -ne 0) {
        throw 'NLI_GIT_FETCH_FAILED'
    }
    $headCommit = (& git rev-parse HEAD).Trim()
    $originCommit = (& git rev-parse origin/main).Trim()
    if ($LASTEXITCODE -ne 0 -or $headCommit -ne $originCommit) {
        throw 'NLI_HEAD_MUST_EQUAL_ORIGIN_MAIN'
    }

    if (
        (Get-LfCanonicalTextSha256 -LiteralPath $configPath) -ne
        $expectedConfigSha256
    ) {
        throw 'NLI_CONFIG_HASH_DRIFT'
    }
    if (
        (Get-LfCanonicalTextSha256 -LiteralPath $reviewPath) -ne
        $expectedReviewSha256
    ) {
        throw 'NLI_CANDIDATE_REVIEW_HASH_DRIFT'
    }

    $inputSource = 'EXISTING_EXACT_PRIVATE_INPUT'
    if (Test-Path -LiteralPath $privateInputPath -PathType Leaf) {
        Assert-FileHash `
            -LiteralPath $privateInputPath `
            -ExpectedSha256 $expectedInputSha256 `
            -FailureCode 'NLI_EXISTING_PRIVATE_INPUT_HASH_DRIFT'
    }
    else {
        if (Test-Path -LiteralPath $importDirectory) {
            throw 'NLI_IMPORT_DIRECTORY_EXISTS_WITHOUT_EXACT_INPUT'
        }
        $InputPackagePath = (Resolve-Path -LiteralPath $InputPackagePath).Path
        Assert-FileHash `
            -LiteralPath $InputPackagePath `
            -ExpectedSha256 $expectedPackageSha256 `
            -FailureCode 'NLI_PRIVATE_PACKAGE_HASH_DRIFT'
        New-Item -ItemType Directory -Path $importDirectory | Out-Null
        Expand-Archive `
            -LiteralPath $InputPackagePath `
            -DestinationPath $importDirectory
        Assert-FileHash `
            -LiteralPath $privateInputPath `
            -ExpectedSha256 $expectedInputSha256 `
            -FailureCode 'NLI_EXTRACTED_PRIVATE_INPUT_HASH_DRIFT'
        $inputSource = 'VERIFIED_EXTRACTED_PACKAGE'
    }

    $smiName = (& nvidia-smi --query-gpu=name --format=csv,noheader).Trim()
    if ($LASTEXITCODE -ne 0 -or $smiName -notmatch 'RTX 4090') {
        throw 'NLI_NVIDIA_RTX4090_REQUIRED'
    }

    & .\.venv\Scripts\python.exe -m pip install `
        "torch==$expectedTorchVersion" `
        --index-url $torchIndexUrl
    if ($LASTEXITCODE -ne 0) {
        throw 'NLI_TORCH_INSTALL_FAILED'
    }
    & .\.venv\Scripts\python.exe -m pip install -e '.[reranker]'
    if ($LASTEXITCODE -ne 0) {
        throw 'NLI_PROJECT_INSTALL_FAILED'
    }
    & .\.venv\Scripts\python.exe -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw 'NLI_PIP_CHECK_FAILED'
    }

    $cudaProbe = @'
import json
import torch
ok = (
    torch.__version__ == "2.13.0+cu126"
    and torch.version.cuda == "12.6"
    and torch.cuda.is_available()
    and "RTX 4090" in torch.cuda.get_device_name(0)
)
if not ok:
    raise SystemExit(2)
x = torch.ones((32, 32), device="cuda")
print(json.dumps({
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "gpu": torch.cuda.get_device_name(0),
    "allocation_sum": float(x.sum().item()),
}, sort_keys=True))
'@
    $cudaResultText = $cudaProbe | & .\.venv\Scripts\python.exe -
    if ($LASTEXITCODE -ne 0) {
        throw 'NLI_CUDA_ALLOCATION_PROBE_FAILED'
    }
    $cudaResult = $cudaResultText | ConvertFrom-Json

    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path $ModelCachePath | Out-Null
    & .\.venv\Scripts\python.exe $runnerPath `
        --config $configPath `
        --config-sha256 $expectedConfigSha256.ToLowerInvariant() `
        --private-input $privateInputPath `
        --model-cache $ModelCachePath `
        --output $reportPath
    if ($LASTEXITCODE -ne 0) {
        throw 'NLI_REMOTE_RUNNER_FAILED'
    }

    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if (
        $report.schema_version -ne 'phase4_multilingual_nli_candidate_report_v1' -or
        $report.model.revision -ne $expectedRevision -or
        $report.model.snapshot_sha256 -ne $expectedSnapshotSha256.ToLowerInvariant() -or
        $report.positive_diagnostics.candidate_supported_total -ne 21 -or
        $report.positive_diagnostics.human_finalized_positive_total -ne 225 -or
        $report.benchmark.pair_count -ne 16 -or
        $report.benchmark.repetitions -ne 30 -or
        $report.input_sha256.private_input -ne $expectedInputSha256.ToLowerInvariant() -or
        $report.input_sha256.candidate_review -ne $expectedReviewSha256.ToLowerInvariant() -or
        $report.decision.online_enforcement_enabled -ne $false -or
        $report.decision.candidate_promoted_to_truth -ne $false -or
        $report.unavailable_metrics.precision -ne 'NOT_MEASURABLE_NO_HUMAN_ADJUDICATED_NEGATIVES' -or
        $report.unavailable_metrics.human_agreement -ne 'NOT_MEASURABLE_AI_ASSISTED_CANDIDATE'
    ) {
        throw 'NLI_REPORT_CONTRACT_INVALID'
    }

    [pscustomobject]@{
        status = 'PASS'
        head_commit = $headCommit
        input_source = $inputSource
        input_package_sha256 = if ($inputSource -eq 'VERIFIED_EXTRACTED_PACKAGE') {
            $expectedPackageSha256.ToLowerInvariant()
        }
        else {
            'NOT_USED_EXISTING_EXACT_PRIVATE_INPUT'
        }
        torch_version = $cudaResult.torch
        cuda_runtime = $cudaResult.cuda
        gpu_name = $cudaResult.gpu
        model_revision = $expectedRevision
        model_snapshot_sha256 = $expectedSnapshotSha256.ToLowerInvariant()
        unique_pair_count = $report.workload.unique_pair_count
        truncated_pair_count = $report.workload.truncated_pair_count
        candidate_supported_retention = (
            $report.positive_diagnostics.candidate_supported_retention
        )
        human_finalized_positive_retention = (
            $report.positive_diagnostics.human_finalized_positive_retention
        )
        component_pair_count = $report.benchmark.pair_count
        component_latency_ms_p50 = $report.benchmark.latency_ms_p50
        component_latency_ms_p95 = $report.benchmark.latency_ms_p95
        quality_decision = $report.decision.decision
        online_enforcement_enabled = $false
        report_sha256 = (Get-Sha256 -LiteralPath $reportPath).ToLowerInvariant()
        stable_error_code = 'NONE'
    } | ConvertTo-Json -Depth 4
}
finally {
    Pop-Location
}
