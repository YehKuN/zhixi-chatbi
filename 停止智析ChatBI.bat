@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev-services.ps1" -Action Stop
echo.
echo 智析 ChatBI 服务已停止。
pause
endlocal
