# Auremont AI Agent

> Trợ lý AI dạng RAG cho đội Sale bất động sản: tra cứu tức thời bảng giá, mặt bằng, chính sách và tồn kho căn theo thời gian thực, luôn trích nguồn để tránh tư vấn sai.

## Vấn đề (Problem)

Sale bất động sản phải nhớ/tìm thủ công thông tin nằm rải rác trong hàng chục file PDF/Excel (bảng giá, mặt bằng, chính sách bán hàng) và một hệ tồn kho đổi liên tục theo thời gian thực. Tư vấn sai giá hoặc cam kết nhầm chính sách với khách là rủi ro trực tiếp tới hợp đồng.

## Giải pháp (Solution)

- **Tra cứu tài liệu (RAG)**: Admin upload PDF/Excel/Word, hệ thống chunk & embed vào Qdrant; Sale hỏi bằng ngôn ngữ tự nhiên, luôn nhận kèm trích nguồn tài liệu.
- **Tồn kho real-time**: Agent gọi API tồn kho nội bộ qua Function Calling thay vì vector hoá — số lượng căn đổi liên tục nên chỉ tra trực tiếp mới đúng.
- **Verifier Agent**: chấm điểm Faithfulness/Relevancy độc lập trước khi trả lời; điểm thấp thì bắt sinh lại hoặc từ chối trả lời.
- **HITL (Human-in-the-loop)**: câu trả lời có rủi ro giá/cam kết bắt buộc Sale bấm xác nhận trước khi gửi khách — AI không tự ý cam kết hợp đồng.
- **Admin dashboard**: quản lý kho tài liệu, quét Prompt Injection lúc ingest, theo dõi điểm Verifier (faithfulness/relevancy) và cảnh báo mâu thuẫn giữa các phiên bản tài liệu.

## Target User

- **Primary**: Sale bất động sản — tra cứu & tư vấn khách tại hiện trường.
- **Secondary**: Admin/Quản lý kinh doanh — quản lý tài liệu, giám sát chất lượng AI.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.11, LangGraph (`StateGraph` 1 graph, 9 node) |
| LLM / RAG | Google Gemini (`gemini-3.5-flash-lite` generate/verify, `gemini-embedding-001` embed), Qdrant (vector DB) |
| Database | MySQL 8.4 + Alembic |
| Object Storage | MinIO (file gốc + ảnh dự án) |
| Eval | Verifier score (Gemini LLM-as-judge) ghi trực tiếp MySQL, đọc cho Admin dashboard; DeepEval chỉ dùng offline trong `eval/`, không chạy trong request path |
| Frontend | React 19 + Vite + TypeScript (1 SPA, phân nhánh role) + nginx (trong container frontend) |
| Deploy | Docker Compose (local dev) — **chưa có** hạ tầng production (không có `vercel.json`/`fly.toml`, `deploy/` hiện rỗng) |

> Chi tiết đầy đủ về kiến trúc thật (bao gồm các chỗ khác với thiết kế ban đầu) xem [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-110.git
cd P-110

# 2. Setup environment
cp .env.example .env
cp frontend/.env.example frontend/.env
# Điền GEMINI_API_KEY, SECRET_KEY, INVENTORY_API_URL... vào .env

# 3. Chạy toàn bộ stack (backend, frontend, MySQL, Qdrant, MinIO)
docker compose up -d --build
```

Migration DB và seed 2 tài khoản test (`sale_test` / `admin_test`, mật khẩu `pass1234`) chạy tự động lúc container khởi động — không cần thao tác thêm. Ảnh dự án (~58MB, không nằm trong git) được backend tự tải về MinIO theo `PROJECT_IMAGES_BASE_URL` trong `.env`.

**Env vars chính cần điền trong `.env`** (đầy đủ xem `.env.example`):

| Biến | Bắt buộc | Ghi chú |
| :--- | :--- | :--- |
| `SECRET_KEY` | Có | Ký JWT — đổi giá trị mặc định trước khi deploy |
| `GEMINI_API_KEY` | Có | Dùng cho cả generate, verify và embedding |
| `DATABASE_URL` | Không (docker compose tự set) | Chỉ cần điền khi chạy `uvicorn` thủ công ngoài Docker |
| `INVENTORY_API_URL` / `INVENTORY_API_KEY` | Không | Trống = tồn kho luôn báo lỗi; trỏ vào mock mockapi.io để test (xem `docs/DEVELOPMENT.md`) |
| `INVENTORY_PROJECT_MAP` | Không | Ánh xạ slug catalogue (`the-palma`) sang mã dự án của API tồn kho (`ocean-park-3`) |
| `PROJECT_IMAGES_BASE_URL` / `PROJECT_IMAGES_ARCHIVE_URL` | Không | Trống = catalogue chạy nhưng không có ảnh |
| `CLASSIFICATION_AUTO_APPROVE_THRESHOLD` | Không | Mặc định `0.90` — tài liệu phân loại tự động ở ngưỡng này trở lên không cần Admin duyệt tay |

`frontend/.env`: `VITE_API_URL=http://localhost:8000/api/v1`, `VITE_WS_URL=ws://localhost:8000` — dùng nguyên giá trị mẫu khi chạy local.

Chạy dev mode không qua Docker (hot reload), chi tiết mock API tồn kho, hoặc migration Alembic: xem [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Câu hỏi mẫu (Sample Queries)

Ví dụ Sale có thể hỏi trong khung chat (tài khoản demo được seed sẵn dự án `Vinhomes Ocean Park 3`):

- *"Giá căn 2PN dự án Ocean Park 3 là bao nhiêu?"* — cần tra Bảng hàng real-time qua Inventory API, có thể chạm rủi ro giá → HITL.
- *"Còn căn 2PN nào trống không?"* — Tool `lookup_inventory` lọc theo loại căn đọc trực tiếp trong câu hỏi.
- *"Chính sách thanh toán của dự án là gì?"* — trả lời từ tài liệu đã ingest (Qdrant), kèm trích nguồn.
- *"Cho xem mặt bằng The Palma"* / *"Cho xem hình ảnh dự án"* — trả về kèm ảnh từ catalogue (`image_tool`), bỏ qua bước Verify vì câu trả lời là ảnh.
- *"Tiện ích nội khu có những gì?"* — RAG thuần trên tài liệu tiện ích, không cần tra tồn kho.

Hỏi lại đúng một câu đã hỏi trước đó (cùng dự án) sẽ được trả lời ngay từ Semantic Cache thay vì gọi lại LLM.

## Project Structure

```
├── backend/
│   ├── ai/                    # Prompts, citations, intent detection
│   ├── core/                  # Config, Gemini client, security, MinIO/MySQL client
│   ├── middleware/             # Request logging, exception handlers
│   ├── models/                 # ORM models (SQLAlchemy)
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── repositories/             # Database access layer
│   ├── services/                 # Agent pipeline (LangGraph), RAG, verifier, inventory, ingestion, cache...
│   ├── routers/                   # API endpoints
│   ├── utils/                      # Helpers
│   └── main.py                      # FastAPI app entry point
├── frontend/                 # React SPA (Sale & Admin, phân nhánh theo role)
├── migrations/                # Alembic migrations
├── scripts/                    # Seed/data-loading scripts (load catalogue, upload ảnh...)
├── seed-data/                    # Catalogue demo + manifest ảnh (JSON, đã commit)
├── tests/                         # test_api/ test_core/ test_models/ test_services/ test_e2e/ + test_migrations.py
├── eval/                           # Kết quả đánh giá offline (DeepEval, không chạy live)
├── docs/                            # Tài liệu chi tiết (DEVELOPMENT.md)
├── deploy/                          # (hiện rỗng — chưa có cấu hình deploy production)
├── Dockerfile / docker-compose.yml / docker-entrypoint.sh
└── requirements.txt
```

## API Endpoints chính

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Đăng nhập, phân quyền SALE/ADMIN |
| POST | `/api/v1/sale/sessions/{session_id}/messages` | Hỏi Agent trong một phiên tư vấn |
| POST | `/api/v1/hitl/{message_id}/confirm` | Xác nhận nội dung cam kết trước khi gửi khách |
| POST | `/api/v1/documents` | Admin upload tài liệu (ingest + quét Prompt Injection) |
| GET | `/api/v1/projects` | Danh sách dự án/catalogue |
| GET | `/health` | Health check |

Toàn bộ API: `http://localhost:8000/docs` (Swagger UI) sau khi chạy `docker compose up`.

## Testing

```bash
pytest tests/test_api tests/test_migrations.py  # nhanh, không cần Docker (SQLite in-memory)
docker compose up -d && pytest tests/test_e2e    # E2E trên MySQL thật — tự skip nếu backend chưa chạy
make check                                        # lint (ruff) + format (ruff) + test
```

`make typecheck` (mypy) và `make lint`/`make format` chạy tách riêng khỏi `make check` chỉ khi cần. Chi tiết 3 tầng test, truy cập sau khi chạy (URL/port từng service, tài khoản demo), và logging/audit trail: xem [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Team

| Member | Role | Student ID |
|--------|------|-----------|
| [Tên] | [Vai trò] | [MSSV] |
| [Tên] | [Vai trò] | [MSSV] |
| [Tên] | [Vai trò] | [MSSV] |

## License

MIT
