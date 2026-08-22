from functools import lru_cache
from typing import ClassVar, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments that are NOT production. Anything outside this set is treated as
# production, so security checks fail closed on an unrecognised APP_ENV.
_NON_PRODUCTION_ENVS = frozenset({"development", "dev", "test", "testing", "local"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Project"
    app_env: str = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    # Business dashboards group UTC-naive database timestamps by the team's
    # local calendar day. Keep this configurable for deployments in other regions.
    business_timezone: str = "Asia/Bangkok"
    log_level: str = "INFO"
    # None = auto-select: JSON in production/staging (machine-readable), plain
    # text in dev (human-readable). Set LOG_JSON=true/false to force one mode
    # regardless of environment.
    log_json: bool | None = None
    # Logs the first 200 characters of a Sale's question to the audit log. This is
    # the single most valuable field when reproducing a wrong answer, and it is
    # text the Sale typed, not customer PII. Still toggleable without a code change.
    log_query_text: bool = True

    # Authentication
    # The default is a PUBLIC constant, usable only outside production. `_reject_insecure_secret_key`
    # below refuses to start a production app that still carries it — anyone reading this repository
    # could otherwise mint valid admin tokens against a real deployment.
    DEFAULT_INSECURE_SECRET_KEY: ClassVar[str] = "dev-secret-key-change-in-production"
    secret_key: str = Field(default=DEFAULT_INSECURE_SECRET_KEY, description="Secret key for JWT signing")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Database (optional - fill in if using relational DB)
    database_url: str = ""

    # LLM (optional - fill in with your LLM provider)
    llm_api_key: str = ""
    llm_model: str = ""

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    # A classification is published without human review only when the model both
    # declines to request review and reaches this confidence.  Keep the threshold in
    # configuration so deployments can tighten it after evaluating their own corpus.
    classification_auto_approve_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    # Production-safe default: the LLM only proposes metadata. Chunking, embedding and
    # retrieval publication begin after an Admin confirms/corrects that proposal.
    classification_require_admin_approval_before_indexing: bool = True
    # Hybrid conflict detection keeps deterministic comparisons for exact numeric/text
    # changes and adds an LLM judge for paraphrases and cross-category business claims.
    # The judge runs before the MySQL advisory lock; only grounded structured evidence
    # is persisted while the lock is held.
    semantic_conflict_detection_enabled: bool = True
    semantic_conflict_fail_closed: bool = True
    semantic_conflict_min_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    semantic_conflict_max_candidates: int = Field(default=40, ge=1, le=200)
    semantic_conflict_max_chars_per_document: int = Field(default=48_000, ge=4_000, le=60_000)
    semantic_conflict_sample_segments: int = Field(default=5, ge=3, le=7)
    semantic_conflict_max_facts_per_document: int = Field(default=200, ge=1, le=500)
    semantic_conflict_max_fact_chars_per_document: int = Field(default=32_000, ge=1_000, le=100_000)

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Vector DB (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "salesmate_documents"
    # Bound vector-store latency on the interactive chat path. Qdrant's Python client
    # otherwise inherits a comparatively generous transport default, which can leave a
    # Sale staring at a request that will ultimately be degraded anyway.
    qdrant_timeout_seconds: int = Field(default=5, ge=1, le=60)

    # Hybrid retrieval: BM25 keyword search alongside the dense vector search, fused by
    # Qdrant's own RRF. Off by default because it requires the named dense+sparse
    # collection schema — turn it on only once every document has been re-indexed
    # (POST /documents/{id}/reindex), and turn it back off to fall straight back to
    # dense-only without a code change.
    hybrid_search_enabled: bool = False
    sparse_model_name: str = "Qdrant/bm25"

    # Reranking (Cohere Rerank v3.5, hosted). A cross-encoder scores query+passage
    # together and is far more accurate than the identifier-overlap heuristic it
    # replaces, at the cost of one network call per question. Hosted rather than a
    # self-hosted cross-encoder (e.g. BGE-reranker-v2-m3) because the backend runs on
    # Render's free tier — loading a few-hundred-MB model at cold start risks OOM
    # there. Off by default so a missing API key never breaks retrieval; `rag_service`
    # falls back to the identifier heuristic whenever this is disabled or fails.
    rerank_enabled: bool = False
    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-v3.5"
    cohere_rerank_timeout_seconds: float = Field(default=2.5, gt=0, le=30)

    # Context selection runs after retrieval/reranking. It keeps the prompt bounded and
    # removes overlapping chunks from the same source before they consume several of the
    # limited context slots. Values are character-based because chunking is character-
    # based too; this remains provider/tokenizer independent.
    rag_max_context_chars: int = Field(default=12_000, ge=1_000, le=100_000)
    rag_duplicate_similarity_threshold: float = Field(default=0.88, ge=0.5, le=1.0)

    # Pipeline tracing: one JSONL record per question holding every routing decision,
    # tool call and retry. Separate from the audit log, which keeps one business row per
    # request in MySQL — see backend/core/tracing.py for why they are not the same sink.
    # Off by default: it writes to local disk, which is ephemeral on Render and of no use
    # in production; turn it on while gathering runs to build an eval set from.
    tracing_enabled: bool = False
    trace_file: str = "eval/runs.jsonl"
    # Durable operational metrics are stored in MySQL and power the Admin dashboard.
    # This is independent from TRACING_ENABLED: JSONL traces are an optional eval/debug
    # export, while dashboard metrics must survive a container rebuild.
    observability_metrics_enabled: bool = False
    # Used only by the Admin observability dashboard. Defaults to zero instead of
    # baking a provider price into the app: model pricing changes and deployments
    # can have negotiated rates. Configure both values to enable cost estimates.
    token_input_cost_per_million_usd: float = Field(default=0.0, ge=0)
    token_output_cost_per_million_usd: float = Field(default=0.0, ge=0)
    admin_presence_window_minutes: int = Field(default=15, ge=1, le=1440)

    # Long-term memory (Redis). Ho so ghi nho theo tung nguoi dung — KHONG phai
    # nguon su that: Redis chet thi pipeline van tra loi day du, chi mat ca nhan hoa.
    # De trong de tat han tinh nang (vi du khi chay test hoac deploy khong co Redis).
    redis_url: str = "redis://localhost:6379/0"

    # Ho so ngu quen sau 90 ngay khong tuong tac: so thich bat dong san cu qua thi
    # gay hieu nham nhieu hon la giup.
    memory_ttl_seconds: int = 60 * 60 * 24 * 90

    # Reflection memory: bai hoc agent rut ra tu chinh loi cua no (backend/services/
    # reflection_memory.py). Bat de agent thoi lap lai cung mot loi o cac phien khac
    # nhau; tat de quay ve hanh vi khong hoc gi giua cac cau hoi.
    reflection_memory_enabled: bool = True
    # Ngan hon memory_ttl_seconds (30 ngay): mot bai hoc rut ra tu bo tai lieu cu se sai
    # sau khi Admin thay tai lieu, nen no phai tu het han thay vi bam mai vao prompt.
    reflection_ttl_seconds: int = 60 * 60 * 24 * 30

    # Tieu chi tim can tich luy qua nhieu luot cua mot phien (backend/services/
    # search_criteria.py). Bat de "giu nguyen dieu kien, tang gia len 5 ty" khong lam mat
    # cac tieu chi da neu truoc do; tat de quay ve hanh vi stateless: moi luot parse lai
    # tu dau chi tu cau hoi hien tai.
    search_criteria_enabled: bool = True
    # 24 gio, ngan hon han memory_ttl_seconds (90 ngay): tieu chi tim kiem la bo nho lam
    # viec cua MOT cuoc tu van, khong phai so thich lau dai cua mot nguoi. Mot bo loc cua
    # phien hom qua song lai hom nay se am tham an di nhung can khach dang muon xem —
    # loi nay khong co trieu chung nao ben ngoai, nen TTL phai ngan.
    search_criteria_ttl_seconds: int = 60 * 60 * 24

    # Minimum Verifier confidence (0-1). Below this the Sale sees the
    # "Không đủ thông tin, liên hệ Admin" notice instead of the answer.
    verifier_threshold_sale: float = 0.7

    # There is deliberately no "documents must be approved before they answer" setting here.
    # An uploaded document is retrievable straight away: what protects an answer is the
    # visibility tier (a customer never sees an internal document), the Verifier's
    # faithfulness score, and the HITL card in front of anything price- or
    # commitment-related. Correctness exclusions (duplicate, conflicting, expired) run off
    # `is_current`, not off review — see rag_service's retrieval filter.

    # Object storage (MinIO) — document originals
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket_documents: str = "salesmate-documents"
    minio_bucket_project_images: str = "project-images"
    # Host:port the BROWSER uses to fetch public objects (project images).
    # `minio_endpoint` is how the backend reaches MinIO — inside Docker that is
    # the service name `minio:9000`, which no browser can resolve. Public image
    # URLs are rendered by the frontend, so they must use a host-reachable
    # address. Left blank it falls back to minio_endpoint, which is correct when
    # running the backend outside Docker.
    minio_public_endpoint: str = ""
    # Base URL of the bucket/CDN holding the original project images (~58 MB, not
    # checked into git). On startup the backend downloads <base_url>/<path> for
    # each entry in seed-data/project_images_manifest.json into MinIO. Left blank,
    # the image-loading step is skipped — the catalogue still works, minus images.
    project_images_base_url: str = ""
    # URL of a single .tar.gz archive holding all project images (e.g. GitHub
    # Releases). Preferred over project_images_base_url: one request instead of ~180.
    project_images_archive_url: str = ""
    # Auto-loads demo data (images + project catalogue) on startup if the DB is
    # still empty. Enabled so `docker compose up` works out of the box, with no
    # manual script to run. Set to false once an environment has real data.
    auto_load_demo_data: bool = True

    # Inventory API — real-time unit availability from the company's internal API
    inventory_api_url: str = ""
    inventory_api_key: str = ""
    # Bridges two different project-id namespaces. The `projects` table is keyed by
    # catalogue slug (`the-sapphire`, `vinhomes-ocean-park`), while the inventory API keys
    # units by its own project code (`ocp1`) — a slug sent straight through
    # returns 404 and the Sale sees "Tạm thời không tra được tồn kho" for every project.
    #
    # Format: comma-separated `slug=code` pairs. `*=code` is the catch-all, used for any
    # slug not listed and for sessions carrying no project at all (the session flow no
    # longer asks the Sale to pick one). Left blank, the slug is passed through unchanged,
    # which is what a production API keyed by the same slugs would want.
    inventory_project_map: str = ""

    # Model embedding
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768
    upload_max_bytes: int = 20 * 1024 * 1024
    # Prompt-injection screening for uploaded documents. The balanced default only
    # quarantines contextual, high-confidence instructions; standalone security terms are
    # retained as Admin-visible warnings. Set to "warning" for fail-closed deployments or
    # "disabled" only when another document-security layer is enforced upstream.
    document_security_block_threshold: Literal["warning", "high_risk", "disabled"] = "high_risk"
    document_security_max_findings: int = Field(default=20, ge=1, le=200)
    document_security_excerpt_context_chars: int = Field(default=80, ge=20, le=500)

    # Customer chat (public/anonymous flow)
    # How many questions an anonymous visitor gets before the register/login gate blocks
    # the next one outright (no LLM call spent on the blocked turn).
    customer_anonymous_turn_limit: int = 4
    # Per-IP throttle on the unauthenticated customer-chat endpoints (anonymous session
    # creation, anonymous ask) — see backend/core/rate_limit.py.
    anonymous_rate_limit_per_window: int = 20
    anonymous_rate_limit_window_seconds: int = 300
    # Number of reverse proxies in front of the app (Render, nginx, a load balancer). While
    # this is 0 the throttle uses the socket peer address and ignores X-Forwarded-For, which
    # any client can set — trusting that header unconditionally would let one visitor forge a
    # fresh IP per request and bypass the limit entirely. Set it to the real hop count when
    # deploying behind proxies, otherwise every visitor arrives as the proxy's address and
    # they all share one bucket. See backend/core/rate_limit.py.
    trusted_proxy_count: int = 0

    @property
    def is_production(self) -> bool:
        """True outside the known development/test environments.

        Phrased as a denylist so an unrecognised APP_ENV (a typo, a new staging name)
        is treated as production and gets the stricter checks, never the laxer ones.
        """
        return self.app_env.lower() not in _NON_PRODUCTION_ENVS

    @model_validator(mode="after")
    def _resolve_log_json(self) -> "Settings":
        if self.log_json is None:
            # JSON in production (machine-readable), plain text in dev (human-readable).
            self.log_json = self.is_production
        return self

    @model_validator(mode="after")
    def _reject_insecure_secret_key(self) -> "Settings":
        """Refuse to boot a production app signing JWTs with the public default key.

        Failing at startup is deliberate: the alternative is a deployment that looks
        healthy while every token it issues can be forged by anyone with this source.
        """
        if self.is_production and self.secret_key == self.DEFAULT_INSECURE_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set to a unique value when APP_ENV is not a development "
                'environment. Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Global settings instance for import
settings = get_settings()
