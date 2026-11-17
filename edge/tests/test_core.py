import json
from datetime import datetime, timezone, timedelta

from app import config as C
from app import registers as R
from app.bridge import to_points
from app.loadmodel import SCENARIOS, LoadState
from app.optimizer import DemandManager
from app.safety import SafetyMonitor
from app.tariff import tariff

MOTOR = C.LOAD_BY_NAME["motor"]


def run(state, seconds, hour=10.0):
    return [state.step(1.0, hour) for _ in range(seconds)]


def test_normal_operation_has_no_alarm():
    st, mon = LoadState(MOTOR, 1), SafetyMonitor(MOTOR)
    for m in run(st, 600):
        assert mon.evaluate(m) == []


def test_register_roundtrip():
    m = run(LoadState(MOTOR, 2), 5)[-1]
    d = R.decode(R.encode(m, 7))
    assert abs(d["voltage"] - m["voltage"]) < 0.1
    assert abs(d["current"] - m["current"]) < 0.01
    assert abs(d["power_kw"] - m["power_kw"]) < 0.001
    assert d["relay"] is True and d["heartbeat"] == 7


def test_relay_open_zero_current():
    st = LoadState(MOTOR, 3)
    st.relay = False
    m = run(st, 3)[-1]
    assert m["current"] == 0 and m["power_kw"] == 0 and m["leakage_ma"] == 0


def _first_trip(scn, seconds=60):
    st, mon = LoadState(MOTOR, 4), SafetyMonitor(MOTOR)
    run(st, 30)
    st.set_scenario(SCENARIOS[scn])
    for k, m in enumerate(run(st, seconds)):
        trips = [a.code for a in mon.evaluate(m) if a.trip]
        if trips:
            return k, trips[0]
    return None, None


def test_hard_rules_trip():
    for scn, code in [("overload", "OVERCURRENT"), ("ground_leak", "LEAKAGE"),
                      ("voltage_sag", "UNDERVOLTAGE"), ("overvoltage", "OVERVOLTAGE")]:
        k, c = _first_trip(scn)
        assert k is not None and k < 30, scn
        assert c.startswith(code), (scn, c)


def test_bearing_wear_stays_below_hard_trip():
    k, _ = _first_trip("bearing_wear", 120)
    assert k is None          # đây là lỗi tiến triển chậm, chỉ AI mới phát hiện sớm


def test_demand_manager_sheds_in_order_then_restores():
    dm = DemandManager({"hvac": 1, "compressor": 2, "lighting": 3}, over_n=2, restore_n=3, cooldown=0)
    loads = {"motor": (True, 6), "hvac": (True, 12), "compressor": (True, 8), "lighting": (True, 3)}
    assert dm.update(0, 29, 25, loads) == []
    assert dm.update(1, 29, 25, loads) == [("shed", "hvac")]
    loads["hvac"] = (False, 0)
    assert dm.update(2, 17, 25, loads) == []      # 17 + 12 kW vẫn > 85 % ngưỡng: chưa đóng lại
    assert dm.update(3, 17, 25, loads) == []
    for t in (4, 5):
        assert dm.update(t, 8, 25, loads) == []   # 8 + 12 kW đủ thấp, chờ đủ 3 mẫu
    assert dm.update(6, 8, 25, loads) == [("restore", "hvac")]


def test_motor_is_never_shed():
    dm = DemandManager({"hvac": 1}, over_n=1, cooldown=0)
    loads = {"motor": (True, 30), "hvac": (False, 0)}
    assert dm.update(0, 30, 10, loads) == []


def test_tariff_windows():
    tz = timezone(timedelta(hours=7))
    assert tariff(datetime(2026, 11, 16, 10, 0, tzinfo=tz))[0] == "peak"       # Thứ 2 10:00
    assert tariff(datetime(2026, 11, 16, 13, 0, tzinfo=tz))[0] == "normal"
    assert tariff(datetime(2026, 11, 16, 23, 0, tzinfo=tz))[0] == "offpeak"
    assert tariff(datetime(2026, 11, 15, 10, 0, tzinfo=tz))[0] == "normal"     # Chủ nhật


def test_bridge_points():
    tel = json.dumps({"ts": 1.0, "voltage": 400, "current": 10, "power_kw": 5, "relay": 1, "ai_state": "normal"})
    assert len(to_points(f"{C.SITE}/motor/telemetry", tel)) == 1
    alarm = json.dumps({"ts": 1.0, "load": "motor", "severity": "critical", "code": "X", "message": "m", "value": 1})
    assert len(to_points(f"{C.SITE}/alarms", alarm)) == 1
    assert len(to_points(f"{C.SITE}/gateway/status", b"online")) == 1
    assert to_points("other/topic", b"{}") == []
