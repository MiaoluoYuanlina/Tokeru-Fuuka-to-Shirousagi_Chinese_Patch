@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0localization_startup.tjs" goto missing_startup

set "GAME_EXE=%~dp0kazeshiro_demo.exe"
if exist "%GAME_EXE%" goto launch

set "GAME_EXE="
for %%F in ("%~dp0*.exe") do if not defined GAME_EXE set "GAME_EXE=%%~fF"
if not defined GAME_EXE goto missing_exe

:launch
start "" "%GAME_EXE%" -startup="%~dp0localization_startup.tjs" -readencoding=UTF-8
exit /b 0

:missing_exe
echo No executable file was found in the current directory.
pause
exit /b 1

:missing_startup
echo localization_startup.tjs was not found in the current directory.
pause
exit /b 1
