param(
    [ValidateSet("auto", "junction", "copy")]
    [string]$Mode = "auto",

    [ValidateSet("pwsh", "windows", "all", "none")]
    [string]$ProfileShells = "pwsh",

    [switch]$ReplaceExisting,
    [switch]$UpdateExisting,
    [switch]$SkipAgents
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $ScriptRoot "plugins\codex-memory\scripts\install_codex_memory.py"

$InstallerArgs = @(
    "-X",
    "utf8",
    $Installer,
    "--scope",
    "all",
    "--mode",
    $Mode,
    "--profile-shells",
    $ProfileShells
)

if ($ReplaceExisting) {
    $InstallerArgs += "--replace-existing"
}

if ($UpdateExisting) {
    $InstallerArgs += "--update-existing"
}

if ($SkipAgents) {
    $InstallerArgs += "--skip-agents"
}

& py @InstallerArgs
exit $LASTEXITCODE
