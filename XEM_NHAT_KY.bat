@echo off
cd /d "%~dp0"
if exist "data\logs\azb.log" ( start "" notepad "data\logs\azb.log" ) else ( echo Chua co nhat ky: phan mem chua duoc chay lan nao. & pause )
