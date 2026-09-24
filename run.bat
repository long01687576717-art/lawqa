@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   劳动法知识库问答系统
echo ============================================
echo.
echo [1/2] 正在安装依赖（首次运行较慢，请耐心等待）...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo 依赖安装失败，请检查是否已安装 Python 3 并加入 PATH。
    pause
    exit /b 1
)
echo.
echo [2/2] 正在启动服务，请保持本窗口不要关闭...
echo       启动完成后，用浏览器打开 http://127.0.0.1:8000
echo.
python app.py
pause
