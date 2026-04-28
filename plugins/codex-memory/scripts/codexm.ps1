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
$HarnessScript = Join-Path $ScriptRoot "harness_controller.py"
$HookScript = Join-Path $ScriptRoot "hook_runner.py"
$InstallScript = Join-Path $ScriptRoot "install_codex_memory.py"
$VerificationScript = Join-Path $ScriptRoot "verification_runner.py"

function Invoke-PythonScriptAndExit {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$Arguments = @()
    )

    & py -X utf8 $ScriptPath @Arguments
    exit $LASTEXITCODE
}

function Write-MemoryHelp {
    @"
Codex Memory 命令：
  codex memory doctor              诊断当前项目 memory/harness 接入状态。
  codex memory init                初始化缺失的 .codex memory/harness 文件。
  codex memory check-install       检查全局插件、profile 和 marketplace 接入。
  codex memory hook <event> [...]   执行 memory 生命周期 hook 事件。
  codex memory verify list         列出当前项目配置化验证命令。
  codex memory verify run [...]    运行当前项目配置化验证命令。
  codex memory harness ...         执行 harness start/checkpoint/complete。

兼容别名：
  codex-memory-doctor              等同于 codex memory doctor。
  codexm memory ...                通过显式 wrapper 执行同一组命令。
"@
}

function Invoke-MemoryCommand {
    param(
        [string[]]$Arguments = @()
    )

    $cwd = (Get-Location).ProviderPath
    if ($Arguments.Count -eq 0 -or $Arguments[0] -in @("help", "-h", "--help")) {
        Write-MemoryHelp
        exit 0
    }

    $command = $Arguments[0].ToLowerInvariant()
    $remaining = @()
    if ($Arguments.Count -gt 1) {
        $remaining = $Arguments[1..($Arguments.Count - 1)]
    }

    switch ($command) {
        "doctor" {
            Invoke-PythonScriptAndExit -ScriptPath $BootstrapScript -Arguments @("--cwd", $cwd, "--doctor")
        }
        "status" {
            Invoke-PythonScriptAndExit -ScriptPath $BootstrapScript -Arguments @("--cwd", $cwd, "--doctor")
        }
        "init" {
            Invoke-PythonScriptAndExit -ScriptPath $BootstrapScript -Arguments @("--cwd", $cwd, "--init-project")
        }
        "init-project" {
            Invoke-PythonScriptAndExit -ScriptPath $BootstrapScript -Arguments @("--cwd", $cwd, "--init-project")
        }
        "check-install" {
            Invoke-PythonScriptAndExit -ScriptPath $InstallScript -Arguments @("--check")
        }
        "hook" {
            if ($remaining.Count -eq 0) {
                Write-Error "缺少 hook event。运行 'codex memory help' 查看用法。"
                exit 64
            }
            if ($remaining[0].StartsWith("-")) {
                $scriptArgs = $remaining
            } else {
                $hookRest = @()
                if ($remaining.Count -gt 1) {
                    $hookRest = $remaining[1..($remaining.Count - 1)]
                }
                $scriptArgs = @("--event", $remaining[0]) + $hookRest
            }
            Invoke-PythonScriptAndExit -ScriptPath $HookScript -Arguments $scriptArgs
        }
        "verify" {
            $scriptArgs = @("--project-root", $cwd) + $remaining
            Invoke-PythonScriptAndExit -ScriptPath $VerificationScript -Arguments $scriptArgs
        }
        "harness" {
            $scriptArgs = @("--project-root", $cwd) + $remaining
            Invoke-PythonScriptAndExit -ScriptPath $HarnessScript -Arguments $scriptArgs
        }
        default {
            Write-Error "未知 Codex Memory 命令：$($Arguments[0])。运行 'codex memory help' 查看可用命令。"
            exit 64
        }
    }
}

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

if ($CodexArgs.Count -gt 0 -and $CodexArgs[0].ToLowerInvariant() -eq "memory") {
    $memoryArgs = @()
    if ($CodexArgs.Count -gt 1) {
        $memoryArgs = $CodexArgs[1..($CodexArgs.Count - 1)]
    }
    Invoke-MemoryCommand -Arguments $memoryArgs
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
