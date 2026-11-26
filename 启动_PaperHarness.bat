@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================================
echo   PaperHarness Academic Research ^& Publishing Workbench
echo ========================================================

set "PY_CMD="
set "PYW_CMD="

rem 1. Prefer project-local .venv if complete
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import fastapi, uvicorn, httpx, docx, pptx, matplotlib, fitz, bs4, webview" >nul 2>nul
    if !errorlevel!==0 (
        set "PY_CMD=%~dp0.venv\Scripts\python.exe"
        if exist ".venv\Scripts\pythonw.exe" set "PYW_CMD=%~dp0.venv\Scripts\pythonw.exe"
    )
)

rem 2. Otherwise scan ALL python.exe on PATH and pick the first one with all deps ready
if not defined PY_CMD (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PY_CMD (
            echo "%%P" | findstr /i "WindowsApps" >nul
            if !errorlevel! neq 0 (
                "%%P" -c "import fastapi, uvicorn, httpx, docx, pptx, matplotlib, fitz, bs4, webview" >nul 2>nul
                if !errorlevel!==0 (
                    set "PY_CMD=%%P"
                    if exist "%%~dpPpythonw.exe" set "PYW_CMD=%%~dpPpythonw.exe"
                )
            )
        )
    )
)

rem 3. First-time setup: create .venv with the first real Python and install requirements.txt
if not defined PY_CMD (
    set "BASE_PY="
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined BASE_PY (
            echo "%%P" | findstr /i "WindowsApps" >nul
            if !errorlevel! neq 0 set "BASE_PY=%%P"
        )
    )
    if not defined BASE_PY (
        echo [Error] Python 3.10+ not found. Please install Python and check "Add Python to PATH":
        echo         https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo [Setup] Creating .venv using "!BASE_PY!" and installing dependencies...
    "!BASE_PY!" -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo [Error] Failed to create .venv.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    if !errorlevel! neq 0 (
        echo [Retry] Retrying with default PyPI mirror...
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    )
    set "PY_CMD=%~dp0.venv\Scripts\python.exe"
    if exist ".venv\Scripts\pythonw.exe" set "PYW_CMD=%~dp0.venv\Scripts\pythonw.exe"
)

echo [Launch] Python: !PY_CMD!
if defined PYW_CMD (
    start "" "!PYW_CMD!" launch_desktop.py
) else (
    start "" "!PY_CMD!" launch_desktop.py
)
exit /b 0
