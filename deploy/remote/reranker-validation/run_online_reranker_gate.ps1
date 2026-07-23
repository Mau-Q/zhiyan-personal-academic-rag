[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$PdfPath,
    [string]$ExpectedPdfSha256,
    [string]$QuestionSuitePath,
    [string]$ExpectedQuestionSuiteSha256,
    [string]$DocumentTitle,
    [string]$RunId,
    [string]$DatabaseHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$DatabasePort = 5432,
    [string]$DatabaseName = 'zhiyan_stage1_canary',
    [string]$DatabaseUser = 'zhiyan_stage1_canary_app'
)

$ErrorActionPreference = 'Stop'
$databaseUrlCreatedByScript = $false
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Join-Path -Path $PSScriptRoot -ChildPath '..\..\..'
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$PythonPath = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
$RerankerConfig = 'evaluation/reranker/online-fixed-cross-encoder-windows-rtx4090-v1.json'

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Project Python is missing at $PythonPath"
}
if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot $RerankerConfig) -PathType Leaf)) {
    throw 'Online Reranker config is missing.'
}

Push-Location $RepositoryRoot
try {
    $dirtyPaths = @(& git status --porcelain --untracked-files=no)
    if ($LASTEXITCODE -ne 0) {
        throw 'git status failed.'
    }
    if ($dirtyPaths.Count -ne 0) {
        throw 'Remote repository must have no tracked or staged changes before the Online Reranker Gate.'
    }

    & git fetch origin main
    if ($LASTEXITCODE -ne 0) {
        throw 'git fetch origin main failed.'
    }
    $headCommit = (& git rev-parse HEAD).Trim()
    $originCommit = (& git rev-parse origin/main).Trim()
    if ($LASTEXITCODE -ne 0 -or $headCommit -ne $originCommit) {
        throw 'Remote HEAD must equal origin/main before the Online Reranker Gate.'
    }

    & $PythonPath -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw 'Project dependency consistency check failed.'
    }
    $cudaProbe = "import torch; assert torch.__version__ == '2.13.0+cu126'; assert torch.version.cuda == '12.6'; assert torch.cuda.is_available(); assert 'RTX 4090' in torch.cuda.get_device_name(0); torch.ones(1, device='cuda'); torch.cuda.synchronize()"
    & $PythonPath -c $cudaProbe
    if ($LASTEXITCODE -ne 0) {
        throw 'Pinned RTX 4090 CUDA preflight failed.'
    }

    if ([string]::IsNullOrWhiteSpace($PdfPath)) {
        $PdfPath = Read-Host 'Private PDF path'
    }
    if ([string]::IsNullOrWhiteSpace($ExpectedPdfSha256)) {
        $ExpectedPdfSha256 = Read-Host 'Expected PDF SHA-256'
    }
    if ([string]::IsNullOrWhiteSpace($QuestionSuitePath)) {
        $QuestionSuitePath = Read-Host 'Private academic question-suite path'
    }
    if ([string]::IsNullOrWhiteSpace($ExpectedQuestionSuiteSha256)) {
        $ExpectedQuestionSuiteSha256 = Read-Host 'Expected question-suite SHA-256'
    }
    if ([string]::IsNullOrWhiteSpace($DocumentTitle)) {
        $DocumentTitle = Read-Host 'Exact document title for the frozen input template'
    }
    if ([string]::IsNullOrWhiteSpace($RunId)) {
        $RunId = Read-Host 'New non-secret Canary run ID'
    }

    if ($ExpectedPdfSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw 'Expected PDF SHA-256 is invalid.'
    }
    if ($ExpectedQuestionSuiteSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw 'Expected question-suite SHA-256 is invalid.'
    }
    if ([string]::IsNullOrWhiteSpace($DocumentTitle)) {
        throw 'Document title is required.'
    }
    if ($RunId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$') {
        throw 'Canary run ID is invalid.'
    }

    $resolvedPdfPath = (Resolve-Path -LiteralPath $PdfPath).Path
    $resolvedQuestionSuitePath = (Resolve-Path -LiteralPath $QuestionSuitePath).Path
    $actualPdfSha256 = (Get-FileHash -LiteralPath $resolvedPdfPath -Algorithm SHA256).Hash
    if ($actualPdfSha256 -ne $ExpectedPdfSha256) {
        throw 'Private PDF SHA-256 drifted.'
    }
    $actualQuestionSuiteSha256 = (
        Get-FileHash -LiteralPath $resolvedQuestionSuitePath -Algorithm SHA256
    ).Hash
    if ($actualQuestionSuiteSha256 -ne $ExpectedQuestionSuiteSha256) {
        throw 'Private question-suite SHA-256 drifted.'
    }
    $questionSuite = Get-Content -LiteralPath $resolvedQuestionSuitePath -Raw |
        ConvertFrom-Json
    if (@($questionSuite.cases).Count -ne 3) {
        throw 'Online Reranker Gate requires the frozen three-case document suite.'
    }
    $relativeQuestionSuitePath = Resolve-Path `
        -LiteralPath $resolvedQuestionSuitePath `
        -Relative
    if (-not $relativeQuestionSuitePath.StartsWith('.\runtime\')) {
        throw 'Question suite must be under the repository runtime directory.'
    }
    $relativeQuestionSuitePath = $relativeQuestionSuitePath.Substring(2)
    $outputPath = "runtime/stage1-remote-validation/online-reranker-$RunId.json"

    if (-not (Test-Path -LiteralPath 'Env:DATABASE_URL')) {
        $secureDatabasePassword = Read-Host `
            -Prompt "PostgreSQL password for $DatabaseUser" `
            -AsSecureString
        $databasePasswordPointer = [IntPtr]::Zero
        try {
            $databasePasswordPointer = (
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
                    $secureDatabasePassword
                )
            )
            $plainDatabasePassword = (
                [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
                    $databasePasswordPointer
                )
            )
            $encodedDatabaseUser = [Uri]::EscapeDataString($DatabaseUser)
            $encodedDatabasePassword = [Uri]::EscapeDataString(
                $plainDatabasePassword
            )
            $encodedDatabaseName = [Uri]::EscapeDataString($DatabaseName)
            $env:DATABASE_URL = (
                'postgresql://{0}:{1}@{2}:{3}/{4}' -f
                $encodedDatabaseUser,
                $encodedDatabasePassword,
                $DatabaseHost,
                $DatabasePort,
                $encodedDatabaseName
            )
            $databaseUrlCreatedByScript = $true
        }
        finally {
            if ($databasePasswordPointer -ne [IntPtr]::Zero) {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR(
                    $databasePasswordPointer
                )
            }
            Remove-Variable `
                plainDatabasePassword, encodedDatabasePassword `
                -ErrorAction SilentlyContinue
            Remove-Variable secureDatabasePassword -ErrorAction SilentlyContinue
        }
    }

    $arguments = @(
        'scripts/run_stage1_remote_canary.py',
        '--pdf',
        $resolvedPdfPath,
        '--expected-sha256',
        $ExpectedPdfSha256.ToLowerInvariant(),
        '--run-id',
        $RunId,
        '--confirm',
        'RUN_ISOLATED_STAGE1_CANARY',
        '--output',
        $outputPath,
        '--question-suite',
        $relativeQuestionSuitePath,
        '--expected-question-suite-sha256',
        $ExpectedQuestionSuiteSha256.ToLowerInvariant(),
        '--online-reranker-config',
        $RerankerConfig,
        '--online-reranker-document-title',
        $DocumentTitle,
        '--online-reranker-latency-repetitions',
        '10'
    )
    & $PythonPath @arguments
    $pythonExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
        throw 'Online Reranker Gate did not write a report.'
    }
    $report = Get-Content -LiteralPath $outputPath -Raw | ConvertFrom-Json
    if ($pythonExitCode -ne 0) {
        if ($report.status -ne 'FAIL') {
            throw 'Online Reranker Gate failed without a closed failure report.'
        }
        [ordered]@{
            schema_version = 'online_reranker_remote_summary_v1'
            head_commit = $headCommit
            status = $report.status
            model_id = $report.online_reranker.model.model_id
            model_revision = $report.online_reranker.model.revision
            model_snapshot_sha256 = $report.online_reranker.model.snapshot_sha256
            sample_count = $report.online_reranker.sample_count
            applied_count = $report.online_reranker.applied_count
            base_retrieval_latency_ms_p50 = $report.online_reranker.base_retrieval_latency_ms_p50
            base_retrieval_latency_ms_p95 = $report.online_reranker.base_retrieval_latency_ms_p95
            combined_retrieval_latency_ms_p50 = $report.online_reranker.combined_retrieval_latency_ms_p50
            combined_retrieval_latency_ms_p95 = $report.online_reranker.combined_retrieval_latency_ms_p95
            reranker_latency_ms_p50 = $report.online_reranker.reranker_latency_ms_p50
            reranker_latency_ms_p95 = $report.online_reranker.reranker_latency_ms_p95
            fallback_count = $report.online_reranker.fallback_count
            candidate_set_expanded = $report.online_reranker.candidate_set_expanded
            candidate_bound_violated = $report.online_reranker.candidate_bound_violated
            cleanup_jobs_succeeded = $report.cleanup_jobs_succeeded
            inactive_answer_api_status = $report.inactive_answer_api_status
            report_sha256 = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash
            stable_error_code = $report.error_code
        } | ConvertTo-Json -Depth 4
        throw 'Online Reranker Gate failed.'
    }

    if ($report.status -ne 'PASS') {
        throw 'Online Reranker report did not pass.'
    }
    if ($report.online_reranker.status -ne 'PASS') {
        throw 'Online Reranker was not applied successfully.'
    }
    if (
        $report.online_reranker.sample_count -lt 30 -or
        $report.online_reranker.applied_count -ne $report.online_reranker.sample_count
    ) {
        throw 'Online Reranker latency sample count is insufficient.'
    }
    if ($report.online_reranker.combined_retrieval_latency_ms_p95 -gt 300) {
        throw 'Online Reranker combined retrieval P95 exceeded 300 ms.'
    }
    if (
        $report.online_reranker.fallback_count -ne 0 -or
        $report.online_reranker.candidate_set_expanded -ne $false -or
        $report.online_reranker.candidate_bound_violated -ne $false
    ) {
        throw 'Online Reranker fallback or candidate expansion was observed.'
    }
    if (
        $report.cleanup_jobs_succeeded -ne 3 -or
        $report.inactive_answer_api_status -ne 403
    ) {
        throw 'Online Reranker Canary lifecycle cleanup did not close.'
    }

    [ordered]@{
        schema_version = 'online_reranker_remote_summary_v1'
        head_commit = $headCommit
        status = $report.status
        model_id = $report.online_reranker.model.model_id
        model_revision = $report.online_reranker.model.revision
        model_snapshot_sha256 = $report.online_reranker.model.snapshot_sha256
        sample_count = $report.online_reranker.sample_count
        applied_count = $report.online_reranker.applied_count
        base_retrieval_latency_ms_p50 = $report.online_reranker.base_retrieval_latency_ms_p50
        base_retrieval_latency_ms_p95 = $report.online_reranker.base_retrieval_latency_ms_p95
        combined_retrieval_latency_ms_p50 = $report.online_reranker.combined_retrieval_latency_ms_p50
        combined_retrieval_latency_ms_p95 = $report.online_reranker.combined_retrieval_latency_ms_p95
        reranker_latency_ms_p50 = $report.online_reranker.reranker_latency_ms_p50
        reranker_latency_ms_p95 = $report.online_reranker.reranker_latency_ms_p95
        fallback_count = $report.online_reranker.fallback_count
        candidate_set_expanded = $report.online_reranker.candidate_set_expanded
        candidate_bound_violated = $report.online_reranker.candidate_bound_violated
        cleanup_jobs_succeeded = $report.cleanup_jobs_succeeded
        inactive_answer_api_status = $report.inactive_answer_api_status
        report_sha256 = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash
        stable_error_code = 'NONE'
    } | ConvertTo-Json -Depth 4
}
finally {
    try {
        Pop-Location
    }
    finally {
        if ($databaseUrlCreatedByScript) {
            Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
        }
    }
}
