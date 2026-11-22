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


-- =====================================================================
-- DANH GIA MUC DO AN TOAN CUA THONG SO DIEN
-- 3 muc: SAFE (an toan) < WARNING (can kiem tra lai) < DANGER (nguy hiem)
-- Khoang gia tri: min_value <= gia tri < max_value (NULL = khong gioi han)
-- Co the sua nguong bang UPDATE ma khong can sua code.
-- =====================================================================

CREATE TABLE IF NOT EXISTS threshold_rules (
    rule_id SERIAL PRIMARY KEY,
    metric VARCHAR(20) NOT NULL CHECK (metric IN ('voltage', 'current', 'power_w', 'power_factor')),
    level VARCHAR(10) NOT NULL CHECK (level IN ('SAFE', 'WARNING', 'DANGER')),
    severity INT NOT NULL CHECK (severity IN (1, 2, 3)),
    min_value FLOAT,
    max_value FLOAT,
    label_vi VARCHAR(30) NOT NULL,
    description TEXT,
    CHECK (min_value IS NULL OR max_value IS NULL OR min_value < max_value)
);

-- Chi nap du lieu mac dinh khi bang con trong (chay lai khong bi trung)
INSERT INTO threshold_rules (metric, level, severity, min_value, max_value, label_vi, description)
SELECT * FROM (VALUES
    -- Dien ap (V): luoi 220V, cho phep lech +-5% (209-231V), +-10% (198-242V)
    ('voltage',      'DANGER',  3, NULL::float, 198.0, 'Nguy hiem',       'Sut ap nang (< 198V, lech tren 10%)'),
    ('voltage',      'WARNING', 2, 198.0,       209.0, 'Can kiem tra lai', 'Dien ap thap (198-209V, lech 5-10%)'),
    ('voltage',      'SAFE',    1, 209.0,       231.0, 'An toan',          'Dien ap on dinh (209-231V, lech duoi 5%)'),
    ('voltage',      'WARNING', 2, 231.0,       242.0, 'Can kiem tra lai', 'Dien ap cao (231-242V, lech 5-10%)'),
    ('voltage',      'DANGER',  3, 242.0,       NULL,  'Nguy hiem',        'Qua ap (>= 242V, lech tren 10%)'),
    -- Dong dien (A): dinh muc may phay CNC ~ 20A
    ('current',      'SAFE',    1, NULL,        20.0,  'An toan',          'Dong tai binh thuong (< 20A)'),
    ('current',      'WARNING', 2, 20.0,        28.0,  'Can kiem tra lai', 'Dong tai cao (20-28A, tren dinh muc)'),
    ('current',      'DANGER',  3, 28.0,        NULL,  'Nguy hiem',        'Qua tai dong co (>= 28A)'),
    -- Cong suat (W)
    ('power_w',      'SAFE',    1, NULL,        3500.0,'An toan',          'Cong suat binh thuong (< 3500W)'),
    ('power_w',      'WARNING', 2, 3500.0,      5000.0,'Can kiem tra lai', 'Cong suat cao (3500-5000W)'),
    ('power_w',      'DANGER',  3, 5000.0,      NULL,  'Nguy hiem',        'Cong suat qua cao (>= 5000W)'),
    -- He so cong suat (PF): cang thap cang ton hao / ro dien / tu bu hong
    ('power_factor', 'DANGER',  3, NULL,        0.70,  'Nguy hiem',        'PF rat thap (< 0.70), nghi ro dien hoac tu bu hong'),
    ('power_factor', 'WARNING', 2, 0.70,        0.85,  'Can kiem tra lai', 'PF thap (0.70-0.85), can kiem tra tu bu'),
    ('power_factor', 'SAFE',    1, 0.85,        NULL,  'An toan',          'PF tot (>= 0.85)')
) AS v(metric, level, severity, min_value, max_value, label_vi, description)
WHERE NOT EXISTS (SELECT 1 FROM threshold_rules);

-- Muc do cao nhat (1-3) cua 1 thong so; 0 neu khong co luat nao khop
CREATE OR REPLACE FUNCTION metric_severity(p_metric TEXT, p_value DOUBLE PRECISION)
RETURNS INT LANGUAGE sql STABLE AS $$
    SELECT COALESCE(MAX(severity), 0) FROM threshold_rules
    WHERE metric = p_metric
      AND (min_value IS NULL OR p_value >= min_value)
      AND (max_value IS NULL OR p_value < max_value)
$$;

-- Danh gia 1 lan do tong hop: lay muc xau nhat trong 4 thong so
CREATE OR REPLACE FUNCTION assess_reading(
    v DOUBLE PRECISION, i DOUBLE PRECISION, p DOUBLE PRECISION, pf DOUBLE PRECISION
) RETURNS VARCHAR LANGUAGE sql STABLE AS $$
    SELECT CASE GREATEST(
        metric_severity('voltage', v), metric_severity('current', i),
        metric_severity('power_w', p), metric_severity('power_factor', pf))
        WHEN 3 THEN 'DANGER' WHEN 2 THEN 'WARNING' WHEN 1 THEN 'SAFE' ELSE 'UNKNOWN' END
$$;

-- Nhat ky bat thuong kem danh gia muc do (dung cho Grafana / bao cao)
CREATE OR REPLACE VIEW v_anomaly_assessed AS
SELECT
    log_id, device_id, detected_at, voltage, current, power_w, power_factor,
    anomaly_score, action_taken,
    assess_reading(voltage, current, power_w, power_factor) AS risk_level,
    CASE assess_reading(voltage, current, power_w, power_factor)
        WHEN 'DANGER' THEN 'Nguy hiem' WHEN 'WARNING' THEN 'Can kiem tra lai'
        WHEN 'SAFE' THEN 'An toan' ELSE 'Chua xac dinh' END AS risk_label_vi
FROM anomaly_logs;
