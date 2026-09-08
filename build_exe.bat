@echo off
REM ============================================================
REM  build_exe.bat  —  สร้าง FeasFlow.exe ใหม่ในคลิกเดียว
REM ============================================================
echo.
echo [1/3] Installing/updating build tools...
python -m pip install --quiet --upgrade pyinstaller pillow customtkinter matplotlib openpyxl

echo.
echo [2/3] Regenerating app icon...
python make_icon.py

echo.
echo [3/3] Building FeasFlow.exe (this may take a minute)...
python -m PyInstaller FeasFlow.spec --noconfirm --clean

echo.
echo ============================================================
echo  DONE.  Output folder:  dist\FeasFlow\  (run FeasFlow.exe inside)
echo  To distribute: right-click the dist\FeasFlow folder -^> Compress to ZIP
echo ============================================================
pause
