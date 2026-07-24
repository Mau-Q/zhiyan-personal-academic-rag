[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedHeadCommit
)

# Target: Windows PowerShell 5.1 on the user-operated Windows validation host.
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Join-Path -Path $PSScriptRoot -ChildPath '..\..\..'
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$runnerPath = Join-Path `
    -Path $RepositoryRoot `
    -ChildPath (
        'deploy\remote\phase3-comparison-validation\' +
        'run_phase3_comparison_paired_dev_gate.ps1'
    )

Push-Location $RepositoryRoot
try {
    $dirtyPaths = @(& git status --porcelain --untracked-files=no)
    if ($LASTEXITCODE -ne 0) {
        throw 'git status failed.'
    }
    if ($dirtyPaths.Count -ne 0) {
        throw 'Windows repository has tracked or staged changes.'
    }

    & git fetch origin main
    if ($LASTEXITCODE -ne 0) {
        throw 'git fetch origin main failed.'
    }
    $headCommit = (& git rev-parse HEAD).Trim()
    $originCommit = (& git rev-parse origin/main).Trim()
    if (
        $headCommit -ne $ExpectedHeadCommit -or
        $originCommit -ne $ExpectedHeadCommit
    ) {
        throw 'Windows HEAD and origin/main must equal the expected commit.'
    }

    $tokens = $null
    $parseErrors = $null
    $runnerAst = [System.Management.Automation.Language.Parser]::ParseFile(
        $runnerPath,
        [ref]$tokens,
        [ref]$parseErrors
    )
    if ($parseErrors.Count -ne 0) {
        foreach ($parseError in $parseErrors) {
            Write-Error (
                '{0}:{1}: {2}' -f `
                    $parseError.Extent.StartLineNumber,
                    $parseError.Extent.StartColumnNumber,
                    $parseError.Message
            ) -ErrorAction Continue
        }
        throw 'Phase 3 PowerShell entry contains parser errors.'
    }

    $helper = $runnerAst.Find(
        {
            param($node)
            if (
                $node -isnot (
                    [System.Management.Automation.Language.FunctionDefinitionAst]
                )
            ) {
                return $false
            }
            return $node.Name -eq 'Get-OptionalJsonProperty'
        },
        $true
    )
    if ($null -eq $helper) {
        throw 'Optional JSON property helper was not found.'
    }

    Invoke-Expression $helper.Extent.Text
    Set-StrictMode -Version 2.0
    $sampleReport = [pscustomobject]@{
        status = 'FAIL'
        cost = [pscustomobject]@{}
    }
    $missingPrimary = Get-OptionalJsonProperty `
        -InputObject $sampleReport `
        -PropertyPath @('primary_error_code')
    $missingNested = Get-OptionalJsonProperty `
        -InputObject $sampleReport `
        -PropertyPath @('cost', 'selection_p95_ms')
    $observedStatus = Get-OptionalJsonProperty `
        -InputObject $sampleReport `
        -PropertyPath @('status')
    if (
        $null -ne $missingPrimary -or
        $null -ne $missingNested -or
        $observedStatus -ne 'FAIL'
    ) {
        throw 'Optional JSON property behavior is invalid.'
    }

    Write-Output (
        'Phase 3 closeout PowerShell verification passed at commit {0}.' -f `
            $headCommit
    )
    Write-Output 'Built-in Windows PowerShell parser and strict-mode behavior passed.'
    Write-Output 'No quality Gate, service, or private input was executed.'
}
finally {
    Pop-Location
}
