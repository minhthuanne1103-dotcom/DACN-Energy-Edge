import os, json, ssl, time, logging, joblib
import numpy as np
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import pg8000.dbapi

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [AI EDGE ENGINE] - %(message)s")

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", 8883))
INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-super-secret-edge-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "industrial_org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "energy_bucket")

PG_HOST = os.getenv("PG_HOST", "postgres")
PG_DB = os.getenv("PG_DB", "energy_management")
PG_USER = os.getenv("PG_USER", "edge_admin")
PG_PASS = os.getenv("PG_PASS", "edge_password123")

model = joblib.load("./models/iso_forest.joblib")
scaler = joblib.load("./models/scaler.joblib")

prev_current = 12.0
consecutive_anomalies = 0
ANCHOR_THRESHOLD = 2

influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

def get_pg_conn():
    while True:
        try:
            return pg8000.dbapi.connect(host=PG_HOST, port=5432, database=PG_DB, user=PG_USER, password=PG_PASS)
        except Exception as e:
            logging.warning(f"Doi PostgreSQL khoi dong... ({e})")
            time.sleep(3)

pg_conn = get_pg_conn()
pg_cursor = pg_conn.cursor()

def on_message(client, userdata, msg):
    global prev_current, consecutive_anomalies
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        v, i, p_w, pf = float(data["voltage"]), float(data["current"]), float(data["power_w"]), float(data["power_factor"])
        s_va = round(v * i, 2)
        c_diff = round(abs(i - prev_current), 2)
        prev_current = i

        features_scaled = scaler.transform(np.array([[v, i, p_w, pf, s_va, c_diff]]))
        pred = model.predict(features_scaled)[0]
        raw_score = float(model.decision_function(features_scaled)[0])
        is_anomaly = 1 if pred == -1 else 0

        action_taken = "NONE"
        if is_anomaly == 1:
            consecutive_anomalies += 1
            if consecutive_anomalies >= ANCHOR_THRESHOLD:
                action_taken = "AUTO_RELAY_TRIPPED_OFF"
                relay_cmd = {
                    "device_id": data["device_id"], "command": "TRIP_OFF",
                    "reason": f"Critical Anomaly ({consecutive_anomalies}s): V={v}V, I={i}A, PF={pf}",
                    "timestamp": data["timestamp"]
                }
                client.publish(f"factory/zone1/{data['device_id']}/relay/cmd", json.dumps(relay_cmd), qos=1)
                logging.critical(f"[CRITICAL] Da gui lenh NGAT DONG toi IoT Relay! (I={i}A, V={v}V)")
            else:
                action_taken = f"WARNING_COUNT_{consecutive_anomalies}"
                logging.warning(f"[WARNING] AI phat hien bat thuong ({consecutive_anomalies}/{ANCHOR_THRESHOLD}): V={v}V, I={i}A")
        else:
            if consecutive_anomalies >= ANCHOR_THRESHOLD:
                client.publish(f"factory/zone1/{data['device_id']}/relay/cmd", json.dumps({"device_id": data["device_id"], "command": "RESTORE_ON"}), qos=1)
            consecutive_anomalies = 0
            logging.info(f"[NORMAL] V={v}V | I={i}A | P={p_w}W | Score={raw_score:.3f}")

        point = (
            Point("power_metrics").tag("device_id", data["device_id"]).tag("zone", data["zone"])
            .field("voltage", v).field("current", i).field("power_w", p_w).field("power_factor", pf)
            .field("apparent_power_va", s_va).field("ai_anomaly", is_anomaly).field("ai_score", round(raw_score, 4))
        )
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

        if is_anomaly == 1:
            pg_cursor.execute(
                "INSERT INTO anomaly_logs (device_id, voltage, current, power_w, power_factor, anomaly_score, action_taken) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (data["device_id"], v, i, p_w, pf, round(raw_score, 4), action_taken)
            )
            pg_conn.commit()
    except Exception as e:
        logging.error(f"Loi AI Engine: {e}")

def main():
    mqtt_client = mqtt.Client(client_id="Docker_Edge_AI_Engine")
    mqtt_client.tls_set(ca_certs="/app/certs/ca.crt", cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
    mqtt_client.tls_insecure_set(True)
    mqtt_client.on_message = on_message
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            break
        except Exception as e:
            logging.warning(f"Doi MQTT Broker... ({e})")
            time.sleep(3)
    mqtt_client.subscribe("factory/zone1/+/telemetry", qos=1)
    logging.info("AI Edge Container da san sang phan tich thoi gian thuc!")
    mqtt_client.loop_forever()

if __name__ == "__main__":
    main()
