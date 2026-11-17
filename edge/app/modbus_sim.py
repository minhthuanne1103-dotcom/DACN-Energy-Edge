"""Mô phỏng thiết bị hiện trường: đồng hồ đa năng + relay ngắt dòng.

  - Cổng 5020: Modbus TCP (khung MBAP)  -> motor (unit 1), compressor (unit 2)
  - Cổng 5021: Modbus RTU (khung CRC16, mô phỏng bus RS485 qua bộ chuyển đổi serial-TCP)
               -> hvac (unit 3), lighting (unit 4)
Relay là coil 0. Kịch bản lỗi ghi vào holding register 100.
"""
import asyncio
import logging
import time

from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
from pymodbus.server import StartAsyncTcpServer
from pymodbus.transaction import ModbusRtuFramer, ModbusSocketFramer

from . import config as C
from . import registers as R
from .loadmodel import SCENARIO_NAMES, LoadState
from .tariff import local_now

log = logging.getLogger("modbus-sim")


def _new_slave():
    return ModbusSlaveContext(
        di=ModbusSequentialDataBlock(0, [0] * 16),
        co=ModbusSequentialDataBlock(0, [1] * 16),      # relay mặc định đóng
        hr=ModbusSequentialDataBlock(0, [0] * 200),
        ir=ModbusSequentialDataBlock(0, [0] * 16),
        zero_mode=True,                                 # địa chỉ 0 = phần tử đầu tiên
    )


async def _updater(slaves, states, dt=1.0):
    hb = 0
    while True:
        now = local_now()
        hour = now.hour + now.minute / 60.0
        hb += 1
        for ld in C.LOADS:
            ctx, st = slaves[ld.unit], states[ld.unit]
            st.relay = bool(ctx.getValues(1, R.COIL_RELAY, 1)[0])
            scn = ctx.getValues(3, R.SCENARIO_REG, 1)[0]
            if scn != st.scenario:
                log.info("%s: kịch bản -> %s", ld.name, SCENARIO_NAMES.get(scn, scn))
            st.set_scenario(scn)
            ctx.setValues(3, 0, R.encode(st.step(dt, hour), hb))
        await asyncio.sleep(dt)


async def main():
    slaves = {ld.unit: _new_slave() for ld in C.LOADS}
    states = {ld.unit: LoadState(ld) for ld in C.LOADS}
    tcp_ctx = ModbusServerContext(
        slaves={ld.unit: slaves[ld.unit] for ld in C.LOADS if ld.transport == "tcp"}, single=False)
    rtu_ctx = ModbusServerContext(
        slaves={ld.unit: slaves[ld.unit] for ld in C.LOADS if ld.transport == "rtu"}, single=False)
    log.info("Modbus TCP :%d | Modbus RTU :%d", C.MODBUS_TCP_PORT, C.MODBUS_RTU_PORT)
    await asyncio.gather(
        StartAsyncTcpServer(context=tcp_ctx, address=("0.0.0.0", C.MODBUS_TCP_PORT),
                            framer=ModbusSocketFramer),
        StartAsyncTcpServer(context=rtu_ctx, address=("0.0.0.0", C.MODBUS_RTU_PORT),
                            framer=ModbusRtuFramer),
        _updater(slaves, states),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    asyncio.run(main())
