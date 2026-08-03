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

Sau đó mở `.env` và điền `GEMINI_API_KEY`, `SECRET_KEY`, `DATABASE_URL`...

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
| Frontend | `http://localhost:5173` | — |
| Backend API | `http://localhost:8000` | — |
| Swagger UI | `http://localhost:8000/docs` | — |
| Health check | `http://localhost:8000/health` | — |
| Qdrant Dashboard | `http://localhost:6333/dashboard` | — |
| MinIO Console | `http://localhost:9001` | `minioadmin` / `minioadmin` |
| MySQL | `localhost:3306` | `salesmate` / `salesmate` (db: `salesmate_db`) |

---

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
| **API** | Mock API — `mockapi.io` |
