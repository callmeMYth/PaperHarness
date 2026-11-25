@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================================
echo   PaperHarness 学术论文写作与科研绘图工作台
echo ========================================================

set "PY_CMD="
set "PYW_CMD="

:: 1. 优先使用项目内已创建的 .venv 虚拟环境
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
    if exist ".venv\Scripts\pythonw.exe" set "PYW_CMD=.venv\Scripts\pythonw.exe"
)

:: 2. 否则检测当前系统 / Conda 的 Python 是否已装齐依赖
if not defined PY_CMD (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python -c "import fastapi, uvicorn, httpx, docx, pptx, matplotlib, fitz, webview" >nul 2>nul
        if !errorlevel!==0 (
            set "PY_CMD=python"
            where pythonw >nul 2>nul && set "PYW_CMD=pythonw"
        )
    )
)

:: 3. 首次运行且缺少依赖时，自动创建 .venv 并使用清华镜像快速安装
if not defined PY_CMD (
    where python >nul 2>nul
    if not %errorlevel%==0 (
        echo [错误] 未检测到 Python，请先安装 Python 3.10+ 并勾选 "Add Python to PATH"：
        echo        https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo [首次启动] 正在创建独立虚拟环境 .venv 并安装 Python 依赖...
    python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo [错误] 创建 .venv 失败，请确认 Python 环境完整。
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    if not %errorlevel%==0 (
        echo [提示] 清华镜像安装受阻，正在切换官方源重试...
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    )
    set "PY_CMD=.venv\Scripts\python.exe"
    if exist ".venv\Scripts\pythonw.exe" set "PYW_CMD=.venv\Scripts\pythonw.exe"
)

echo [启动中] 正在打开 PaperHarness 独立桌面窗口...
if defined PYW_CMD (
    start "" "%PYW_CMD%" launch_desktop.py
) else (
    start "" "%PY_CMD%" launch_desktop.py
)
exit /b 0
