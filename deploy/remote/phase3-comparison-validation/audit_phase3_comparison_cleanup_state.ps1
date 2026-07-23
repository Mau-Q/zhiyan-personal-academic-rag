[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$ExpectedHeadCommit,
    [string]$RunId = 'phase3_comparison_dev_20260723_02',
    [string]$DatabaseHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$DatabasePort = 5432,
    [string]$DatabaseName = 'zhiyan_stage1_canary',
    [string]$DatabaseUser = 'zhiyan_stage1_canary_app'
)

# Target: Windows PowerShell 5.1 on the user-operated Windows validation host.
# This script only reads PostgreSQL state for one isolated Phase 3 run.
$ErrorActionPreference = 'Stop'
$databaseUrlCreatedByScript = $false

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Join-Path -Path $PSScriptRoot -ChildPath '..\..\..'
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$PythonPath = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Project Python is missing at $PythonPath"
}
if ($RunId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$') {
    throw 'Run ID is invalid.'
}

Push-Location $RepositoryRoot
try {
    $dirtyPaths = @(& git status --porcelain --untracked-files=no)
    if ($LASTEXITCODE -ne 0) {
        throw 'git status failed.'
    }
    if ($dirtyPaths.Count -ne 0) {
        throw 'Remote repository must have no tracked or staged changes before this audit.'
    }

    & git fetch origin main
    if ($LASTEXITCODE -ne 0) {
        throw 'git fetch origin main failed.'
    }
    $headCommit = (& git rev-parse HEAD).Trim()
    $originCommit = (& git rev-parse origin/main).Trim()
    if (
        $LASTEXITCODE -ne 0 -or
        $headCommit -ne $originCommit -or
        $headCommit -ne $ExpectedHeadCommit
    ) {
        throw 'Remote HEAD, origin/main, and ExpectedHeadCommit must match.'
    }

    & $PythonPath -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw 'Project dependency consistency check failed.'
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

    $outputPath = "runtime\phase3-comparison-cleanup-audit-$RunId.json"
    $arguments = @(
        'scripts/audit_phase3_comparison_cleanup_state.py',
        '--run-id',
        $RunId,
        '--output',
        $outputPath
    )
    & $PythonPath @arguments
    $auditExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
        throw 'The read-only cleanup audit did not write a report.'
    }
    $audit = Get-Content -LiteralPath $outputPath -Raw | ConvertFrom-Json
    $auditSha256 = (
        Get-FileHash -LiteralPath $outputPath -Algorithm SHA256
    ).Hash

    $summary = [ordered]@{
        schema_version = $audit.schema_version
        run_id = $audit.run_id
        read_only = $audit.read_only
        status = $audit.status
        decision = $audit.decision
        error_code = $audit.error_code
        version_count = $audit.summary.version_count
        active_version_count = $audit.summary.active_version_count
        noninactive_version_count = $audit.summary.noninactive_version_count
        ingestion_job_count = $audit.summary.ingestion_job_count
        nonterminal_ingestion_job_count = (
            $audit.summary.nonterminal_ingestion_job_count
        )
        cleanup_job_count = $audit.summary.cleanup_job_count
        nonterminal_cleanup_job_count = (
            $audit.summary.nonterminal_cleanup_job_count
        )
        global_nonterminal_cleanup_job_count = (
            $audit.summary.global_nonterminal_cleanup_job_count
        )
        cleanup_backends = $audit.summary.cleanup_backends
        chunk_rows = $audit.summary.chunk_rows
        pdf_object_rows = $audit.summary.pdf_object_rows
        audit_sha256 = $auditSha256
    }
    $summary | ConvertTo-Json -Depth 4

    if (
        $auditExitCode -ne 0 -or
        $audit.status -ne 'PASS' -or
        $audit.decision -ne 'CLEAN'
    ) {
        throw 'Read-only audit did not prove a clean state; do not rerun the quality Gate.'
    }
}
finally {
    if ($databaseUrlCreatedByScript) {
        Remove-Item -LiteralPath 'Env:DATABASE_URL' -ErrorAction SilentlyContinue
    }
    Pop-Location
}
