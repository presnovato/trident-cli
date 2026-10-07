@echo off
rem Run trident-cli straight from a clone, without installing it.
rem Works from any directory (cmd and PowerShell).

setlocal
set "ROOT=%~dp0.."

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

set "PYTHONUTF8=1"
set "PYTHONPATH=%ROOT%;%PYTHONPATH%"

%PY% -m trident_cli %*
exit /b %errorlevel%
