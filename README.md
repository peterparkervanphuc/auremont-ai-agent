# TỔNG QUAN DỰ ÁN
## SalesMate AI Agent — Trợ lý AI cho Đội Sale Bất động sản

### 1. Ý tưởng và Tầm quan trọng

* **Ý tưởng**: Xây dựng một AI Agent dạng RAG (Retrieval-Augmented Generation) đóng vai trò "trợ lý tư vấn ảo" cho đội sale bất động sản, có khả năng tra cứu tức thời trên kho tài liệu dự án (bảng giá, mặt bằng, chính sách, tiện ích) và tồn kho căn theo thời gian thực, luôn trích nguồn tài liệu khi trả lời để tránh tư vấn sai.


### 3. Input đầu vào dự án

* **Kho tài liệu dự án**: Bảng giá, mặt bằng, chính sách bán hàng, tiện ích — dạng PDF/Excel/Word do Admin upload.
* **Dữ liệu tồn kho căn**: Kết nối qua API nội bộ của doanh nghiệp (real-time).
* **Bộ cấu hình phân quyền (RBAC)**: Danh sách tài liệu nội bộ (chỉ sale/admin xem) vs tài liệu công khai (khách xem được).

---

### 4. Người dùng & Vai trò (Roles)

Hệ thống phân quyền theo 2 vai trò chính ngay từ màn hình đăng nhập, quyết định luồng trải nghiệm hoàn toàn khác nhau.

| Role | Giao diện | Mục tiêu chính |
| :--- | :--- | :--- |
| **SALE** | Web App | Tra cứu thông tin dự án/tồn kho, tư vấn khách hàng tức thời, xác nhận (HITL) trước khi gửi thông tin cam kết. |
| **ADMIN (Quản lý kinh doanh)** | Web App | Quản lý kho tài liệu (ingestion), giám sát chất lượng AI, xử lý cảnh báo mâu thuẫn dữ liệu. |

---

### 5. Mô tả chi tiết Ý tưởng và Quy trình Giải quyết (Agentic Workflow)

Hệ thống sử dụng kiến trúc Multi-Agent và các biện pháp Tối ưu Độ trễ/Chi phí để đảm bảo tốc độ phản hồi dưới 3 giây tại hiện trường.

1. **Ingest & Sanitize**: Admin upload PDF/Excel -> Quét và gỡ bỏ các mã độc ẩn (Prompt Injection) trong tài liệu -> File gốc lưu vào **MinIO bucket** (nguồn lưu trữ chính, dùng để tải lại/tham chiếu) -> LlamaIndex xử lý, chunk & embed -> **chỉ vector embedding được ghi vào Qdrant** (Qdrant không lưu file gốc).
2. **Retrieval & Tool-Use (Main Agent)**: Nhận câu hỏi, Agent gọi API Tồn kho (Function Calling) và truy vấn Vector DB. *Tối ưu chi phí*: Sử dụng Semantic Caching để tái sử dụng câu trả lời cho các câu hỏi trùng lặp mà không tốn Token LLM.
3. **Generation**: Agent sinh câu trả lời kèm Trích nguồn và Hình ảnh mặt bằng.
4. **Verify (The Verifier Agent)**: Agent độc lập đối chiếu câu trả lời với tài liệu gốc để chấm điểm Faithfulness/Relevance. Nếu điểm thấp -> Bắt Main Agent sinh lại.
5. **Human-In-The-Loop (HITL)**: Sale BẮT BUỘC phải đọc và bấm nút "Xác nhận" trước khi đưa thông tin cho khách. AI không tự ý cam kết hợp đồng.

#### 5.1. Luồng Đăng nhập & Phân quyền (chung cho cả 2 role)
* Màn hình **ĐĂNG NHẬP** -> Hệ thống thực hiện Xác thực (Authentication).
* Sau xác thực, hệ thống thực hiện Phân quyền Role, rẽ nhánh theo 2 giá trị:
  * `ROLE = SALE` -> Vào luồng Web App (Sale).
  * `ROLE = ADMIN` -> Vào luồng Web Dashboard (Admin).

#### 5.2. Luồng SALE — Web App

* **a) Kiểm tra dữ liệu dự án**
  * Hệ thống kiểm tra: Đã có dữ liệu dự án chưa?
    * *Chưa có* -> Hiển thị Empty State: *"Chưa có dữ liệu dự án, vui lòng báo Admin cập nhật"*.
    * *Đã có* -> Vào Màn hình chính: Chat & Lịch sử.
* **b) Màn hình chính: Chat & Lịch sử**
  * Giao diện gồm thanh bên (giống ChatGPT) hiển thị danh sách Session, cùng khung chat chính:
    * Nút `+`: Tạo phiên khách hàng mới (Session), lưu Memory riêng theo từng khách.
    * Danh sách `Session: Khách ...`: Xem lại lịch sử các phiên tư vấn cũ (Session History).
    * Ô nhập liệu `Nhập câu hỏi tư vấn...`: Sale gửi câu hỏi bằng Text/Voice.
* **c) Xử lý câu hỏi (Agent Pipeline)**
  * Sale gửi câu hỏi (ví dụ: *"Giá căn 2PN?"*) -> Hệ thống hiển thị trạng thái Loading: *"Đang đọc tài liệu bảng giá..."*.
  * Hệ thống xác định: Cần tra cứu Bảng hàng (Real-time)?
    * **KHÔNG** -> Dữ liệu cố định, lấy trực tiếp trong DB/Vector DB (các file PDF đã ingest).
    * **CÓ** -> Dữ liệu không có sẵn trong DB, Agent dùng Tool gọi API tồn kho real-time của công ty.
    * *Trường hợp lỗi kết nối*: Nếu Mất kết nối tới API tồn kho -> Hiển thị Lỗi chung: *"Tạm thời không tra được tồn kho"*.
  * Sau khi có dữ liệu, hệ thống đánh giá: Tìm thấy thông tin đủ tin cậy? (dựa trên điểm Verifier Agent)
    * **KHÔNG / điểm thấp** -> Hiển thị Cảnh báo giới hạn: *"Không đủ thông tin, liên hệ Admin"*.
    * **CÓ** -> Tiếp tục đánh giá rủi ro nội dung.
  * Đánh giá: Có rủi ro cam kết/giá trong câu trả lời không?
    * **KHÔNG** -> Hiển thị Text trả lời thường + Trích nguồn tài liệu.
    * **CÓ** -> Hiển thị Thẻ HITL (Human-in-the-loop): Nút bắt buộc xác nhận.
* **d) Thẻ HITL (Human-in-the-loop) — chặn cam kết sai**
  * Khi câu trả lời liên quan tới giá/cam kết, hệ thống hiển thị thẻ cảnh báo gồm:
    * **Tiêu đề**: "CẢNH BÁO THÔNG TIN CAM KẾT".
    * **Nội dung**: [Thông tin] và [Tài liệu] nguồn trích dẫn tương ứng.
    * **Nút bắt buộc**: "XÁC NHẬN & COPY GỬI KHÁCH" — Sale phải đọc và bấm xác nhận trước khi copy nội dung gửi cho khách.
* **e) Phản hồi & cải tiến liên tục**
  * Mỗi câu trả lời đều kèm nút **Feedback** — cho phép Sale báo cáo câu trả lời sai/thiếu, tạo thành vòng lặp cải thiện chất lượng (feedback loop) cho Admin theo dõi ở Tab 2.

#### 5.3. Luồng ADMIN — Web App

Giao diện "SalesMate Admin" gồm thanh điều hướng trên cùng (Tài khoản: Quản lý Kinh doanh, Đăng xuất) và sidebar 4 mục: Kho tài liệu, Đánh giá AI, Cảnh báo mâu thuẫn, Cài đặt chung.

* **Tab 1 — Quản lý Tài liệu (Ingestion)**
  * Khu vực "Kéo thả file PDF/Excel vào đây" hoặc nút `[Chọn từ máy tính]`.
  * Admin bấm Update file PDF/Excel -> Hệ thống chuyển sang trạng thái Đang xử lý & Quét mã độc (Prompt Injection scanning).
  * Kết quả Ingestion rẽ 2 nhánh:
    * *Phát hiện Rủi ro Prompt Injection* -> Cảnh báo: *"Phát hiện nội dung bất thường, chặn file"*.
    * *Thành công* -> Trạng thái: *"Upload & Vector hóa thành công"*.
  * Danh sách tài liệu đã tải lên hiển thị dạng bảng với các cột: Tên file, Trạng thái, Phân quyền, Xóa.
* **Tab 2 — Đánh giá & Phân tích AI**
  * Xem Dashboard điểm DeepEval (đo Faithfulness/Answer Relevancy tự động của Verifier Agent).
  * Xem Top các câu hỏi AI trả lời thất bại — tổng hợp từ nút Feedback của Sale, giúp Admin ưu tiên bổ sung/chỉnh sửa tài liệu.
* **Tab 3 — Cảnh báo mâu thuẫn**
  * Xem Flag mâu thuẫn giữa 2 tài liệu (VD: 2 phiên bản bảng giá cùng dự án có nội dung khác nhau).
  * Hành động xử lý: Xóa tài liệu cũ / Ưu tiên tài liệu mới.
* **Cài đặt chung**
  * Cấu hình chung của hệ thống (quyền truy cập, thông số vận hành...).

#### 5.4. Bảng tổng hợp trạng thái & xử lý lỗi (Edge cases)

| Tình huống | Phản hồi hệ thống |
| :--- | :--- |
| Chưa có dữ liệu dự án | Empty State — yêu cầu Sale báo Admin cập nhật |
| Mất kết nối API tồn kho | Lỗi chung: "Tạm thời không tra được tồn kho" |
| Thông tin không đủ tin cậy / điểm Verifier thấp | Cảnh báo giới hạn: "Không đủ thông tin, liên hệ Admin" |
| Câu trả lời có rủi ro cam kết/giá | Bắt buộc hiển thị Thẻ HITL, chặn gửi khi chưa xác nhận |
| File upload chứa Prompt Injection | Cảnh báo, chặn file, không đưa vào Vector DB |
| Hai tài liệu mâu thuẫn nội dung | Flag cảnh báo cho Admin, chờ xử lý (xóa cũ / ưu tiên mới) |

---

### 6. Hướng dẫn chạy dự án (Local Development)

#### 6.1. Yêu cầu môi trường

* Python 3.11
* Node.js 20+ (khuyến nghị) và npm
* Docker Desktop (nếu chạy bằng Docker Compose)

#### 6.2. Chuẩn bị biến môi trường

```bash
# Backend
cp .env.example .env

# Frontend
cp frontend/.env.example frontend/.env
```

> Windows PowerShell: dùng `Copy-Item .env.example .env` và `Copy-Item frontend/.env.example frontend/.env`.

Sau đó mở `.env` và điền `GEMINI_API_KEY`, `SECRET_KEY`, `DATABASE_URL`, `INVENTORY_API_URL`...

#### 6.2.1. Mock API tồn kho

Tồn kho căn được tra **real-time qua HTTP**, không ingest vào Qdrant — số lượng căn
thay đổi liên tục nên vector hoá là sẽ trả lời số cũ. Giai đoạn build dùng mock API
dựng trên [mockapi.io](https://mockapi.io) theo đúng shape của API nội bộ sẽ dùng ở
production, nên khi đổi sang API thật chỉ cần sửa biến môi trường, không phải sửa code.

**Bước 1 — Tạo resource trên mockapi.io**

Tạo project mới, thêm resource tên `units` với 5 field dưới đây (mockapi tự thêm `id`,
`lookup_inventory` sẽ bỏ qua field lạ này):

| Field | Kiểu | Ví dụ | Ghi chú |
| :--- | :--- | :--- | :--- |
| `unit_code` | string | `OP3-A-0203` | Mã căn |
| `project_id` | string | `ocean-park-3` | Khớp `project_id` truyền vào khi tra cứu |
| `unit_type` | string | `2PN` | `1PN`…`10PN`, `Penthouse`, `Studio`, `Shophouse`, `Duplex` |
| `price` | number | `3600000000` | VND. Nhận cả chuỗi `"3600000000"` |
| `status` | string | `available` | `available` / `reserved` / `sold` |

Endpoint trả về một **JSON array**:

```json
[
  { "unit_code": "OP3-A-0203", "project_id": "ocean-park-3",
    "unit_type": "2PN", "price": 3600000000, "status": "available" }
]
```

**Bước 2 — Trỏ `.env` vào endpoint**

```bash
INVENTORY_API_URL=https://<project-id>.mockapi.io/units
INVENTORY_API_KEY=
```

> Tên biến phải đúng là `INVENTORY_API_URL`. `Settings` đặt `extra="ignore"`
> (`backend/core/config.py`), nên gõ sai tên (vd. `INVENTORY_MOCK_API`) sẽ **không
> báo lỗi** — biến bị bỏ qua im lặng và tra cứu luôn thất bại với thông báo
> "INVENTORY_API_URL chưa được cấu hình".

`INVENTORY_API_KEY` để trống với mockapi.io. Khi có giá trị, nó được gửi kèm dưới
dạng header `Authorization: Bearer <key>` — dành cho API nội bộ ở production.

**Bước 3 — Kiểm tra**

```bash
python -c "from backend.services.inventory_service import lookup_inventory; print(lookup_inventory('ocean-park-3', 'Còn căn 2PN nào trống không?'))"
```

Hoặc chạy unit test (không cần mạng, đã mock sẵn `httpx`):

```bash
pytest tests/test_services/test_inventory_service.py -v
```

**Cách hàm hoạt động** — `lookup_inventory(project_id, query)` trong
`backend/services/inventory_service.py`:

* Gửi `project_id` làm query param, timeout 5 giây.
* Đọc loại căn ngay trong câu hỏi tự nhiên của Sale ("còn căn **2PN** không") và lọc
  theo đó; không nhắc loại căn nào thì trả cả bảng hàng.
* **Không còn căn khớp → trả về `[]`**, đây là câu trả lời hợp lệ ("hết căn 2PN").
* **Không gọi được API → raise `InventoryApiError`**, để pipeline hiển thị
  "Tạm thời không tra được tồn kho". Hai trường hợp này tách bạch: gộp lại sẽ báo lỗi
  hệ thống trong khi thực chất chỉ là hết hàng.
* Record thiếu field bắt buộc bị bỏ qua thay vì làm hỏng cả lần tra cứu.

#### 6.3. Cách 1 — Chạy toàn bộ bằng Docker Compose (khuyến nghị)

```bash
# Build & khởi động tất cả service (backend, frontend, MySQL, Qdrant, MinIO)
docker compose up -d --build

# Xem log
docker compose logs -f backend
docker compose logs -f frontend

# Kiểm tra trạng thái các container
docker compose ps

# Dừng
docker compose down

# Dừng và xóa luôn dữ liệu (MySQL/Qdrant/MinIO volumes)
docker compose down -v
```

Chỉ chạy các service hạ tầng (khi muốn tự chạy backend/frontend ở máy):

```bash
docker compose up -d mysql qdrant minio
```

#### 6.4. Cách 2 — Chạy thủ công (dev mode, hot reload)

**Backend (FastAPI)**

```bash
# Tạo virtualenv
python -m venv .venv

# Kích hoạt: macOS/Linux
source .venv/bin/activate
# Kích hoạt: Windows PowerShell
.venv\Scripts\Activate.ps1

# Cài dependencies
pip install -r requirements.txt

# Tạo/cập nhật schema DB (BẮT BUỘC trước lần chạy đầu)
alembic upgrade head

# Chạy server (hot reload)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# hoặc
make run
```

> Chạy bằng Docker Compose thì không cần bước `alembic upgrade head` — container
> tự chạy migration lúc khởi động (`docker-entrypoint.sh`).

#### 6.4.1. Migration cơ sở dữ liệu (Alembic)

Schema do Alembic quản lý, **không** dùng `Base.metadata.create_all` nữa:
`create_all` chỉ tạo bảng còn thiếu và không bao giờ `ALTER` bảng đã tồn tại, nên
cột thêm sau sẽ âm thầm vắng mặt cho tới khi có query nổ lỗi lúc chạy.

```bash
alembic upgrade head                              # đưa DB lên bản mới nhất
alembic revision --autogenerate -m "mô tả"        # sinh migration sau khi sửa model
alembic downgrade -1                              # lùi 1 bước
alembic current                                   # DB đang ở revision nào
alembic check                                     # model có lệch migration không
```

Sau khi sửa bất kỳ file nào trong `backend/models/`, **phải** tạo revision mới —
`tests/test_migrations.py` sẽ fail nếu quên.

DB đã có sẵn bảng từ trước (tạo bằng `create_all`) thì đánh dấu một lần thay vì
chạy upgrade: `alembic stamp head`.

**Frontend (React + Vite)**

```bash
cd frontend
npm install
npm run dev          # dev server tại http://localhost:5173
npm run build        # build production vào frontend/dist
npm run preview      # xem thử bản build
npm run lint         # oxlint
```

#### 6.5. Test & chất lượng code (backend)

Bộ test chia 3 tầng:

| Tầng | Đường dẫn | Cần gì | Kiểm cái gì |
| :--- | :--- | :--- | :--- |
| Unit / API | `tests/test_api/` | Không | Từng endpoint trên SQLite in-memory |
| Migration | `tests/test_migrations.py` | Không | Migration khớp model, không drift |
| E2E | `tests/test_e2e/` | `docker compose up -d` | Hành trình Sale/Admin trên MySQL thật |

```bash
pytest tests/test_api tests/test_migrations   # nhanh, không cần Docker
docker compose up -d && pytest tests/test_e2e # E2E trên stack thật
```

E2E tự **skip** nếu backend chưa chạy, nên `pytest tests/` luôn an toàn.

```bash
make test        # pytest tests/ -v
make lint        # ruff check backend/ tests/
make format      # ruff format backend/ tests/
make typecheck   # mypy backend/
make check       # lint + format + test
make clean       # xóa cache __pycache__, .pytest_cache, .ruff_cache
```

Nếu không dùng `make`, chạy trực tiếp:

```bash
pytest tests/ -v
ruff check backend/ tests/
ruff format backend/ tests/
mypy backend/
```

#### 6.6. Truy cập sau khi chạy

| Thành phần | URL | Thông tin đăng nhập |
| :--- | :--- | :--- |
| Frontend | `http://localhost:5173` | `sale_test` / `pass1234` — `admin_test` / `pass1234` |
| Backend API | `http://localhost:8000` | — |
| Swagger UI | `http://localhost:8000/docs` | — |
| Health check | `http://localhost:8000/health` | — |
| Qdrant Dashboard | `http://localhost:6333/dashboard` | — |
| MinIO Console | `http://localhost:9001` | `minioadmin` / `minioadmin` |
| MySQL | `localhost:3306` | `salesmate` / `salesmate` (db: `salesmate_db`) |

#### 6.7. Tài khoản thử nghiệm

Backend tự seed 2 tài khoản mỗi lần khởi động (`SEED_USERS` trong
`backend/main.py`), nên máy nào clone repo về rồi `docker compose up` cũng đăng
nhập được ngay — không cần chia sẻ database giữa các máy hay chạy script tạo
user thủ công.

| Tài khoản | Mật khẩu | Role |
| :--- | :--- | :--- |
| `sale_test` | `pass1234` | SALE |
| `admin_test` | `pass1234` | ADMIN |

Seed là **idempotent**: tài khoản đã tồn tại thì được đặt lại mật khẩu/role/trạng
thái active về đúng bảng trên. Muốn thêm tài khoản dùng chung thì bổ sung vào
`SEED_USERS` — email phải là tên miền hợp lệ với `EmailStr` (tránh `.local`,
`.test`), nếu không `/auth/login` sẽ lỗi 500 lúc serialize response.

---

#### 6.7. Tài khoản thử nghiệm

Backend tự seed 2 tài khoản mỗi lần khởi động (`SEED_USERS` trong
`backend/main.py`), nên máy nào clone repo về rồi `docker compose up` cũng đăng
nhập được ngay — không cần chia sẻ database giữa các máy hay chạy script tạo
user thủ công.

| Tài khoản | Mật khẩu | Role |
| :--- | :--- | :--- |
| `sale_test` | `pass1234` | SALE |
| `admin_test` | `pass1234` | ADMIN |

Seed là **idempotent**: tài khoản đã tồn tại thì được đặt lại mật khẩu/role/trạng
thái active về đúng bảng trên. Muốn thêm tài khoản dùng chung thì bổ sung vào
`SEED_USERS` — email phải là tên miền hợp lệ với `EmailStr` (tránh `.local`,
`.test`), nếu không `/auth/login` sẽ lỗi 500 lúc serialize response.

### 7. Ứng dụng Công nghệ (Tech Stack)

* **AI Logic**: Gemini 2.5 Flash
* **RAG**: Gemini 2.5 Flash, Vector DB Qdrant (chỉ lưu vector embedding, không lưu file gốc), Re-ranker.
* **Object Storage**: MinIO — lưu file gốc (PDF/Excel/Word) khi Admin upload tài liệu; MySQL chỉ lưu metadata + đường dẫn tham chiếu tới MinIO.
* **Eval**: DeepEval — cho phép triển khai các metric RAG chuẩn công nghiệp chỉ trong vài dòng code, dùng để đo faithfulness/answer relevancy tự động.
* **Tool-use**: Tool tra cứu tồn kho qua API nội bộ.
* **Backend**: FastAPI, LangGraph, MySQL.
* **Frontend**: React, Vite, TypeScript, nginx, Swagger UI.
* **Deploy**: Vercel (frontend) + Fly.io (backend).

#### Cổng (Ports) chạy local — `docker-compose.yml`

| Dịch vụ | Cổng host | Ghi chú |
| :--- | :--- | :--- |
| Backend (FastAPI) | `8000` | `http://localhost:8000` — Swagger UI tại `/docs` |
| Frontend (React/Vite) | `5173` | `http://localhost:5173` |
| MySQL | `3306` | `mysql+pymysql://user:password@localhost:3306/salesmate_db` |
| Qdrant | `6333` | `http://localhost:6333` |
| MinIO API | `9000` | `http://localhost:9000` |
| MinIO Console | `9001` | `http://localhost:9001` |

#### Nguồn tham khảo dữ liệu / API mock

| Hạng mục | Nguồn |
| :--- | :--- |
| **File PDF Chính sách bán hàng** | `market-files.vinhomes.vn` (public-mngt) — tra cứu Google: `site:vinhomes.vn "chính sách bán hàng" filetype:pdf` |
| **Hình ảnh Mặt bằng (Floor Plans) & Tiện ích** | `rever.vn`; `batdongsan.com.vn` hoặc website chính thức của dự án (mục "Mặt bằng tổng thể") |
| **API** | Mock API tồn kho — `mockapi.io` (cách dựng: mục 6.2.1) |

---

### 7. Logging & Observability

Backend ghi log ra **stdout** (`docker compose logs -f backend`). Không ghi file, không ghi stderr — log collector coi mọi dòng stderr là lỗi bất kể mức độ.

#### 7.1. Định dạng

| `APP_ENV` | Định dạng | Dùng khi |
| :--- | :--- | :--- |
| `development` / `test` | Console — một dòng dễ đọc, có `[req=<id>]` | Chạy máy local |
| còn lại | JSON — mỗi record một dòng | Production, để collector parse |

Ép định dạng bằng `LOG_JSON=true|false`. Mức log theo `LOG_LEVEL` (mặc định `INFO`).

Mỗi dòng JSON có: `timestamp`, `level`, `logger`, `message`, `module`, `func`, `line`, `request_id`, cộng các field riêng của sự kiện, và `exc_type` + `exception` (traceback đầy đủ) khi có lỗi.

#### 7.2. `request_id` — sợi chỉ xuyên suốt một request

Mỗi request được gán một id (hoặc tái dùng header `X-Request-ID` gửi tới, cho phép trace xuyên service), id này xuất hiện trên **mọi** dòng log của request đó và được trả lại trong header `X-Request-ID`. Khi Sale báo lỗi, chỉ cần id đó là dựng lại được toàn bộ diễn biến:

```bash
docker compose logs backend | grep <request_id> | jq .
```

Khi backend trả lỗi 500, body chứa sẵn `request_id` để người dùng đọc cho support — nội dung lỗi thật không bao giờ lộ ra ngoài.

#### 7.3. Audit trail nghiệp vụ

Sự kiện nghiệp vụ đi vào logger riêng `salesmate.audit`, **ghim cứng ở mức INFO** để chạy production với `LOG_LEVEL=WARNING` không vô tình tắt mất vết kiểm toán.

| Event | Ý nghĩa |
| :--- | :--- |
| `auth.login.success` / `auth.login.failure` | Đăng nhập. Thất bại dùng chung một `reason` cho cả sai user lẫn sai mật khẩu, để log không dò được username hợp lệ |
| `auth.refresh.failure`, `auth.logout` | Vòng đời token |
| `document.upload` | Admin tải tài liệu lên |
| `document.ingest.success` / `.blocked` / `.failure` | Kết quả ingest; `.blocked` là phát hiện prompt injection |
| `sale.query` | **Nguồn dữ liệu cho Dashboard Admin (§5.3 Tab 2)** — `verifier_score`, `faithfulness`, `answer_relevancy`, `requires_hitl`, `used_cache`, `citation_count`, `duration_ms` |
| `hitl.confirm` | Sale bấm xác nhận nội dung cam kết |

Lọc riêng audit event:

```bash
docker compose logs backend | jq 'select(.audit == true)'
docker compose logs backend | jq 'select(.event == "sale.query") | {verifier_score, requires_hitl, duration_ms}'
```

#### 7.3.1. Lưu trữ bền trong MySQL (bảng `audit_logs`)

Audit event đi vào **hai nơi cùng lúc**, mỗi nơi một nhiệm vụ:

| Nơi | Trả lời câu hỏi | Vòng đời |
| :--- | :--- | :--- |
| stdout (JSON) | "Vừa nãy hỏng cái gì?" — nối được với traceback cùng `request_id` | Mất khi container bị thay |
| Bảng `audit_logs` | "Ai đăng nhập tuần trước? Sale nào xác nhận mức giá đó?" | Còn mãi trong DB |

Log chẩn đoán (traceback, access log) **không** ghi vào MySQL — khối lượng lớn, vòng đời ngắn, thuộc về log collector chứ không phải database vận hành.

Hai tính chất bắt buộc của việc ghi (đều có test canh giữ trong `tests/test_core/test_audit_sink.py`):

* **Ghi bằng session riêng.** `auth.login.failure` được phát ngay trước `raise HTTPException`; nếu dùng chung session của request thì dòng đó không bao giờ được commit — mất đúng những sự kiện bảo mật đáng giữ nhất. Dùng chung rồi `commit()` còn tệ hơn: nó commit lây cả nghiệp vụ đang dở dang.
* **Không bao giờ raise.** MySQL sập chỉ làm suy giảm audit trail (dòng stdout vẫn có), không biến một request đang chạy tốt thành lỗi 500.

Admin đọc qua API:

```bash
GET /api/v1/admin/eval/audit?limit=100
GET /api/v1/admin/eval/audit?event=auth.login.failure&days=7
GET /api/v1/admin/eval/audit?user_id=3
```

Hoặc truy vấn thẳng SQL:

```sql
-- Đăng nhập thất bại 24h qua, gom theo tài khoản
SELECT username, COUNT(*) FROM audit_logs
WHERE event = 'auth.login.failure' AND created_at > NOW() - INTERVAL 1 DAY
GROUP BY username ORDER BY 2 DESC;

-- Toàn bộ dấu vết của một request (nối với dòng stdout cùng request_id)
SELECT * FROM audit_logs WHERE request_id = '<request_id>';
```

#### 7.4. Những gì KHÔNG bao giờ vào log

Mật khẩu, JWT (kể cả một phần — prefix JWT vẫn decode được), `GEMINI_API_KEY`/`SECRET_KEY`/khóa MinIO, nội dung file tài liệu, câu trả lời sinh ra, và nội dung HITL gửi khách (chỉ ghi độ dài và việc Sale có sửa hay không).

Đặt `LOG_QUERY_TEXT=false` nếu không được phép lưu cả câu hỏi của Sale — khi đó `sale.query` vẫn giữ `query_len` nhưng bỏ `query`.

Ngoài kỷ luật tại chỗ gọi, handler còn gắn `RedactingFilter` tự động che các field có tên gợi ý bí mật. Đây là lưới an toàn, không thay thế nguyên tắc "không truyền bí mật vào logger".

#### 7.5. Chẩn đoán sự cố thường gặp

```bash
# Pipeline sập / Gemini lỗi — traceback đầy đủ nằm ở đây
docker compose logs backend | jq 'select(.event | startswith("pipeline."))'

# Verifier hỏng (khác hoàn toàn với "câu trả lời chất lượng kém")
docker compose logs backend | jq 'select(.event | startswith("verifier."))'

# Qdrant / MinIO / API tồn kho lỗi
docker compose logs backend | jq 'select(.event | test("retrieval|vectorstore|storage|inventory"))'

# Request chậm
docker compose logs backend | jq 'select(.event == "http.access" and .duration_ms > 3000)'
```
