"""Chạy thử KHÔNG cần Docker: simulator Modbus + gateway thật + giao diện web tại http://127.0.0.1:8080

  cd edge
  python -m app.demo

Khác bản Docker: không có MQTT/TLS, InfluxDB, Grafana. Phần Modbus TCP/RTU, luật an toàn, AI,
ngắt relay và tối ưu năng lượng là mã thật dùng chung với bản Docker.
"""
import os

os.environ.setdefault("MODBUS_HOST", "127.0.0.1")
os.environ.setdefault("MODEL_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models"))

import asyncio  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections import deque  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from . import config as C  # noqa: E402
from . import modbus_sim  # noqa: E402
from .gateway import Gateway  # noqa: E402
from .inject import inject  # noqa: E402
from .loadmodel import SCENARIOS  # noqa: E402

PORT = int(os.environ.get("DEMO_PORT", "8080"))


class _NoMqtt:
    def loop_stop(self): pass
    def disconnect(self): pass
    def publish(self, *a, **k): pass


class DemoGateway(Gateway):
    """Gateway thật, chỉ thay đường ra MQTT bằng bộ nhớ trong để giao diện web đọc."""

    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()
        self.tel, self.relay, self.scn = {}, {}, {ld.name: "normal" for ld in C.LOADS}
        self.alarms, self.summary = deque(maxlen=60), {}
        self.hist = {ld.name: deque(maxlen=150) for ld in C.LOADS}

    def setup_mqtt(self):
        self.mqtt = _NoMqtt()

    def pub(self, topic, obj, retain=False):
        if not isinstance(obj, dict):
            return
        rel = topic[len(C.SITE) + 1:].split("/")
        with self.lock:
            if rel[-1] == "telemetry":
                self.tel[rel[0]] = obj
                self.hist[rel[0]].append({"p": obj["power_kw"], "ae": obj["ae_ratio"],
                                          "i": obj["current"], "t": obj["temp_c"], "l": obj["leakage_ma"]})
            elif rel[-2:] == ["relay", "state"]:
                self.relay[rel[0]] = obj
            elif rel == ["alarms"]:
                self.alarms.appendleft(obj)
            elif rel == ["energy", "summary"]:
                self.summary = obj

    def snapshot(self):
        with self.lock:
            return {
                "loads": {n: {**self.tel.get(n, {}), "state": self.relay.get(n, {}), "scn": self.scn[n]}
                          for n in self.rt},
                "hist": {n: list(h) for n, h in self.hist.items()},
                "alarms": list(self.alarms)[:30], "summary": self.summary, "limit": self.limit_kw,
                "scenarios": list(SCENARIOS), "now": time.time(),
            }


def make_handler(gw):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body, ctype="application/json", code=200):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/api/state":
                self._send(json.dumps(gw.snapshot()))
            elif self.path in ("/", "/index.html"):
                self._send(PAGE, "text/html")
            else:
                self._send("not found", "text/plain", 404)

        def do_POST(self):
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/api/inject" and d["load"] in gw.rt and d["scenario"] in SCENARIOS:
                    inject([d["load"]], d["scenario"])
                    gw.scn[d["load"]] = d["scenario"]
                elif self.path == "/api/relay" and d["load"] in gw.rt and d["cmd"] in ("ON", "OFF", "RESET"):
                    gw.cmds.put((gw.t(d["load"], "relay", "set"), d["cmd"]))
                elif self.path == "/api/limit":
                    gw.cmds.put((gw.t("config", "demand_limit_kw"), str(float(d["kw"]))))
                else:
                    return self._send('{"ok":false}', code=400)
                self._send('{"ok":true}')
            except Exception as e:
                self._send(json.dumps({"ok": False, "error": str(e)}), code=400)
    return H


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    threading.Thread(target=lambda: asyncio.run(modbus_sim.main()), daemon=True).start()
    time.sleep(3)
    gw = DemoGateway()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(gw))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"\n>>> Mở trình duyệt: http://127.0.0.1:{PORT}   (Ctrl+C để dừng)\n")
    try:
        gw.run()
    except KeyboardInterrupt:
        gw.stop = True


PAGE = r"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Giám sát Năng lượng Công nghiệp - Demo</title><style>
:root{--bg:#f4f6f9;--card:#fff;--tx:#1b2430;--mu:#64707f;--bd:#dde3ea;--ok:#1a9d5a;--bad:#d4382c;--warn:#d98a00;--ac:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#0f141a;--card:#18202a;--tx:#e8edf3;--mu:#93a0b0;--bd:#2a3542;--ok:#34c47e;--bad:#ef6a5e;--warn:#f0b13a;--ac:#6ea0ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 system-ui,Segoe UI,sans-serif}
.w{max-width:1200px;margin:0 auto;padding:16px}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--mu);margin-bottom:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:12px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px}
.t .k{color:var(--mu);font-size:12px}.t .v{font-size:22px;font-weight:650}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:12px;margin:12px 0}
.hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}.hd b{font-size:15px}
.badge{padding:2px 8px;border-radius:99px;font-size:12px;font-weight:600;color:#fff;background:var(--ok)}
.badge.off{background:var(--bad)}.badge.shed{background:var(--warn)}
.m{display:grid;grid-template-columns:1fr 1fr;gap:2px 10px;font-size:13px;margin:6px 0}.m span{color:var(--mu)}
.m i{font-style:normal;float:right;font-weight:600;color:var(--tx)}
svg{width:100%;height:56px;display:block;background:transparent}
.ai{font-size:12px;margin:2px 0 6px}.ai.anomaly{color:var(--bad);font-weight:700}.ai.suspect{color:var(--warn)}
.ctl{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
select,button,input{font:inherit;border:1px solid var(--bd);background:var(--card);color:var(--tx);border-radius:6px;padding:4px 8px}
button{cursor:pointer}button:hover{border-color:var(--ac)}
.log{max-height:240px;overflow:auto;font-size:13px}.log div{padding:3px 0;border-bottom:1px solid var(--bd)}
.c{font-weight:700}.c.critical{color:var(--bad)}.c.warning{color:var(--warn)}
.note{color:var(--mu);font-size:12px;margin-top:10px}
</style></head><body><div class="w">
<h1>Giám sát và Tối ưu Năng lượng Công nghiệp</h1>
<div class="sub">Bản demo chạy trực tiếp bằng Python (không Docker). Modbus TCP/RTU, luật an toàn, AI cục bộ, ngắt relay và tối ưu năng lượng là mã thật.</div>
<div class="tiles" id="tiles"></div>
<div class="card"><div class="hd"><b>Tổng công suất so với ngưỡng đỉnh</b><span id="lim"></span></div>
<svg id="tot" viewBox="0 0 600 120" preserveAspectRatio="none" style="height:120px"></svg>
<div class="ctl">Ngưỡng đỉnh (kW): <input id="limin" type="number" value="28" min="3" max="100" style="width:70px"><button onclick="setLimit()">Đặt</button>
<span class="note" style="margin:0 0 0 8px">Hạ xuống khoảng 15 để thấy cắt tải giảm đỉnh.</span></div></div>
<div class="grid" id="loads"></div>
<div class="card"><b>Nhật ký cảnh báo và sự kiện</b><div class="log" id="log"></div></div>
<div class="note">Relay ngắt do sự cố bị khóa cho đến khi bấm RESET. Ngắt do cắt tải giảm đỉnh thì tự đóng lại khi công suất thấp.</div>
</div><script>
const NAMES={motor:"Động cơ (trọng yếu)",compressor:"Máy nén khí",hvac:"Điều hòa HVAC",lighting:"Chiếu sáng"};
const SCN={normal:"Bình thường",overload:"Quá tải",voltage_sag:"Sụt áp",ground_leak:"Rò điện",bearing_wear:"Mòn ổ trục (AI)",overvoltage:"Quá áp"};
const REASON={init:"khởi tạo",manual_on:"đóng tay",manual_off:"ngắt tay",demand_shed:"cắt giảm đỉnh",demand_restore:"đóng lại",external:"bên ngoài",
OVERCURRENT:"quá dòng",OVERCURRENT_SHORT:"ngắn mạch",LEAKAGE:"dòng rò",UNDERVOLTAGE:"sụt áp",OVERVOLTAGE:"quá áp",OVERTEMP:"quá nhiệt",AI_TRIP:"AI ngắt phòng ngừa"};
const $=id=>document.getElementById(id);
const post=(u,b)=>fetch(u,{method:"POST",body:JSON.stringify(b)});
const setLimit=()=>post("/api/limit",{kw:+$("limin").value});
function pts(v,mx,w=300,h=50){if(v.length<2)return"";return v.map((y,i)=>(i/(v.length-1)*w).toFixed(1)+","+(h-Math.min(y/mx,1)*h).toFixed(1)).join(" ")}
const f=(x,d=1)=>x==null?"-":(+x).toFixed(d);
$("loads").innerHTML=Object.keys(NAMES).map(n=>`<div class="card"><div class="hd"><b>${NAMES[n]}</b><span class="badge" id="b_${n}">-</span></div>
<div class="m"><span>Điện áp<i id="v_${n}"></i></span><span>Dòng<i id="i_${n}"></i></span><span>Công suất<i id="p_${n}"></i></span><span>PF<i id="f_${n}"></i></span>
<span>THD<i id="h_${n}"></i></span><span>Dòng rò<i id="l_${n}"></i></span><span>Nhiệt độ<i id="t_${n}"></i></span><span>Lý do relay<i id="r_${n}"></i></span></div>
<div class="ai" id="a_${n}"></div><svg viewBox="0 0 300 50" preserveAspectRatio="none"><polyline id="s_${n}" fill="none" stroke="var(--ac)" stroke-width="1.5"/></svg>
<div class="ctl"><select id="sc_${n}">${Object.keys(SCN).map(k=>`<option value="${k}">${SCN[k]}</option>`).join("")}</select>
<button onclick="post('/api/inject',{load:'${n}',scenario:$('sc_${n}').value})">Tiêm lỗi</button>
<button onclick="post('/api/relay',{load:'${n}',cmd:'RESET'})">Đóng / RESET</button><button onclick="post('/api/relay',{load:'${n}',cmd:'OFF'})">Ngắt</button></div></div>`).join("");
async function tick(){let s;try{s=await(await fetch("/api/state")).json()}catch(e){return}
const m=s.summary||{};
$("tiles").innerHTML=[["Tổng công suất",f(m.total_kw)+" kW"],["Ngưỡng hiện tại",f(m.limit_kw)+" kW"],["Khung giờ giá",{peak:"Cao điểm",normal:"Bình thường",offpeak:"Thấp điểm"}[m.tariff]||"-"],
["Chi phí điện",f(m.cost_vnd,0)+" VND"],["Tiết kiệm (cắt đỉnh)",f(m.saved_vnd,0)+" VND"],["PF tổng",f(m.pf_total,2)],["Tải đang cấp điện",(m.loads_on??"-")+"/4"]]
.map(([k,v])=>`<div class="card t"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
$("lim").textContent="ngưỡng "+f(m.limit_kw)+" kW";
for(const n in NAMES){const d=s.loads[n]||{},st=d.state||{};const on=st.closed!==false&&d.relay!==0;
const b=$("b_"+n);const shed=st.reason==="demand_shed";b.textContent=on?"ĐÓNG":(shed?"CẮT ĐỈNH":(st.latched?"NGẮT (khóa)":"NGẮT"));b.className="badge"+(on?"":(shed?" shed":" off"));
$("v_"+n).textContent=f(d.voltage,0)+" V";$("i_"+n).textContent=f(d.current,1)+" A";$("p_"+n).textContent=f(d.power_kw)+" kW";$("f_"+n).textContent=f(d.pf,2);
$("h_"+n).textContent=f(d.thd)+" %";$("l_"+n).textContent=f(d.leakage_ma)+" mA";$("t_"+n).textContent=f(d.temp_c,0)+" °C";$("r_"+n).textContent=REASON[st.reason]||st.reason||"-";
const a=$("a_"+n);a.className="ai "+(d.ai_state||"");a.textContent="AI: "+({normal:"bình thường",suspect:"nghi ngờ",anomaly:"BẤT THƯỜNG"}[d.ai_state]||"-")+"  (Autoencoder "+f(d.ae_ratio,1)+"x, IF "+f(d.if_score,2)+")";
$("s_"+n).setAttribute("points",pts((s.hist[n]||[]).map(x=>x.p),Math.max(1,...(s.hist[n]||[]).map(x=>x.p))*1.1));
const sel=$("sc_"+n);if(document.activeElement!==sel)sel.value=d.scn||"normal"}
const H=Object.values(s.hist),L=Math.min(...H.map(h=>h.length));
if(L>1){const tot=[];for(let i=0;i<L;i++)tot.push(H.reduce((a,h)=>a+h[h.length-L+i].p,0));const mx=Math.max(s.limit*1.3,...tot)*1.05;
const y=v=>(120-v/mx*120).toFixed(1);$("tot").innerHTML=`<polyline fill="none" stroke="var(--ac)" stroke-width="2" points="${tot.map((v,i)=>(i/(L-1)*600).toFixed(1)+","+y(v)).join(" ")}"/>
<line x1="0" x2="600" y1="${y(m.limit_kw||s.limit)}" y2="${y(m.limit_kw||s.limit)}" stroke="var(--bad)" stroke-dasharray="6 4" stroke-width="1.5"/>`}
$("log").innerHTML=(s.alarms||[]).map(a=>`<div><span class="c ${a.severity}">${a.code}</span> [${a.load}] ${a.message} <span style="color:var(--mu)">${new Date(a.ts*1000).toLocaleTimeString("vi-VN")}</span></div>`).join("")||"<div style='color:var(--mu)'>Chưa có cảnh báo.</div>"}
tick();setInterval(tick,1000);
</script></body></html>"""

if __name__ == "__main__":
    main()
