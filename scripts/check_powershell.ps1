[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$SettingsPath
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
if ([string]::IsNullOrWhiteSpace($SettingsPath)) {
    $SettingsPath = Join-Path `
        -Path $RepositoryRoot `
        -ChildPath 'config/PSScriptAnalyzerSettings.psd1'
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$SettingsPath = (Resolve-Path -LiteralPath $SettingsPath).Path

Import-Module PSScriptAnalyzer -RequiredVersion 1.25.0 -ErrorAction Stop

$diagnostics = New-Object 'System.Collections.Generic.List[object]'
$checkedDefinitions = 0
$checkedFiles = 0

function Add-CheckDiagnostic {
    param(
        [string]$Source,
        [int]$Line,
        [int]$Column,
        [string]$Rule,
        [string]$Message
    )

    $script:diagnostics.Add([pscustomobject]@{
        Source = $Source
        Line = $Line
        Column = $Column
        Rule = $Rule
        Message = $Message
    })
}

function Test-PowerShellDefinition {
    param(
        [string]$Definition,
        [string]$Source,
        [int]$StartLine
    )

    $script:checkedDefinitions += 1
    $tokens = $null
    $parseErrors = $null

    [System.Management.Automation.Language.Parser]::ParseInput(
        $Definition,
        $Source,
        [ref]$tokens,
        [ref]$parseErrors
    ) | Out-Null

    if ($parseErrors.Count -gt 0) {
        foreach ($parseError in $parseErrors) {
            Add-CheckDiagnostic `
                -Source $Source `
                -Line ($StartLine + $parseError.Extent.StartLineNumber - 1) `
                -Column $parseError.Extent.StartColumnNumber `
                -Rule 'ParseError' `
                -Message $parseError.Message
        }
        return
    }

    $analysis = @(Invoke-ScriptAnalyzer `
        -ScriptDefinition $Definition `
        -Settings $SettingsPath)

    foreach ($record in $analysis) {
        Add-CheckDiagnostic `
            -Source $Source `
            -Line ($StartLine + $record.Line - 1) `
            -Column $record.Column `
            -Rule $record.RuleName `
            -Message $record.Message
    }
}

$sourceFiles = @(& git -C $RepositoryRoot ls-files --cached --others --exclude-standard -- '*.ps1' '*.psm1' '*.psd1' '*.md')
if ($LASTEXITCODE -ne 0) {
    throw 'git ls-files failed while locating tracked and unignored PowerShell and Markdown sources.'
}

foreach ($relativePath in $sourceFiles) {
    if ([string]::IsNullOrWhiteSpace($relativePath)) {
        continue
    }

    $fullPath = Join-Path $RepositoryRoot $relativePath
    $extension = [System.IO.Path]::GetExtension($relativePath)

    if ($extension -ne '.md') {
        $script:checkedFiles += 1
        $definition = [System.IO.File]::ReadAllText($fullPath)
        Test-PowerShellDefinition -Definition $definition -Source $relativePath -StartLine 1
        continue
    }

    $lines = [System.IO.File]::ReadAllLines($fullPath)
    $insidePowerShellFence = $false
    $fenceStartLine = 0
    $buffer = New-Object 'System.Collections.Generic.List[string]'

    for ($index = 0; $index -lt $lines.Length; $index += 1) {
        $line = $lines[$index]

        if (-not $insidePowerShellFence) {
            if ($line -match '^\s*```(?:powershell|pwsh|ps1)\s*$') {
                $insidePowerShellFence = $true
                $fenceStartLine = $index + 2
                $buffer.Clear()
            }
            continue
        }

        if ($line -match '^\s*```\s*$') {
            $script:checkedFiles += 1
            $definition = $buffer -join [Environment]::NewLine
            Test-PowerShellDefinition `
                -Definition $definition `
                -Source $relativePath `
                -StartLine $fenceStartLine
            $insidePowerShellFence = $false
            $fenceStartLine = 0
            $buffer.Clear()
            continue
        }

        $buffer.Add($line)
    }

    if ($insidePowerShellFence) {
        Add-CheckDiagnostic `
            -Source $relativePath `
            -Line ($fenceStartLine - 1) `
            -Column 1 `
            -Rule 'MarkdownFence' `
            -Message 'PowerShell code fence is not closed.'
    }
}

if ($diagnostics.Count -gt 0) {
    foreach ($diagnostic in $diagnostics) {
        Write-Error ('{0}:{1}:{2}: [{3}] {4}' -f `
            $diagnostic.Source,
            $diagnostic.Line,
            $diagnostic.Column,
            $diagnostic.Rule,
            $diagnostic.Message) -ErrorAction Continue
    }
    exit 1
}

Write-Output ('PowerShell static check passed: {0} definitions from {1} files/code blocks.' -f `
    $checkedDefinitions,
    $checkedFiles)
