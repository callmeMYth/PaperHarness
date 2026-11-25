@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   PaperHarness 二次开发热更新模式 (后端自动重载 + 前端 HMR)
echo ========================================================

set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"

where node >nul 2>nul
if not %errorlevel%==0 (
    echo [提示] 未检测到 Node.js（仅修改后端 Python 可直接继续；如需修改前端 React 请安装 Node.js 18+）
    echo        正在仅启动后端热重载服务 http://127.0.0.1:8765 ...
    "%PY_CMD%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload
    pause
    exit /b 0
)

if not exist "frontend\node_modules" (
    echo [首次开发] 正在安装前端依赖 frontend\node_modules ...
    pushd frontend
    call npm install
    popd
)

echo [1/2] 启动后端热重载服务 (http://127.0.0.1:8765) ...
start "PaperHarness Backend (--reload)" cmd /k "cd /d "%~dp0" && "%PY_CMD%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload"

echo [2/2] 启动前端 Vite 热更新开发服务器 (http://localhost:5173) ...
echo       修改 frontend\src 下的任何文件都会在浏览器实时生效；修改完后请运行「重新构建前端.bat」同步到桌面版。
pushd frontend
call npm run dev
popd
pause
