@echo off
cd /d "%~dp0"
title HE THONG GIAM SAT NANG LUONG VA AI DOCKER EDGE

echo =====================================================================
echo   KHOI DONG HA TANG GIAM SAT NANG LUONG VA AI LOCAL ANOMALY DETECTION
echo =====================================================================

docker info >nul 2>&1
if errorlevel 1 (
    echo [LOI] Docker Desktop chua chay. Hay mo Docker Desktop, doi no san sang roi chay lai.
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo [1/6] Dang tao moi truong ao Python cho may moi...
    py -3.12 -m venv venv 2>nul || py -3.11 -m venv venv 2>nul || python -m venv venv
    if not exist "venv\Scripts\python.exe" (
        echo [LOI] Khong tao duoc venv. Hay cai Python 3.11 hoac 3.12 ^(tich "Add to PATH"^).
        pause
        exit /b 1
    )
    echo [1/6] Dang cai dat cac thu vien Python...
    call "venv\Scripts\pip.exe" install -r requirements.txt
) else (
    echo [1/6] Moi truong ao Python da san sang!
)

if not exist "certs\ca.crt" (
    echo [2/6] Dang tao chung chi bao mat TLS...
    call "venv\Scripts\python.exe" scripts/generate_certs.py
)

if not exist "ai-service\models\iso_forest.joblib" (
    echo [2/6] Dang huan luyen mo hinh AI Isolation Forest...
    call "venv\Scripts\python.exe" scripts/train_ai_model.py
)

echo [3/6] Dang khoi chay 5 Container Docker Edge...
docker compose up -d --build

echo [4/6] Doi 8 giay de Database va Grafana khoi dong...
timeout /t 8 /nobreak >nul
call "venv\Scripts\python.exe" scripts/setup_grafana.py

echo [5/6] Dang bat cac tien trinh Modbus TCP, MQTT over TLS va IoT Relay...
start "1. MODBUS SIMULATOR" cmd /k ""%~dp0venv\Scripts\python.exe" scripts/modbus_sim_server.py"
timeout /t 2 /nobreak >nul
start "2. EDGE GATEWAY" cmd /k ""%~dp0venv\Scripts\python.exe" scripts/modbus_to_mqtt.py"
start "3. IOT RELAY" cmd /k ""%~dp0venv\Scripts\python.exe" scripts/iot_relay_actuator.py"
start "4. BANG DIEU KHIEN DEMO" cmd /k ""%~dp0venv\Scripts\python.exe" scripts/fault_injector.py"

echo [6/6] Dang mo giao dien Grafana Dashboard tren trinh duyet...
start http://localhost:3000/d/industrial-energy-ai

echo.
echo [HOAN TAT] He thong da chay 100%%! Dang hien thi log AI ben duoi:
echo =====================================================================
docker logs -f edge_ai_engine
pause