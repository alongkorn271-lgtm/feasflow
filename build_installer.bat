@echo off
REM ============================================================
REM  build_installer.bat  —  สร้าง FeasFlow_Setup.exe ครบจบในคลิกเดียว
REM  (1) build โปรแกรม (onedir)  (2) ห่อเป็น installer ด้วย Inno Setup
REM ============================================================
setlocal

echo.
echo [1/4] Installing/updating build tools...
python -m pip install --quiet --upgrade pyinstaller pillow customtkinter matplotlib openpyxl

echo.
echo [2/4] Regenerating app icon...
python make_icon.py

echo.
echo [3/4] Building FeasFlow (onedir)...
python -m PyInstaller FeasFlow.spec --noconfirm --clean

echo.
echo [4/4] Compiling Windows installer...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo   ERROR: ไม่พบ Inno Setup. ติดตั้งด้วยคำสั่ง:
  echo          winget install --id JRSoftware.InnoSetup -e
  pause
  exit /b 1
)
"%ISCC%" FeasFlow_installer.iss

echo.
echo ============================================================
echo  DONE.  Installer:  Output\FeasFlow_Setup.exe
echo  ส่งไฟล์นี้ไฟล์เดียวให้ผู้ใช้ -^> ดับเบิลคลิกติดตั้งได้เลย
echo ============================================================
pause
