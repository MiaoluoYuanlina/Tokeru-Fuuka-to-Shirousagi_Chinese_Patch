@echo off
title kazeshiro_demo patch builder
cd /d "%~dp0"
chcp 65001 >nul

if "%~1"=="" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_patch.ps1"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_patch.ps1" -TsvPath "%~f1" -NoDialog
)

set "BUILD_EXIT=%ERRORLEVEL%"
echo.
if not "%BUILD_EXIT%"=="0" echo Patch build failed. See the errors above.
if "%~1"=="" pause
exit /b %BUILD_EXIT%
