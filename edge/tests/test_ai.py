import pytest

from app import config as C
from app.ai import Detector
from app.evaluate import false_alarms, run_scenario


@pytest.fixture(scope="module")
def det():
    ld = C.LOAD_BY_NAME["motor"]
    return ld, Detector.train(ld, n=4000)


def test_no_false_alarm_in_normal_operation(det):
    ld, d = det
    assert false_alarms(ld, d, seconds=1200) == 0


def test_ai_detects_slow_bearing_wear_before_any_hard_rule(det):
    ld, d = det
    t_rule, t_trip, t_ai, _ = run_scenario(ld, d, "bearing_wear", seconds=150)
    assert t_ai is not None and t_ai < 90      # AI phát hiện trong vòng 90 s
    assert t_trip is None                      # luật cứng không ngắt vì chưa vượt ngưỡng


def test_ai_detects_leakage_ramp(det):
    ld, d = det
    _, _, t_ai, _ = run_scenario(ld, d, "ground_leak", seconds=60)
    assert t_ai is not None
