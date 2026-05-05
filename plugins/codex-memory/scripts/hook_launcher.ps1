param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$HookArgs
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$HookBridgeScript = Join-Path $ScriptRoot "hook_bridge.py"
$RequiredPythonMajor = 3
$RequiredPythonMinor = 11

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
    $candidates = @(
        [pscustomobject]@{ Name = "py"; PrefixArgs = @("-3") },
        [pscustomobject]@{ Name = "python"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3.14"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3.13"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3.12"; PrefixArgs = @() },
        [pscustomobject]@{ Name = "python3.11"; PrefixArgs = @() }
    )
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) { continue }
        $runtime = [pscustomobject]@{ Command = if ($command.Source) { $command.Source } else { $command.Name }; PrefixArgs = @($candidate.PrefixArgs) }
        $version = Get-PythonVersion -Runtime $runtime
        if ($version -and (Test-PythonVersion -VersionText $version)) {
            return $runtime
        }
    }
    return [pscustomobject]@{ Command = $null; PrefixArgs = @() }
}

$runtime = Resolve-PythonRuntime
if (-not $runtime.Command) {
    Write-Error "Python 3.11 or newer is required to run Codex Memory hooks."
    exit 127
}

$pythonArgs = @($runtime.PrefixArgs) + @("-X", "utf8", $HookBridgeScript) + @($HookArgs)
& $runtime.Command @pythonArgs
exit $LASTEXITCODE
