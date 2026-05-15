@echo off
setlocal EnableExtensions

set "SCRIPT_ROOT=%~dp0"
call "%SCRIPT_ROOT%install.bat" --uninstall %*
exit /b %ERRORLEVEL%
