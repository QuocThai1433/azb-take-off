@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title AZB Take-off

if not exist ".venv\Scripts\python.exe" (
  echo Lan dau chay: dang cai dat ...
  call CAI_DAT.bat
  if errorlevel 1 exit /b 1
)

rem --- Da co ban dang chay thi chi mo trinh duyet ---
".venv\Scripts\python.exe" tools\kiem_cai_dat.py --cong
if errorlevel 2 (
  echo AZB da dang chay san, dang mo trinh duyet ...
  start "" http://127.0.0.1:8765
  exit /b 0
)

".venv\Scripts\python.exe" tools\kiem_cai_dat.py
echo.
echo Dang khoi dong AZB Take-off tai http://127.0.0.1:8765
echo Dong cua so nay (hoac bam Ctrl + C) de tat phan mem.
echo Nhat ky loi: data\logs\azb.log
echo.
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8765"
".venv\Scripts\python.exe" -m app.main
if errorlevel 1 (
  echo.
  echo [LOI] Phan mem dung bat thuong. Xem data\logs\azb.log hoac gui file do cho nguoi ho tro.
  pause
)
