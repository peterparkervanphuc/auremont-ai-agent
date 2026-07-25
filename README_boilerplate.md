# [Tên Dự Án]

> Tóm tắt 1 câu: [Vấn đề] → [Giải pháp AI] cho [Target User]

## Vấn đề (Problem)

Mô tả pain point cụ thể với data/số liệu:
- Ai đang gặp vấn đề?
- Vấn đề tốn bao nhiêu thời gian/tiền?
- Tại sao các giải pháp hiện tại chưa đủ?

## Giải pháp (Solution)

Sản phẩm giải quyết vấn đề như thế nào bằng AI:
- Feature 1: [mô tả]
- Feature 2: [mô tả]
- Feature 3: [mô tả]

## Target User

- Primary: [mô tả user chính]
- Secondary: [mô tả user phụ]

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.11+ |
| LLM | Google Gemini |
| Database | SQL (PostgreSQL / MySQL / SQLite) |
| Frontend | React/Next.js + TypeScript |
| DevOps | Docker + GitHub Actions |

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/a20-ai-thuc-chien/A20-App-XXX.git
cd A20-App-XXX

# 2. Setup environment
cp .env.example .env
# Edit .env with your API keys

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run development server
uvicorn backend.main:app --reload
```

## Project Structure

```
├── backend/
│   ├── core/                    # Config, utilities
│   │   ├── config.py            # Pydantic settings
│   │   ├── gemini_client.py     # Gemini LLM wrapper
│   │   ├── mysql_client.py      # Database client (SQLAlchemy)
│   │   └── enums.py             # Common enums
│   ├── models/                  # ORM models (SQLAlchemy)
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── repositories/            # Database access layer
│   ├── services/                # Business logic
│   ├── routers/                 # API endpoints
│   ├── utils/                   # Utilities (logger, helpers, etc.)
│   ├── main.py                  # FastAPI app entry point
│   └── requirements.txt          # Python dependencies (if separate)
├── frontend/                    # React/Next.js app (to be created)
├── tests/                       # Test suite
├── docs/                        # Documentation
├── eval/                        # Evaluation results
├── presentation/                # Demo materials
├── Dockerfile                   # Multi-stage build
├── docker-compose.yml           # Service orchestration
├── requirements.txt             # Python dependencies
└── .github/workflows/           # CI/CD pipelines
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /api/v1/chat | Chat with agent |
| POST | /api/v1/analyze | Analyze input |

## Deliverables Checklist

- [x] Source Code (GitHub)
- [x] README.md
- [x] Architecture Diagram (`docs/architecture_diagram.md`)
- [x] AI Logs (auto-collected)
- [ ] Live URL / Deploy
- [ ] Video Demo
- [ ] Pitch Deck (`presentation/`)
- [x] Weekly Journal (`JOURNAL.md`)
- [x] Worklog (`WORKLOG.md`)
- [ ] Evaluation Evidence (`eval/results/`)

## Team

| Member | Role | Student ID |
|--------|------|-----------|
| [Name] | [Role] | [ID] |
| [Name] | [Role] | [ID] |
| [Name] | [Role] | [ID] |

## License

MIT
