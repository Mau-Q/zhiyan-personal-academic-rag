[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$InputPackagePath,
    [string]$ExpectedPackageSha256,
    [string]$ExpectedManifestSha256,
    [string]$RunId,
    [string]$DatabaseHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$DatabasePort = 5432,
    [string]$DatabaseName = 'zhiyan_stage1_canary',
    [string]$DatabaseUser = 'zhiyan_stage1_canary_app'
)

# Target: Windows PowerShell 5.1 on the user-operated Windows validation host.
$ErrorActionPreference = 'Stop'
$databaseUrlCreatedByScript = $false
$inputRootCreatedByScript = $false
$phase3SwitchExisted = Test-Path -LiteralPath 'Env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED'
$originalPhase3Switch = $env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Join-Path -Path $PSScriptRoot -ChildPath '..\..\..'
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$PythonPath = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'

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
        throw 'Remote repository must have no tracked or staged changes before this Gate.'
    }

    & git fetch origin main
    if ($LASTEXITCODE -ne 0) {
        throw 'git fetch origin main failed.'
    }
    $headCommit = (& git rev-parse HEAD).Trim()
    $originCommit = (& git rev-parse origin/main).Trim()
    if ($LASTEXITCODE -ne 0 -or $headCommit -ne $originCommit) {
        throw 'Remote HEAD must equal origin/main before this Gate.'
    }

    & $PythonPath -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw 'Project dependency consistency check failed.'
    }

    if ([string]::IsNullOrWhiteSpace($InputPackagePath)) {
        $InputPackagePath = Read-Host 'Private Phase 3 dev input ZIP path'
    }
    if ([string]::IsNullOrWhiteSpace($ExpectedPackageSha256)) {
        $ExpectedPackageSha256 = Read-Host 'Expected input ZIP SHA-256'
    }
    if ([string]::IsNullOrWhiteSpace($ExpectedManifestSha256)) {
        $ExpectedManifestSha256 = Read-Host 'Expected manifest SHA-256'
    }
    if ([string]::IsNullOrWhiteSpace($RunId)) {
        $RunId = Read-Host 'New non-secret Phase 3 dev run ID'
    }
    if ($ExpectedPackageSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw 'Expected package SHA-256 is invalid.'
    }
    if ($ExpectedManifestSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw 'Expected manifest SHA-256 is invalid.'
    }
    if ($RunId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$') {
        throw 'Run ID is invalid.'
    }

    $resolvedPackagePath = (Resolve-Path -LiteralPath $InputPackagePath).Path
    $actualPackageSha256 = (
        Get-FileHash -LiteralPath $resolvedPackagePath -Algorithm SHA256
    ).Hash
    if ($actualPackageSha256 -ne $ExpectedPackageSha256) {
        throw 'Private input ZIP SHA-256 drifted.'
    }

    $inputRoot = "runtime\phase3-comparison-paired-dev-$RunId"
    if (Test-Path -LiteralPath $inputRoot) {
        throw 'The isolated input directory already exists; choose a new run ID.'
    }
    Expand-Archive -LiteralPath $resolvedPackagePath -DestinationPath $inputRoot
    $inputRootCreatedByScript = $true
    $manifestPath = Join-Path $inputRoot 'manifest.json'
    $actualManifestSha256 = (
        Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256
    ).Hash
    if ($actualManifestSha256 -ne $ExpectedManifestSha256) {
        throw 'Extracted manifest SHA-256 drifted.'
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if (
        $manifest.schema_version -ne 'phase3_comparison_dev_input_manifest_v1' -or
        $manifest.split_boundary -ne 'DEV_ONLY_TEST_AND_ACCEPTANCE_EXCLUDED' -or
        $manifest.strategy -ne 'section_parent_child_v1' -or
        @($manifest.target_question_ids).Count -ne 4 -or
        @($manifest.artifacts).Count -ne 6
    ) {
        throw 'Extracted manifest contract is invalid.'
    }
    foreach ($artifact in @($manifest.artifacts)) {
        $artifactPath = Join-Path $inputRoot $artifact.path
        if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
            throw 'A manifest artifact is missing.'
        }
        $actualArtifactSha256 = (
            Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256
        ).Hash
        if ($actualArtifactSha256 -ne $artifact.sha256) {
            throw 'A manifest artifact SHA-256 drifted.'
        }
    }

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

    # The repository-wide default remains disabled. The runner constructs the
    # Treatment planner only inside this isolated Control/Treatment process.
    $env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED = 'false'
    $outputPath = "runtime\phase3-comparison-paired-dev-$RunId-report.json"
    $arguments = @(
        'scripts/run_phase3_comparison_paired_dev_gate.py',
        '--input-root',
        $inputRoot,
        '--expected-manifest-sha256',
        $ExpectedManifestSha256.ToLowerInvariant(),
        '--run-id',
        $RunId,
        '--expected-head-commit',
        $headCommit,
        '--confirm',
        'RUN_ISOLATED_PHASE3_COMPARISON_DEV_GATE',
        '--output',
        $outputPath,
        '--latency-repetitions',
        '30'
    )
    & $PythonPath @arguments
    $pythonExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
        throw 'Phase 3 paired dev Gate did not write a report.'
    }
    $report = Get-Content -LiteralPath $outputPath -Raw | ConvertFrom-Json
    $reportSha256 = (
        Get-FileHash -LiteralPath $outputPath -Algorithm SHA256
    ).Hash
    $adjudicationPath = (
        "runtime\phase3-comparison-paired-dev-$RunId-adjudication.json"
    )
    $adjudicationArguments = @(
        'scripts/adjudicate_phase3_comparison_paired_dev_report.py',
        '--report',
        $outputPath,
        '--expected-report-sha256',
        $reportSha256.ToLowerInvariant(),
        '--expected-head-commit',
        $headCommit,
        '--expected-run-id',
        $RunId,
        '--expected-input-manifest-sha256',
        $ExpectedManifestSha256.ToLowerInvariant(),
        '--output',
        $adjudicationPath
    )
    & $PythonPath @adjudicationArguments
    $adjudicationExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $adjudicationPath -PathType Leaf)) {
        throw 'Phase 3 report adjudicator did not write a decision.'
    }
    $adjudication = (
        Get-Content -LiteralPath $adjudicationPath -Raw | ConvertFrom-Json
    )
    $summary = [ordered]@{
        schema_version = 'phase3_comparison_paired_dev_summary_v1'
        head_commit = $headCommit
        status = $report.status
        stable_error_code = $report.error_code
        input_manifest_sha256 = $report.input_manifest_sha256
        config_sha256 = $report.config_sha256
        target_ids_sha256 = $report.target_ids_sha256
        control_strict_two_sided_passed = $report.control.strict_two_sided_passed
        treatment_strict_two_sided_passed = $report.treatment.strict_two_sided_passed
        strict_two_sided_absolute_gain = $report.gains.strict_two_sided_absolute_gain
        macro_recall_at_3_absolute_gain = $report.gains.macro_recall_at_3_absolute_gain
        macro_ndcg_at_3_absolute_gain = $report.gains.macro_ndcg_at_3_absolute_gain
        non_target_recall_at_3_drop = $report.critical_non_regression.recall_at_3_drop
        non_target_ndcg_at_10_drop = $report.critical_non_regression.ndcg_at_10_drop
        fixed_15_canary_passed = $report.fixed_15_canary.passed
        control_retrieval_p95_ms = $report.cost.control_retrieval_p95_ms
        treatment_retrieval_p95_ms = $report.cost.treatment_retrieval_p95_ms
        incremental_retrieval_p95_ms = $report.cost.incremental_retrieval_p95_ms
        decomposition_p95_ms = $report.cost.decomposition_p95_ms
        cleanup_status = $report.cleanup.status
        cleanup_jobs_succeeded = $report.cleanup.jobs_succeeded
        deleted_answer_api_status = $report.cleanup.deleted_answer_api_status
        performance_boundary = $report.performance_boundary
        test_status = $report.split_isolation.test
        acceptance_status = $report.split_isolation.acceptance
        report_sha256 = $reportSha256
        adjudication_status = $adjudication.status
        adjudication_decision = $adjudication.decision
        adjudicated_test_gate = $adjudication.test_gate
        adjudicated_acceptance = $adjudication.acceptance
        adjudication_sha256 = (
            Get-FileHash -LiteralPath $adjudicationPath -Algorithm SHA256
        ).Hash
    }
    $summary | ConvertTo-Json -Depth 4
    if (
        $pythonExitCode -ne 0 -or
        $report.status -ne 'PASS' -or
        $adjudicationExitCode -ne 0 -or
        $adjudication.status -ne 'PASS'
    ) {
        throw 'Phase 3 paired dev Gate failed closed.'
    }
    if (
        $report.cleanup.status -ne 'PASS' -or
        $report.cleanup.jobs_succeeded -ne 9 -or
        $report.cleanup.deleted_answer_api_status -ne 403
    ) {
        throw 'Phase 3 paired dev cleanup proof is incomplete.'
    }
}
finally {
    if ($inputRootCreatedByScript -and (Test-Path -LiteralPath $inputRoot)) {
        Remove-Item -LiteralPath $inputRoot -Recurse -Force
    }
    if ($databaseUrlCreatedByScript) {
        Remove-Item -LiteralPath 'Env:DATABASE_URL' -ErrorAction SilentlyContinue
    }
    if ($phase3SwitchExisted) {
        $env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED = $originalPhase3Switch
    }
    else {
        Remove-Item `
            -LiteralPath 'Env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED' `
            -ErrorAction SilentlyContinue
    }
    Remove-Variable originalPhase3Switch -ErrorAction SilentlyContinue
    Pop-Location
}
