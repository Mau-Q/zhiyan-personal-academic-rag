[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$ExpectedHeadCommit,
    [ValidateSet(
        'phase3_comparison_dev_20260723_02',
        'phase3_comparison_dev_20260723_03'
    )]
    [string]$RunId = 'phase3_comparison_dev_20260723_02',
    [string]$DatabaseHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$DatabasePort = 5432,
    [string]$DatabaseName = 'zhiyan_stage1_canary',
    [string]$DatabaseUser = 'zhiyan_stage1_canary_app'
)

# Target: Windows PowerShell 5.1 on the user-operated Windows validation host.
# This processes one explicitly frozen nine-job cleanup queue, then audits it.
$ErrorActionPreference = 'Stop'
$databaseUrlCreatedByScript = $false

$confirmation = switch ($RunId) {
    'phase3_comparison_dev_20260723_02' {
        'RECOVER_EXACT_PHASE3_COMPARISON_02_CLEANUP'
    }
    'phase3_comparison_dev_20260723_03' {
        'RECOVER_EXACT_PHASE3_COMPARISON_03_CLEANUP'
    }
}

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
        throw 'Remote repository must have no tracked or staged changes before recovery.'
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

    $recoveryPath = "runtime\phase3-comparison-cleanup-recovery-$RunId.json"
    $recoveryArguments = @(
        'scripts/recover_phase3_comparison_cleanup.py',
        '--run-id',
        $RunId,
        '--expected-head-commit',
        $ExpectedHeadCommit,
        '--confirm',
        $confirmation,
        '--output',
        $recoveryPath
    )
    & $PythonPath @recoveryArguments
    $recoveryExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $recoveryPath -PathType Leaf)) {
        throw 'Cleanup recovery did not write a report.'
    }
    $recovery = Get-Content -LiteralPath $recoveryPath -Raw | ConvertFrom-Json
    $recoverySha256 = (
        Get-FileHash -LiteralPath $recoveryPath -Algorithm SHA256
    ).Hash

    $auditPath = (
        "runtime\phase3-comparison-cleanup-post-recovery-audit-$RunId.json"
    )
    $auditArguments = @(
        'scripts/audit_phase3_comparison_cleanup_state.py',
        '--run-id',
        $RunId,
        '--output',
        $auditPath
    )
    & $PythonPath @auditArguments
    $auditExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $auditPath -PathType Leaf)) {
        throw 'Post-recovery read-only audit did not write a report.'
    }
    $audit = Get-Content -LiteralPath $auditPath -Raw | ConvertFrom-Json
    $auditSha256 = (
        Get-FileHash -LiteralPath $auditPath -Algorithm SHA256
    ).Hash

    $summary = [ordered]@{
        schema_version = 'phase3_comparison_cleanup_recovery_summary_v1'
        run_id = $RunId
        head_commit = $headCommit
        recovery_status = $recovery.status
        recovery_stage = $recovery.stage
        recovery_error_code = $recovery.error_code
        jobs_observed = $recovery.jobs_observed
        jobs_succeeded = $recovery.jobs_succeeded
        pre_cleanup_status_counts = (
            $recovery.precondition.cleanup_status_counts
        )
        post_cleanup_status_counts = (
            $recovery.postcondition.cleanup_status_counts
        )
        post_chunk_rows = $recovery.postcondition.chunk_rows
        post_pdf_object_rows = $recovery.postcondition.pdf_object_rows
        post_global_nonterminal_cleanup_job_count = (
            $recovery.postcondition.global_nonterminal_cleanup_job_count
        )
        recovery_sha256 = $recoverySha256
        audit_status = $audit.status
        audit_decision = $audit.decision
        audit_error_code = $audit.error_code
        audit_sha256 = $auditSha256
        test = 'NOT_READ_NOT_RUN'
        acceptance = 'NOT_READ_NOT_RUN'
        quality_gate = 'NOT_RUN'
        performance_gate = 'NOT_RUN'
    }
    $summary | ConvertTo-Json -Depth 6

    if (
        $recoveryExitCode -ne 0 -or
        $recovery.status -ne 'PASS' -or
        $auditExitCode -ne 0 -or
        $audit.status -ne 'PASS' -or
        $audit.decision -ne 'CLEAN'
    ) {
        throw 'Cleanup recovery or post-recovery audit failed; do not rerun the quality Gate.'
    }
}
finally {
    if ($databaseUrlCreatedByScript) {
        Remove-Item -LiteralPath 'Env:DATABASE_URL' -ErrorAction SilentlyContinue
    }
    Pop-Location
}
