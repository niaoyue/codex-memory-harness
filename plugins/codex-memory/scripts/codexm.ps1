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
$PluginRoot = Split-Path -Parent $ScriptRoot
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PluginRoot)
$BootstrapScript = Join-Path $ScriptRoot "codex_bootstrap.py"
$HarnessScript = Join-Path $ScriptRoot "harness_controller.py"
$HookScript = Join-Path $ScriptRoot "hook_runner.py"
$InstallScript = Join-Path $ScriptRoot "install_codex_memory.py"
$VerificationScript = Join-Path $ScriptRoot "verification_runner.py"
$SharedMemoryScript = Join-Path $ScriptRoot "shared_memory.py"
$LegacyGlobalMigrationScript = Join-Path $ScriptRoot "legacy_global_memory_migration.py"
$WorkspaceScript = Join-Path $ScriptRoot "workspace_scanner.py"
$WorkspaceRouterScript = Join-Path $ScriptRoot "workspace_router.py"
$WorkspaceVerifierScript = Join-Path $ScriptRoot "workspace_verifier.py"
$WorkspaceSubagentsScript = Join-Path $ScriptRoot "workspace_subagents.py"
$SubagentSchedulerScript = Join-Path $ScriptRoot "subagent_scheduler.py"
$WorkspaceSessionScript = Join-Path $ScriptRoot "workspace_session.py"
$ReviewGateScript = Join-Path $ScriptRoot "review_gate_runner.py"
$ReviewWorkflowScript = Join-Path $ScriptRoot "review_workflow.py"
$GameClientProfilesScript = Join-Path $ScriptRoot "game_client_profiles.py"
$WorkspaceBusinessTemplatesScript = Join-Path $ScriptRoot "workspace_business_templates.py"
$HookBridgeScript = Join-Path $ScriptRoot "hook_bridge.py"
$RequiredPythonMajor = 3
$RequiredPythonMinor = 11
$ReviewGateIdleSeconds = 1800
$ReviewGateRunningEnv = "CODEX_REVIEW_GATE_RUNNING"
$XHighReviewDispatchDisableEnv = "CODEX_XHIGH_REVIEW_DISPATCH_DISABLE"
$script:ResolvedPythonRuntime = $null

function Get-PythonVersion {
    param([Parameter(Mandatory = $true)][pscustomobject]$Runtime)
    $probeArgs = @($Runtime.PrefixArgs) + @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
    $versionText = & $Runtime.Command @probeArgs 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $versionText) { return $null }
    return ($versionText | Select-Object -First 1).Trim()
}

function Test-PythonVersion {
    param([Parameter(Mandatory = $true)][string]$VersionText)
    $parts = $VersionText.Split(".")
    if ($parts.Count -lt 2) { return $false }
    try { $major = [int]$parts[0]; $minor = [int]$parts[1] } catch { return $false }
    return ($major -gt $RequiredPythonMajor) -or ($major -eq $RequiredPythonMajor -and $minor -ge $RequiredPythonMinor)
}

function Resolve-PythonRuntime {
    if ($script:ResolvedPythonRuntime) { return $script:ResolvedPythonRuntime }
    $candidates = @(
        [pscustomobject]@{ Name = "py"; PrefixArgs = @("-3") },
        [pscustomobject]@{ Name = "python"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3.14"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3.13"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3.12"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3.11"; PrefixArgs = @() }
    )
    $detected = @()
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) { continue }
        $runtime = [pscustomobject]@{ Command = if ($command.Source) { $command.Source } else { $command.Name }; PrefixArgs = @($candidate.PrefixArgs) }
        $version = Get-PythonVersion -Runtime $runtime
        if ($version) { $detected += "$($candidate.Name) $version" }
        if ($version -and (Test-PythonVersion -VersionText $version)) {
            $script:ResolvedPythonRuntime = [pscustomobject]@{ Command = $runtime.Command; PrefixArgs = $runtime.PrefixArgs; Detected = $detected }
            return $script:ResolvedPythonRuntime
        }
    }
    return [pscustomobject]@{ Command = $null; PrefixArgs = @(); Detected = $detected }
}
function Write-PythonDependencyHint {
    param([string[]]$Detected = @())
    Write-Host "Python 3.11 or newer is required to run Codex Memory commands." -ForegroundColor Yellow
    if ($Detected.Count -gt 0) { Write-Host "Detected Python command(s): $($Detected -join ', ')" }
    Write-Host "Install Python, then rerun the command."
    Write-Host "Windows winget: winget install --id Python.Python.3.12 -e --source winget"
    Write-Host "Manual installer: https://www.python.org/downloads/windows/"
    Write-Host "During manual installation, enable 'Add python.exe to PATH'."
}

function Require-PythonRuntime {
    $runtime = Resolve-PythonRuntime
    if (-not $runtime.Command) {
        Write-PythonDependencyHint -Detected $runtime.Detected
        if ($runtime.Detected.Count -gt 0) { exit 126 }
        exit 127
    }
    return $runtime
}
function Invoke-PythonScriptCapture {
    param([Parameter(Mandatory = $true)][string]$ScriptPath, [string[]]$Arguments = @())
    $runtime = Require-PythonRuntime
    $pythonArgs = @($runtime.PrefixArgs) + @("-X", "utf8", $ScriptPath) + @($Arguments)
    $output = & $runtime.Command @pythonArgs
    return [pscustomobject]@{ Output = $output; ExitCode = $LASTEXITCODE }
}

function Invoke-PythonScriptAndExit {
    param([Parameter(Mandatory = $true)][string]$ScriptPath, [string[]]$Arguments = @())
    $runtime = Require-PythonRuntime
    $pythonArgs = @($runtime.PrefixArgs) + @("-X", "utf8", $ScriptPath) + @($Arguments)
    & $runtime.Command @pythonArgs
    exit $LASTEXITCODE
}

function Resolve-RepoScript {
    param([Parameter(Mandatory = $true)][string]$ScriptName, [Parameter(Mandatory = $true)][string]$Cwd)
    $candidates = @((Join-Path $Cwd "scripts\$ScriptName"), (Join-Path $RepoRoot "scripts\$ScriptName"))
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    Write-Error "未找到 $ScriptName。请在 Codex Memory Harness 仓库根目录运行该命令。"
    exit 64
}

function Write-MemoryHelp {
    @"
Codex Memory 命令：
  codex memory doctor/init/install/update/check-install/uninstall
  codex memory hook <event> [...]
  codex memory promote --task-id <task-id> [--kind fact]
  codex memory shared validate|index rebuild
  codex memory migrate-legacy-global [--dry-run|--confirm]
兼容别名：codex harness/package/workspace ...；codex xhigh review --commit <commit-sha>；codex-memory-doctor；codexm memory ...
常用：codex workspace schedule；codex workspace game-client
"@
}

function Invoke-ReviewCommand {
    param([string[]]$Arguments = @())
    $cwd = (Get-Location).ProviderPath
    if ($Arguments.Count -eq 0 -or $Arguments[0] -in @("help", "-h", "--help")) {
        Write-Output "Codex Review 命令：status|preflight|plan|record|findings list|findings resolve|ledger show"
        exit 0
    }
    Invoke-PythonScriptAndExit -ScriptPath $ReviewWorkflowScript -Arguments (@("--project-root", $cwd) + $Arguments)
}

function Is-HarnessReviewCommand { param([string[]]$Arguments); return $Arguments.Count -ge 2 -and @("status", "preflight", "plan", "record", "findings", "ledger") -contains $Arguments[1].ToLowerInvariant() }

function Write-HarnessHelp {
    @"
Codex Harness 命令：
  codex harness start --task-file task.json
  codex harness checkpoint --task-id <task-id> --result-file result.json
  codex harness complete --task-id <task-id> --summary-file summary.md
  codex harness verify list
  codex harness verify run --profile primary
  codex harness verify run --task-id <task-id> --profile primary
"@
}

function Write-PackageHelp {
    @"
Codex Package 命令：
  codex package build              生成可分发 zip。
  codex package verify             运行项目健康检查、编译、行为测试和发布包边界检查。
"@
}

function Write-WorkspaceHelp {
    @"
Codex Workspace 命令：
  doctor|scan|route|verify|bind|schedule|scope-check|summarize
  session status|bind|heartbeat|release; worktree list|prune --dry-run|--confirm|recover <binding-id>; write-guard --session-id <id> --task-id <id> [--path <path>]
  game-client init --engine unity|laya|cocos
  project-template init --domain game_server|backoffice_web|design_docs|art_pipeline
"@
}

function Invoke-MemoryCommand {
    param([string[]]$Arguments = @())
    $cwd = (Get-Location).ProviderPath
    if ($Arguments.Count -eq 0 -or $Arguments[0] -in @("help", "-h", "--help")) {
        Write-MemoryHelp
        exit 0
    }

    $command = $Arguments[0].ToLowerInvariant()
    $remaining = if ($Arguments.Count -gt 1) { $Arguments[1..($Arguments.Count - 1)] } else { @() }

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
        "install" {
            Invoke-PythonScriptAndExit -ScriptPath $InstallScript -Arguments $remaining
        }
        "update" {
            Invoke-PythonScriptAndExit -ScriptPath $InstallScript -Arguments (@("--update-existing") + $remaining)
        }
        "check-install" {
            Invoke-PythonScriptAndExit -ScriptPath $InstallScript -Arguments @("--check")
        }
        "check" {
            Invoke-PythonScriptAndExit -ScriptPath $InstallScript -Arguments @("--check")
        }
        "uninstall" {
            Invoke-PythonScriptAndExit -ScriptPath $InstallScript -Arguments (@("--uninstall") + $remaining)
        }
        "hook" {
            if ($remaining.Count -eq 0) {
                Write-Error "缺少 hook event。运行 'codex memory help' 查看用法。"
                exit 64
            }
            if ($remaining[0].StartsWith("-")) { $scriptArgs = $remaining } else { $hookRest = if ($remaining.Count -gt 1) { $remaining[1..($remaining.Count - 1)] } else { @() }; $scriptArgs = @("--event", $remaining[0]) + $hookRest }
            Invoke-PythonScriptAndExit -ScriptPath $HookScript -Arguments $scriptArgs
        }
        "codex-hook" {
            Invoke-PythonScriptAndExit -ScriptPath $HookBridgeScript -Arguments $remaining
        }
        "promote" {
            Invoke-PythonScriptAndExit -ScriptPath $SharedMemoryScript -Arguments (@("--project-root", $cwd, "promote") + $remaining)
        }
        "shared" {
            Invoke-PythonScriptAndExit -ScriptPath $SharedMemoryScript -Arguments (@("--project-root", $cwd, "shared") + $remaining)
        }
        "migrate-legacy-global" {
            Invoke-PythonScriptAndExit -ScriptPath $LegacyGlobalMigrationScript -Arguments $remaining
        }
        "verify" {
            Invoke-HarnessCommand -Arguments (@("verify") + $remaining)
        }
        "harness" {
            Invoke-HarnessCommand -Arguments $remaining
        }
        default {
            Write-Error "未知 Codex Memory 命令：$($Arguments[0])。运行 'codex memory help' 查看可用命令。"
            exit 64
        }
    }
}
function Invoke-HarnessCommand {
    param([string[]]$Arguments = @())
    $cwd = (Get-Location).ProviderPath
    if ($Arguments.Count -eq 0 -or $Arguments[0] -in @("help", "-h", "--help")) {
        Write-HarnessHelp
        exit 0
    }

    $command = $Arguments[0].ToLowerInvariant()
    $remaining = if ($Arguments.Count -gt 1) { $Arguments[1..($Arguments.Count - 1)] } else { @() }

    switch ($command) {
        "start" {
            Invoke-PythonScriptAndExit -ScriptPath $HarnessScript -Arguments (@("--project-root", $cwd, "start") + $remaining)
        }
        "checkpoint" {
            Invoke-PythonScriptAndExit -ScriptPath $HarnessScript -Arguments (@("--project-root", $cwd, "checkpoint") + $remaining)
        }
        "complete" {
            Invoke-PythonScriptAndExit -ScriptPath $HarnessScript -Arguments (@("--project-root", $cwd, "complete") + $remaining)
        }
        "verify" {
            Invoke-PythonScriptAndExit -ScriptPath $VerificationScript -Arguments (@("--project-root", $cwd) + $remaining)
        }
        default {
            Write-Error "未知 Codex Harness 命令：$($Arguments[0])。运行 'codex harness help' 查看可用命令。"
            exit 64
        }
    }
}
function Invoke-PackageCommand {
    param([string[]]$Arguments = @())
    $cwd = (Get-Location).ProviderPath
    if ($Arguments.Count -eq 0 -or $Arguments[0] -in @("help", "-h", "--help")) {
        Write-PackageHelp
        exit 0
    }

    $command = $Arguments[0].ToLowerInvariant()
    $remaining = if ($Arguments.Count -gt 1) { $Arguments[1..($Arguments.Count - 1)] } else { @() }

    switch ($command) {
        "build" {
            $script = Resolve-RepoScript -ScriptName "build_release.py" -Cwd $cwd
            Invoke-PythonScriptAndExit -ScriptPath $script -Arguments $remaining
        }
        "verify" {
            $script = Resolve-RepoScript -ScriptName "verify_project.py" -Cwd $cwd
            Invoke-PythonScriptAndExit -ScriptPath $script -Arguments $remaining
        }
        "check" {
            $script = Resolve-RepoScript -ScriptName "verify_project.py" -Cwd $cwd
            Invoke-PythonScriptAndExit -ScriptPath $script -Arguments $remaining
        }
        default {
            Write-Error "未知 Codex Package 命令：$($Arguments[0])。运行 'codex package help' 查看可用命令。"
            exit 64
        }
    }
}
function Invoke-WorkspaceCommand {
    param([string[]]$Arguments = @())
    $cwd = (Get-Location).ProviderPath
    if ($Arguments.Count -eq 0 -or $Arguments[0] -in @("help", "-h", "--help")) {
        Write-WorkspaceHelp
        exit 0
    }
    $command = $Arguments[0].ToLowerInvariant()
    $remaining = if ($Arguments.Count -gt 1) { $Arguments[1..($Arguments.Count - 1)] } else { @() }
    switch ($command) {
        "doctor" {
            Invoke-PythonScriptAndExit -ScriptPath $WorkspaceScript -Arguments (@("--workspace-root", $cwd, "doctor") + $remaining)
        }
        "scan" {
            Invoke-PythonScriptAndExit -ScriptPath $WorkspaceScript -Arguments (@("--workspace-root", $cwd, "scan") + $remaining)
        }
        "route" {
            Invoke-PythonScriptAndExit -ScriptPath $WorkspaceRouterScript -Arguments (@("--workspace-root", $cwd) + $remaining)
        }
        "verify" {
            Invoke-PythonScriptAndExit -ScriptPath $WorkspaceVerifierScript -Arguments (@("--project-root", $cwd) + $remaining)
        }
        "bind" {
            Invoke-PythonScriptAndExit -ScriptPath $WorkspaceSubagentsScript -Arguments (@("--project-root", $cwd, "bind") + $remaining)
        }
        "schedule" { Invoke-PythonScriptAndExit -ScriptPath $SubagentSchedulerScript -Arguments (@("--project-root", $cwd) + $remaining) }
        "session" { Invoke-PythonScriptAndExit -ScriptPath $WorkspaceSessionScript -Arguments (@("--project-root", $cwd, $command) + $remaining) }
        "worktree" { Invoke-PythonScriptAndExit -ScriptPath $WorkspaceSessionScript -Arguments (@("--project-root", $cwd, $command) + $remaining) }
        "write-guard" { Invoke-PythonScriptAndExit -ScriptPath $WorkspaceSessionScript -Arguments (@("--project-root", $cwd, $command) + $remaining) }
        "game-client" { Invoke-PythonScriptAndExit -ScriptPath $GameClientProfilesScript -Arguments (@("--project-root", $cwd) + $remaining) }
        "project-template" { Invoke-PythonScriptAndExit -ScriptPath $WorkspaceBusinessTemplatesScript -Arguments (@("--project-root", $cwd) + $remaining) }
        "scope-check" {
            Invoke-PythonScriptAndExit -ScriptPath $WorkspaceSubagentsScript -Arguments (@("--project-root", $cwd, "scope-check") + $remaining)
        }
        "summarize" {
            Invoke-PythonScriptAndExit -ScriptPath $WorkspaceSubagentsScript -Arguments (@("--project-root", $cwd, "summarize") + $remaining)
        }
        default {
            Write-Error "未知 Codex Workspace 命令：$($Arguments[0])。运行 'codex workspace help' 查看可用命令。"
            exit 64
        }
    }
}

function Invoke-Bootstrap {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $result = Invoke-PythonScriptCapture -ScriptPath $BootstrapScript -Arguments $Arguments
    $text = ($result.Output | Out-String).Trim()
    $json = $null
    if ($text) { try { $json = $text | ConvertFrom-Json } catch { $json = $null } }
    return [pscustomobject]@{ ExitCode = $result.ExitCode; Text = $text; Json = $json }
}

function Find-RealCodex {
    $commands = Get-Command codex -All -ErrorAction SilentlyContinue
    foreach ($type in @("Application", "ExternalScript")) { foreach ($command in $commands) { if ($command.CommandType -eq $type) { return $command.Source } } }
    return $null
}

function Invoke-RealCodex {
    param([string[]]$Arguments)

    $codex = Find-RealCodex
    if (-not $codex) {
        Write-Error "Unable to find the real codex command in PATH."
        exit 127
    }

    & $codex @Arguments
    exit $LASTEXITCODE
}

function Resolve-CodexReviewAlias {
    param([string[]]$Arguments)
    if ($Arguments.Count -lt 2) { return $Arguments }

    $effort = $Arguments[0].ToLowerInvariant()
    $command = $Arguments[1].ToLowerInvariant()
    if ($command -ne "review") { return $Arguments }
    if (@("low", "medium", "high", "xhigh") -notcontains $effort) { return $Arguments }

    $tail = if ($Arguments.Count -gt 2) { $Arguments[2..($Arguments.Count - 1)] } else { @() }
    return @("review", "-c", "model_reasoning_effort=`"$effort`"") + $tail
}

function Set-MemoryEnvironment {
    param($Doctor)

    if ($null -eq $Doctor -or $null -eq $Doctor.recommended_env) { return }
    $scope = [string]$Doctor.recommended_env.CODEX_MEMORY_SCOPE
    $cwd = [string]$Doctor.recommended_env.CODEX_MEMORY_CWD
    if ($scope) { $env:CODEX_MEMORY_SCOPE = $scope }
    if ($cwd) { $env:CODEX_MEMORY_CWD = $cwd }
}

function Should-InitProject {
    param($Doctor)

    if ($InitProject) { return $true }
    if ($null -eq $Doctor -or $null -eq $Doctor.project -or $null -eq $Doctor.checks) { return $false }
    if (-not [bool]$Doctor.project.detected) { return $false }
    return (-not [bool]$Doctor.checks.project_memory_exists) -or
        (-not [bool]$Doctor.checks.project_commands_exists) -or
        (-not [bool]$Doctor.checks.project_profile_exists) -or
        (-not [bool]$Doctor.checks.project_shared_exists) -or
        (-not [bool]$Doctor.checks.project_shared_index_exists)
}

$cwd = (Get-Location).ProviderPath
$doctorResult = $null

if ($env:CODEX_MEMORY_DISABLE_WRAPPER -eq "1") { Invoke-RealCodex -Arguments $CodexArgs }

if ($CodexArgs.Count -gt 0 -and $CodexArgs[0].ToLowerInvariant() -eq "memory") {
    $memoryArgs = if ($CodexArgs.Count -gt 1) { $CodexArgs[1..($CodexArgs.Count - 1)] } else { @() }
    Invoke-MemoryCommand -Arguments $memoryArgs
}

if ($CodexArgs.Count -gt 0 -and $CodexArgs[0].ToLowerInvariant() -eq "harness") {
    $harnessArgs = if ($CodexArgs.Count -gt 1) { $CodexArgs[1..($CodexArgs.Count - 1)] } else { @() }
    Invoke-HarnessCommand -Arguments $harnessArgs
}

if ($CodexArgs.Count -gt 0 -and $CodexArgs[0].ToLowerInvariant() -eq "package") {
    $packageArgs = if ($CodexArgs.Count -gt 1) { $CodexArgs[1..($CodexArgs.Count - 1)] } else { @() }
    Invoke-PackageCommand -Arguments $packageArgs
}

if ($CodexArgs.Count -gt 0 -and $CodexArgs[0].ToLowerInvariant() -eq "workspace") {
    $workspaceArgs = if ($CodexArgs.Count -gt 1) { $CodexArgs[1..($CodexArgs.Count - 1)] } else { @() }
    Invoke-WorkspaceCommand -Arguments $workspaceArgs
}

if ($CodexArgs.Count -gt 0 -and $CodexArgs[0].ToLowerInvariant() -eq "review" -and (Is-HarnessReviewCommand -Arguments $CodexArgs)) {
    $reviewArgs = if ($CodexArgs.Count -gt 1) { $CodexArgs[1..($CodexArgs.Count - 1)] } else { @() }
    Invoke-ReviewCommand -Arguments $reviewArgs
}

if (-not $SkipBootstrap) {
    $doctorResult = Invoke-Bootstrap -Arguments @("--cwd", $cwd, "--doctor")
    if ($DoctorOnly) {
        if ($doctorResult.Text) { Write-Output $doctorResult.Text }
        exit $doctorResult.ExitCode
    }

    if (Should-InitProject -Doctor $doctorResult.Json) {
        $initResult = Invoke-Bootstrap -Arguments @("--cwd", $cwd, "--init-project")
        if ($VerboseBootstrap -and $initResult.Text) { Write-Host $initResult.Text }
        $doctorResult = Invoke-Bootstrap -Arguments @("--cwd", $cwd, "--doctor")
    }

    if ($VerboseBootstrap -and $doctorResult.Text) { Write-Host $doctorResult.Text }

    Set-MemoryEnvironment -Doctor $doctorResult.Json
    if ($doctorResult.ExitCode -ne 0) {
        Write-Warning "Codex Memory bootstrap reported a non-ready state; launching Codex with degraded memory support."
    }
}

if ($CodexArgs.Count -ge 2 -and $CodexArgs[1].ToLowerInvariant() -eq "review" -and @("low", "medium", "high", "xhigh") -contains $CodexArgs[0].ToLowerInvariant()) {
    $tail = if ($CodexArgs.Count -gt 2) { $CodexArgs[2..($CodexArgs.Count - 1)] } else { @() }
    $realCodex = Find-RealCodex
    if (-not $realCodex) { Write-Error "Unable to find the real codex command in PATH."; exit 127 }
    $oldReviewGateRunning = [Environment]::GetEnvironmentVariable($ReviewGateRunningEnv, "Process")
    $oldXHighDispatchDisable = [Environment]::GetEnvironmentVariable($XHighReviewDispatchDisableEnv, "Process")
    $exitCode = 0
    try {
        [Environment]::SetEnvironmentVariable($XHighReviewDispatchDisableEnv, "1", "Process")
        if ($oldReviewGateRunning -eq "1") {
            $reviewArgs = @("review", "-c", "model_reasoning_effort=`"$($CodexArgs[0].ToLowerInvariant())`"") + @($tail)
            & $realCodex @reviewArgs
            $exitCode = $LASTEXITCODE
        } else {
            [Environment]::SetEnvironmentVariable($ReviewGateRunningEnv, "1", "Process")
            $runtime = Require-PythonRuntime
            $pythonArgs = @($runtime.PrefixArgs) + @("-X", "utf8", $ReviewGateScript, "--codex", $realCodex, "--effort", $CodexArgs[0].ToLowerInvariant(), "--idle-seconds", "$ReviewGateIdleSeconds", "--max-seconds", "0", "--cwd", $cwd, "--") + @($tail)
            & $runtime.Command @pythonArgs
            $exitCode = $LASTEXITCODE
        }
    } finally {
        [Environment]::SetEnvironmentVariable($ReviewGateRunningEnv, $oldReviewGateRunning, "Process")
        [Environment]::SetEnvironmentVariable($XHighReviewDispatchDisableEnv, $oldXHighDispatchDisable, "Process")
    }
    exit $exitCode
}
Invoke-RealCodex -Arguments (Resolve-CodexReviewAlias -Arguments $CodexArgs)
