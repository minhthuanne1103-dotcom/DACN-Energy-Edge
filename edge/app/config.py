"""Cấu hình chung của hệ thống, đọc từ biến môi trường (xem file .env)."""
import os
from dataclasses import dataclass


def _s(name, default):
    return os.environ.get(name, default)


def _f(name, default):
    return float(os.environ.get(name, default))


def _i(name, default):
    return int(os.environ.get(name, default))


def _b(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ---- Chung -----------------------------------------------------------------
SITE = _s("SITE", "factory/line1")          # tiền tố topic MQTT
UTC_OFFSET_H = _f("UTC_OFFSET_H", 7)        # múi giờ Việt Nam
POLL_INTERVAL = _f("POLL_INTERVAL", 1.0)    # chu kỳ đọc Modbus (giây)
NOMINAL_V = 400.0                           # điện áp dây 3 pha (V)
NOMINAL_HZ = 50.0

# ---- Modbus ----------------------------------------------------------------
MODBUS_HOST = _s("MODBUS_HOST", "modbus-sim")
MODBUS_TCP_PORT = _i("MODBUS_TCP_PORT", 5020)   # Modbus TCP (khung MBAP)
MODBUS_RTU_PORT = _i("MODBUS_RTU_PORT", 5021)   # Modbus RTU (khung CRC16) qua cổng RS485-TCP

# ---- MQTT over TLS (mutual TLS) -------------------------------------------
MQTT_HOST = _s("MQTT_HOST", "mosquitto")
MQTT_PORT = _i("MQTT_PORT", 8883)
CERT_DIR = _s("CERT_DIR", "/certs")
MODEL_DIR = _s("MODEL_DIR", "/models")

# ---- Tối ưu năng lượng -----------------------------------------------------
DEMAND_LIMIT_KW = _f("DEMAND_LIMIT_KW", 28.0)       # ngưỡng công suất đỉnh
PEAK_LIMIT_FACTOR = _f("PEAK_LIMIT_FACTOR", 0.9)    # giờ cao điểm siết ngưỡng xuống 90 %
# Đơn giá minh họa (VND/kWh). Hãy sửa theo hóa đơn tiền điện thực tế của cơ sở.
PRICE_PEAK = _f("PRICE_PEAK", 3000)
PRICE_NORMAL = _f("PRICE_NORMAL", 1800)
PRICE_OFFPEAK = _f("PRICE_OFFPEAK", 1100)

# ---- AI --------------------------------------------------------------------
AI_WARN_N = _i("AI_WARN_N", 5)      # số mẫu bất thường liên tiếp để cảnh báo
AI_TRIP_N = _i("AI_TRIP_N", 30)     # số mẫu bất thường liên tiếp để ngắt relay
AI_TRIP = _b("AI_TRIP", True)

# ---- InfluxDB (cho bridge) ------------------------------------------------
INFLUX_URL = _s("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = _s("INFLUX_TOKEN", "")
INFLUX_ORG = _s("INFLUX_ORG", "factory")
INFLUX_BUCKET = _s("INFLUX_BUCKET", "energy")


@dataclass(frozen=True)
class Load:
    name: str
    unit: int          # Modbus slave id
    transport: str     # "tcp" hoặc "rtu"
    rated_kw: float
    pf: float          # hệ số công suất định mức
    shed_order: int    # 0 = tải trọng yếu, không bao giờ bị cắt; số nhỏ bị cắt trước

    @property
    def rated_a(self):
        return self.rated_kw * 1000 / (3 ** 0.5 * NOMINAL_V * self.pf)


LOADS = (
    Load("motor", 1, "tcp", 7.5, 0.85, 0),        # động cơ dây chuyền (trọng yếu)
    Load("compressor", 2, "tcp", 11.0, 0.82, 2),  # máy nén khí
    Load("hvac", 3, "rtu", 15.0, 0.88, 1),        # điều hòa / thông gió (cắt đầu tiên)
    Load("lighting", 4, "rtu", 3.0, 0.95, 3),     # chiếu sáng
)
LOAD_BY_NAME = {ld.name: ld for ld in LOADS}
