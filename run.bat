@echo off
chcp 65001 >nul
echo ============================================
echo   PM小帮手 启动脚本
echo ============================================
echo.
echo 选择启动模式:
echo   1. Web 界面 (python webapp.py)
echo   2. CLI 命令行 (python main.py)
echo   3. 运行测试 (pytest)
echo   4. 测试 + 覆盖率报告 (pytest --cov)
echo.
set /p choice="请输入选项 (1/2/3/4): "

if "%choice%"=="1" (
    echo.
    echo 🌐 启动 Web 界面...
    python webapp.py
) else if "%choice%"=="2" (
    echo.
    echo 🤖 启动 CLI 命令行...
    python main.py
) else if "%choice%"=="3" (
    echo.
    echo 🧪 运行测试...
    python -m pytest tests/ -v
) else if "%choice%"=="4" (
    echo.
    echo 📊 运行测试 + 覆盖率报告...
    python -m pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html
    echo.
    echo ✅ HTML 报告已生成: htmlcov\index.html
) else (
    echo ❌ 无效选项，请输入 1/2/3/4
)

pause
