@echo off
setlocal
title Apply uipsd image translations
cd /d "%~dp0"
chcp 65001 >nul
if "%~1"=="" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\apply_uipsd_translations.ps1"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\apply_uipsd_translations.ps1" -WorkbookPath "%~f1" -NoDialog
)
set "SCRIPT_EXIT=%ERRORLEVEL%"
echo.
if not "%SCRIPT_EXIT%"=="0" echo Image processing failed. See the errors above.
pause
exit /b %SCRIPT_EXIT%
