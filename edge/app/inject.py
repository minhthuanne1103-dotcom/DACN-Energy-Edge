"""Tiêm lỗi vào thiết bị mô phỏng để trình diễn.

  docker compose exec gateway python -m app.inject motor overload
  docker compose exec gateway python -m app.inject all normal
Kịch bản: normal overload voltage_sag ground_leak bearing_wear overvoltage
"""
import sys

from pymodbus.client import ModbusTcpClient
from pymodbus.transaction import ModbusRtuFramer

from . import config as C
from .registers import SCENARIO_REG
from .loadmodel import SCENARIOS


def inject(names, scenario):
    code = SCENARIOS[scenario]
    for name in names:
        ld = C.LOAD_BY_NAME[name]
        port = C.MODBUS_TCP_PORT if ld.transport == "tcp" else C.MODBUS_RTU_PORT
        framer = {} if ld.transport == "tcp" else {"framer": ModbusRtuFramer}
        c = ModbusTcpClient(C.MODBUS_HOST, port=port, timeout=2, **framer)
        try:
            if not c.connect():
                raise ConnectionError("không kết nối được simulator")
            rr = c.write_register(SCENARIO_REG, code, slave=ld.unit)
            print(f"{name}: kịch bản '{scenario}'", "OK" if not rr.isError() else f"LỖI {rr}")
        finally:
            c.close()


def main():
    if len(sys.argv) != 3 or sys.argv[2] not in SCENARIOS or (
            sys.argv[1] != "all" and sys.argv[1] not in C.LOAD_BY_NAME):
        print(__doc__)
        print("Tải:", ", ".join(C.LOAD_BY_NAME), "| Kịch bản:", ", ".join(SCENARIOS))
        sys.exit(1)
    inject(list(C.LOAD_BY_NAME) if sys.argv[1] == "all" else [sys.argv[1]], sys.argv[2])


if __name__ == "__main__":
    main()
