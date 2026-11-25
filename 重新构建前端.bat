@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [构建前端] 正在执行 TypeScript 严格检查与 Vite 生产构建...
pushd frontend
if not exist "node_modules" (
    echo [安装依赖] 正在执行 npm install ...
    call npm install
)
call npm run build
popd

if %errorlevel%==0 (
    echo.
    echo [完成] 前端已构建至 frontend\dist，现在可直接双击「启动_PaperHarness.bat」体验最新界面！
) else (
    echo.
    echo [失败] 前端编译存在 TypeScript 或语法错误，请根据上方提示修复。
)
pause
