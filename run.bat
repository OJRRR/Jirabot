@echo off
chcp 65001 >nul

title PM小帮手 / Jira Bot

:menu
cls
echo ========================================
echo   PM小帮手（Jira Bot）
echo ========================================
echo.
echo 请选择启动模式：
echo.
echo   [1] CLI 后台模式
echo   [2] Web 网页服务
echo   [Q] 退出
echo.
set /p choice="输入 1, 2 或 Q: "
if "%choice%"=="1" goto cli
if "%choice%"=="2" goto web
if /i "%choice%"=="q" goto end
goto menu

:cli
cls
echo ========================================
echo   CLI 模式 - PM小帮手
echo ========================================
echo.
python main.py
if %errorlevel% neq 0 (
    echo.
    echo ! 运行失败，请确保已安装 Python 并安装依赖: pip install -r requirements.txt
    echo.
    pause
)
goto menu

:web
cls
echo ========================================
echo   Web 模式 - PM小帮手
echo ========================================
echo.
echo 访问地址: http://127.0.0.1:5000
echo.
python webapp.py
if %errorlevel% neq 0 (
    echo.
    echo ! 运行失败，请确保已安装 Python 并安装依赖: pip install -r requirements.txt
    echo.
    pause
)
goto menu

:end
echo.
echo 再见！
timeout /t 2 /nobreak >nul
