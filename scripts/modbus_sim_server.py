import asyncio, random, logging
from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [MODBUS SIM] - %(message)s")

async def update_registers(context):
    slave_id = 0x00
    while True:
        is_anomaly = 1 if random.random() < 0.20 else 0
        if is_anomaly == 0:
            v, i, pf = random.uniform(218.0, 224.0), random.uniform(10.0, 15.0), random.uniform(0.88, 0.96)
        else:
            mode = random.choice(["OVERLOAD", "SAG", "LEAK"])
            if mode == "OVERLOAD": v, i, pf = random.uniform(210.0, 216.0), random.uniform(28.0, 42.0), random.uniform(0.75, 0.85)
            elif mode == "SAG": v, i, pf = random.uniform(165.0, 185.0), random.uniform(18.0, 25.0), random.uniform(0.70, 0.82)
            else: v, i, pf = random.uniform(218.0, 225.0), random.uniform(16.0, 22.0), random.uniform(0.45, 0.62)

        power = int(v * i * pf)
        regs = [int(v * 10), int(i * 100), power, int(pf * 100), is_anomaly]
        context[slave_id].setValues(3, 0, regs)
        logging.info(f"Updated -> V: {v:.1f}V | I: {i:.2f}A | P: {power}W | PF: {pf:.2f} | Anomaly: {is_anomaly}")
        await asyncio.sleep(1)

async def main():
    store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0]*10))
    context = ModbusServerContext(slaves=store, single=True)
    asyncio.create_task(update_registers(context))
    logging.info("Khoi dong Modbus TCP Simulator tai 127.0.0.1:5020...")
    await StartAsyncTcpServer(context=context, address=("127.0.0.1", 5020))

if __name__ == "__main__":
    asyncio.run(main())
