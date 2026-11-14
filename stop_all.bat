@echo off
cd /d "%~dp0"
echo Dang tat cac tien trinh Python va dung Docker Containers...
taskkill /FI "WINDOWTITLE eq 1. MODBUS SIMULATOR*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq 2. EDGE GATEWAY*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq 3. IOT RELAY*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq 4. BANG DIEU KHIEN DEMO*" /T /F >nul 2>&1
docker compose stop
echo [OK] Da dung toan bo he thong!
pause