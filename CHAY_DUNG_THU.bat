@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title AZB dung thu (Cloudflare)

rem Ban dung thu: du lieu rieng (data_dung_thu), cong 8766. Khong dong vao du lieu ban dang test o CHAY_AZB.bat (8765).
if not exist ".venv\Scripts\python.exe" (
  echo [LOI] Chua cai dat. Hay chay CAI_DAT.bat truoc.
  pause
  exit /b 1
)

set "AZB_DATA_DIR=%~dp0data_dung_thu"
set "AZB_PORT=8766"
if not exist "%AZB_DATA_DIR%" mkdir "%AZB_DATA_DIR%"

echo Dang khoi dong server dung thu tai http://127.0.0.1:8766 ...
start "AZB dung thu - server (dong cua so nay de tat)" cmd /k ".venv\Scripts\python.exe -m app.main"
timeout /t 5 /nobreak >nul

set "CF=cloudflared"
where cloudflared >nul 2>&1 || set "CF=C:\Program Files (x86)\cloudflared\cloudflared.exe"

echo.
echo Tim dong "https://xxxx.trycloudflare.com" ben duoi va gui cho nguoi dung thu.
echo Dong cua so nay de tat tunnel. Muon tat server thi dong cua so "AZB dung thu - server".
echo.
"%CF%" tunnel --url http://127.0.0.1:8766
pause
