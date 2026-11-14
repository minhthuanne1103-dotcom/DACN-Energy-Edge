import time, json, ssl, logging
from datetime import datetime, timezone
from pymodbus.client import ModbusTcpClient
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [EDGE GATEWAY] - %(message)s")

mqtt_client = mqtt.Client(client_id="Edge_Modbus_Publisher")
mqtt_client.tls_set(ca_certs="./certs/ca.crt", cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
mqtt_client.tls_insecure_set(True)

def connect_mqtt():
    while True:
        try:
            mqtt_client.connect("localhost", 8883, keepalive=60)
            mqtt_client.loop_start()
            logging.info("Da ket noi MQTT Broker qua TLS (Port 8883)!")
            break
        except Exception as e:
            logging.error(f"Loi MQTT: {e}. Thu lai sau 3s...")
            time.sleep(3)

def main():
    connect_mqtt()
    modbus_client = ModbusTcpClient("127.0.0.1", port=5020)
    while True:
        try:
            if not modbus_client.connected: modbus_client.connect()
            res = modbus_client.read_holding_registers(address=0, count=5, slave=1)
            if not res.isError():
                r = res.registers
                payload = {
                    "device_id": "DEV_001", "zone": "Xuong_CNC_01",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "voltage": round(r[0] / 10.0, 1), "current": round(r[1] / 100.0, 2),
                    "power_w": float(r[2]), "power_factor": round(r[3] / 100.0, 2),
                    "simulated_anomaly": int(r[4])
                }
                mqtt_client.publish("factory/zone1/DEV_001/telemetry", json.dumps(payload), qos=1)
                logging.info(f"Published TLS -> {payload}")
        except Exception as e:
            logging.error(f"Mat ket noi Modbus: {e}")
            modbus_client.close()
        time.sleep(1)

if __name__ == "__main__":
    main()
