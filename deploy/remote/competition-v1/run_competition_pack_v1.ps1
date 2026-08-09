[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedHeadCommit,
    [string]$SourcePackageRoot,
    [string]$RunId
)

# Target: Windows PowerShell 5.1 on the user-operated competition host.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Join-Path -Path $PSScriptRoot -ChildPath '..\..\..'
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if ([string]::IsNullOrWhiteSpace($ExpectedHeadCommit)) {
    $ExpectedHeadCommit = Read-Host 'Expected 40-character competition commit'
}
if ($ExpectedHeadCommit -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'COMPETITION_EXPECTED_COMMIT_INVALID'
}
if ([string]::IsNullOrWhiteSpace($SourcePackageRoot)) {
    $SourcePackageRoot = Read-Host 'Repository-relative Phase-2 V2 package directory under runtime'
}
if ([string]::IsNullOrWhiteSpace($RunId)) {
    $RunId = Read-Host 'New non-secret competition Run ID'
}
if ($RunId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$') {
    throw 'COMPETITION_RUN_ID_INVALID'
}
if (
    [System.IO.Path]::IsPathRooted($SourcePackageRoot) -or
    -not $SourcePackageRoot.StartsWith('runtime\')
) {
    throw 'COMPETITION_SOURCE_PACKAGE_MUST_BE_UNDER_RUNTIME'
}

$python = Join-Path -Path $RepositoryRoot -ChildPath '.venv\Scripts\python.exe'
$finalizedManifest = 'runtime\competition\v1\finalized-baseline-manifest.json'
$inputDirectory = 'runtime\competition\v1\input'
$inputManifest = Join-Path -Path $inputDirectory -ChildPath 'input-manifest.json'
$outputDirectory = Join-Path -Path 'runtime\competition\v1' -ChildPath $RunId
$redactedResult = Join-Path -Path $outputDirectory -ChildPath 'redacted-results.json'
$stage1Report = Join-Path -Path $outputDirectory -ChildPath 'stage1-report.json'

function Invoke-CheckedPython {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'COMPETITION_PYTHON_GATE_FAILED'
    }
}

Push-Location $RepositoryRoot
try {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'COMPETITION_PROJECT_VENV_MISSING'
    }
    $dirtyPaths = @(& git status --porcelain --untracked-files=no)
    if ($LASTEXITCODE -ne 0 -or $dirtyPaths.Count -ne 0) {
        throw 'COMPETITION_TRACKED_WORKTREE_NOT_CLEAN'
    }
    & git fetch origin main
    if ($LASTEXITCODE -ne 0) {
        throw 'COMPETITION_GIT_FETCH_FAILED'
    }
    $headCommit = (& git rev-parse HEAD).Trim().ToLowerInvariant()
    $originCommit = (& git rev-parse origin/main).Trim().ToLowerInvariant()
    $expectedCommit = $ExpectedHeadCommit.ToLowerInvariant()
    if ($headCommit -ne $expectedCommit -or $originCommit -ne $expectedCommit) {
        throw 'COMPETITION_HEAD_ORIGIN_EXPECTED_COMMIT_MISMATCH'
    }

    Invoke-CheckedPython -Arguments @(
        'scripts\validate_competition_pack.py',
        '--expected-head', $expectedCommit,
        '--output', $finalizedManifest
    )
    Invoke-CheckedPython -Arguments @(
        'scripts\prepare_competition_input.py',
        '--source-package', $SourcePackageRoot,
        '--output-directory', $inputDirectory
    )

    $databaseName = Read-Host 'Existing PostgreSQL database name'
    $databaseUser = Read-Host 'PostgreSQL user'
    $databasePassword = Read-Host 'PostgreSQL password' -AsSecureString
    $databaseCredential = New-Object System.Management.Automation.PSCredential(
        $databaseUser,
        $databasePassword
    )
    $plainPassword = $databaseCredential.GetNetworkCredential().Password
    try {
        $escapedUser = [System.Uri]::EscapeDataString($databaseUser)
        $escapedPassword = [System.Uri]::EscapeDataString($plainPassword)
        $escapedDatabase = [System.Uri]::EscapeDataString($databaseName)
        $env:DATABASE_URL = (
            'postgresql://{0}:{1}@127.0.0.1:5432/{2}' -f
            $escapedUser,
            $escapedPassword,
            $escapedDatabase
        )
    }
    finally {
        $plainPassword = $null
    }
    $env:ELASTICSEARCH_URL = 'http://127.0.0.1:9200'
    $env:MILVUS_URI = 'http://127.0.0.1:19530'
    $env:OLLAMA_URL = 'http://127.0.0.1:11434'
    $env:OLLAMA_EMBED_MODEL = 'bge-m3:latest'

    Invoke-CheckedPython -Arguments @('-m', 'backend.storage.migrate')
    Invoke-CheckedPython -Arguments @(
        'scripts\run_competition_real_core.py',
        '--finalized-manifest', $finalizedManifest,
        '--input-manifest', $inputManifest,
        '--run-id', $RunId,
        '--output-directory', $outputDirectory,
        '--confirm', 'RUN_COMPETITION_REAL_CORE_V1'
    )

    $result = Get-Content -LiteralPath $redactedResult -Raw | ConvertFrom-Json
    if (
        $result.status -ne 'PASS' -or
        $result.scenarios.Count -ne 3 -or
        $result.cleanup.status -ne 'PASS'
    ) {
        throw 'COMPETITION_REDACTED_RESULT_GATE_FAILED'
    }
    Write-Output ('COMPETITION_REAL_REPRODUCTION_PASS commit={0} run_id={1}' -f $headCommit, $RunId)
    Write-Output ('finalized_manifest_sha256={0}' -f (Get-FileHash -LiteralPath $finalizedManifest -Algorithm SHA256).Hash.ToLowerInvariant())
    Write-Output ('redacted_result_sha256={0}' -f (Get-FileHash -LiteralPath $redactedResult -Algorithm SHA256).Hash.ToLowerInvariant())
    Write-Output ('stage1_private_report_sha256={0}' -f (Get-FileHash -LiteralPath $stage1Report -Algorithm SHA256).Hash.ToLowerInvariant())
    Write-Output ('redacted_result={0}' -f $redactedResult)
}
catch {
    Write-Error (
        'Competition Gate failed. Keep commit, private input, and Run ID unchanged. ' +
        'Do not claim PASS; return only the sanitized report and hashes.'
    ) -ErrorAction Continue
    throw
}
finally {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:ELASTICSEARCH_URL -ErrorAction SilentlyContinue
    Remove-Item Env:MILVUS_URI -ErrorAction SilentlyContinue
    Remove-Item Env:OLLAMA_URL -ErrorAction SilentlyContinue
    Remove-Item Env:OLLAMA_EMBED_MODEL -ErrorAction SilentlyContinue
    Pop-Location
}
