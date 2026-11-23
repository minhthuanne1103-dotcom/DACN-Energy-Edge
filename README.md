Các phần mềm và môi trường cần cài đặt sẵn (Prerequisites):
Trước khi chạy đồ án trên máy tính mới, hãy đảm bảo máy đã cài đặt các công cụ sau:
* 1. Docker Desktop: Đã cài và đang ở trạng thái chạy (Engine running) hỗ trợ WSL 2.
* 2. Python 3.11 hoặc 3.12 (KHÔNG dùng 3.13/3.14 vì thư viện chưa hỗ trợ đủ; khi cài nhớ tích "Add python.exe to PATH"): Dùng để chạy các tiến trình giả lập Modbus, Edge Gateway và AI Engine.
* 3. Git: Dùng để quản lý mã nguồn.
* 4. VS Code (Khuyên dùng): Dùng làm trình soạn thảo mã nguồn.

---

Hướng dẫn cài đặt và khởi động nhanh (Quick Start):
* Bước 1: Clone mã nguồn từ GitHub về máy
  Mở Terminal (PowerShell hoặc CMD) và chạy:
  `git clone https://github.com/minhthuanne1103-dotcom/DACN-Energy-Edge.git`
  `cd DACN-Energy-Edge`
* Bước 2: Khởi động toàn bộ hệ thống
  Cách nhanh nhất (Tự động 100%): Nhấp đúp chuột trực tiếp vào file **run_all.bat** nằm ngay trong thư mục gốc của dự án.

---

Tổng hợp các lệnh thủ công (Dành cho việc bảo vệ & Thuyết trình):
* **A.** Khởi chạy hạ tầng Docker Edge (Mosquitto, InfluxDB, PostgreSQL, AI Engine, Grafana): 
  `docker compose up -d --build`
* **B.** Kích hoạt môi trường ảo Python và cài thư viện: 
  `python -m venv venv`
  `.\venv\Scripts\activate`
  `pip install -r requirements.txt`
* **C.** Chạy các tiến trình thành phần (Mỗi tiến trình chạy trong 1 cửa sổ riêng):
  * Khởi chạy giả lập đồng hồ đo điện (Modbus TCP Server): `python scripts/modbus_sim_server.py`
  * Khởi chạy Edge Gateway (Đọc Modbus đẩy lên MQTT over TLS Port 8883): `python scripts/modbus_to_mqtt.py`
  * Khởi chạy nút mạng IoT Relay (Chờ lệnh cắt điện khẩn cấp): `python scripts/iot_relay_actuator.py`
  * Bật Bảng điều khiển tiêm lỗi thủ công (Dùng để demo bấm phím cho Hội đồng): `python scripts/fault_injector.py`
* **D.** Xem log thời gian thực của AI Edge Container: 
  `docker logs -f edge_ai_engine`
* **E.** Tắt toàn bộ hệ thống khi không sử dụng: Nhấp đúp chuột vào file **stop_all.bat** (hoặc chạy lệnh dừng Docker thủ công: `docker compose stop`).

---

Thông tin truy cập giao diện giám sát (Dashboard):
* Grafana Web UI: http://localhost:3000
* Không cần đăng nhập: mở link là vào thẳng dashboard (quyền Admin, chỉ truy cập được trên máy này)
* Đường dẫn Dashboard chính: http://localhost:3000/d/industrial-energy-ai
