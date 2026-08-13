# SalesMate AI Agent

> Trợ lý AI dạng RAG cho đội Sale bất động sản: tra cứu tức thời bảng giá, mặt bằng, chính sách và tồn kho căn theo thời gian thực, luôn trích nguồn để tránh tư vấn sai.

## Vấn đề (Problem)

Sale bất động sản phải nhớ/tìm thủ công thông tin nằm rải rác trong hàng chục file PDF/Excel (bảng giá, mặt bằng, chính sách bán hàng) và một hệ tồn kho đổi liên tục theo thời gian thực. Tư vấn sai giá hoặc cam kết nhầm chính sách với khách là rủi ro trực tiếp tới hợp đồng.

## Giải pháp (Solution)

- **Tra cứu tài liệu (RAG)**: Admin upload PDF/Excel/Word, hệ thống chunk & embed vào Qdrant; Sale hỏi bằng ngôn ngữ tự nhiên, luôn nhận kèm trích nguồn tài liệu.
- **Tồn kho real-time**: Agent gọi API tồn kho nội bộ qua Function Calling thay vì vector hoá — số lượng căn đổi liên tục nên chỉ tra trực tiếp mới đúng.
- **Verifier Agent**: chấm điểm Faithfulness/Relevancy độc lập trước khi trả lời; điểm thấp thì bắt sinh lại hoặc từ chối trả lời.
- **HITL (Human-in-the-loop)**: câu trả lời có rủi ro giá/cam kết bắt buộc Sale bấm xác nhận trước khi gửi khách — AI không tự ý cam kết hợp đồng.
- **Admin dashboard**: quản lý kho tài liệu, quét Prompt Injection lúc ingest, theo dõi điểm DeepEval và cảnh báo mâu thuẫn giữa các phiên bản tài liệu.

## Target User

- **Primary**: Sale bất động sản — tra cứu & tư vấn khách tại hiện trường.
- **Secondary**: Admin/Quản lý kinh doanh — quản lý tài liệu, giám sát chất lượng AI.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.11, LangGraph |
| LLM / RAG | Google Gemini 2.5 Flash, Qdrant (vector DB) |
| Database | MySQL 8 + Alembic |
| Object Storage | MinIO (file gốc + ảnh dự án) |
| Eval | DeepEval (Faithfulness / Answer Relevancy) |
| Frontend | React, Vite, TypeScript, nginx |
| Deploy | Vercel (frontend) + Fly.io (backend) |

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

Chạy dev mode không qua Docker (hot reload) hoặc chi tiết mock API tồn kho: xem [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Project Structure

```
├── backend/
│   ├── core/                 # Config, Gemini client, security, MinIO client
│   ├── models/                # ORM models (SQLAlchemy)
│   ├── schemas/                # Pydantic request/response schemas
│   ├── repositories/            # Database access layer
│   ├── services/                # RAG, verifier, inventory, ingestion, cache...
│   ├── routers/                  # API endpoints
│   ├── utils/                     # Helpers
│   └── main.py                     # FastAPI app entry point
├── frontend/                # React + Vite app (Sale & Admin)
├── migrations/               # Alembic migrations
├── scripts/                   # Seed/data-loading scripts
├── seed-data/                   # Catalogue demo (JSON, đã commit)
├── tests/                        # Unit / API / E2E
├── eval/                          # Kết quả DeepEval
├── docs/                           # Tài liệu chi tiết (kiến trúc, dev guide)
├── Dockerfile / docker-compose.yml
└── requirements.txt
```

## API Endpoints chính

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Đăng nhập, phân quyền SALE/ADMIN |
| POST | `/api/v1/sale-chat/sessions/{id}/ask` | Hỏi Agent trong một phiên tư vấn |
| POST | `/api/v1/hitl/confirm` | Xác nhận nội dung cam kết trước khi gửi khách |
| POST | `/api/v1/documents` | Admin upload tài liệu (ingest + quét Prompt Injection) |
| GET | `/api/v1/projects` | Danh sách dự án/catalogue |
| GET | `/health` | Health check |

Toàn bộ API: `http://localhost:8000/docs` (Swagger UI) sau khi chạy `docker compose up`.

## Testing

```bash
pytest tests/test_api tests/test_migrations   # nhanh, không cần Docker
docker compose up -d && pytest tests/test_e2e # E2E trên stack thật
make check                                     # lint + format + test
```

## Team

| Member | Role | Student ID |
|--------|------|-----------|
| [Tên] | [Vai trò] | [MSSV] |
| [Tên] | [Vai trò] | [MSSV] |
| [Tên] | [Vai trò] | [MSSV] |

## License

MIT
