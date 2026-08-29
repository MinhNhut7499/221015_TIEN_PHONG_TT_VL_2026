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
    # Hybrid mobile app (Cloud-Sync Polling) login. The Flutter app opens this
    # backend's flutter login endpoint in a Chrome Custom Tab; Google redirects
    # back to GOOGLE_FLUTTER_REDIRECT_URI, which stores the token in the
    # LoginSessions table so the web (running in the app's WebView) can poll for
    # it. This URI MUST be registered in Google Cloud Console (Authorized
    # redirect URIs) alongside GOOGLE_REDIRECT_URI.
    GOOGLE_FLUTTER_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback/flutter"
    # How long a pending hybrid-login session stays valid before it expires and
    # is cleaned up (one-time use; the web polls within this window).
    LOGIN_SESSION_TTL_MIN: int = 10

    # ── Email / SMTP (password-reset emails) ──────────────────────────────────
    # A SINGLE system "outbox" account that sends reset links to ANY user — not
    # a per-user setting. Leave SMTP_HOST empty to disable email sending (the
    # forgot-password endpoint still returns a generic 200, it just logs that no
    # mail was sent). For Gmail: enable 2FA, create an App Password, and use
    # SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_USE_TLS=true.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""          # e.g. "ArchiAI <no-reply@example.com>"
    SMTP_USE_TLS: bool = True
    # Base URL of the React frontend, used to build the password-reset link
    # ({FRONTEND_BASE_URL}/reset-password?token=...).
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    # How long a password-reset link stays valid.
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    # How long an email-verification link stays valid (registration is only
    # completed when the user clicks it, proving the email is real/reachable).
    EMAIL_VERIFY_EXPIRE_MINUTES: int = 1440

    # ── LLM (legacy simple flow) ──────────────────────────────────────────────
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gemini-pro-vision"

    # ── LLM Pipeline — API keys ───────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.4-mini"
    # xAI Grok — third VISION panel judge (OpenAI-compatible API). Lets the panel
    # be 3 symmetric image-seeing judges (Gemini/OpenAI/Grok) instead of having
    # one text-only judge, so equal judge weights are justified.
    XAI_API_KEY: str = ""
    XAI_BASE_URL: str = "https://api.x.ai/v1"
    # Fast non-reasoning vision Grok (matches Gemini Flash / GPT-mini judges).
    # Verified present in the xAI model list; "grok-4-vision" does NOT exist.
    GROK_MODEL: str = "grok-4.20-0309-non-reasoning"

    # ── LLM Pipeline — tuning ─────────────────────────────────────────────────
    PIPELINE_AGENT_TIMEOUT_SEC: int = 60
    # Retry on transient LLM errors (503 overloaded / 429 rate limit). Total
    # backoff stays well under PIPELINE_AGENT_TIMEOUT_SEC so asyncio.wait_for
    # does not cut a call mid-retry.
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_BASE_DELAY_SEC: float = 0.5
    # Provider circuit breaker (A4b): after this many consecutive failures a
    # provider's circuit "opens" and its calls fail fast for CIRCUIT_COOLDOWN_SEC
    # — so a long outage falls straight through to a backup provider instead of
    # wasting a full timeout on every call (matters most across a batch run).
    CIRCUIT_FAIL_THRESHOLD: int = 3
    CIRCUIT_COOLDOWN_SEC: float = 60.0

    # ── Open-vocabulary knowledge base / retrieval ────────────────────────────
    # KB file driving the open-vocabulary recognition (add a style = add a row).
    STYLE_KB_PATH: str = "chatbot/knowledge/styles.json"
    # How many candidate styles the KB-grounding step passes to the judge panel.
    # Raised from 8 → 12 so the three recall channels (voted names, feature
    # retrieval, family expansion) do not crowd each other out (Phase 1).
    RETRIEVAL_TOP_K: int = 12
    # How many feature-retrieved entries the feature channel contributes to the
    # candidate set (Phase 1b: styles whose defining features match the observed
    # evidence even if the VLM never named them).
    FEATURE_RETRIEVAL_TOP_N: int = 6
    # Recall strategy switch (for reproducible before/after evaluation):
    #   True  → multichannel candidates (voted names + feature retrieval + family
    #           expansion), the Phase 1 improvement.
    #   False → legacy voted-name-only candidates (the original baseline).
    # Set False (with RETRIEVAL_TOP_K=8) to reproduce the pre-Phase-1 baseline.
    RECALL_MULTICHANNEL: bool = True
    # Recall escape hatch: when a judge/arbiter names a style OUTSIDE the KB
    # candidate set, accept it only if it matches an existing KB entry
    # (StyleKbService.match) and add it to the allowed set. Lifts the candidate
    # ceiling without polluting the KB. False = legacy hard candidate ceiling.
    RECALL_ESCAPE_HATCH: bool = True
    # Extra safety on the escape hatch: an out-of-candidate style must ALSO be
    # backed by the observed evidence — its KB defining-features must overlap
    # what Agent A actually described (StyleKbService.retrieve_by_features) —
    # before it is admitted. Stops the arbiter naming a KB style the image shows
    # no sign of. False = name match alone is enough (the A3 behaviour).
    RECALL_ESCAPE_REQUIRE_EVIDENCE: bool = True
    # Stage A is run once per provider key listed here (repeats allowed), in
    # parallel; their proposed styles are voted by frequency. Set to "gemini" to
    # revert to a single extraction call. Providers: "gemini", "openai".
    EVIDENCE_EXTRACTION_CALLS: str = "gemini,gemini,openai,openai"
    # A proposed style is kept as a candidate only if it appears in at least this
    # many extraction calls (counted by KB id). 1 = union (max recall), 2 = the
    # pairwise threshold (balanced), 3 = triple (strictest). Falls back to union
    # if the threshold would leave no candidates.
    EVIDENCE_MIN_VOTES: int = 1
    # Superseded by EVIDENCE_EXTRACTION_CALLS; kept for backward compatibility.
    EVIDENCE_MC_SAMPLES: int = 1
    # Independent VISION judges in the panel (comma list of provider keys). All
    # three see the image + evidence sheet, so judge weights are symmetric.
    # DeepSeek is text-only → no longer a judge (it handles translation).
    PANEL_MODELS: str = "gemini,openai,grok"
    # Minimum difflib ratio for a fuzzy match of a proposed style name to the KB.
    # Lower = looser matching (risks false matches); higher = stricter.
    KB_FUZZY_CUTOFF: float = 0.82

    # ── Out-of-KB styles (open-set escape) ────────────────────────────────────
    # When the true style is NOT in the curated KB, the proposed name is normally
    # dropped at Stage B (only queued for human review). With this enabled, a
    # strongly-voted out-of-KB name is clustered into a single tagged candidate,
    # given a synthetic card from the observed evidence, and flows through the
    # panel like any candidate. It can become the displayed result ONLY if the
    # panel reaches a HIGHER agreement bar than in-KB styles (it has no curated
    # provenance to lean on). Default OFF so existing evaluations are unaffected.
    OUT_OF_KB_ENABLED: bool = False
    # An out-of-KB name must appear in at least this many extraction/free-read
    # sources to be admitted (filters one-off hallucinations).
    OUT_OF_KB_MIN_VOTES: int = 2
    # Cap on how many out-of-KB clusters may enter the candidate set.
    OUT_OF_KB_MAX_CANDIDATES: int = 2
    # Inter-judge agreement an out-of-KB primary must clear to be DISPLAYED (vs
    # demoted to the best in-KB style). Higher than PANEL_AGREEMENT_MIN because an
    # out-of-KB consensus is only internally consistent, not KB-grounded.
    OUT_OF_KB_AGREEMENT_MIN: float = 0.7

    # ── Uncertainty / abstention ──────────────────────────────────────────────
    # Below either bound → mark result uncertain and return top-K candidates.
    # margin = primary − second-best probability; entropy = spread of the final
    # mixture. UNCERTAINTY_CONF_MIN is an optional max-prob gate (0 disables it).
    # Inter-judge agreement (panel stage, Day 3) becomes the primary signal.
    UNCERTAINTY_MARGIN_MIN: float = 0.15
    UNCERTAINTY_ENTROPY_MAX: float = 1.6
    UNCERTAINTY_CONF_MIN: float = 0.0     # 0 disables the max-prob gate
    UNCERTAINTY_TOP_K: int = 3
    # PRIMARY abstention signal (decisions #73/#75): mean pairwise Spearman
    # agreement across the panel judges below this → mark the result uncertain.
    PANEL_AGREEMENT_MIN: float = 0.5
    # Who decides the FINAL style mixture (W1 redesign):
    #   "arbiter"   — the arbiter's own mixture (legacy / baseline behaviour)
    #   "panel"     — the decisiveness-weighted mean of the judges (panel votes;
    #                 arbiter only writes the narrative)
    #   "consensus" — the panel mean when the panel is decisive, but the arbiter
    #                 breaks ties when the panel is split / low-agreement, and may
    #                 lift the recall ceiling via its evidence-gated escape hatch
    # Default stays "arbiter" so behaviour is unchanged until the diagnostic
    # subset shows panel/consensus is better (decision: choose by numbers).
    DECISION_MODE: str = "arbiter"
    # Hybrid detection (SEPARATE from uncertainty). When the extraction calls
    # disagree — mean pairwise Jaccard of their proposed KB-id sets below this —
    # the image is treated as multi-style → mark the result ``hybrid``.
    EXTRACTION_AGREEMENT_MIN: float = 0.5
    # Minimum probability mass for a style to count as "significant" when
    # deciding the final mixture is a hybrid (≥ 2 significant styles → hybrid).
    HYBRID_MASS_MIN: float = 0.25

    # ── Contrastive run-off (conversion lever) ────────────────────────────────
    # When the final top-2 styles are within RUNOFF_MARGIN_MAX of each other the
    # decision engine is genuinely torn between them — the conversion-failure
    # regime where the right style is available but the wrong one is picked. A
    # focused vision call then contrasts the two finalists' KB defining-features
    # against the image, and the verdict is fused MULTIPLICATIVELY with the
    # arbiter's split (p ∝ p_arbiter × p_runoff), so it only overturns the
    # arbiter's lead when confident. False disables the stage (baseline).
    RUNOFF_ENABLED: bool = True
    RUNOFF_MARGIN_MAX: float = 0.30

    # ── Free-read judge (decorrelation + recall lever) ────────────────────────
    # An extra strong-vision call that names the style DIRECTLY from the image —
    # no candidate list, no merged evidence sheet — the way a base model answers.
    # Its proposals (a) seed the candidate set (lifting the recall ceiling) and
    # (b) are surfaced to the arbiter as an independent, unconstrained opinion
    # that did not pass through the shared sheet/candidate bottleneck, so its
    # errors are decorrelated from the panel's. False disables it (baseline).
    FREE_READ_ENABLED: bool = True
    # Translate the final narrative (explanation/evidence/composition) into
    # Vietnamese via one extra text-LLM call after Agent 7. Disable to skip the
    # added latency/cost.
    ENABLE_BILINGUAL: bool = True
    # Latency lever: move the Vietnamese translation OFF the analyse critical path.
    # When True, the pipeline returns the English result immediately (``*_vi`` =
    # None) and the translation is produced lazily the first time the analysis is
    # re-opened in Vietnamese (GET /analyze/history/{id}), then cached into
    # DetailJson. The translation never feeds the decision, so this is accuracy-
    # neutral. False = translate inline inside run() as before (full rollback).
    DEFER_TRANSLATION: bool = True

    # ── Vision image preprocessing (latency lever) ────────────────────────────
    # Downscale the image to this max LONG-edge (pixels) before encoding it for
    # the vision calls — every vision call (extraction + free-read + panel +
    # arbiter + run-off) carries the image, so a 4000px phone photo is shrunk
    # once and reused. thumbnail() only ever shrinks (never upscales). Validated
    # target is 1536 (balances ornament detail vs latency); ships at 0 (DISABLED
    # = original resolution, exact current behaviour) until the harness A/B
    # confirms no accuracy regression, then set 1536. 0 disables resizing.
    VISION_IMAGE_MAX_DIM: int = 0
    # Apply the EXIF orientation tag before encoding so rotated phone photos are
    # sent upright (the current path ignores EXIF). Correctness fix; False =
    # legacy behaviour (orientation ignored).
    APPLY_EXIF_TRANSPOSE: bool = True

    # ── Follow-up Q&A (POST /analyze/{image_id}/ask) ──────────────────────────
    # Grounded chat over a single stored analysis. The frontend sends prior
    # turns; only the last QA_MAX_HISTORY are kept to bound the prompt size.
    QA_MAX_HISTORY: int = 6
    # Low temperature keeps answers grounded in the analysis evidence + KB.
    QA_TEMPERATURE: float = 0.2

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

    # ── Billing / token wallet (v2) ───────────────────────────────────────────
    # Master switch. When False the whole billing layer is inert: analyses are
    # not charged, billing endpoints still exist but the analyze path skips the
    # wallet entirely — so the existing free-flow behaviour and tests are intact.
    BILLING_ENABLED: bool = False
    # Tokens charged per analysis on the default/free tier. A subscription tier
    # can lower this via its BenefitsJson "cost_per_analysis" (free=3, pro=2,
    # premium=1 by default) — that is the concrete tier benefit.
    TOKEN_COST_PER_ANALYSIS: int = 3
    # Tokens granted once to a brand-new account (written through the ledger).
    SIGNUP_BONUS_TOKENS: int = 10
    # Fraction of the reserved cost refunded when a run completes "degraded"
    # (partial pipeline failure but still returns a result). 1.0 = full refund,
    # 0.0 = charge in full. "failed" runs are always refunded 100%.
    DEGRADED_REFUND_RATIO: float = 0.5

    # ── Payments — gateway ────────────────────────────────────────────────────
    PAYMENT_DEFAULT_PROVIDER: str = "vnpay"
    # How long a created payment order stays payable before it is expired by the
    # reconciliation pass.
    PAYMENT_ORDER_TTL_MIN: int = 15
    # VNPay sandbox credentials (get them from the VNPay merchant sandbox portal).
    VNPAY_TMN_CODE: str = ""
    VNPAY_HASH_SECRET: str = ""
    VNPAY_PAYMENT_URL: str = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
    VNPAY_API_URL: str = "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
    # Where VNPay redirects the browser after payment (a backend endpoint that
    # verifies the signature then 302-redirects to the frontend result page).
    VNPAY_RETURN_URL: str = "http://localhost:8000/billing/callback/vnpay/return"
    # Server-to-server IPN URL (needs to be publicly reachable, e.g. via ngrok).
    VNPAY_IPN_URL: str = "http://localhost:8000/billing/callback/vnpay/ipn"
    # When True the return-url may also fulfil the order (idempotently) — useful
    # for local demos where the IPN cannot reach localhost. In production keep
    # False and let the IPN + reconciliation be the source of truth.
    VNPAY_RETURN_MAY_FULFILL: bool = False

    # ── Provider API-key management (admin-managed, DB-backed) ────────────────
    # Fernet key(s) used to encrypt provider API keys at rest in the DB. Generate
    # one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Multiple keys may be comma-separated to support encryption-key ROTATION
    # (the first key encrypts; every key is tried when decrypting). LEAVE EMPTY
    # to disable DB-backed keys (the resolver then always uses the .env keys).
    # IMPORTANT: back this value up SEPARATELY from the DB — a DB backup is
    # useless without it, and losing it makes every stored key undecryptable.
    APP_ENCRYPTION_KEY: str = ""
    # Master switch for the DB-backed key resolver. When False the system reads
    # provider keys straight from .env (the original behaviour) — a kill-switch
    # for instant rollback without reverting code.
    PROVIDER_KEYS_FROM_DB: bool = True
    # How long (seconds) each worker caches the runtime-config epoch before
    # re-checking the DB. A key change made on one worker converges to the others
    # within this window (matters because prod runs multiple uvicorn workers).
    RUNTIME_EPOCH_TTL_SEC: float = 15.0

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

    @property
    def panel_models_list(self) -> List[str]:
        """Return PANEL_MODELS parsed as a list of lowercase provider keys."""
        return [m.strip().lower() for m in self.PANEL_MODELS.split(",") if m.strip()]

    @property
    def evidence_extraction_calls_list(self) -> List[str]:
        """Return EVIDENCE_EXTRACTION_CALLS parsed as a list of provider keys.

        Repeats are meaningful (e.g. ``gemini,gemini`` = two Gemini calls).
        """
        return [c.strip().lower() for c in self.EVIDENCE_EXTRACTION_CALLS.split(",") if c.strip()]

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
