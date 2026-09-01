# Worklog — Team [P-110]

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.
> Tổng hợp tự động từ lịch sử git (`git log`) — cột **Time** để trống do git không lưu giờ công thực tế, member điền tay nếu cần.

---

## 2026-07-24

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| phoenix-mentor[bot] | Khởi tạo repo từ template | ✅ Done | commit c5c8e00 | - |

**Tổng kết ngày:** Khởi tạo repository.

---

## 2026-07-25

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| lilwrx | Khởi tạo project từ template | ✅ Done | commit e28c617 | - |
| truclinh1234 | Cập nhật tên team P-110 trong JOURNAL và WORKLOG | ✅ Done | commit 37ee87d | - |
| Vinh | Thay boilerplate src/ bằng cấu trúc backend/ FastAPI | ✅ Done | commit 225ae48 | - |
| lilwrx | Cập nhật log config | ✅ Done | commit e2c43df | - |
| Vinh | Merge PR #1 (feature/Linh) | ✅ Done | commit bbf38e8 | - |

**Tổng kết ngày:** Dựng khung backend FastAPI, thiết lập cấu trúc project ban đầu.

---

## 2026-07-26

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| lilwrx | Thêm file test AI cho BTC logging | ✅ Done | commit a6c2c53 | - |
| lilwrx | Test verify ai log upload | ✅ Done | commit 22e919c | - |

**Tổng kết ngày:** Kiểm thử pipeline log AI usage.

---

## 2026-08-01

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Thêm customer portal, chatbot, live chat, HITL, inventory, admin modules + React frontend | ✅ Done | commit be6efc6 | - |
| Vinh | Sửa README cho project SalesMate AI Agent | ✅ Done | commit 4f8efe5 | - |
| Vinh | Thu gọn scope: bỏ customer portal, inventory, live chat modules | ✅ Done | commit 0c417d5 | - |
| Vinh | Dọn Qdrant client và document model | ✅ Done | commit 8dd8565 | - |
| Vinh | Dọn code thừa trong main.py và SessionList | ✅ Done | commit a254158 | - |

**Tổng kết ngày:** Dựng khung tính năng lớn (chatbot, HITL, inventory...) rồi thu hẹp lại scope MVP, dọn code thừa.

---

## 2026-08-02

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Chuẩn hóa API endpoint với prefix /api/v1, bỏ chatbot router | ✅ Done | commit 29c917f | - |
| Vinh | Thêm CLAUDE.md và .claude/ vào gitignore | ✅ Done | commit 2c559fd | - |
| Vinh | Cập nhật tài liệu kiến trúc cho thay đổi frontend/backend | ✅ Done | commit 41d1c86 | - |
| Vinh | Thêm feedback module, tab admin chat/API test, cập nhật UI/config | ✅ Done | commit 7ab5c7f | - |
| Vinh | Merge PR #2 (feature/Vinh) | ✅ Done | commit c8ca514 | - |
| Vinh | Fix ruff UP017: dùng datetime.UTC thay vì timezone.utc | ✅ Done | commit f040b08 | - |
| Vinh | Merge feature/Vinh vào develop | ✅ Done | commit 2c8c00e | - |
| Vinh | Thêm hướng dẫn chạy local dev vào README | ✅ Done | commit dde33b2 | - |

**Tổng kết ngày:** Chuẩn hóa API, bổ sung feedback module và tài liệu vận hành.

---

## 2026-08-03

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Refactor UI frontend: tổ chức lại component, tách sidebar, bỏ CSS cũ | ✅ Done | commit b247a68 | - |
| Vinh | Quản lý schema bằng Alembic thay vì create_all | ✅ Done | commit 4c895c1 | - |
| Vinh | Fix rò rỉ session ownership, thêm token refresh, ép resolve conflict | ✅ Done | commit fa1ca88 | - |
| Vinh | Fix nginx serving trong Docker, thêm gợi ý test-account ở login | ✅ Done | commit b56228a | - |
| Vinh | Thay datetime.utcnow (deprecated) bằng helper naive-UTC | ✅ Done | commit bda53de | - |
| Vinh | Thêm E2E journey tests, viết tài liệu các lớp test | ✅ Done | commit 509c84a | - |

**Tổng kết ngày:** Chuyển sang Alembic cho schema, vá lỗ hổng bảo mật session, hoàn thiện Docker/nginx và bổ sung E2E test.

---

## 2026-08-04

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Seed shared test account khi khởi động | ✅ Done | commit f0ff781 | - |
| lilwrx | Thêm document ingestion pipeline | ✅ Done | commit 55b3bc8 | - |
| lilwrx | Merge/sync remote feature/Giang | ✅ Done | commit 3a67b95 | - |
| lilwrx | Fix load ai log config không cần dotenv | ✅ Done | commit c7c18c4 | - |
| lilwrx | Thu thập Codex prompts cho ai logs | ✅ Done | commit fa8dd48 | - |
| lilwrx | Fix ghi Windows hook không kèm BOM | ✅ Done | commit 00c576a | - |
| lilwrx | Dùng trusted CA bundle khi submit ai log | ✅ Done | commit 2c38343 | - |
| lilwrx | Tránh gửi lại Codex log đã archive | ✅ Done | commit 9bdc99e | - |
| Vinh | Merge PR #3 (feature/Vinh) | ✅ Done | commit 56bbb9b | - |
| giang123 | Merge develop vào feature/Giang; merge PR #4 | ✅ Done | commits 2deaa3f, 3e4cafd | - |

**Tổng kết ngày:** Xây dựng document ingestion pipeline và hoàn thiện hệ thống AI usage logging (Codex, Windows hook, CA bundle).

---

## 2026-08-06

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| truclinh1234 | Triển khai Qdrant retrieval với RBAC filtering và reranking | ✅ Done | commit ca466a4 | - |
| truclinh1234 | Triển khai inventory lookup qua mock API | ✅ Done | commit 6a99d4d | - |
| truclinh1234 | Thêm sweep script cho Claude Code prompts (ai-log) | ✅ Done | commit aaf78eb | - |

**Tổng kết ngày:** RAG retrieval có RBAC + reranking, tích hợp inventory mock API.

---

## 2026-08-07

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Merge PR #5 (feature/Linh) | ✅ Done | commit dd05131 | - |
| Vinh | Hoàn thiện agentic RAG pipeline, nối lại chain project_id | ✅ Done | commit 1b3bf8c | - |

**Tổng kết ngày:** Hoàn thiện pipeline agentic RAG.

---

## 2026-08-09

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Cập nhật chung | ✅ Done | commit 6d4dd0c | - |
| lilwrx | Triển khai luồng LangGraph | ✅ Done | commit e26a52d | - |
| Vinh | Lưu điểm thành phần faithfulness/relevancy của Verifier | ✅ Done | commit 794f192 | - |

**Tổng kết ngày:** Thêm LangGraph flow và eval scoring cho Verifier.

---

## 2026-08-10

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| truclinh1234 | UI/UX phiên bản 2 | ✅ Done | commit 50e0fa8 | - |
| Vinh | Merge PR #6 (feature/Vinh) | ✅ Done | commit 77eb0f9 | - |

**Tổng kết ngày:** Nâng cấp UI/UX v2.

---

## 2026-08-11

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| lilwrx | Merge develop vào feature/Giang | ✅ Done | commit b4177dc | - |

**Tổng kết ngày:** Đồng bộ nhánh.

---

## 2026-08-12

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| lilwrx | Nâng cấp inventory_service và test_inventory_service | ✅ Done | commit 2442e39 | - |

**Tổng kết ngày:** Nâng cấp inventory service.

---

## 2026-08-13

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Thêm cấu hình JSON/console logging và request-id contextvar | ✅ Done | commit 1f48308 | - |
| Vinh | Middleware request-id và structured access log | ✅ Done | commit 7481d3f | - |
| Vinh | Global exception handlers với request-scoped logging | ✅ Done | commit 9670f77 | - |
| Vinh | Thay print() bằng structured logging | ✅ Done | commit 370f473 | - |
| Vinh | Log mọi silent failure path | ✅ Done | commit 6dbab58 | - |
| Vinh | Audit trail cho auth, documents, sale queries, HITL | ✅ Done | commit 271b7fb | - |
| Vinh | Test cho formatter, middleware, handlers, audit, silent failures | ✅ Done | commit 748cf15 | - |
| Vinh | Viết tài liệu log shape, audit events, env switches | ✅ Done | commit 767c0e7 | - |
| Vinh | Fix: build Qdrant client trong try block | ✅ Done | commit d47a578 | - |
| Vinh | Lưu business events xuống MySQL (audit) | ✅ Done | commit 15b9b21 | - |
| truclinh1234 | Hoàn thành UI/UX v2 | ✅ Done | commit 1f57c94 | - |
| Vinh | Merge feature/Linh vào develop | ✅ Done | commit d5bd121 | - |
| Vinh | Refactor system prompt agent cho ngắn gọn, phù hợp field | ✅ Done | commit 2e345b0 | - |
| Vinh | Fix resolve ảnh project catalogue dùng URL MinIO truy cập được từ browser | ✅ Done | commit cfd7b84 | - |
| Vinh | Dịch comment sang tiếng Anh, bỏ ảnh project khỏi git, cập nhật docs | ✅ Done | commit b96776f | - |

**Tổng kết ngày:** Ngày lớn về observability — xây dựng toàn bộ hệ thống structured logging, audit trail, exception handling; hoàn thành UI/UX v2.

---

## 2026-08-14

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Tách mỗi zone thành page riêng (/inventory/<category>/<zone>) | ✅ Done | commit 5bc122e | - |
| lilwrx | Tích hợp MockAPI inventory, thêm document update workflow, kết hợp realtime inventory + policy RAG cho sale query hỗn hợp | ✅ Done | commit c6631db | - |
| Vinh | Bảo mật: chặn deploy production dùng JWT key mặc định không an toàn | ✅ Done | commit 1904117 | - |
| Vinh | Bỏ project picker khỏi luồng tạo session | ✅ Done | commit caa8009 | - |
| lilwrx | Merge develop, resolve workflow conflicts | ✅ Done | commit b693c17 | - |
| lilwrx | Fix mockapi | ✅ Done | commit 323a864 | - |
| Vinh | Merge feature/Giang vào feature/Vinh | ✅ Done | commit 019e5bd | - |

**Tổng kết ngày:** Tích hợp inventory + RAG cho sale query hỗn hợp, vá lỗ hổng bảo mật JWT key mặc định.

---

## 2026-08-15

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Cập nhật chung | ✅ Done | commit 17df1cf | - |
| Vinh | Merge PR #12 (feature/Vinh) | ✅ Done | commit edbe026 | - |
| Vinh | Tích hợp thay đổi xuyên backend, frontend, tests | ✅ Done | commit 3ce90ab | - |
| Vinh | Merge origin/develop vào feature/Vinh | ✅ Done | commit 813613d | - |
| Vinh | Chuyển CI runner sang self-hosted | ✅ Done | commit 02d9d72 | - |
| Vinh | Merge PR #13 (develop) | ✅ Done | commit b460050 | - |
| Vinh | Fix tài liệu architecture & setup, thêm eval evidence | ✅ Done | commit 036f625 | - |

**Tổng kết ngày:** Ổn định CI (self-hosted runner), hoàn thiện tài liệu kiến trúc kèm bằng chứng eval.

---

## 2026-08-16

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| truclinh1234 | Trỏ ảnh project thẳng sang R2, thêm Render blueprint | ✅ Done | commit d9cd4a5 | - |
| truclinh1234 | Deploy | ✅ Done | commit 47a24fe | - |
| truclinh1234 | Áp lại guardrail cross-project và off-topic từ feature/Linh | ✅ Done | commit 8366d57 | - |

**Tổng kết ngày:** Triển khai deploy qua Render, dùng R2 làm nơi lưu ảnh, củng cố guardrail prompt.

---

## 2026-08-18

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| lilwrx | Business dashboard cho admin + category-aware chunking | ✅ Done | commit 582a835 | - |
| lilwrx | Merge develop vào feature/Giang | ✅ Done | commit 4086c5f | - |
| lilwrx | Fix ingestion: đóng 4 lỗ hổng khiến tài liệu sai trả lời | ✅ Done | commit 40adf07 | - |
| lilwrx | Fix conflicts: phát hiện mâu thuẫn ở tài liệu không gắn project | ✅ Done | commit 9f6e3d1 | - |

**Tổng kết ngày:** Vá lỗ hổng ingestion nghiêm trọng (trả lời sai tài liệu), thêm dashboard admin.

---

## 2026-08-19

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| truclinh1234 | Thêm customer role | ✅ Done | commit 66aa754 | - |
| Vinh | Thêm memory service, hybrid search, document reindex | ✅ Done | commit 60b14c7 | - |
| Vinh | Merge feature/Linh vào feature/Vinh | ✅ Done | commit a15bdb7 | - |
| Vinh | Thêm Cohere Rerank v3.5 cross-encoder cho retrieval quality | ✅ Done | commit 2243273 | - |
| Vinh | Cô lập rerank tests khỏi live Cohere API | ✅ Done | commit fc3a3f5 | - |
| Vinh | Nâng cấp Verifier lên 4 tiêu chí với Reflexion loop thật | ✅ Done | commit 5dec4bf | - |
| Vinh | Thêm pipeline tracing và eval flywheel | ✅ Done | commit 89659d8 | - |
| Vinh | Thêm reflection memory, ngừng lưu giá dưới dạng budget | ✅ Done | commit d6fd16c | - |

**Tổng kết ngày:** Ngày lớn về chất lượng RAG — hybrid search, Cohere rerank, Verifier 4 tiêu chí + Reflexion loop, pipeline tracing/eval flywheel.

---

## 2026-08-20

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Dọn comment, import, dead code | ✅ Done | commit 569089b | - |
| truclinh1234 | Thêm AI consultation | ✅ Done | commit a8b18ff | - |
| lilwrx | Củng cố document classification và conflict handling trong ingestion | ✅ Done | commit f60ce45 | - |

**Tổng kết ngày:** Dọn code, thêm tính năng AI consultation, siết ingestion classification/conflict.

---

## 2026-08-21

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Thêm table-aware chunking và citation y-position | ✅ Done | commit 57708d1 | - |
| Vinh | Merge luồng customer consult của feature/Linh vào feature/Vinh | ✅ Done | commit e466744 | - |
| Vinh | Fix: lesson mới không bị evict ngay khi vừa lưu | ✅ Done | commit e549f4d | - |
| Vinh | Fix: khôi phục 20 icon bị merge xóa mất khỏi Icons.tsx | ✅ Done | commit 74d695c | - |
| Vinh | Fix: xung đột alembic revision id do merge tạo ra | ✅ Done | commit ba7905e | - |
| Vinh | Dọn import không dùng sau merge | ✅ Done | commit 72bd001 | - |
| Vinh | Merge ingestion hardening của feature/Giang vào feature/Vinh | ✅ Done | commit ee02581 | - |
| Vinh | Cập nhật chung | ✅ Done | commit bfccb93 | - |
| truclinh1234 | Trigger Vercel deploy | ✅ Done | commit a215829 | - |
| Vinh | Thêm follow-up question gợi ý, tự đính kèm ảnh, golden RAG eval, refresh doc | ✅ Done | commit f44e750 | - |
| Vinh | Merge feature/Vinh vào develop | ✅ Done | commit 9814ce5 | - |
| truclinh1234 | Fix: index document_id trong Qdrant để tránh lỗi 503 khi xóa document | ✅ Done | commit 1f1b731 | - |

**Tổng kết ngày:** Xử lý nhiều xung đột do merge (icon, alembic revision), thêm table-aware chunking, golden RAG eval, và các fix ổn định Qdrant.

---

## 2026-08-22

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| lilwrx | Mở rộng dashboard, siết document governance (admin) | ✅ Done | commit e1da424 | - |
| Vinh | Cải thiện độ bao phủ tiêu chí chatbot bất động sản | ✅ Done | commit 0c2d7d0 | - |
| Vinh | Merge origin/develop vào feature/Vinh | ✅ Done | commit 763530d | - |
| truclinh1234 | Fix xử lý giá trong customer-chat, RAG visibility, thêm listing card | ✅ Done | commit ca10c82 | - |
| truclinh1234 | Merge origin/develop vào feature/Linh | ✅ Done | commit 5b45ac3 | - |
| truclinh1234 | Style: fix spacing import block trong catalog_context_service.py | ✅ Done | commit c2bb0d8 | - |
| truclinh1234 | Listing card hiển thị nhiều ảnh thật + tiện ích | ✅ Done | commit b202a89 | - |
| lilwrx | Merge origin/develop vào feature/Giang | ✅ Done | commit 9dc6619 | - |
| lilwrx | Củng cố document governance và observability (admin) | ✅ Done | commit da250e0 | - |
| lilwrx | Nâng cấp luồng ingestion và admin dashboard | ✅ Done | commit 575682e | - |

**Tổng kết ngày:** Tập trung vào trải nghiệm customer-chat (listing card, giá, RAG visibility) và siết document governance phía admin.

---

## 2026-08-23

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| truclinh1234 | v3 | ✅ Done | commit a023fbd | - |
| Vinh | Cập nhật chung | ✅ Done | commit 0af8545 | - |
| Vinh | Merge feature/Giang vào feature/Vinh | ✅ Done | commit 9ca08e9 | - |
| Vinh | Fix migrations: thêm merge revision nối 2 alembic head | ✅ Done | commit 48f8a29 | - |
| Vinh | Merge feature/Linh vào feature/Vinh | ✅ Done | commit 92aefa0 | - |
| Vinh | Xóa tmp snapshot lạc, ignore tmp/ | ✅ Done | commit 50945c6 | - |
| peterparkervanphuc | Cập nhật README, JOURNAL, thêm project assets | ✅ Done | commit 6440bf2 | - |
| Dao Ngoc Duy | Merge PR #18 (docs/readme-journal) | ✅ Done | commit 1eddd24 | - |
| truclinh1234 | Merge origin/main vào feature/Linh | ✅ Done | commit f1b4b15 | - |
| truclinh1234 | v4 | ✅ Done | commit 7aeab87 | - |

**Tổng kết ngày:** Gộp nhiều nhánh feature (nhiều alembic head conflict), cập nhật tài liệu dự án và assets.

---

## 2026-08-24

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Nguyễn Darwinn | Merge feature/Linh vào develop | ✅ Done | commit f83585c | - |
| Nguyễn Darwinn | Fix semantic cache hoạt động được, dedupe reflection lessons, trace rerank fallback | ✅ Done | commit 4ba8be3 | - |
| Nguyễn Darwinn | Dọn type checker sạch, ép formatting trong CI | ✅ Done | commit 6fbd99e | - |
| Nguyễn Darwinn | Thêm các file chuẩn open-source repo cần có | ✅ Done | commit b081bfd | - |
| Nguyễn Darwinn | Refactor: tách build_prompt thành các section | ✅ Done | commit f6c9713 | - |
| Nguyễn Darwinn | Refactor: tách RBAC filter và point mapping khỏi retrieve | ✅ Done | commit 3a3099f | - |
| truclinh1234 | Trigger Vercel deploy | ✅ Done | commit 83e5131 | - |
| truclinh1234 | Thêm SPA rewrite để URL trực tiếp/refresh không 404 trên Vercel | ✅ Done | commit 3a1add3 | - |
| truclinh1234 | Index category trên collection documents, project_id/visibility trên QA cache | ✅ Done | commit be641f0 | - |
| truclinh1234 | Fix: ngừng lặp bullet inventory realtime trong câu trả lời Sale | ✅ Done | commit a8f3608 | - |
| Vinh | Đồng bộ sơ đồ kiến trúc với pipeline node và cấu trúc thư mục | ✅ Done | commit 4df32ae | - |
| Vinh | Fix seed-data: đồng bộ lại manifest ảnh project với nội dung R2 bucket thật | ✅ Done | commit 941f073 | - |
| Vinh | Merge feature/Vinh (docs sync + fix R2 manifest) vào develop | ✅ Done | commit 163d1b3 | - |
| truclinh1234 | Merge origin/develop vào feature/Linh | ✅ Done | commit cfa9538 | - |

**Tổng kết ngày:** Refactor lớn (build_prompt, RBAC filter), fix semantic cache, siết CI type-check/format, fix deploy Vercel (SPA rewrite, 404).

---

## 2026-08-25

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Giới hạn shared API project theo alias phân khu (subdivision) | ✅ Done | commit 7e6ee4d | - |
| truclinh1234 | 25_258 | ✅ Done | commit 25facea | - |
| Vinh | Merge origin/feature/Linh vào develop | ✅ Done | commit 5147322 | - |
| Vinh | Tách customer AI chat và live-Sale handoff thành session row riêng | ✅ Done | commit 4a1fffd | - |
| Vinh | Fix: khớp ảnh trả lời theo folder category MinIO thay vì chỉ tên file | ✅ Done | commit 562dc68 | - |
| Vinh | Fix: ngừng lộ cơ chế lookup và claim hết hàng sai khi inventory unavailable | ✅ Done | commit 81418a3 | - |
| Vinh | Fix: nâng độ tương phản chữ Sale-bubble đạt WCAG AA, bỏ 2 mục catalogue chết | ✅ Done | commit 2cf7a7e | - |
| Vinh | Mở rộng .gitignore, bật mặc định hybrid search/rerank/tracing | ✅ Done | commit 15d8d03 | - |
| truclinh1234 | Trigger Vercel deploy | ✅ Done | commit 8821f37 | - |

**Tổng kết ngày:** Tách rõ luồng session AI chat vs Sale handoff, vá lỗi bảo mật thông tin (lộ cơ chế lookup), cải thiện accessibility (WCAG AA).

---

## 2026-08-26

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| lilwrx | Thêm tóm tắt handoff riêng tư cho AI customer | ✅ Done | commit de83d0b | - |
| Vinh | Thêm batch DeepEval offline chạy trên golden dataset | ✅ Done | commit e663656 | - |
| truclinh1234 | Merge origin/develop vào feature/Linh | ✅ Done | commit c155e24 | - |
| Vinh | Hybrid lead scoring + siết eval/guardrail cho answer-quality flywheel | ✅ Done | commit 6c1eac5 | - |

**Tổng kết ngày:** Xây dựng batch eval offline (DeepEval + golden dataset) và hybrid lead scoring.

---

## 2026-08-27

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| truclinh1234 | Fix chat history | ✅ Done | commit feefaeb | - |
| Vinh | Bỏ comment giải thích khỏi backend/tests, thêm test sửa unit-count | ✅ Done | commit fc6defa | - |
| Vinh | Merge feature/Linh vào develop | ✅ Done | commit 34a6f20 | - |
| Vinh | Thu hẹp kiểu optional customer_id và scored_at cho mypy | ✅ Done | commit dedd458 | - |
| lilwrx | Thêm ingestion tin tức chính thức và public feed | ✅ Done | commit 19c8a40 | - |

**Tổng kết ngày:** Fix chat history, thêm tính năng news ingestion + public feed.

---

## 2026-08-28

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| lilwrx | Fix ocp 1 2 3 news | ✅ Done | commit 0a70087 | - |
| lilwrx | Merge develop mới nhất, không làm mất tính năng feature | ✅ Done | commit acaf468 | - |
| Vinh | Merge feature/Giang vào develop | ✅ Done | commit c7f826f | - |
| Vinh | Merge origin/develop vào develop | ✅ Done | commit 481c23b | - |
| giang123 | Merge develop vào feature/Giang; merge PR #19 | ✅ Done | commits 9078b35, cddacf9 | - |

**Tổng kết ngày:** Ổn định tính năng news, dọn merge giữa các nhánh feature/Giang và develop.

---

## 2026-08-29

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| truclinh1234 | Chỉnh màu sắc Admin | ✅ Done | commit 257ed96 | - |
| truclinh1234 | Fix UI text | ✅ Done | commit d04aa12 | - |
| truclinh1234 | Tắt section News (coming-soon), fix ảnh Shophouse | ✅ Done | commit 1a0fdce | - |
| truclinh1234 | Thêm dynamic chat background, nhấn mạnh nút clear-history | ✅ Done | commit ab2d4a4 | - |
| truclinh1234 | Thêm dynamic background và cursor particles cho mọi trang chat | ✅ Done | commit b308746 | - |
| lilwrx | Thêm reviewed news và document classification nhiều section | ✅ Done | commit ebce8d6 | - |
| lilwrx | Merge origin/feature/Giang vào feature/Giang | ✅ Done | commit a583197 | - |
| lilwrx | Fix merge: hòa giải migrations và Beverly gallery manifest | ✅ Done | commit d6f2334 | - |

**Tổng kết ngày:** Hoàn thiện UI chat (background động, particles, dọn nút clear-history) và bổ sung phân loại tài liệu nhiều section + tin tức đã duyệt; xử lý xong conflict merge nhánh feature/Giang.

---

## 2026-08-30

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Merge feature/Giang vào develop | ✅ Done | commit f8e4dc4 | - |
| Vinh | Cải thiện độ ổn định DeepEval, fix News navbar, ổn định test | ✅ Done | commit 934a85f | - |
| Vinh | Revert tạm thay đổi workflow do token thiếu quyền `workflow` | ✅ Done | commit 37a3b9e | - |
| Vinh | Fix CI: endpoint trùng lặp sau merge, 19 lỗi mypy, formatting | ✅ Done | commit c8587c6 | - |
| Vinh | Thêm luồng subscription B2B và daily AI budget cho public chat | ✅ Done | commit 754912f | - |
| Vinh | Dọn inline comment thừa, thêm tùy chọn "giữ cả hai" khi resolve conflict | ✅ Done | commit 5358ce4 | - |
| Vinh | Đồng bộ document_categories lên Qdrant mỗi lần ghi metadata | ✅ Done | commit c0ede4d | - |
| Vinh | Fix Docker build args, bật coverage gate và TS strict mode | ✅ Done | commit 556d9a3 | - |
| Vinh | Ngừng gitignore .dockerignore để track frontend/.dockerignore | ✅ Done | commit 5662e88 | - |
| Vinh | Revert thay đổi coverage-gate trong ci.yml (token thiếu quyền workflow) | ✅ Done | commit 6782380 | - |
| Vinh | Pin lại behavior parser giá VND hiện tại trước khi hợp nhất | ✅ Done | commit 5a236ef | - |
| Vinh | Thêm backend/utils/vnd.py: gộp 1 parser tiền VND duy nhất | ✅ Done | commit 66c7a00 | - |

**Tổng kết ngày:** Ngày làm việc nặng về ổn định hệ thống: dọn CI/CD (mypy, coverage gate, Docker), hợp nhất parser tiền VND, đồng bộ metadata Qdrant, và bổ sung tính năng subscription B2B + AI budget.

---

## 2026-08-31

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Route tất cả 5 parser VND qua backend/utils/vnd.py | ✅ Done | commit 53659d9 | - |
| Vinh | Chuyển db_session vào conftest.py, xóa 28 fixture trùng lặp | ✅ Done | commit 07cfeda | - |
| Vinh | Merge refactor/phase-1-bugs-and-quickwins vào develop | ✅ Done | commit 5e75dc7 | - |
| Vinh | Cập nhật architecture doc và README cho rõ ràng, chính xác | ✅ Done | commit e6515ab | - |
| Vinh | Refactor file config, cải thiện tài liệu cho nhất quán | ✅ Done | commit c70c717 | - |
| Vinh | Thêm mục Authors vào README với thông tin thành viên nhóm | ✅ Done | commit 42b6034 | - |
| Vinh | Xóa file chết và tham chiếu doc lỗi thời | ✅ Done | commit 4bd105b | - |
| Vinh | Route Gemini theo tier task, cải thiện format câu trả lời | ✅ Done | commit 7e8e4a3 | - |
| Vinh | Fix eval graders, citation scope, ingestion và dismiss conflict | ✅ Done | commit f2d0ecd | - |
| Vinh | Route document classification, conflict judging và summaries khỏi answer model | ✅ Done | commit a479758 | - |

**Tổng kết ngày:** Dọn dẹp lớn: hợp nhất parser VND, gộp test fixtures, cập nhật tài liệu kiến trúc/README, tách routing model cho từng loại tác vụ (classification/judging/summary khỏi answer model), fix eval graders.

---

## 2026-09-01

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Vinh | Apply ruff format để fix lỗi CI lint-and-test | ✅ Done | commit 0852f02 | - |

**Tổng kết ngày:** Fix nhanh lỗi formatting chặn CI.

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
