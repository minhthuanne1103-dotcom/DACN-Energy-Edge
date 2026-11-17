"""Bảo vệ an toàn điện bằng luật cứng (chạy tại biên, độc lập với AI và với đám mây)."""
from dataclasses import dataclass

from .config import NOMINAL_V

I_SHORT = 1.5          # x định mức: ngắn mạch / quá dòng tức thời -> ngắt ngay
I_OVER, I_OVER_N = 1.2, 3
LEAK_TRIP, LEAK_WARN = 30.0, 15.0          # mA (RCD 30 mA)
V_LOW, V_HIGH, V_N = 0.88 * NOMINAL_V, 1.10 * NOMINAL_V, 3
T_TRIP, T_WARN = 85.0, 75.0                # °C
THD_WARN, THD_N = 12.0, 5                  # %


@dataclass
class Alarm:
    code: str
    severity: str       # warning | critical
    message: str
    value: float
    trip: bool = False  # True -> gateway phải ngắt relay


class SafetyMonitor:
    def __init__(self, load):
        self.load = load
        self.c = {}

    def reset(self):
        self.c.clear()

    def _sust(self, key, cond, n):
        self.c[key] = self.c.get(key, 0) + 1 if cond else 0
        return self.c[key] >= n

    def evaluate(self, m):
        if not m["relay"]:
            self.reset()
            return []
        ir, out = self.load.rated_a, []

        i = m["current"]
        short = i > I_SHORT * ir
        over = self._sust("oc", i > I_OVER * ir, I_OVER_N)
        if short or over:
            out.append(Alarm("OVERCURRENT_SHORT" if short else "OVERCURRENT", "critical",
                             f"Dòng {i:.1f} A vượt ngưỡng (định mức {ir:.1f} A)", i, True))

        lk = m["leakage_ma"]
        lk_trip = self._sust("lk_t", lk > LEAK_TRIP, 2)
        lk_warn = self._sust("lk_w", lk > LEAK_WARN, 2)
        if lk_trip:
            out.append(Alarm("LEAKAGE", "critical", f"Dòng rò {lk:.1f} mA > {LEAK_TRIP:.0f} mA", lk, True))
        elif lk_warn:
            out.append(Alarm("LEAKAGE_WARN", "warning", f"Dòng rò tăng cao {lk:.1f} mA", lk))

        v = m["voltage"]
        if self._sust("uv", v < V_LOW, V_N):
            out.append(Alarm("UNDERVOLTAGE", "critical", f"Sụt áp {v:.0f} V", v, True))
        if self._sust("ov", v > V_HIGH, V_N):
            out.append(Alarm("OVERVOLTAGE", "critical", f"Quá áp {v:.0f} V", v, True))

        t = m["temp_c"]
        t_trip = self._sust("tt", t > T_TRIP, 2)
        if t_trip:
            out.append(Alarm("OVERTEMP", "critical", f"Nhiệt độ {t:.0f} °C", t, True))
        elif t > T_WARN:
            out.append(Alarm("OVERTEMP_WARN", "warning", f"Nhiệt độ cao {t:.0f} °C", t))

        if self._sust("thd", m["thd"] > THD_WARN, THD_N):
            out.append(Alarm("THD_HIGH", "warning", f"Méo hài dòng {m['thd']:.1f} %", m["thd"]))
        return out
