@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ClipXD kurulumu...
where python >nul 2>nul || (echo Python bulunamadi. https://www.python.org adresinden Python 3.11+ kurun. & pause & exit /b 1)
if not exist .venv (
    python -m venv .venv || (echo Sanal ortam olusturulamadi. & pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt || (echo Paketler kurulamadi. & pause & exit /b 1)
echo.
echo Kurulum tamamlandi. Uygulamayi baslatmak icin ClipXD.bat dosyasini calistirin.
pause
