"""Đánh giá offline AI so với luật ngưỡng cứng: thời gian phát hiện từng kịch bản và báo động giả.

  docker compose run --rm --no-deps gateway python -m app.evaluate
Kết quả in dạng bảng Markdown, dùng thẳng trong báo cáo đồ án.
"""
from . import config as C
from .ai import W, AiTracker, get_detector
from .loadmodel import FEATURES, SCENARIOS, LoadState
from .safety import SafetyMonitor

ONSET = 60  # giây chạy bình thường trước khi tiêm lỗi


def run_scenario(load, det, scenario, seconds=180, seed=123, hour=10.0):
    """Trả về (giây phát hiện bởi luật cảnh báo, giây luật ngắt, giây AI cảnh báo, giây AI ngắt) tính từ lúc tiêm lỗi."""
    st, mon, trk = LoadState(load, seed), SafetyMonitor(load), AiTracker(C.AI_WARN_N, C.AI_TRIP_N)
    window, t_rule, t_trip, t_ai, t_ai_trip = [], None, None, None, None
    for k in range(ONSET + seconds):
        if k == ONSET:
            st.set_scenario(SCENARIOS[scenario])
        m = st.step(1.0, hour)
        alarms = mon.evaluate(m)
        window = (window + [[m[f] for f in FEATURES]])[-W:]
        if len(window) == W:
            trk.update(*det.score(window))
        t = k - ONSET
        if t < 0:
            continue
        if alarms and t_rule is None:
            t_rule = t
        if any(a.trip for a in alarms) and t_trip is None:
            t_trip = t
        if trk.warn and t_ai is None:
            t_ai = t
        if trk.trip and t_ai_trip is None:
            t_ai_trip = t
    return t_rule, t_trip, t_ai, t_ai_trip


def false_alarms(load, det, seconds=3600, seed=7, start_hours=(3.0, 9.0, 14.0, 20.0)):
    """Số lần AI cảnh báo (cạnh lên) khi vận hành hoàn toàn bình thường.

    Chạy liên tục `seconds` giây (giờ trong ngày trôi theo thời gian thực) tại từng mốc giờ trong start_hours.
    """
    per = seconds // len(start_hours)
    count = 0
    for s, h0 in enumerate(start_hours):
        st, trk = LoadState(load, seed + s), AiTracker(C.AI_WARN_N, C.AI_TRIP_N)
        window, prev = [], False
        for k in range(per):
            m = st.step(1.0, h0 + k / 3600.0)
            window = (window + [[m[f] for f in FEATURES]])[-W:]
            if len(window) == W:
                trk.update(*det.score(window))
                count += trk.warn and not prev
                prev = trk.warn
    return count


def fmt(x):
    return "không phát hiện" if x is None else f"{x} s"


def main():
    print("| Tải | Kịch bản | Luật ngưỡng: cảnh báo | Luật ngưỡng: ngắt | AI: cảnh báo | AI: ngắt |")
    print("|---|---|---|---|---|---|")
    fa = {}
    for ld in C.LOADS:
        det = get_detector(ld, C.MODEL_DIR)
        for scn in list(SCENARIOS)[1:]:
            r = run_scenario(ld, det, scn)
            print(f"| {ld.name} | {scn} | " + " | ".join(fmt(x) for x in r) + " |")
        fa[ld.name] = false_alarms(ld, det)
    print("\nBáo động giả của AI trong 1 giờ vận hành bình thường:", fa)


if __name__ == "__main__":
    main()
