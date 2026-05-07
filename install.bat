@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_ROOT=%~dp0"
set "INSTALLER=%SCRIPT_ROOT%plugins\codex-memory\scripts\install_codex_memory.py"
set "AUTO_INSTALL=%CODEX_MEMORY_AUTO_INSTALL_PYTHON%"
set "ARG_COUNT=0"
set "PY_CMD="
set "PY_NAME="
set "PY_PREFIX="
set "DETECTED="

if "%AUTO_INSTALL%"=="" set "AUTO_INSTALL=0"

call :parse_args %*
if errorlevel 1 exit /b %ERRORLEVEL%

call :resolve_python
if not defined PY_CMD (
    call :handle_missing_python
    if errorlevel 1 exit /b !ERRORLEVEL!
)

set "USER_ARGS="
for /L %%I in (1,1,%ARG_COUNT%) do (
    set "USER_ARGS=!USER_ARGS! "!ARG_%%I!""
)

if defined PY_PREFIX (
    %PY_CMD% %PY_PREFIX% -X utf8 "%INSTALLER%" --mcp-python-command "%PY_NAME%" --mcp-python-prefix-arg "%PY_PREFIX%" %USER_ARGS%
) else (
    %PY_CMD% -X utf8 "%INSTALLER%" --mcp-python-command "%PY_NAME%" %USER_ARGS%
)
exit /b %ERRORLEVEL%

:parse_args
if "%~1"=="" exit /b 0
if /I "%~1"=="--install-python" (
    set "AUTO_INSTALL=1"
    shift
    goto :parse_args
)
if /I "%~1"=="/install-python" (
    set "AUTO_INSTALL=1"
    shift
    goto :parse_args
)
if /I "%~1"=="-UpdateExisting" (
    call :append_arg "--update-existing"
    shift
    goto :parse_args
)
if /I "%~1"=="-ReplaceExisting" (
    call :append_arg "--replace-existing"
    shift
    goto :parse_args
)
if /I "%~1"=="-SkipAgents" (
    call :append_arg "--skip-agents"
    shift
    goto :parse_args
)
if /I "%~1"=="-SkipSkills" (
    call :append_arg "--skip-skills"
    shift
    goto :parse_args
)
if /I "%~1"=="-RemoveHomePlugin" (
    call :append_arg "--remove-home-plugin"
    shift
    goto :parse_args
)
if /I "%~1"=="-ProfileShells" (
    shift
    goto :parse_profile_shells
)
if /I "%~1"=="-Mode" (
    shift
    goto :parse_mode
)
call :append_arg "%~1"
shift
goto :parse_args

:parse_profile_shells
if "%~1"=="" (
    echo -ProfileShells requires a value: auto, pwsh, windows, all, none, profile, bash, or zsh.
    exit /b 2
)
call :append_arg "--profile-shells"
call :append_arg "%~1"
shift
goto :parse_args

:parse_mode
if "%~1"=="" (
    echo -Mode requires a value: auto, junction, or copy.
    exit /b 2
)
call :append_arg "--mode"
call :append_arg "%~1"
shift
goto :parse_args

:append_arg
set /A ARG_COUNT+=1
set "ARG_!ARG_COUNT!=%~1"
exit /b 0

:resolve_python
set "PY_CMD="
set "PY_NAME="
set "PY_PREFIX="
set "DETECTED="
call :try_python "py" "-3"
if defined PY_CMD exit /b 0
call :try_python "python" ""
if defined PY_CMD exit /b 0
call :try_python "python3" ""
if defined PY_CMD exit /b 0
call :try_python "python3.14" ""
if defined PY_CMD exit /b 0
call :try_python "python3.13" ""
if defined PY_CMD exit /b 0
call :try_python "python3.12" ""
if defined PY_CMD exit /b 0
call :try_python "python3.11" ""
exit /b 0

:try_python
set "CANDIDATE=%~1"
set "CANDIDATE_PREFIX=%~2"
where "%CANDIDATE%" >nul 2>nul
if errorlevel 1 exit /b 1

set "VERSION_TEXT="
if "%CANDIDATE_PREFIX%"=="" (
    for /F "usebackq delims=" %%V in (`%CANDIDATE% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2^>nul`) do (
        set "VERSION_TEXT=%%V"
    )
    %CANDIDATE% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
) else (
    for /F "usebackq delims=" %%V in (`%CANDIDATE% %CANDIDATE_PREFIX% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2^>nul`) do (
        set "VERSION_TEXT=%%V"
    )
    %CANDIDATE% %CANDIDATE_PREFIX% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
)
set "PROBE_EXIT=%ERRORLEVEL%"
if defined VERSION_TEXT (
    if defined DETECTED (
        set "DETECTED=%DETECTED%, %CANDIDATE% %VERSION_TEXT%"
    ) else (
        set "DETECTED=%CANDIDATE% %VERSION_TEXT%"
    )
)
if not "%PROBE_EXIT%"=="0" exit /b 1

set "PY_CMD=%CANDIDATE%"
set "PY_NAME=%CANDIDATE%"
set "PY_PREFIX=%CANDIDATE_PREFIX%"
exit /b 0

:handle_missing_python
if /I "%AUTO_INSTALL%"=="1" (
    call :install_python_with_winget
    if errorlevel 1 exit /b !ERRORLEVEL!
    call :resolve_python
    if defined PY_CMD exit /b 0
)
call :write_python_hint
if defined DETECTED exit /b 126
exit /b 127

:install_python_with_winget
where winget >nul 2>nul
if errorlevel 1 (
    echo winget was not found. Install Python 3.11+ manually, then rerun install.bat.
    exit /b 1
)
echo Installing Python 3.12 with winget...
winget install --id Python.Python.3.12 -e --source winget
if errorlevel 1 (
    echo winget did not complete successfully. Install Python 3.11+ manually, then rerun install.bat.
    exit /b 1
)
exit /b 0

:write_python_hint
echo Python 3.11 or newer is required to run the Codex Memory installer.
if defined DETECTED echo Detected Python command(s): %DETECTED%
echo Install Python, then rerun: install.bat
echo Windows winget: winget install --id Python.Python.3.12 -e --source winget
echo Manual installer: https://www.python.org/downloads/windows/
echo During manual installation, enable "Add python.exe to PATH".
echo To let this script try winget for you, rerun: install.bat --install-python
exit /b 0
