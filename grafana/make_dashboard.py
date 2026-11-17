"""Sinh dashboard Grafana (provisioning/dashboards/energy.json). Chạy: python grafana/make_dashboard.py"""
import json
import pathlib

DS = {"type": "influxdb", "uid": "influx-energy"}
BASE = 'from(bucket: "energy") |> range(start: v.timeRangeStart, stop: v.timeRangeStop) '
_id = [0]


def flux_ts(measure, field, group="load", fn="mean"):
    return (BASE + f'|> filter(fn: (r) => r._measurement == "{measure}" and r._field == "{field}") '
            f'|> group(columns: ["{group}"]) |> aggregateWindow(every: v.windowPeriod, fn: {fn}, createEmpty: false)')


def panel(kind, title, x, y, w, h, query, unit="", extra=None, options=None, name="${__field.labels.load}"):
    _id[0] += 1
    defaults = {"unit": unit, "displayName": name}
    defaults.update(extra or {})
    p = {"id": _id[0], "type": kind, "title": title, "datasource": DS,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "fieldConfig": {"defaults": defaults, "overrides": []},
         "targets": [{"refId": "A", "datasource": DS, "query": query}]}
    if options:
        p["options"] = options
    return p


def thresh(value, color="red", line=True):
    d = {"thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": color, "value": value}]}}
    if line:
        d["custom"] = {"thresholdsStyle": {"mode": "line"}}
    return d


def stat(title, x, field, unit, decimals=1, noval=None):
    q = BASE + f'|> filter(fn: (r) => r._measurement == "energy" and r._field == "{field}") |> last()'
    extra = {"decimals": decimals}
    if noval:
        extra["noValue"] = noval
    return panel("stat", title, x, 0, 4, 4, q, unit, extra, {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}, name=title)


panels = [
    stat("Tổng công suất", 0, "total_kw", "kwatt"),
    stat("Ngưỡng đỉnh", 4, "limit_kw", "kwatt"),
    stat("Chi phí điện (VND)", 8, "cost_vnd", "none", 0),
    stat("Tiết kiệm nhờ cắt đỉnh (VND)", 12, "saved_vnd", "none", 0),
    stat("PF tổng", 16, "pf_total", "none", 2),
]
alarm_count = (BASE + '|> filter(fn: (r) => r._measurement == "alarm" and r._field == "value") |> group() |> count()')
panels.append(panel("stat", "Số cảnh báo (khoảng chọn)", 20, 0, 4, 4, alarm_count, "none", {"noValue": "0"},
                    {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}, name="Cảnh báo"))

total_q = (BASE + '|> filter(fn: (r) => r._measurement == "energy" and (r._field == "total_kw" or r._field == "limit_kw")) '
           '|> group(columns: ["_field"]) |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)')
panels.append(panel("timeseries", "Tổng công suất so với ngưỡng đỉnh", 0, 4, 12, 8, total_q, "kwatt", name="${__field.labels._field}"))
panels.append(panel("timeseries", "Công suất từng tải", 12, 4, 12, 8, flux_ts("telemetry", "power_kw"), "kwatt"))

relay_q = (BASE + '|> filter(fn: (r) => r._measurement == "relay" and r._field == "closed") '
           '|> keep(columns: ["_time", "_value", "load"]) |> group(columns: ["load"]) '
           '|> aggregateWindow(every: v.windowPeriod, fn: last, createEmpty: false)')
relay_extra = {"mappings": [{"type": "value", "options": {"0": {"text": "NGẮT", "color": "red", "index": 0},
                                                          "1": {"text": "ĐÓNG", "color": "green", "index": 1}}}],
               "color": {"mode": "thresholds"},
               "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}}
panels.append(panel("state-timeline", "Trạng thái relay ngắt dòng", 0, 12, 12, 8, relay_q, "", relay_extra))
panels.append(panel("timeseries", "AI: sai số Autoencoder (>1 là bất thường)", 12, 12, 12, 8,
                    flux_ts("telemetry", "ae_ratio", fn="max"), "none", thresh(1)))

panels.append(panel("timeseries", "Điện áp (V)", 0, 20, 12, 8, flux_ts("telemetry", "voltage"), "volt", {"min": 300, "max": 480}))
panels.append(panel("timeseries", "Dòng điện (A)", 12, 20, 12, 8, flux_ts("telemetry", "current"), "amp"))
panels.append(panel("timeseries", "Dòng rò (mA) - ngưỡng RCD 30 mA", 0, 28, 12, 8, flux_ts("telemetry", "leakage_ma", fn="max"), "none", thresh(30)))
panels.append(panel("timeseries", "Nhiệt độ (°C)", 12, 28, 12, 8, flux_ts("telemetry", "temp_c"), "celsius", thresh(85)))
panels.append(panel("timeseries", "Méo hài dòng THD (%)", 0, 36, 12, 8, flux_ts("telemetry", "thd"), "percent", thresh(12)))
panels.append(panel("timeseries", "AI: điểm Isolation Forest (>0 là bất thường)", 12, 36, 12, 8,
                    flux_ts("telemetry", "if_score", fn="max"), "none", thresh(0)))

alarm_q = (BASE + '|> filter(fn: (r) => r._measurement == "alarm" and r._field == "message") '
           '|> keep(columns: ["_time", "load", "severity", "code", "_value"]) |> group() '
           '|> sort(columns: ["_time"], desc: true) |> limit(n: 100) |> rename(columns: {_value: "message"})')
panels.append(panel("table", "Nhật ký cảnh báo và sự kiện ngắt", 0, 44, 24, 9, alarm_q, "", name=""))

dash = {"uid": "energy-edge", "title": "Giám sát và Tối ưu Năng lượng Công nghiệp", "tags": ["energy", "edge"],
        "timezone": "browser", "refresh": "5s", "schemaVersion": 39, "version": 1,
        "time": {"from": "now-15m", "to": "now"}, "panels": panels}
out = pathlib.Path(__file__).parent / "provisioning" / "dashboards" / "energy.json"
out.write_text(json.dumps(dash, ensure_ascii=False, indent=1), encoding="utf-8")
print("Đã ghi", out)
