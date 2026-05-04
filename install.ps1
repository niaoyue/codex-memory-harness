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
$RequiredPythonMajor = 3
$RequiredPythonMinor = 11

function Get-PythonVersion {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Candidate
    )

    $probeArgs = @($Candidate.PrefixArgs) + @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
    $versionText = & $Candidate.Command @probeArgs 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $versionText) {
        return $null
    }
    return ($versionText | Select-Object -First 1).Trim()
}

function Test-PythonVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VersionText
    )

    $parts = $VersionText.Split(".")
    if ($parts.Count -lt 2) {
        return $false
    }
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    return ($major -gt $RequiredPythonMajor) -or (
        $major -eq $RequiredPythonMajor -and $minor -ge $RequiredPythonMinor
    )
}

function Write-PythonDependencyHint {
    param([string[]]$Detected = @())

    Write-Host "Python 3.11 or newer is required to run the Codex Memory installer." -ForegroundColor Yellow
    if ($Detected.Count -gt 0) {
        Write-Host "Detected Python command(s): $($Detected -join ', ')"
    }
    Write-Host "Install Python, then rerun: .\install.ps1"
    Write-Host "Windows winget: winget install Python.Python.3.12"
    Write-Host "Manual installer: https://www.python.org/downloads/windows/"
    Write-Host "During manual installation, enable 'Add python.exe to PATH'."
}

function Resolve-PythonRuntime {
    $candidates = @(
        [pscustomobject]@{ Name = "py"; PrefixArgs = @("-3") },
        [pscustomobject]@{ Name = "python"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3"; PrefixArgs = @() }
    )
    $detected = @()
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) {
            continue
        }
        $runtime = [pscustomobject]@{
            Name = $candidate.Name
            Command = $command.Source
            PrefixArgs = @($candidate.PrefixArgs)
        }
        $version = Get-PythonVersion -Candidate $runtime
        if ($version) {
            $detected += "$($candidate.Name) $version"
        }
        if ($version -and (Test-PythonVersion -VersionText $version)) {
            return [pscustomobject]@{
                Name = $runtime.Name
                Command = $runtime.Command
                PrefixArgs = $runtime.PrefixArgs
                Detected = $detected
            }
        }
    }
    return [pscustomobject]@{ Command = $null; PrefixArgs = @(); Detected = $detected }
}

$PythonRuntime = Resolve-PythonRuntime
if (-not $PythonRuntime.Command) {
    Write-PythonDependencyHint -Detected $PythonRuntime.Detected
    if ($PythonRuntime.Detected.Count -gt 0) {
        exit 126
    }
    exit 127
}

$InstallerArgs = @(
    "-X",
    "utf8",
    $Installer,
    "--scope",
    "all",
    "--mode",
    $Mode,
    "--profile-shells",
    $ProfileShells,
    "--mcp-python-command",
    $PythonRuntime.Name
)

foreach ($prefixArg in $PythonRuntime.PrefixArgs) {
    $InstallerArgs += @("--mcp-python-prefix-arg", $prefixArg)
}

if ($ReplaceExisting) {
    $InstallerArgs += "--replace-existing"
}

if ($UpdateExisting) {
    $InstallerArgs += "--update-existing"
}

if ($SkipAgents) {
    $InstallerArgs += "--skip-agents"
}

$PythonArgs = @($PythonRuntime.PrefixArgs) + $InstallerArgs
& $PythonRuntime.Command @PythonArgs
exit $LASTEXITCODE
