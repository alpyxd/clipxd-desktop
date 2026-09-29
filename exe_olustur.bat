@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Once kurulum.bat dosyasini calistirin.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m pip install --upgrade pyinstaller || exit /b 1
.venv\Scripts\python.exe -c "from clipxd.app import write_icon; write_icon('assets/icon.ico')" || exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --name ClipXD --icon assets\icon.ico ^
    --collect-data imageio_ffmpeg --collect-all yt_dlp_ejs ClipXD.pyw || exit /b 1
echo.
echo Hazir: dist\ClipXD\ClipXD.exe  (dist\ClipXD klasorunun tamamini birlikte tasiyin)
pause
