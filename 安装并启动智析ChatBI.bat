@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ================================================
echo   智析 ChatBI V1.0 - 首次安装并启动
echo ================================================
echo.

where py >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 Python Launcher。请安装 Python 3.12。
  pause
  exit /b 1
)

echo 正在停止项目托管的旧服务，以避免依赖文件被占用...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev-services.ps1" -Action Stop
if errorlevel 1 (
  echo [错误] 无法安全停止旧服务。
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/5] 创建 Python 3.12 虚拟环境...
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo [错误] 创建虚拟环境失败。
    pause
    exit /b 1
  )
)

echo [2/5] 安装后端依赖...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
call ".venv\Scripts\python.exe" -m pip install uv
if errorlevel 1 (
  echo [错误] uv 安装失败。
  pause
  exit /b 1
)
call ".venv\Scripts\uv.exe" sync --locked --group dev
if errorlevel 1 (
  echo [错误] 后端依赖安装失败。
  pause
  exit /b 1
)

echo [3/5] 安装前端依赖...
call powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-frontend.ps1"
if errorlevel 1 (
  echo [错误] 前端依赖安装失败。
  pause
  exit /b 1
)

echo [5/5] 启动服务...
call "%~dp0启动智析ChatBI.bat"
endlocal
