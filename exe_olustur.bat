@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Once kurulum.bat dosyasini calistirin.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m pip install --upgrade pyinstaller || exit /b 1
.venv\Scripts\python.exe packaging\build_release.py || exit /b 1
echo.
echo Hazir: dist\ClipXD\ClipXD.exe ve dist\ClipXD-Desktop-*-win64.zip
pause
