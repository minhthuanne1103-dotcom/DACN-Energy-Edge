"""Bản đồ thanh ghi Modbus của đồng hồ đa năng + relay (xem docs/ARCHITECTURE.md).

Holding registers (FC03), địa chỉ bắt đầu từ 0:
  0 Điện áp      x0.1  V        6 Dòng rò       x0.1 mA
  1 Dòng điện    x0.01 A        7 Nhiệt độ      x0.1 °C
  2 Công suất    W              8 Điện năng HI  Wh (uint32)
  3 PF           x0.001         9 Điện năng LO
  4 Tần số       x0.01 Hz      10 Trạng thái    bit0 = relay đóng
  5 THD dòng     x0.1 %        11 Heartbeat
  100 (ghi)  kịch bản lỗi mô phỏng (chỉ có trong simulator)
Coil 0 (FC01/FC05): relay, 1 = đóng (cấp điện), 0 = ngắt.
"""

N_REGS = 12
SCENARIO_REG = 100
COIL_RELAY = 0


def _u16(x):
    return max(0, min(65535, int(round(x))))


def encode(m, heartbeat=0):
    e = int(m["energy_wh"]) & 0xFFFFFFFF
    return [
        _u16(m["voltage"] * 10), _u16(m["current"] * 100), _u16(m["power_kw"] * 1000),
        _u16(m["pf"] * 1000), _u16(m["freq"] * 100), _u16(m["thd"] * 10),
        _u16(m["leakage_ma"] * 10), _u16(m["temp_c"] * 10),
        (e >> 16) & 0xFFFF, e & 0xFFFF, 1 if m["relay"] else 0, heartbeat & 0xFFFF,
    ]


def decode(r):
    e = (r[8] << 16) | r[9]
    return {
        "voltage": r[0] / 10.0, "current": r[1] / 100.0, "power_kw": r[2] / 1000.0,
        "pf": r[3] / 1000.0, "freq": r[4] / 100.0, "thd": r[5] / 10.0,
        "leakage_ma": r[6] / 10.0, "temp_c": r[7] / 10.0,
        "energy_wh": e, "energy_kwh": e / 1000.0,
        "relay": bool(r[10] & 1), "heartbeat": r[11],
    }
