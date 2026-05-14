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
