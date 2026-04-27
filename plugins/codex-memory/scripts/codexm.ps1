param(
    [switch]$DoctorOnly,
    [switch]$InitProject,
    [switch]$SkipBootstrap,
    [switch]$VerboseBootstrap,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CodexArgs
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BootstrapScript = Join-Path $ScriptRoot "codex_bootstrap.py"

function Invoke-Bootstrap {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & py -X utf8 $BootstrapScript @Arguments
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    $json = $null
    if ($text) {
        try {
            $json = $text | ConvertFrom-Json
        } catch {
            $json = $null
        }
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Text = $text
        Json = $json
    }
}

function Find-RealCodex {
    $commands = Get-Command codex -All -ErrorAction SilentlyContinue
    foreach ($command in $commands) {
        if ($command.CommandType -in @("Application", "ExternalScript")) {
            return $command.Source
        }
    }
    return $null
}

function Invoke-RealCodex {
    param(
        [string[]]$Arguments
    )

    $codex = Find-RealCodex
    if (-not $codex) {
        Write-Error "Unable to find the real codex command in PATH."
        exit 127
    }

    & $codex @Arguments
    exit $LASTEXITCODE
}

function Set-MemoryEnvironment {
    param($Doctor)

    if ($null -eq $Doctor -or $null -eq $Doctor.recommended_env) {
        return
    }
    $scope = [string]$Doctor.recommended_env.CODEX_MEMORY_SCOPE
    $cwd = [string]$Doctor.recommended_env.CODEX_MEMORY_CWD
    if ($scope) {
        $env:CODEX_MEMORY_SCOPE = $scope
    }
    if ($cwd) {
        $env:CODEX_MEMORY_CWD = $cwd
    }
}

function Should-InitProject {
    param($Doctor)

    if ($InitProject) {
        return $true
    }
    if ($null -eq $Doctor -or $null -eq $Doctor.project -or $null -eq $Doctor.checks) {
        return $false
    }
    if (-not [bool]$Doctor.project.detected) {
        return $false
    }
    return (-not [bool]$Doctor.checks.project_memory_exists) -or
        (-not [bool]$Doctor.checks.project_commands_exists) -or
        (-not [bool]$Doctor.checks.project_profile_exists)
}

$cwd = (Get-Location).ProviderPath
$doctorResult = $null

if ($env:CODEX_MEMORY_DISABLE_WRAPPER -eq "1") {
    Invoke-RealCodex -Arguments $CodexArgs
}

if (-not $SkipBootstrap) {
    $doctorResult = Invoke-Bootstrap -Arguments @("--cwd", $cwd, "--doctor")
    if ($DoctorOnly) {
        if ($doctorResult.Text) {
            Write-Output $doctorResult.Text
        }
        exit $doctorResult.ExitCode
    }

    if (Should-InitProject -Doctor $doctorResult.Json) {
        $initResult = Invoke-Bootstrap -Arguments @("--cwd", $cwd, "--init-project")
        if ($VerboseBootstrap -and $initResult.Text) {
            Write-Host $initResult.Text
        }
        $doctorResult = Invoke-Bootstrap -Arguments @("--cwd", $cwd, "--doctor")
    }

    if ($VerboseBootstrap -and $doctorResult.Text) {
        Write-Host $doctorResult.Text
    }

    Set-MemoryEnvironment -Doctor $doctorResult.Json
    if ($doctorResult.ExitCode -ne 0) {
        Write-Warning "Codex Memory bootstrap reported a non-ready state; launching Codex with degraded memory support."
    }
}

Invoke-RealCodex -Arguments $CodexArgs
