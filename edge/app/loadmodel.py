"""Mô hình vật lý đơn giản của một tải 3 pha, dùng để mô phỏng thiết bị và sinh dữ liệu huấn luyện AI.

Các kịch bản lỗi (ghi vào thanh ghi 100 của thiết bị Modbus):
  0 normal        bình thường
  1 overload      quá tải (dòng tăng ~1.9 lần trong 8 s)
  2 voltage_sag   sụt áp (-18 % trong 4 s)
  3 ground_leak   dòng rò tăng 3 mA/s (chạm đất / hỏng cách điện)
  4 bearing_wear  mòn ổ trục: THD, độ gợn dòng, nhiệt độ tăng chậm trong 60 s, CHƯA vượt ngưỡng cứng
  5 overvoltage   quá áp (+14 % trong 4 s)
"""
import math
import random

from .config import NOMINAL_HZ, NOMINAL_V

SCENARIOS = {
    "normal": 0, "overload": 1, "voltage_sag": 2,
    "ground_leak": 3, "bearing_wear": 4, "overvoltage": 5,
}
SCENARIO_NAMES = {v: k for k, v in SCENARIOS.items()}

# Các đặc trưng đưa vào AI (khóa trong dict đo lường)
FEATURES = ("voltage", "current", "power_kw", "pf", "thd", "leakage_ma", "temp_c")


def _utilization(load, t, hour):
    """Hệ số mang tải 0..1+ theo thời gian và giờ trong ngày."""
    if load.name == "motor":
        return 0.72 + 0.06 * math.sin(t / 37.0)
    if load.name == "compressor":   # chu kỳ có tải / không tải
        return 0.68 + 0.22 * math.sin(2 * math.pi * t / 90.0)
    if load.name == "hvac":
        day = 0.5 + 0.5 * math.sin(math.pi * (hour - 7) / 12) if 7 <= hour <= 19 else 0.0
        return 0.35 + 0.5 * day
    if load.name == "lighting":
        return 0.9 if 6 <= hour < 22 else 0.35
    return 0.6


class LoadState:
    def __init__(self, load, seed=None):
        self.load = load
        self.rng = random.Random(seed)
        self.t = 0.0
        self.temp = 38.0
        self.energy_wh = 0.0
        self.relay = True
        self._scn = 0
        self._scn_t = 0.0

    @property
    def scenario(self):
        return self._scn

    def set_scenario(self, scn):
        if scn != self._scn:
            self._scn = scn
            self._scn_t = 0.0

    def step(self, dt, hour):
        """Tiến mô hình thêm dt giây, trả về dict các đại lượng đo."""
        L, r = self.load, self.rng
        self.t += dt
        self._scn_t += dt
        s, k = self._scn, self._scn_t

        util = max(0.05, _utilization(L, self.t, hour)) * (1 + r.gauss(0, 0.012))
        v = NOMINAL_V + r.gauss(0, 1.2)
        thd = 3.0 + r.gauss(0, 0.25)
        leak = 2.0 + abs(r.gauss(0, 0.3))
        pf_drop = ripple = dtemp = 0.0

        if s == 1:      # quá tải
            util = max(util, 0.7) * (1 + 0.9 * min(1.0, k / 8.0))
        elif s == 2:    # sụt áp
            v *= 1 - 0.18 * min(1.0, k / 4.0)
        elif s == 3:    # rò điện
            leak = 2.0 + min(80.0, 3.0 * k) + abs(r.gauss(0, 0.3))
        elif s == 4:    # mòn ổ trục (hỏng hóc tiến triển chậm)
            ramp = min(1.0, k / 60.0)
            thd += 6.5 * ramp
            pf_drop = 0.07 * ramp
            ripple = 0.10 * ramp
            dtemp = 12.0 * ramp
            util *= 1 + 0.05 * ramp
        elif s == 5:    # quá áp
            v *= 1 + 0.14 * min(1.0, k / 4.0)

        if self.relay:
            pf = max(0.5, L.pf * (0.88 + 0.12 * min(util, 1.0)) - pf_drop)
            p_kw = L.rated_kw * util
            i = p_kw * 1000 / (math.sqrt(3) * v * pf)
            i *= 1 + r.gauss(0, 0.005 + ripple)
            p_kw = math.sqrt(3) * v * i * pf / 1000
        else:           # relay ngắt: tải cách ly khỏi lưới
            pf = i = p_kw = leak = thd = 0.0

        target = 30.0 + 25.0 * (i / L.rated_a) ** 2 + dtemp
        self.temp += (target - self.temp) * min(1.0, dt / 40.0) + r.gauss(0, 0.05)
        self.energy_wh += p_kw * 1000 * dt / 3600.0

        return {
            "voltage": v, "current": i, "power_kw": p_kw, "pf": pf,
            "freq": NOMINAL_HZ + r.gauss(0, 0.02), "thd": thd,
            "leakage_ma": leak, "temp_c": self.temp,
            "energy_wh": self.energy_wh, "relay": self.relay,
        }
