[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$InputPackagePath,
    [string]$ExpectedPackageSha256,
    [string]$ExpectedManifestSha256,
    [string]$DatabaseHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$DatabasePort = 5432,
    [string]$DatabaseName = 'zhiyan_stage1_canary',
    [string]$DatabaseUser = 'zhiyan_stage1_canary_app'
)

# Target: Windows PowerShell 5.1 on the user-operated Windows validation host.
$ErrorActionPreference = 'Stop'
$runId = 'phase3_candidate_ladder_20260809_01'
$confirmation = 'RUN_PHASE3_IDENTITY_MATCHED_CANDIDATE_LADDER_LOCALIZATION'
$databaseUrlCreatedByScript = $false
$inputRootCreatedByScript = $false
$decompositionSwitchExisted = (
    Test-Path -LiteralPath 'Env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED'
)
$originalDecompositionSwitch = $env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED
$routeCoverageSwitchExisted = (
    Test-Path -LiteralPath 'Env:PHASE3_COMPARISON_ROUTE_COVERAGE_ENABLED'
)
$originalRouteCoverageSwitch = $env:PHASE3_COMPARISON_ROUTE_COVERAGE_ENABLED

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
    if ($LASTEXITCODE -ne 0 -or $dirtyPaths.Count -ne 0) {
        throw 'Remote repository must have no tracked or staged changes.'
    }
    & git fetch origin main
    if ($LASTEXITCODE -ne 0) {
        throw 'git fetch origin main failed.'
    }
    $headCommit = (& git rev-parse HEAD).Trim()
    $originCommit = (& git rev-parse origin/main).Trim()
    if ($LASTEXITCODE -ne 0 -or $headCommit -ne $originCommit) {
        throw 'Remote HEAD must equal origin/main before this diagnostic.'
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
    if ($ExpectedPackageSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw 'Expected package SHA-256 is invalid.'
    }
    if ($ExpectedManifestSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw 'Expected manifest SHA-256 is invalid.'
    }

    $resolvedPackagePath = (Resolve-Path -LiteralPath $InputPackagePath).Path
    $actualPackageSha256 = (
        Get-FileHash -LiteralPath $resolvedPackagePath -Algorithm SHA256
    ).Hash
    if ($actualPackageSha256 -ne $ExpectedPackageSha256) {
        throw 'Private input ZIP SHA-256 drifted.'
    }

    $inputRoot = "runtime\phase3-candidate-ladder-$runId"
    if (Test-Path -LiteralPath $inputRoot) {
        throw 'The isolated input directory already exists; this Run ID is single-use.'
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
    $expectedTargetIds = @(
        'local3.assisted.0033',
        'local3.assisted.0304',
        'local3.assisted.0383',
        'local3.assisted.0387'
    )
    $observedTargetIds = @($manifest.target_question_ids)
    if (
        $manifest.schema_version -ne 'phase3_comparison_dev_input_manifest_v1' -or
        $manifest.split_boundary -ne 'DEV_ONLY_TEST_AND_ACCEPTANCE_EXCLUDED' -or
        $manifest.target_ids_sha256 -ne (
            '3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8'
        ) -or
        $observedTargetIds.Count -ne 4
    ) {
        throw 'Extracted manifest cohort contract is invalid.'
    }
    for ($index = 0; $index -lt $expectedTargetIds.Count; $index += 1) {
        if ($observedTargetIds[$index] -ne $expectedTargetIds[$index]) {
            throw 'Extracted manifest cohort identity drifted.'
        }
    }
    foreach ($artifact in @($manifest.artifacts)) {
        $artifactPath = Join-Path $inputRoot $artifact.path
        if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
            throw 'A manifest artifact is missing.'
        }
        $artifactSha256 = (
            Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256
        ).Hash
        if ($artifactSha256 -ne $artifact.sha256) {
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

    $env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED = 'false'
    $env:PHASE3_COMPARISON_ROUTE_COVERAGE_ENABLED = 'false'
    $outputPath = "runtime\phase3-candidate-ladder-$runId-report.json"
    $arguments = @(
        'scripts/run_phase3_candidate_ladder_localization.py',
        '--input-root',
        $inputRoot,
        '--expected-manifest-sha256',
        $ExpectedManifestSha256.ToLowerInvariant(),
        '--run-id',
        $runId,
        '--expected-head-commit',
        $headCommit,
        '--confirm',
        $confirmation,
        '--output',
        $outputPath
    )
    & $PythonPath @arguments
    $runnerExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
        throw 'Candidate-ladder runner did not write a report.'
    }
    $report = Get-Content -LiteralPath $outputPath -Raw | ConvertFrom-Json
    $reportSha256 = (
        Get-FileHash -LiteralPath $outputPath -Algorithm SHA256
    ).Hash
    $adjudicationPath = (
        "runtime\phase3-candidate-ladder-$runId-adjudication.json"
    )
    $adjudicationArguments = @(
        'scripts/adjudicate_phase3_candidate_ladder_report.py',
        '--report',
        $outputPath,
        '--expected-report-sha256',
        $reportSha256.ToLowerInvariant(),
        '--expected-head-commit',
        $headCommit,
        '--expected-input-manifest-sha256',
        $ExpectedManifestSha256.ToLowerInvariant(),
        '--expected-run-id',
        $runId,
        '--output',
        $adjudicationPath
    )
    & $PythonPath @adjudicationArguments
    $adjudicationExitCode = $LASTEXITCODE
    $adjudication = (
        Get-Content -LiteralPath $adjudicationPath -Raw | ConvertFrom-Json
    )
    $adjudicationSha256 = (
        Get-FileHash -LiteralPath $adjudicationPath -Algorithm SHA256
    ).Hash

    $summary = [ordered]@{
        run_id = $runId
        head_commit = $headCommit
        runner_exit_code = $runnerExitCode
        report_status = $report.status
        experiment_decision = $adjudication.experiment_decision
        report_sha256 = $reportSha256
        adjudication_status = $adjudication.status
        adjudication_sha256 = $adjudicationSha256
        case_count = $adjudication.case_count
        cleanup = $adjudication.cleanup
        strategy_handoff = 'NO_NEXT_ALGORITHM_SELECTED'
        report_path = $outputPath
        adjudication_path = $adjudicationPath
    }
    $summary | ConvertTo-Json -Depth 5
    if ($runnerExitCode -ne 0 -or $adjudicationExitCode -ne 0) {
        throw 'Candidate-ladder localization did not produce an admissible decision.'
    }
}
finally {
    if ($inputRootCreatedByScript -and (Test-Path -LiteralPath $inputRoot)) {
        Remove-Item -LiteralPath $inputRoot -Recurse -Force
    }
    if ($databaseUrlCreatedByScript) {
        Remove-Item -LiteralPath 'Env:DATABASE_URL' -ErrorAction SilentlyContinue
    }
    if ($decompositionSwitchExisted) {
        $env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED = $originalDecompositionSwitch
    }
    else {
        Remove-Item `
            -LiteralPath 'Env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED' `
            -ErrorAction SilentlyContinue
    }
    if ($routeCoverageSwitchExisted) {
        $env:PHASE3_COMPARISON_ROUTE_COVERAGE_ENABLED = $originalRouteCoverageSwitch
    }
    else {
        Remove-Item `
            -LiteralPath 'Env:PHASE3_COMPARISON_ROUTE_COVERAGE_ENABLED' `
            -ErrorAction SilentlyContinue
    }
    Pop-Location
}
