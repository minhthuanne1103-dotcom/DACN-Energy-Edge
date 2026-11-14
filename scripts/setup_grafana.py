import urllib.request, json, base64

GRAFANA_URL = "http://localhost:3000"
AUTH = base64.b64encode(b"admin:admin").decode("utf-8")
HEADERS = {"Content-Type": "application/json", "Authorization": f"Basic {AUTH}"}

def api_call(path, method="POST", data=None):
    req = urllib.request.Request(f"{GRAFANA_URL}{path}", method=method, headers=HEADERS)
    if data: req.data = json.dumps(data).encode("utf-8")
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))

influx_payload = {
    "uid": "edge_influxdb_uid",
    "name": "InfluxDB_Edge",
    "type": "influxdb",
    "access": "proxy",
    "url": "http://influxdb:8086",
    "jsonData": {
        "version": "Flux",
        "organization": "industrial_org",
        "defaultBucket": "energy_bucket",
        "httpMode": "POST",
        "tlsSkipVerify": True
    },
    "secureJsonData": {"token": "my-super-secret-edge-token"}
}
api_call("/api/datasources/uid/edge_influxdb_uid", "DELETE")
api_call("/api/datasources", "POST", influx_payload)

dashboard_payload = {
    "dashboard": {
        "uid": "industrial-energy-ai",
        "title": "Giam Sat Nang Luong & AI Anomaly Detection (Docker Edge)",
        "refresh": "5s",
        "time": {"from": "now-15m", "to": "now"},
        "panels": [
            {
                "id": 1,
                "title": "Dien ap (V) & Dong dien (A) Thoi gian thuc",
                "type": "timeseries",
                "gridPos": {"h": 9, "w": 12, "x": 0, "y": 0},
                "datasource": {"type": "influxdb", "uid": "edge_influxdb_uid"},
                "targets": [{
                    "refId": "A",
                    "query": 'from(bucket: "energy_bucket")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r["_measurement"] == "power_metrics")\n  |> filter(fn: (r) => r["_field"] == "voltage" or r["_field"] == "current")\n  |> aggregateWindow(every: 2s, fn: mean, createEmpty: false)'
                }]
            },
            {
                "id": 2,
                "title": "Cong suat tieu thu (W) & Co canh bao AI (0=Binh thuong, 1=Su co)",
                "type": "timeseries",
                "gridPos": {"h": 9, "w": 12, "x": 12, "y": 0},
                "datasource": {"type": "influxdb", "uid": "edge_influxdb_uid"},
                "targets": [{
                    "refId": "A",
                    "query": 'from(bucket: "energy_bucket")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r["_measurement"] == "power_metrics")\n  |> filter(fn: (r) => r["_field"] == "power_w" or r["_field"] == "ai_anomaly")\n  |> aggregateWindow(every: 2s, fn: last, createEmpty: false)'
                }]
            },
            {
                "id": 3,
                "title": "Nhat ky Phat hien Bat thuong AI & Trang thai Ngat IoT Relay (PostgreSQL)",
                "type": "table",
                "gridPos": {"h": 10, "w": 24, "x": 0, "y": 9},
                "datasource": {"type": "postgres", "uid": "edge_postgres_uid"},
                "targets": [{
                    "refId": "A",
                    "rawSql": "SELECT detected_at AS \"Thoi gian\", device_id AS \"Thiet bi\", voltage AS \"Dien ap (V)\", current AS \"Dong dien (A)\", power_w AS \"Cong suat (W)\", power_factor AS \"PF\", anomaly_score AS \"Diem AI\", action_taken AS \"Hanh dong IoT Relay\" FROM anomaly_logs ORDER BY detected_at DESC LIMIT 20;",
                    "format": "table"
                }]
            }
        ]
    },
    "overwrite": True
}
api_call("/api/dashboards/db", "POST", dashboard_payload)
print("[OK] Da cap nhat xong 2 bieu do InfluxDB!")
