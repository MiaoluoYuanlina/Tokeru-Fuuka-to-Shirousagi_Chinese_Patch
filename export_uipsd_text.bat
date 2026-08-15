@echo off
setlocal
title Export uipsd text workbook
cd /d "%~dp0"
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\export_uipsd_text.ps1"
set "SCRIPT_EXIT=%ERRORLEVEL%"
echo.
if not "%SCRIPT_EXIT%"=="0" echo Export failed. See the errors above.
pause
exit /b %SCRIPT_EXIT%
