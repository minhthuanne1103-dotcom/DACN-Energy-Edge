import json, ssl, logging
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [IOT RELAY NODE] - %(message)s")
RELAY_STATE = "CLOSED (DANG CAP DIEN)"

def on_message(client, userdata, msg):
    global RELAY_STATE
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        cmd = payload.get("command")
        if cmd == "TRIP_OFF" and "NGAT" not in RELAY_STATE:
            RELAY_STATE = "OPEN (DA NGAT DIEN KHAN CAP)"
            logging.critical("==========================================================")
            logging.critical(f"[RELAY TRIGGERED] DA CAT NGUON TU DIEN: {payload.get('device_id')}")
            logging.critical(f"Nguyen nhan: {payload.get('reason')}")
            logging.critical(f"Trang thai tiep diem: {RELAY_STATE}")
            logging.critical("==========================================================")
        elif cmd == "RESTORE_ON" and "DANG CAP DIEN" not in RELAY_STATE:
            RELAY_STATE = "CLOSED (DANG CAP DIEN)"
            logging.info(f"[RELAY RESTORED] He thong on dinh, da dong lai nguon cho {payload.get('device_id')}!")
    except Exception as e:
        logging.error(f"Loi Relay: {e}")

def main():
    client = mqtt.Client(client_id="IoT_Relay_DEV001")
    client.tls_set(ca_certs="./certs/ca.crt", cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
    client.tls_insecure_set(True)
    client.on_message = on_message
    client.connect("localhost", 8883, 60)
    client.subscribe("factory/zone1/DEV_001/relay/cmd", qos=1)
    logging.info(f"IoT Relay dang lang nghe lenh. Trang thai: {RELAY_STATE}")
    client.loop_forever()

if __name__ == "__main__":
    main()
