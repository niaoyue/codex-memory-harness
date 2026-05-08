@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "PS_CMD="

where pwsh.exe >nul 2>nul
if not errorlevel 1 set "PS_CMD=pwsh.exe"

if not defined PS_CMD (
    if exist "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" (
        set "PS_CMD=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
    )
)

if not defined PS_CMD (
    where powershell.exe >nul 2>nul
    if not errorlevel 1 set "PS_CMD=powershell.exe"
)

if not defined PS_CMD (
    echo PowerShell 5.1 or PowerShell 7 is required to run Codex Memory hooks. 1>&2
    exit /b 127
)

"%PS_CMD%" -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%hook_launcher.ps1" %*
exit /b %ERRORLEVEL%
