@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ================================================
echo   智析 ChatBI V1.0 - 一键启动
echo ================================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 未找到项目 Python 环境：.venv\Scripts\python.exe
  echo 请先在项目目录执行：py -3.12 -m venv .venv
  pause
  exit /b 1
)

if not exist "node_modules\vite\bin\vite.js" (
  echo [错误] 未找到前端依赖，请先执行：npm ci
  pause
  exit /b 1
)

call ".venv\Scripts\python.exe" -c "import fastapi, openai, uvicorn, sqlalchemy"
if errorlevel 1 (
  echo [错误] 后端依赖未安装，请先运行“安装并启动智析ChatBI.bat”。
  pause
  exit /b 1
)

if "%DEEPSEEK_API_KEY%"=="" (
  echo [提示] 当前环境未发现 DEEPSEEK_API_KEY，DeepSeek 问数会显示配置提示。
) else (
  echo [提示] 已发现 DEEPSEEK_API_KEY，服务端将从环境变量读取密钥。
)

echo [1/3] 检查环境、初始化数据库并启动服务...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev-services.ps1" -Action Start
if errorlevel 1 (
  echo.
  echo [错误] 服务启动失败，请查看 .tmp\logs 目录。
  pause
  exit /b 1
)

echo.
echo [完成] Web:     http://127.0.0.1:5280/workspace
echo [完成] API:     http://127.0.0.1:8280/health
echo [完成] DataLink: http://127.0.0.1:8281/health
echo.
if "%CHATBI_NONINTERACTIVE%"=="1" (
  echo [完成] 非交互启动结束。
  endlocal
  exit /b 0
)
start "" "http://127.0.0.1:5280/workspace"
echo 窗口保持打开以便查看服务状态，按任意键关闭此窗口（不会停止服务）。
pause >nul
endlocal
