@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title AZB Tunnel (Cloudflare)

rem Phai chay CHAY_AZB.bat truoc. Tunnel tro vao 127.0.0.1 (khong dung "localhost" vi co the bi phan giai sang IPv6 ::1, trong khi app chi nghe IPv4).
".venv\Scripts\python.exe" tools\kiem_cai_dat.py --cong
if not errorlevel 2 (
  echo [LOI] AZB chua chay. Hay bam dup CHAY_AZB.bat truoc, doi no len roi chay lai file nay.
  pause
  exit /b 1
)

rem Tat tunnel cu (vi du tro nham cong 8000) de khong bi lan.
taskkill /f /im cloudflared.exe >nul 2>&1

set "CF=cloudflared"
where cloudflared >nul 2>&1 || set "CF=C:\Program Files (x86)\cloudflared\cloudflared.exe"

echo Dang mo tunnel Cloudflare toi http://127.0.0.1:8765 ...
echo Tim dong "https://xxxx.trycloudflare.com" ben duoi de lay link. Dong cua so nay de tat tunnel.
echo.
"%CF%" tunnel --url http://127.0.0.1:8765
pause
