CREATE TABLE IF NOT EXISTS devices (
    device_id VARCHAR(50) PRIMARY KEY,
    device_name VARCHAR(100) NOT NULL,
    zone VARCHAR(50),
    modbus_slave_id INT DEFAULT 1,
    relay_topic VARCHAR(100),
    status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS anomaly_logs (
    log_id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) REFERENCES devices(device_id),
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    voltage FLOAT,
    current FLOAT,
    power_w FLOAT,
    power_factor FLOAT,
    anomaly_score FLOAT,
    action_taken VARCHAR(50)
);

INSERT INTO devices (device_id, device_name, zone, modbus_slave_id, relay_topic)
VALUES ('DEV_001', 'Tu dien May Phay CNC 01', 'Xuong_CNC_01', 1, 'factory/zone1/DEV_001/relay/cmd')
ON CONFLICT (device_id) DO NOTHING;
