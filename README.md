# Auremont AI Agent

> RAG assistant for real-estate sales teams: instant lookup of pricing, floor plans, policies, and live inventory — every answer cited.

## Problem

Sales reps manually search dozens of PDFs/Excels for pricing, floor plans, and policies, alongside inventory that changes in real time. A wrong price or policy quoted to a customer is a direct contract risk.

## Solution

- **Document RAG** — PDF/Excel/Word ingested, chunked, embedded into Qdrant; every answer cites its source.
- **Live inventory** — real-time stock lookup via Function Calling, never from stale documents.
- **Verifier Agent** — independent Faithfulness/Relevancy/Completeness scoring; low score triggers a corrected retry or a decline.
- **HITL** — price/commitment answers require explicit Sale confirmation before being sent to a customer.
- **Customer chat** — public/anonymous chat with a soft registration gate and AI→Sale handoff.
- **Memory (Redis)** — per-user preferences and agent self-correction lessons, fail-open.
- **Auto-attached images, suggested follow-ups** — contextual photos and next-question suggestions generated alongside each answer.
- **Admin dashboard** — document management, prompt-injection scanning, Verifier score tracking, conflict detection.

## Target Users

| Role | Use case |
|---|---|
| Sale | Field consultation, inventory lookup |
| Admin | Document management, AI quality monitoring |
| Customer | Public self-service chat |

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.11, LangGraph `StateGraph` |
| LLM / RAG | Gemini (`gemini-3.5-flash-lite`, `gemini-embedding-001`), Qdrant, Cohere Rerank (optional) |
| Database | MySQL 8.4 + Alembic |
| Memory | Redis (fail-open) |
| Object Storage | MinIO |
| Eval | Verifier scores in MySQL; deterministic graders + golden regression dataset in CI |
| Frontend | React 19 + Vite + TypeScript, nginx |
| Deploy | Docker Compose (local only — no production infra configured) |

> Full architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)

## Ports

| Service | Port | URL |
|---|---|---|
| Backend | `8000` | http://localhost:8000 (`/docs` for Swagger) |
| Frontend | `5173` | http://localhost:5173 |
| MySQL | `3307→3306` | `mysql+pymysql://salesmate:salesmate@localhost:3307/salesmate_db` |
| Qdrant | `6333` | http://localhost:6333 |
| Redis | `6379` | `redis://localhost:6379/0` |
| MinIO API | `9000` | http://localhost:9000 |
| MinIO Console | `9001` | http://localhost:9001 |

## Quick Start

```bash
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-110.git
cd P-110

cp .env.example .env
cp frontend/.env.example frontend/.env
# fill in GEMINI_API_KEY, SECRET_KEY, INVENTORY_API_URL...

docker compose up -d --build
```

Migrations and demo accounts (`sale_test` / `admin_test`, password `pass1234`) run automatically on startup.

**Required env vars** (full list in `.env.example`):

| Var | Required | Notes |
|---|---|---|
| `SECRET_KEY` | Yes | JWT signing |
| `GEMINI_API_KEY` | Yes | Generate, verify, embed |
| `REDIS_URL` | No | Empty = personalization/self-correction disabled, chat still works |
| `INVENTORY_API_URL` / `INVENTORY_API_KEY` | No | Empty = inventory always errors |
| `PROJECT_IMAGES_BASE_URL` | No | Empty = catalogue runs without images |
| `RERANK_ENABLED` / `HYBRID_SEARCH_ENABLED` | No | Both off by default |

Dev mode without Docker, mock inventory API setup, migrations: see [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Project Structure

```
├── backend/
│   ├── ai/            # Prompts, citations, intent detection
│   ├── core/           # Config, clients, security
│   ├── middleware/       # Request logging
│   ├── models/             # SQLAlchemy models
│   ├── schemas/              # Pydantic schemas
│   ├── repositories/          # Data access
│   ├── services/                # Agent pipeline, RAG, verifier, memory, ingestion
│   ├── routers/                    # API endpoints
│   ├── utils/                         # Shared helpers (text, time)
│   └── main.py
├── frontend/            # React SPA (Sale / Admin / Customer)
├── migrations/            # Alembic
├── eval/                    # graders.py + golden_dataset.py
├── tests/
├── docs/
└── docker-compose.yml
```

## API

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/sale/sessions/{id}/messages` | Sale asks the agent |
| POST | `/api/v1/customer/sessions/{id}/messages` | Customer asks the agent |
| GET | `/api/v1/sale/live-inbox` | AI→Sale handoff queue |
| POST | `/api/v1/hitl/{id}/confirm` | Confirm a commitment answer |
| POST | `/api/v1/documents/upload` | Upload/ingest a document |
| GET | `/health` | Health check |

Full API: http://localhost:8000/docs

## Testing

```bash
pytest tests/test_api tests/test_migrations.py         # fast, no Docker
pytest tests/test_services/test_golden_regression.py    # golden RAG regression gate
docker compose up -d && pytest tests/test_e2e             # full E2E
make check                                                  # lint + format + test
```

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for details.

## Team

| Member | Role | Student ID |
|---|---|---|
| [Name] | [Role] | [ID] |

## License

MIT
