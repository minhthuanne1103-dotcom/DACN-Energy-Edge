"""Tạo MQTT client kết nối TLS 1.2+ với xác thực hai chiều (mutual TLS)."""
import logging
import time

import paho.mqtt.client as mqtt

from . import config as C

log = logging.getLogger("mqtt")


def make_client(identity, will=None):
    """identity trùng CN của chứng chỉ client (gateway / bridge / operator)."""
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=identity)
    c.tls_set(ca_certs=f"{C.CERT_DIR}/ca.crt",
              certfile=f"{C.CERT_DIR}/{identity}.crt",
              keyfile=f"{C.CERT_DIR}/{identity}.key")
    if will:
        c.will_set(*will)          # (topic, payload, qos, retain)
    c.reconnect_delay_set(1, 30)
    return c


def connect_retry(c):
    while True:
        try:
            c.connect(C.MQTT_HOST, C.MQTT_PORT, keepalive=30)
            return
        except Exception as e:     # broker chưa sẵn sàng
            log.warning("Chưa kết nối được MQTT broker (%s), thử lại sau 3 s", e)
            time.sleep(3)
