# Architecture Document

## System Overview

[Tóm tắt 2-3 câu về kiến trúc hệ thống]

## Architecture Diagram

```mermaid
flowchart TB
    subgraph CLIENT["🖥️ Client Layer"]
        direction LR
        SaleApp["Sale Web App<br/>React + Vite + TS"]
        AdminApp["Admin Dashboard<br/>React + Vite + TS"]
    end
 
    Nginx["nginx<br/>Reverse Proxy"]
 
    subgraph BACKEND["⚙️ Backend - FastAPI"]
        direction TB
        API["FastAPI REST API<br/>Swagger UI tại /docs"]
        Auth["Auth và RBAC<br/>phân quyền Sale / Admin"]
 
        subgraph AGENT["🤖 Agent Orchestration - LangGraph"]
            direction TB
            MainAgent["Main Agent<br/>Retrieval + Tool-Use"]
            VerifierAgent["Verifier Agent<br/>chấm Faithfulness/Relevance"]
            SemCache["Semantic Cache<br/>tái sử dụng câu trả lời trùng lặp"]
        end
 
        subgraph INGEST["📥 Ingestion Pipeline"]
            direction TB
            Sanitizer["Prompt Injection Scanner"]
            LlamaIdx["LlamaIndex<br/>Chunk + Embed"]
            Reranker["Re-ranker"]
        end
    end
 
    subgraph DATA["🗄️ Data Layer"]
        direction LR
        MySQL[("MySQL<br/>metadata + đường dẫn tham chiếu")]
        Qdrant[("Qdrant<br/>Vector DB - chỉ lưu embedding")]
        MinIO[("MinIO<br/>Object Storage - file gốc PDF/Excel/Word")]
    end
 
    subgraph EXTERNAL["🌐 External Services"]
        direction LR
        LLM["LLM API<br/>Gemini 2.5 Flash / Claude / GPT-4o"]
        InventoryAPI["Inventory API<br/>nội bộ doanh nghiệp - real-time"]
    end
 
    DeepEval["DeepEval<br/>Dashboard Faithfulness/Relevancy"]
 
    subgraph DEPLOY["☁️ Deployment"]
        direction LR
        Vercel["Vercel<br/>Frontend hosting"]
        FlyIO["Fly.io<br/>Backend hosting"]
    end
 
    SaleApp --> Nginx
    AdminApp --> Nginx
    Nginx --> API
    API --> Auth
 
    Auth --> MainAgent
    Auth --> Sanitizer
 
    MainAgent --> SemCache
    SemCache -.cache hit, bỏ qua LLM.-> MainAgent
    MainAgent --> Qdrant
    MainAgent --> InventoryAPI
    MainAgent --> LLM
    MainAgent --> VerifierAgent
    VerifierAgent --> LLM
    VerifierAgent -->|điểm thấp, bắt sinh lại| MainAgent
    VerifierAgent --> DeepEval
 
    Sanitizer -->|an toàn| MinIO
    Sanitizer -->|phát hiện mã độc| BlockFile["Chặn file, cảnh báo Admin"]
    MinIO --> LlamaIdx
    LlamaIdx --> Reranker
    Reranker --> Qdrant
 
    API --> MySQL
    MinIO -.đường dẫn tham chiếu.-> MySQL
 
    SaleApp -.deploy.-> Vercel
    AdminApp -.deploy.-> Vercel
    API -.deploy.-> FlyIO
 
    classDef client fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef backend fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef data fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef external fill:#fce7f3,stroke:#db2777,color:#831843
    classDef deploy fill:#e0e7ff,stroke:#4f46e5,color:#312e81
 
    class SaleApp,AdminApp client
    class API,Auth,MainAgent,VerifierAgent,SemCache,Sanitizer,LlamaIdx,Reranker backend
    class MySQL,Qdrant,MinIO data
    class LLM,InventoryAPI external
    class Vercel,FlyIO deploy
```

## Components
 
### 1. Frontend (React + Vite)
- **Purpose:** Giao diện web cho 2 vai trò — Sale (chat tư vấn tức thời) và Admin (quản lý kho tài liệu, giám sát chất lượng AI). Phân nhánh hoàn toàn theo Role ngay từ màn hình đăng nhập.
- **Key Features:**
  - Sale: sidebar Session (giống ChatGPT), khung chat Text/Voice, trạng thái Loading theo bước xử lý, Thẻ HITL bắt buộc xác nhận trước khi copy nội dung gửi khách, nút Feedback trên từng câu trả lời.
  - Admin: kéo-thả upload PDF/Excel, bảng danh sách tài liệu (Tên file/Trạng thái/Phân quyền/Xóa), Dashboard điểm DeepEval, danh sách câu hỏi AI trả lời thất bại, Flag mâu thuẫn tài liệu với hành động Xóa cũ/Ưu tiên mới.
  - Swagger UI (`/docs`) dùng nội bộ để dev/test API, không expose cho end-user.
- **State Management:** Zustand cho state cục bộ (session hiện tại, danh sách message, trạng thái Loading/HITL) kết hợp TanStack Query cho server state (fetch tài liệu, tồn kho, lịch sử session) để tận dụng cache/refetch tự động — phù hợp với yêu cầu phản hồi dưới 3 giây.
### 2. Backend (FastAPI)
- **Purpose:** Điều phối toàn bộ pipeline — nhận câu hỏi từ Sale, gọi Agent xử lý, quản lý ingestion tài liệu từ Admin, cung cấp dữ liệu cho Dashboard đánh giá.
- **API Design:** RESTful, tự sinh docs qua Swagger UI tại `/docs`.
- **Authentication:** *(đề xuất)* JWT kèm claim `role` (SALE/ADMIN) — RBAC không chỉ chặn ở route mà còn filter ở tầng retrieval (payload filter trong Qdrant) để phân biệt tài liệu nội bộ vs công khai.
### 3. AI Agent (LangGraph)
- **Agent Type:** Multi-Agent tùy biến — Main Agent theo mô hình ReAct (reason → tool-call → observe → answer) kết hợp Verifier Agent độc lập chạy sau để chấm điểm, tạo vòng lặp tự sửa lỗi.
- **State:** `{ session_id, messages[], retrieved_docs[], needs_realtime: bool, inventory_data, verifier_score, risk_flag: bool, retry_count }`
- **Nodes:**
  - `CacheCheck` — tra Semantic Cache trước khi tốn token.
  - `Retrieve` — truy vấn Qdrant lấy context liên quan.
  - `ToolCall` — gọi API tồn kho real-time khi câu hỏi cần dữ liệu động.
  - `Generate` — sinh câu trả lời kèm trích nguồn.
  - `Verify` — Verifier Agent chấm Faithfulness/Relevance.
  - `RiskCheck` — đánh giá câu trả lời có chạm giá/cam kết không, quyết định gắn cờ HITL.
- **Tools:** `vector_search_tool` (query Qdrant), `inventory_api_tool` (gọi API tồn kho nội bộ), `citation_formatter` (chuẩn hóa trích nguồn + ảnh mặt bằng đính kèm).
- **Flow:**
```mermaid
graph LR
    START --> Cache{Cache Hit?}
    Cache -->|Yes| END
    Cache -->|No| Retrieve[Retrieve: Qdrant Search]
    Retrieve --> NeedRT{Cần Real-time?}
    NeedRT -->|Yes| ToolCall[Tool: Inventory API]
    NeedRT -->|No| Generate[Generate Answer]
    ToolCall --> Generate
    Generate --> Verify[Verify: Faithfulness Score]
    Verify -->|Điểm thấp| Generate
    Verify -->|Đạt| Risk{Rủi ro cam kết/giá?}
    Risk -->|Yes| HITL[Gắn cờ HITL]
    Risk -->|No| END
    HITL --> END
```
 
### 4. Database
- **Type:** MySQL.
- **Tables:** 
  - `users` (id, role, permissions)
  - `documents` (id, filename, status, permission_level, minio_path, uploaded_by, uploaded_at)
  - `document_conflicts` (doc_id_1, doc_id_2, status, resolved_by)
  - `sessions` (id, sale_id, customer_name, created_at)
  - `chat_messages` (id, session_id, role, content, citations, risk_flag, timestamp)
  - `feedback` (id, message_id, type, comment, created_at)
- **Migrations:** Alembic.
### 5. Vector Store
- **Type:** Qdrant (self-host, chỉ lưu vector embedding — không lưu file gốc, tách biệt hoàn toàn với MinIO).
- **Embeddings:** *(chưa chốt trong CLAUDE.md — đề xuất)* `text-embedding-004` (đồng bộ hệ sinh thái Gemini đang dùng cho generation) hoặc `multilingual-e5-large` nếu ưu tiên chất lượng tiếng Việt cho văn bản pháp lý/chính sách bán hàng — cùng hướng lựa chọn từng dùng ở RegWatch.
- **Purpose:** RAG — truy hồi ngữ cảnh từ bảng giá, mặt bằng, chính sách, tiện ích đã ingest; hỗ trợ payload filter theo `permission_level` để phục vụ RBAC.
## Data Flow
1. Sale gửi câu hỏi (Text/Voice) từ Frontend.
2. FastAPI route nhận request, validate input bằng Pydantic, xác thực JWT + kiểm tra Role.
3. Main Agent kiểm tra Semantic Cache — trùng câu hỏi đã cache thì trả ngay, bỏ qua các bước dưới.
4. Cache miss: Agent truy vấn Qdrant lấy context; nếu câu hỏi cần dữ liệu tồn kho, gọi Tool tới API real-time.
5. LLM (Gemini 2.5 Flash / Claude / GPT-4o) sinh câu trả lời kèm trích nguồn tài liệu.
6. Verifier Agent chấm điểm Faithfulness/Relevance; điểm thấp → bắt Main Agent sinh lại (quay về bước 5).
7. Nếu câu trả lời chạm rủi ro cam kết/giá → gắn cờ HITL, Sale phải xác nhận mới được copy gửi khách.
8. Response trả về Frontend kèm nút Feedback để Admin theo dõi chất lượng.
## Deployment Architecture
```mermaid
graph LR
    subgraph Docker Compose - Local Dev
        FE[Frontend :5173]
        BE[Backend :8000]
        DB_C[(MySQL :3306)]
        VDB[(Qdrant :6333)]
        OBJ[(MinIO :9000/9001)]
    end
    FE --> BE
    BE --> DB_C
    BE --> VDB
    BE --> OBJ
```

## Security
- API keys (LLM, MinIO, DB) lưu trong `.env`, không commit.
- Input validation qua Pydantic ở mọi endpoint.
- Rate limiting trên API endpoint, đặc biệt endpoint chat để tránh spam gọi LLM tốn chi phí.
- CORS cấu hình riêng cho domain frontend (Vercel).
- RBAC 2 lớp: chặn ở route (role SALE/ADMIN) và filter ở tầng retrieval (payload Qdrant) để phân biệt tài liệu nội bộ/công khai.
- Prompt Injection scanning bắt buộc khi ingest tài liệu — chặn file trước khi vào MinIO/Qdrant.
- HITL bắt buộc cho mọi câu trả lời có rủi ro cam kết/giá — lớp bảo vệ nghiệp vụ, không chỉ kỹ thuật.
## Design Decisions
| Decision | Choice | Reason |
|----------|--------|--------|
| Framework | FastAPI | Async, auto-docs (Swagger UI), type-safe, phù hợp pipeline nhiều tầng agent |
| Agent | LangGraph | Quản lý state linh hoạt cho Multi-Agent (Main + Verifier), dễ thêm vòng lặp retry khi Verifier chấm điểm thấp |
| Database | MySQL | Quan hệ rõ ràng giữa Users/Documents/Sessions/Feedback, dễ join cho Admin dashboard, team đã quen thuộc |
| Frontend | React + Vite (thay Next.js) | Đây là internal tool yêu cầu đăng nhập, không cần SSR/SEO; Vite cho dev/build nhanh hơn |
| Vector Store | Qdrant | Self-host đáp ứng yêu cầu bảo mật enterprise, hỗ trợ payload filtering cho RBAC tài liệu |
| Object Storage | MinIO | S3-compatible, tách file gốc khỏi vector DB, dùng để tải lại/tham chiếu khi cần |
 
