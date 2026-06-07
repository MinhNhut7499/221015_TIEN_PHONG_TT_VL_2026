"""Application configuration.

All values are loaded from the .env file at startup via pydantic-settings.
Never hard-code secrets — add them to .env instead.
"""
from functools import lru_cache
from typing import List

from pydantic import field_validator
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object for the entire application.

    Fields map directly to environment variables defined in .env.
    pydantic-settings handles type coercion automatically.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "Architecture AI API"
    APP_ENV: str = "development"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    ADMIN_EMAILS: str = ""

    # ── Security / JWT ────────────────────────────────────────────────────────
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Google OAuth 2.0 ──────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # ── LLM (legacy simple flow) ──────────────────────────────────────────────
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gemini-pro-vision"

    # ── LLM Pipeline — API keys ───────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # ── LLM Pipeline — tuning ─────────────────────────────────────────────────
    PIPELINE_MAX_PER_TYPE: int = 2
    PIPELINE_MAX_COMPONENTS: int = 10
    PIPELINE_AGENT_TIMEOUT_SEC: int = 30
    # Retry on transient LLM errors (503 overloaded / 429 rate limit). Total
    # backoff stays well under PIPELINE_AGENT_TIMEOUT_SEC so asyncio.wait_for
    # does not cut a call mid-retry.
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_BASE_DELAY_SEC: float = 0.5

    # ── Trained models ────────────────────────────────────────────────────────
    # Empty paths → Mock services (for development / tests).
    # When set, the orchestrator swaps in the real inference service.
    YOLO_DETECTION_MODEL_PATH: str = ""   # best.pt — YOLOv8s component detector
    MATERIAL_MODEL_PATH: str = ""         # YOLOv8s-cls material (not trained yet)
    # Material classifier backend: "mock" (deterministic, default) or "gemini"
    # (reuse the pipeline's GeminiService to classify material from the image).
    MATERIAL_CLASSIFIER: str = "mock"
    STYLE_HEAD_MODEL_PATH: str = ""       # style_head.pt — ResNet50 style prior head
    YOLO_CONF_THRESHOLD: float = 0.25     # min detection confidence to keep
    ENABLE_GRADCAM: bool = True           # populate GlobalFeatureOutput.gradcam_b64 (real service only)
    # Soften/sharpen the ResNet style prior: softmax(logits / T). T>1 = softer
    # (less over-confident). Fit on a validation set (see scripts/train_fuser.py).
    STYLE_HEAD_TEMPERATURE: float = 1.0

    # ── Numeric fusion (anchor + LLM-down fallback) ───────────────────────────
    # Attribute is a tie-breaker → small weight. votes + CNN prior are primary.
    FUSION_WEIGHT_VOTES: float = 0.45
    FUSION_WEIGHT_PRIOR: float = 0.45
    FUSION_WEIGHT_ATTRIBUTE: float = 0.10
    # Learned fuser (overrides numeric_fuse when present). Empty → numeric_fuse.
    FUSER_MODEL_PATH: str = ""

    # ── Uncertainty / abstention ──────────────────────────────────────────────
    # Below either bound → mark result uncertain and return top-K candidates.
    # UNCERTAINTY_CONF_MIN (max-prob threshold) is set from a risk-coverage sweep
    # on validation once the learned fuser exists; the margin/entropy bounds are
    # the pre-fuser heuristic still used in the LLM-fusion path.
    UNCERTAINTY_MARGIN_MIN: float = 0.15
    UNCERTAINTY_ENTROPY_MAX: float = 1.6
    UNCERTAINTY_CONF_MIN: float = 0.0     # 0 disables the max-prob gate
    UNCERTAINTY_TOP_K: int = 3
    # Translate the final narrative (explanation/evidence/composition) into
    # Vietnamese via one extra text-LLM call after Agent 7. Disable to skip the
    # added latency/cost.
    ENABLE_BILINGUAL: bool = True

    # ── Database — connection ─────────────────────────────────────────────────
    DB_HOST: str = "localhost"
    DB_PORT: int = 1433
    DB_NAME: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_ENCRYPT: bool = True
    DB_TRUST_SERVER_CERT: bool = False
    DB_ODBC_DRIVER: str = "ODBC Driver 17 for SQL Server"

    # ── Database — connection pool ────────────────────────────────────────────
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # ── File Upload ───────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "utils/upload_temp"
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: str = "jpg,jpeg,png,webp"

    # ── Derived helpers (read-only properties) ────────────────────────────────
    @property
    def admin_emails_list(self) -> List[str]:
        """Return ADMIN_EMAILS parsed as a list of lowercase email strings."""
        return [e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()]

    @property
    def allowed_origins_list(self) -> List[str]:
        """Return ALLOWED_ORIGINS parsed as a list of origin strings."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_extensions_list(self) -> List[str]:
        """Return ALLOWED_EXTENSIONS parsed as a lowercase list."""
        return [e.strip().lower() for e in self.ALLOWED_EXTENSIONS.split(",") if e.strip()]

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_not_be_empty(cls, value: str) -> str:
        """Reject an empty or placeholder SECRET_KEY at startup."""
        if not value or value == "changeme":
            raise ValueError("SECRET_KEY must be set to a strong random value in .env")
        return value


@lru_cache()
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()


settings: Settings = get_settings()
