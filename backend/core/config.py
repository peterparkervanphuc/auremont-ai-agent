from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    log_level: str = "INFO"
    # One JSON object per log line (for collectors) vs. readable console text.
    # Left as None it derives from app_env — see _default_log_json below.
    log_json: bool | None = None
    # Include the Sale's question text (truncated) in sale.query audit events.
    # A switch so a compliance decision can turn it off without a code change.
    log_query_text: bool = True

    # Authentication
    secret_key: str = Field(default="dev-secret-key-change-in-production", description="Secret key for JWT signing")
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

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Vector DB (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "salesmate_documents"

    # Minimum Verifier confidence (0-1). Below this the Sale sees
    # "Không đủ thông tin, liên hệ Admin" instead of the answer.
    verifier_threshold_sale: float = 0.7

    # Object storage (MinIO) — document originals
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket_documents: str = "salesmate-documents"

    # Inventory API — real-time unit availability from the company's internal API
    inventory_api_url: str = ""
    inventory_api_key: str = ""

    # Model embedding
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768
    upload_max_bytes: int = 20 * 1024 * 1024

    @model_validator(mode="after")
    def _default_log_json(self) -> "Settings":
        """JSON logs everywhere except local development and tests.

        Explicit LOG_JSON always wins; this only fills in the unset case.
        """
        if self.log_json is None:
            self.log_json = self.app_env not in ("development", "test")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Global settings instance for import
settings = get_settings()
