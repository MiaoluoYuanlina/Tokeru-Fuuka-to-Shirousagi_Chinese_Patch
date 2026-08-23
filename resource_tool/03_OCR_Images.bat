@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
"runtime\python\python.exe" "app\resource_tool.py" --mode ocr
set "TOOL_EXIT=%ERRORLEVEL%"
echo.
if not "%TOOL_EXIT%"=="0" echo 操作失败，退出代码：%TOOL_EXIT%
pause
exit /b %TOOL_EXIT%
