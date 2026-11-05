@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title AZB Take-off - Cai dat

echo ============================================================
echo   AZB Take-off: cai dat (chi can lam mot lan)
echo ============================================================

rem --- Tim Python ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo.
  echo [LOI] Chua cai Python. Tai Python 3.12 tai https://www.python.org/downloads/
  echo       Khi cai nho tick "Add python.exe to PATH", sau do chay lai file nay.
  pause & exit /b 1
)

rem --- Tao moi truong ao neu chua co ---
if not exist ".venv\Scripts\python.exe" (
  echo Dang tao moi truong ao .venv ...
  %PY% -m venv .venv || ( echo [LOI] Khong tao duoc .venv & pause & exit /b 1 )
)

echo Dang cai thu vien (lan dau co the mat vai phut) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (
  echo [LOI] Cai thu vien that bai. Kiem tra ket noi mang roi chay lai.
  pause & exit /b 1
)

echo.
".venv\Scripts\python.exe" tools\kiem_cai_dat.py
echo.
echo Xong. Bam dup CHAY_AZB.bat de mo phan mem.
pause
