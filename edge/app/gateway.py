"""Edge gateway: Modbus -> an toàn -> AI -> tối ưu năng lượng -> MQTT over TLS.

Mọi quyết định bảo vệ (ngắt relay) được thực hiện CỤC BỘ tại đây, kể cả khi mất kết nối MQTT/Internet.

Topic (tiền tố SITE, mặc định factory/line1):
  <load>/telemetry      JSON đo lường + điểm AI          (gateway -> )
  <load>/relay/state    JSON trạng thái relay, retained  (gateway -> )
  <load>/relay/set      ON | OFF | RESET                 (-> gateway)
  alarms                JSON cảnh báo / ngắt             (gateway -> )
  energy/summary        JSON công suất, chi phí, tiết kiệm
  config/demand_limit_kw  số kW                          (-> gateway)
  gateway/status        online | offline (LWT, retained)
"""
import json
import logging
import queue
import signal
import time
from collections import deque

from pymodbus.client import ModbusTcpClient
from pymodbus.transaction import ModbusRtuFramer

from . import config as C
from . import registers as R
from .ai import W, AiTracker, get_detector
from .loadmodel import FEATURES
from .mqttutil import connect_retry, make_client
from .optimizer import DemandManager
from .safety import Alarm, SafetyMonitor
from .tariff import local_now, tariff

log = logging.getLogger("gateway")
RELAY_SETTLE_S = 3.0    # bỏ qua đọc lệch trạng thái relay trong thời gian này sau lệnh của gateway
AI_WARMUP_S = 30.0      # không chấm AI trong thời gian này sau khi relay vừa đóng


class Runtime:
    """Trạng thái chạy của một tải."""

    def __init__(self, load):
        self.load = load
        self.monitor = SafetyMonitor(load)
        self.tracker = AiTracker(C.AI_WARN_N, C.AI_TRIP_N)
        self.window = deque(maxlen=W)
        self.closed = True        # relay đang đóng?
        self.reason = "init"
        self.latched = False      # ngắt do sự cố, cần người dùng RESET
        self.shed = False         # đang bị cắt do quản lý nhu cầu
        self.active = set()       # mã cảnh báo đang hoạt động (để chỉ báo khi mới xuất hiện)
        self.comm_fail = 0
        self.power_kw = 0.0
        self.pf = 0.0
        self.cmd_t = float("-inf")    # thời điểm gateway gửi lệnh relay gần nhất (monotonic)


class Gateway:
    def __init__(self):
        self.rt = {ld.name: Runtime(ld) for ld in C.LOADS}
        self.det = {ld.name: get_detector(ld, C.MODEL_DIR) for ld in C.LOADS}
        self.clients = {
            "tcp": ModbusTcpClient(C.MODBUS_HOST, port=C.MODBUS_TCP_PORT, timeout=2, retries=1),
            "rtu": ModbusTcpClient(C.MODBUS_HOST, port=C.MODBUS_RTU_PORT,
                                   framer=ModbusRtuFramer, timeout=2, retries=1),
        }
        self.dm = DemandManager({ld.name: ld.shed_order for ld in C.LOADS if ld.shed_order > 0})
        self.limit_kw = C.DEMAND_LIMIT_KW
        self.cmds = queue.Queue()
        self.stop = False
        self.energy_kwh = self.cost_vnd = self.saved_kwh = self.saved_vnd = 0.0
        self.mqtt = None

    # ---------------- MQTT ----------------
    def t(self, *parts):
        return "/".join((C.SITE,) + parts)

    def pub(self, topic, obj, retain=False):
        payload = obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"))
        self.mqtt.publish(topic, payload, qos=1, retain=retain)

    def setup_mqtt(self):
        self.mqtt = make_client("gateway", will=(self.t("gateway", "status"), "offline", 1, True))
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_message = lambda c, u, msg: self.cmds.put((msg.topic, msg.payload.decode("utf-8", "ignore")))
        connect_retry(self.mqtt)
        self.mqtt.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            log.error("MQTT từ chối kết nối: %s", reason_code)
            return
        log.info("Đã kết nối MQTT over TLS")
        client.subscribe([(self.t("+", "relay", "set"), 1), (self.t("config", "demand_limit_kw"), 1)])
        self.pub(self.t("gateway", "status"), "online", retain=True)
        for rt in self.rt.values():
            self.publish_relay(rt)

    def publish_relay(self, rt):
        self.pub(self.t(rt.load.name, "relay", "state"),
                 {"ts": round(time.time(), 3), "closed": rt.closed, "reason": rt.reason,
                  "latched": rt.latched}, retain=True)

    def publish_alarm(self, rt, a):
        log.warning("[%s] %s %s: %s", rt.load.name, a.severity, a.code, a.message)
        self.pub(self.t("alarms"), {"ts": round(time.time(), 3), "load": rt.load.name,
                                    "severity": a.severity, "code": a.code,
                                    "message": a.message, "value": round(a.value, 3)})

    # ---------------- Modbus ----------------
    def _client(self, ld):
        c = self.clients[ld.transport]
        if not c.connected and not c.connect():
            raise ConnectionError("không kết nối được Modbus")
        return c

    def read(self, rt):
        ld = rt.load
        try:
            rr = self._client(ld).read_holding_registers(0, R.N_REGS, slave=ld.unit)
            if rr.isError():
                raise IOError(str(rr))
            return R.decode(rr.registers)
        except Exception as e:
            self.clients[ld.transport].close()
            rt.comm_fail += 1
            if rt.comm_fail in (1, 5):
                log.warning("[%s] lỗi đọc Modbus: %s", ld.name, e)
            return None

    def write_relay(self, rt, closed):
        ld = rt.load
        try:
            rr = self._client(ld).write_coil(R.COIL_RELAY, closed, slave=ld.unit)
            return not rr.isError()
        except Exception as e:
            self.clients[ld.transport].close()
            log.error("[%s] không ghi được relay: %s", ld.name, e)
            return False

    def set_relay(self, rt, closed, reason, latch=False):
        if not self.write_relay(rt, closed):
            return False
        rt.closed, rt.reason, rt.latched = closed, reason, (latch and not closed)
        rt.shed = reason == "demand_shed"
        rt.cmd_t = time.monotonic()
        if closed:
            rt.window.clear()
            rt.tracker.reset()
            rt.monitor.reset()
            rt.active.clear()
            self.dm.release(rt.load.name)
        log.info("[%s] relay -> %s (%s)", rt.load.name, "ĐÓNG" if closed else "NGẮT", reason)
        self.publish_relay(rt)
        return True

    # ---------------- Lệnh từ MQTT ----------------
    def drain_commands(self):
        while True:
            try:
                topic, payload = self.cmds.get_nowait()
            except queue.Empty:
                return
            try:
                parts = topic.split("/")
                if topic == self.t("config", "demand_limit_kw"):
                    self.limit_kw = min(max(float(payload), 1.0), 500.0)
                    log.info("Ngưỡng công suất đỉnh = %.1f kW", self.limit_kw)
                elif parts[-2:] == ["relay", "set"] and parts[-3] in self.rt:
                    rt, cmd = self.rt[parts[-3]], payload.strip().upper()
                    if cmd in ("ON", "RESET"):
                        self.set_relay(rt, True, "manual_on")
                    elif cmd == "OFF":
                        self.set_relay(rt, False, "manual_off", latch=True)
                    else:
                        log.warning("Lệnh relay không hợp lệ: %r", payload)
            except ValueError:
                log.warning("Payload không hợp lệ trên %s: %r", topic, payload)

    # ---------------- Một chu kỳ đọc ----------------
    def poll_load(self, rt):
        ld = rt.load
        m = self.read(rt)
        if m is None:
            if rt.comm_fail == 3:
                self.publish_alarm(rt, Alarm("COMM_LOSS", "warning", "Mất liên lạc Modbus", rt.comm_fail))
            rt.power_kw = 0.0
            return
        if rt.comm_fail >= 3:
            log.info("[%s] liên lạc Modbus phục hồi", ld.name)
        rt.comm_fail = 0
        since_cmd = time.monotonic() - rt.cmd_t
        if m["relay"] != rt.closed:
            if since_cmd < RELAY_SETTLE_S:  # thanh ghi thiết bị chưa kịp phản ánh lệnh vừa gửi
                return
            rt.closed, rt.reason = m["relay"], "external"   # relay bị đổi bởi tác nhân bên ngoài
            self.publish_relay(rt)

        alarms = rt.monitor.evaluate(m)

        # --- AI ---
        if_score = ae_ratio = 0.0
        if m["relay"] and since_cmd < AI_WARMUP_S:
            rt.window.clear()               # tải vừa đóng lại: đang khởi động/nguội, chưa chấm AI
            rt.tracker.reset()
        elif m["relay"]:
            rt.window.append([m[f] for f in FEATURES])
            if len(rt.window) == W:
                if_score, ae_ratio = self.det[ld.name].score(list(rt.window))
                rt.tracker.update(if_score, ae_ratio)
                if rt.tracker.warn:
                    alarms.append(Alarm("AI_ANOMALY", "warning",
                                        f"AI phát hiện bất thường (IF={if_score:.2f}, AE={ae_ratio:.1f}x)",
                                        ae_ratio))
                if rt.tracker.trip and C.AI_TRIP:
                    alarms.append(Alarm("AI_TRIP", "critical",
                                        "Bất thường kéo dài, AI ngắt relay phòng ngừa", ae_ratio, True))
        else:
            rt.window.clear()
            rt.tracker.reset()

        codes = {a.code for a in alarms}
        for a in alarms:
            if a.code not in rt.active:
                self.publish_alarm(rt, a)
        rt.active = codes
        trip = next((a for a in alarms if a.trip), None)
        if trip:
            self.set_relay(rt, False, trip.code, latch=True)

        rt.power_kw, rt.pf = m["power_kw"], m["pf"]
        self.pub(self.t(ld.name, "telemetry"), {
            "ts": round(time.time(), 3),
            "voltage": m["voltage"], "current": m["current"], "power_kw": m["power_kw"],
            "pf": m["pf"], "freq": m["freq"], "thd": m["thd"], "leakage_ma": m["leakage_ma"],
            "temp_c": m["temp_c"], "energy_kwh": m["energy_kwh"], "relay": int(rt.closed),
            "if_score": round(if_score, 4), "ae_ratio": round(ae_ratio, 4),
            "ai_consec": rt.tracker.consec, "ai_state": rt.tracker.state,
        })

    # ---------------- Tối ưu năng lượng ----------------
    def optimize(self, now, dt):
        tname, price = tariff(local_now())
        limit = self.limit_kw * (C.PEAK_LIMIT_FACTOR if tname == "peak" else 1.0)
        total = sum(rt.power_kw for rt in self.rt.values())
        for rt in self.rt.values():
            if rt.latched:
                self.dm.release(rt.load.name)
        loads = {n: (rt.closed, rt.power_kw) for n, rt in self.rt.items()}
        for action, name in self.dm.update(now, total, limit, loads):
            rt = self.rt[name]
            if action == "shed":
                if not self.set_relay(rt, False, "demand_shed"):
                    self.dm.release(name)
                else:
                    self.publish_alarm(rt, Alarm("DEMAND_SHED", "warning",
                                                 f"Cắt tải giảm đỉnh ({total:.1f} kW > {limit:.1f} kW)", total))
            elif not self.set_relay(rt, True, "demand_restore"):
                self.dm.shed.append(name)
        dt = min(max(dt, 0.0), 5.0)
        kwh = total * dt / 3600.0
        saved = sum(self.dm.est.get(n, 0.0) for n in self.dm.shed) * dt / 3600.0
        self.energy_kwh += kwh
        self.cost_vnd += kwh * price
        self.saved_kwh += saved
        self.saved_vnd += saved * price
        return total, limit, tname, price

    def publish_summary(self, total, limit, tname, price):
        kva = sum(rt.power_kw / rt.pf for rt in self.rt.values() if rt.pf > 0.01)
        self.pub(self.t("energy", "summary"), {
            "ts": round(time.time(), 3), "total_kw": round(total, 3), "limit_kw": round(limit, 2),
            "tariff": tname, "price_vnd": price, "energy_kwh": round(self.energy_kwh, 4),
            "cost_vnd": round(self.cost_vnd, 1), "saved_kwh": round(self.saved_kwh, 4),
            "saved_vnd": round(self.saved_vnd, 1),
            "pf_total": round(total / kva, 3) if kva > 0 else 0.0,
            "loads_on": sum(1 for rt in self.rt.values() if rt.closed),
            "shed": ",".join(self.dm.shed),
        })

    # ---------------- Vòng lặp chính ----------------
    def run(self):
        self.setup_mqtt()
        last, next_sum = time.monotonic(), 0.0
        log.info("Gateway chạy: chu kỳ %.1f s, ngưỡng %.1f kW, AI_TRIP=%s", C.POLL_INTERVAL, self.limit_kw, C.AI_TRIP)
        while not self.stop:
            t0 = time.monotonic()
            self.drain_commands()
            for rt in self.rt.values():
                self.poll_load(rt)
            now = time.monotonic()
            total, limit, tname, price = self.optimize(now, now - last)
            last = now
            if now >= next_sum:
                self.publish_summary(total, limit, tname, price)
                next_sum = now + 5
            time.sleep(max(0.0, C.POLL_INTERVAL - (time.monotonic() - t0)))
        self.pub(self.t("gateway", "status"), "offline", retain=True)
        self.mqtt.loop_stop()
        self.mqtt.disconnect()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    gw = Gateway()

    def _stop(*_):
        gw.stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    gw.run()


if __name__ == "__main__":
    main()
