param(
    [ValidateSet("pwsh", "windows", "all", "none")]
    [string]$ProfileShells = "pwsh",

    [switch]$RemoveHomePlugin
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $ScriptRoot "plugins\codex-memory\scripts\install_codex_memory.py"

$InstallerArgs = @(
    "-X",
    "utf8",
    $Installer,
    "--uninstall",
    "--profile-shells",
    $ProfileShells
)

if ($RemoveHomePlugin) {
    $InstallerArgs += "--remove-home-plugin"
}

& py @InstallerArgs
exit $LASTEXITCODE
