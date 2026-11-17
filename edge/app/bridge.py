"""Bridge: đăng ký (subscribe) MQTT over TLS và ghi dữ liệu vào InfluxDB để Grafana hiển thị."""
import json
import logging
import time

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from . import config as C
from .mqttutil import connect_retry, make_client

log = logging.getLogger("bridge")

TELEMETRY_FIELDS = ("voltage", "current", "power_kw", "pf", "freq", "thd", "leakage_ma",
                    "temp_c", "energy_kwh", "if_score", "ae_ratio", "ai_consec")


def _ts(d):
    return int(float(d.get("ts", time.time())) * 1e9)


def to_points(topic, payload):
    """Chuyển một bản tin MQTT thành các điểm InfluxDB (hàm thuần, dễ kiểm thử)."""
    if not topic.startswith(C.SITE + "/"):
        return []
    parts = topic[len(C.SITE) + 1:].split("/")
    if parts == ["gateway", "status"]:
        text = payload.decode() if isinstance(payload, bytes) else str(payload)
        return [Point("gateway").field("online", 1 if text == "online" else 0)]
    d = json.loads(payload)
    p = None
    if len(parts) == 2 and parts[1] == "telemetry":
        p = Point("telemetry").tag("load", parts[0])
        for f in TELEMETRY_FIELDS:
            if f in d:
                p = p.field(f, float(d[f]))
        p = p.field("relay", int(d.get("relay", 0))).field("ai_state", str(d.get("ai_state", "")))
    elif parts == ["alarms"]:
        p = (Point("alarm").tag("load", d["load"]).tag("severity", d["severity"]).tag("code", d["code"])
             .field("message", d["message"]).field("value", float(d["value"])))
    elif len(parts) == 3 and parts[1:] == ["relay", "state"]:
        p = (Point("relay").tag("load", parts[0]).field("closed", int(bool(d["closed"])))
             .field("reason", str(d["reason"])))
    elif parts == ["energy", "summary"]:
        p = Point("energy")
        for k, v in d.items():
            if k == "ts":
                continue
            p = p.field(k, v if isinstance(v, str) else float(v))
    if p is None:
        return []
    return [p.time(_ts(d), WritePrecision.NS)]


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    influx = InfluxDBClient(url=C.INFLUX_URL, token=C.INFLUX_TOKEN, org=C.INFLUX_ORG)
    while not influx.ping():
        log.info("Chờ InfluxDB ...")
        time.sleep(3)
    write = influx.write_api(write_options=SYNCHRONOUS)

    def on_message(client, userdata, msg):
        try:
            pts = to_points(msg.topic, msg.payload)
            if pts:
                write.write(bucket=C.INFLUX_BUCKET, org=C.INFLUX_ORG, record=pts)
        except Exception:
            log.exception("Lỗi xử lý %s", msg.topic)

    def on_connect(client, userdata, flags, reason_code, properties):
        log.info("Bridge đã kết nối MQTT over TLS (%s)", reason_code)
        client.subscribe(C.SITE + "/#", qos=1)

    c = make_client("bridge")
    c.on_connect, c.on_message = on_connect, on_message
    connect_retry(c)
    c.loop_forever()


if __name__ == "__main__":
    main()
