# Hạ tầng Giám sát & Tối ưu Năng lượng Công nghiệp tích hợp AI Local Anomaly Detection trên Docker Edge

Đồ án chuyên ngành Mạng máy tính. Toàn bộ hệ thống chạy bằng **Docker Compose** trên một máy; thiết bị hiện trường (đồng hồ điện Modbus, relay ngắt dòng) được **mô phỏng**, không cần phần cứng thật.

| Yêu cầu đề tài | Thực hiện trong dự án |
|---|---|
| Modbus TCP/RTU | Simulator có 2 cổng: Modbus TCP (khung MBAP) và Modbus RTU (khung CRC16, mô phỏng bus RS485 qua bộ chuyển đổi serial-TCP) |
| MQTT over TLS | Mosquitto chỉ mở cổng 8883, TLS + xác thực hai chiều bằng chứng chỉ (mutual TLS) + ACL theo từng client |
| Docker Edge | 7 container, 2 mạng tách biệt `ot_net` (Modbus) và `it_net` (MQTT, DB); chỉ gateway nối cả hai |
| IoT Relay ngắt dòng | Relay là coil Modbus; gateway ngắt cục bộ khi vi phạm luật an toàn hoặc AI báo bất thường kéo dài |
| AI Anomaly (local) | Isolation Forest + Autoencoder, học từ dữ liệu bình thường, chạy trong container gateway, không cần Internet |
| Tối ưu năng lượng | Cắt tải giảm đỉnh công suất theo thứ tự ưu tiên, ngưỡng chặt hơn giờ cao điểm, tính chi phí theo biểu giá TOU |
| Giám sát an toàn điện | Quá dòng, ngắn mạch, sụt/quá áp, dòng rò (RCD 30 mA), quá nhiệt, méo hài THD, mất liên lạc |

Kiến trúc chi tiết, bản đồ thanh ghi, topic MQTT: xem [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 1. Cài đặt công cụ và thư viện

### 1.1. Cách chính: Docker (khuyến nghị, đúng yêu cầu đề tài)

Chỉ cần cài **3 thứ**. Mọi thư viện Python (pymodbus, paho-mqtt, scikit-learn, ...) được Docker **tự cài** khi build, bạn không phải cài tay.

| Công cụ | Dùng để | Cách cài (Windows 11) |
|---|---|---|
| **Docker Desktop** (backend WSL2) | Chạy toàn bộ hệ thống | https://www.docker.com/products/docker-desktop/ hoặc `winget install Docker.DockerDesktop` |
| **Visual Studio Code** | Mở dự án, chạy bằng phím F5 | https://code.visualstudio.com/ |
| **Git** | Tải mã nguồn | https://git-scm.com/ hoặc `winget install Git.Git` |

Yêu cầu máy: Windows 10/11 64-bit, RAM từ 8 GB, **bật ảo hóa trong BIOS** (Intel VT-x hoặc AMD SVM). Sau khi cài Docker Desktop, khởi động lại máy, mở Docker Desktop và chờ chữ **Engine running** ở góc dưới bên trái.

Nếu Docker Desktop báo "Virtual Machine Platform is not enabled": mở PowerShell **quyền Administrator**, chạy `wsl --install --no-distribution`, khởi động lại máy; nếu vẫn lỗi hãy bật ảo hóa trong BIOS.

### 1.2. Cách phụ: chạy bằng Python, không cần Docker (chỉ để demo nhanh)

Cần **Python 3.11** (`winget install Python.Python.3.11`). Thư viện cài từ `edge/requirements.txt`:

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r edge\requirements.txt
```

| Thư viện | Phiên bản | Dùng để |
|---|---|---|
| pymodbus | 3.6.9 | Modbus TCP/RTU (client + simulator) |
| paho-mqtt | 2.1.0 | MQTT over TLS |
| numpy, scikit-learn, joblib | 1.26.4, 1.4.2, 1.4.2 | AI (Isolation Forest, Autoencoder) |
| cryptography | 42.0.8 | Sinh chứng chỉ TLS |
| influxdb-client | 1.44.0 | Ghi dữ liệu vào InfluxDB |
| pytest | 8.2.2 | Kiểm thử |

Bản Python **không có** Docker, MQTT TLS, InfluxDB, Grafana nên không đủ yêu cầu đề tài; chỉ dùng để xem nhanh.

---

## 2. Tải mã nguồn và cấu hình

```bash
git clone https://github.com/minhthuanne1103-dotcom/DACN-Energy-Edge.git
cd DACN-Energy-Edge
git checkout nhanh-1
copy .env.example .env
```

File `.env` chứa mật khẩu và tham số. Bản mặc định đủ để chạy ở phòng lab; **hãy đổi mật khẩu và token** nếu dùng ngoài lab. Dòng `copy` dùng cho Windows; trên Linux/macOS dùng `cp .env.example .env`.

---

## 3. Cách chạy

### 3.1. Chạy bằng một phím trong VS Code (dễ nhất)

1. Mở thư mục dự án trong VS Code (**File > Open Folder**).
2. Nhấn **F5** (hoặc `Ctrl`+`Shift`+`B`).
3. Hệ thống tự bật Docker, build, chờ Grafana sẵn sàng rồi mở dashboard trong trình duyệt. Lần đầu mất 3-10 phút để tải image.

Grafana mở ở chế độ **chỉ xem, không cần đăng nhập** và chỉ truy cập được từ chính máy bạn. Muốn chỉnh sửa dashboard, vào http://localhost:3000/login, tài khoản `admin`, mật khẩu là `GRAFANA_PASSWORD` trong `.env`.

Các thao tác khác: `Ctrl`+`Shift`+`P`, gõ **Tasks: Run Task**, rồi chọn Tiêm lỗi, RESET relay, Tắt hệ thống, Kiểm thử, Đánh giá AI, Xem log gateway.

### 3.2. Chạy bằng dòng lệnh

```bash
docker compose up -d --build
docker compose ps
```

`certgen` ở trạng thái **Exited (0)** là bình thường (chỉ chạy một lần để tạo chứng chỉ); 6 dịch vụ còn lại phải ở trạng thái **Up**. Mở http://localhost:3000.

Dừng hệ thống: `docker compose down` (thêm `-v` để xóa cả dữ liệu).

Nếu PowerShell báo "running scripts is disabled", chạy script bằng:
`powershell -ExecutionPolicy Bypass -File scripts/run.ps1 start`

### 3.3. Chạy bản Python (không Docker)

```bash
powershell -ExecutionPolicy Bypass -File run-demo.ps1
```

Mở http://127.0.0.1:8080. Script tự tạo `.venv`, cài thư viện và chạy simulator, gateway, AI cùng giao diện web.

| Dịch vụ (Docker) | Địa chỉ | Đăng nhập |
|---|---|---|
| Grafana | http://localhost:3000 | Xem không cần đăng nhập; sửa: `admin` / `GRAFANA_PASSWORD` |
| InfluxDB | http://localhost:8086 | `INFLUX_USER` / `INFLUX_PASSWORD` trong `.env` |
| MQTT over TLS | `localhost:8883` | Chứng chỉ client trong thư mục `certs/` (tự sinh) |

---

## 4. Kịch bản trình diễn

Tiêm lỗi vào thiết bị mô phỏng (hoặc dùng VS Code: Run Task > Tiêm lỗi):

```bash
docker compose exec gateway python -m app.inject <tải> <kịch bản>
```

Tải: `motor`, `compressor`, `hvac`, `lighting`, hoặc `all`.

| Kịch bản | Điều xảy ra | Kết quả mong đợi |
|---|---|---|
| `overload` | Dòng tăng gần gấp đôi trong 8 s | Luật quá dòng ngắt relay sau ~6 s |
| `voltage_sag` / `overvoltage` | Điện áp -18 % / +14 % | Relay ngắt sau ~4 s |
| `ground_leak` | Dòng rò tăng 3 mA/s | Cảnh báo ở 15 mA, ngắt ở 30 mA |
| `bearing_wear` | Mòn ổ trục, tăng chậm, **không vượt ngưỡng cứng** | Luật ngưỡng không phát hiện; AI cảnh báo sau ~20 s và ngắt phòng ngừa sau ~45 s |
| `normal` | Xóa lỗi | Thiết bị trở lại bình thường |

Relay ngắt do sự cố bị **khóa**. Sau khi `normal`, đóng lại bằng lệnh MQTT `RESET` (VS Code: Run Task > RESET relay):

```bash
docker compose exec mosquitto mosquitto_pub -h localhost -p 8883 --cafile /mosquitto/certs/ca.crt --cert /mosquitto/certs/operator.crt --key /mosquitto/certs/operator.key -t factory/line1/motor/relay/set -m RESET
```

**Tối ưu năng lượng:** hạ ngưỡng công suất đỉnh để thấy cắt tải (hvac bị cắt trước, rồi compressor, lighting; motor không bao giờ bị cắt):

```bash
docker compose exec mosquitto mosquitto_pub -h localhost -p 8883 --cafile /mosquitto/certs/ca.crt --cert /mosquitto/certs/operator.crt --key /mosquitto/certs/operator.key -t factory/line1/config/demand_limit_kw -m 15
```

Xem toàn bộ bản tin MQTT:

```bash
docker compose exec mosquitto mosquitto_sub -h localhost -p 8883 --cafile /mosquitto/certs/ca.crt --cert /mosquitto/certs/operator.crt --key /mosquitto/certs/operator.key -t "factory/#" -v
```

## 5. Chứng minh bảo mật TLS (dùng cho báo cáo)

Kết nối không TLS và kết nối TLS không có chứng chỉ client đều phải bị từ chối:

```bash
docker compose exec mosquitto mosquitto_sub -h localhost -p 8883 -t "factory/#"
docker compose exec mosquitto mosquitto_sub -h localhost -p 8883 --cafile /mosquitto/certs/ca.crt -t "factory/#"
```

Phân quyền (ACL) trong `mosquitto/acl`: `bridge` chỉ được đọc; `operator` chỉ được ghi vào `relay/set` và `config/`.

## 6. Kiểm thử và đánh giá AI

```bash
docker compose run --rm --no-deps gateway python -m pytest -q
docker compose run --rm --no-deps gateway python -m app.evaluate
```

Lệnh thứ hai in bảng so sánh thời gian phát hiện giữa luật ngưỡng cứng và AI, cùng số báo động giả. Kết quả trên dữ liệu mô phỏng (motor):

| Kịch bản | Luật ngưỡng: ngắt | AI: cảnh báo | AI: ngắt |
|---|---|---|---|
| overload | 6 s | 4 s | 29 s |
| voltage_sag | 4 s | 4 s | 29 s |
| ground_leak | 10 s | 4 s | 29 s |
| overvoltage | 4 s | 4 s | 29 s |
| bearing_wear | không phát hiện | 18 s | 43 s |

Báo động giả: 0 lần/giờ cho cả 4 tải. Đây là kết quả trên dữ liệu mô phỏng; cần nêu rõ hạn chế này trong báo cáo.

## 7. Cấu trúc thư mục

```
docker-compose.yml        # toàn bộ hệ thống
.env.example              # mẫu cấu hình; sao chép thành .env
.vscode/                  # F5 và các tác vụ Run Task
scripts/run.ps1           # start, stop, inject, reset, test, eval
run-demo.ps1              # chạy bản Python không Docker
mosquitto/                # cấu hình broker TLS + ACL
grafana/                  # datasource + dashboard tự nạp (make_dashboard.py sinh energy.json)
edge/app/
  modbus_sim.py           # thiết bị mô phỏng Modbus TCP/RTU + relay
  loadmodel.py            # mô hình vật lý tải 3 pha + các kịch bản lỗi
  gateway.py              # edge gateway: đọc Modbus, an toàn, AI, tối ưu, MQTT
  safety.py, ai.py        # luật bảo vệ điện; Isolation Forest + Autoencoder
  optimizer.py, tariff.py # cắt tải giảm đỉnh, biểu giá điện
  bridge.py               # MQTT -> InfluxDB
  gencerts.py             # sinh CA và chứng chỉ TLS
  inject.py, evaluate.py  # tiêm lỗi, đánh giá AI
  demo.py                 # bản Python không Docker
edge/tests/               # kiểm thử tự động
docs/ARCHITECTURE.md      # kiến trúc chi tiết
```

## 8. Chuyển sang phần cứng thật

- **Modbus RTU thật (RS485):** trong `gateway.py` thay `ModbusTcpClient(..., framer=ModbusRtuFramer)` bằng `ModbusSerialClient(port="COM3", baudrate=9600, ...)` và ánh xạ thanh ghi theo datasheet đồng hồ trong `registers.py`.
- **Đơn giá điện:** sửa `PRICE_*` theo hóa đơn thực tế (giá trong mã là số minh họa).
- **Chứng chỉ:** CA tự ký chỉ dành cho lab; môi trường thật cần quy trình cấp phát và thu hồi chứng chỉ.
- **Relay an toàn thật:** ngắt bằng phần mềm không thay thế được aptomat/RCD vật lý; hệ thống này là lớp giám sát và bảo vệ bổ sung.

## 9. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `docker` không nhận lệnh | Mở Docker Desktop, chờ Engine running; đóng và mở lại VS Code/terminal |
| `no configuration file provided` | Terminal đang ở sai thư mục; `cd` vào thư mục chứa `docker-compose.yml` |
| `variable is not set` / thiếu `.env` | Chạy `copy .env.example .env` |
| Docker báo thiếu Virtual Machine Platform | Xem mục 1.1; bật ảo hóa trong BIOS |
| Grafana chưa có dữ liệu | Đợi 30-60 s sau khi khởi động; xem `docker compose logs bridge` |
| Cổng 3000 / 8086 / 8883 / 8080 bị chiếm | Đổi cổng bên trái trong `docker-compose.yml` |
| Muốn huấn luyện lại AI | `docker compose down -v` rồi chạy lại |
| Tạo lại chứng chỉ | Xóa thư mục `certs/` rồi `docker compose up -d --force-recreate` |
