import time
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=5020)

def inject_scenario(name, v, i, pf, is_anom, duration=5):
    if not client.connected:
        client.connect()
    power = int(v * i * pf)
    regs = [int(v * 10), int(i * 100), power, int(pf * 100), is_anom]
    print(f"\n>>> DANG BOM KICH BAN [{name}] TRONG {duration} GIAY...")
    for sec in range(duration):
        # Ghi đè liên tục vào thanh ghi Modbus để giữ trạng thái sự cố
        for _ in range(5):
            client.write_registers(address=0, values=regs, slave=1)
            time.sleep(0.2)
        print(f" -> Chu ky {sec+1}/{duration}s: V={v}V | I={i}A | P={power}W | PF={pf}")
    print(">>> Da hoan tat kich ban! Vui long kiem tra Grafana va cửa sổ IoT Relay.")

def main():
    while True:
        print("\n================ BANG DIEU KHIEN DEMO BAO VE DO AN ================")
        print("1. Tao su co QUA TAI DONG CO (Overload: I = 38.5A, V = 212V) -> Kich hoat Relay")
        print("2. Tao su co SUT AP LUOI DIEN (Voltage Sag: V = 168.0V, I = 23.5A) -> Kich hoat Relay")
        print("3. Tao su co LOI TU BU / RO DIEN (Low PF: PF = 0.48, I = 19.5A) -> Kich hoat Relay")
        print("4. Khoi phuc trang thai BINH THUONG (Normal: V = 220.5V, I = 12.0A) -> Dong lai Relay")
        print("0. Thoat")
        choice = input("Chon kich ban demo (0-4): ").strip()

        if choice == "1":
            inject_scenario("QUA TAI DONG CO", 212.0, 38.5, 0.78, 1, duration=4)
        elif choice == "2":
            inject_scenario("SUT AP LUOI DIEN", 168.0, 23.5, 0.75, 1, duration=4)
        elif choice == "3":
            inject_scenario("RO DIEN / SUT PF", 220.0, 19.5, 0.48, 1, duration=4)
        elif choice == "4":
            inject_scenario("HOAT DONG BINH THUONG", 220.5, 12.0, 0.94, 0, duration=4)
        elif choice == "0":
            break

if __name__ == "__main__":
    main()
