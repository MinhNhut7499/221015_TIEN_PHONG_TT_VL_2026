"""Tests for provider API-key management: cipher, resolver, RBAC, reload.

Run with: pytest test/ -v
"""
import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.security import secret_cipher
from app.security.security import create_access_token
from chatbot.services import provider_credentials


@pytest.fixture
def admin_token() -> str:
    """JWT with role=admin."""
    return create_access_token({"sub": "admin-1", "email": "admin@test.com", "role": "admin"})


@pytest.fixture
def user_token() -> str:
    """JWT with role=user."""
    return create_access_token({"sub": "user-1", "email": "user@test.com", "role": "user"})


@pytest.fixture(autouse=True)
def reset_resolver_state():
    """Reset the per-process credential snapshot between tests."""
    provider_credentials._snapshot = {}
    provider_credentials._snapshot_epoch = None
    provider_credentials._epoch_cache = None
    provider_credentials._epoch_cached_at = 0.0
    yield
    provider_credentials._snapshot = {}
    provider_credentials._snapshot_epoch = None


@pytest.fixture
def cipher_key(monkeypatch):
    """Configure a real Fernet key and clear the cipher cache."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "APP_ENCRYPTION_KEY", key)
    secret_cipher._get_cipher.cache_clear()
    yield key
    secret_cipher._get_cipher.cache_clear()


# ── Cipher ──────────────────────────────────────────────────────────────────

def test_cipher_round_trip(cipher_key) -> None:
    """A secret encrypts and decrypts back to the original."""
    token = secret_cipher.encrypt_secret("sk-secret-123")
    assert token != "sk-secret-123"
    assert secret_cipher.decrypt_secret(token) == "sk-secret-123"


def test_cipher_decrypt_garbage_returns_none(cipher_key) -> None:
    """Corrupt ciphertext fails safe to None, never raises."""
    assert secret_cipher.decrypt_secret("not-a-valid-token") is None


def test_cipher_unavailable_without_key(monkeypatch) -> None:
    """With no APP_ENCRYPTION_KEY, encrypt raises and decrypt returns None."""
    monkeypatch.setattr(settings, "APP_ENCRYPTION_KEY", "")
    secret_cipher._get_cipher.cache_clear()
    assert secret_cipher.cipher_available() is False
    assert secret_cipher.decrypt_secret("anything") is None
    with pytest.raises(secret_cipher.CipherUnavailableError):
        secret_cipher.encrypt_secret("x")
    secret_cipher._get_cipher.cache_clear()


# ── Resolver ────────────────────────────────────────────────────────────────

def test_resolver_env_fallback_when_snapshot_empty(monkeypatch) -> None:
    """With no DB snapshot, credentials come from settings (.env)."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "env-gemini")
    cred = provider_credentials.get_credentials("gemini")
    assert cred.source == "env"
    assert cred.key == "env-gemini"


def test_resolver_prefers_db_snapshot(monkeypatch) -> None:
    """A populated snapshot wins over the env key."""
    provider_credentials._snapshot["openai"] = provider_credentials.ProviderCredentials(
        provider="openai", key="db-openai", model="gpt-x", base_url=None, source="db"
    )
    cred = provider_credentials.get_credentials("openai")
    assert cred.source == "db" and cred.key == "db-openai"


def test_provider_keys_from_db_flag_forces_env(monkeypatch) -> None:
    """The kill-switch makes the resolver ignore DB keys entirely."""
    monkeypatch.setattr(settings, "PROVIDER_KEYS_FROM_DB", False)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "env-openai")
    provider_credentials._snapshot["openai"] = provider_credentials.ProviderCredentials(
        provider="openai", key="db-openai", model="m", base_url=None, source="db"
    )
    cred = provider_credentials.get_credentials("openai")
    assert cred.source == "env" and cred.key == "env-openai"


def test_resolver_rejects_unknown_provider() -> None:
    """An unsupported provider name raises ValueError."""
    with pytest.raises(ValueError):
        provider_credentials.get_credentials("not-a-provider")


def test_is_pipeline_configured_reads_env(monkeypatch) -> None:
    """Pipeline is configured when the three core env keys are present."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "d")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "o")
    assert provider_credentials.is_pipeline_configured() is True


def test_mask_shows_only_last4() -> None:
    """The masked form never reveals the full key — only the last 4 chars."""
    from app.services.api_key_service import _mask

    assert _mask("ab12") == "••••ab12"
    assert _mask(None) == "••••"


# ── Runtime reload ──────────────────────────────────────────────────────────

def test_reset_orchestrator_clears_singleton() -> None:
    """reset_orchestrator drops the cached orchestrator instance."""
    import chatbot.services.analysis_orchestrator as orch

    orch._orchestrator = object()
    orch.reset_orchestrator()
    assert orch._orchestrator is None


# ── RBAC endpoint guards ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_keys_no_token_403() -> None:
    """Listing keys without a token is rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/admin/api-keys")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_list_keys_user_forbidden(user_token: str) -> None:
    """A non-admin user cannot manage API keys."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/admin/api-keys", headers={"Authorization": f"Bearer {user_token}"}
        )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_list_keys_admin_ok(admin_token: str) -> None:
    """An admin sees the (empty) key list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/admin/api-keys", headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert res.status_code == 200
    assert res.json() == {"keys": []}


@pytest.mark.asyncio
async def test_create_key_without_cipher_returns_400(admin_token: str, monkeypatch) -> None:
    """Creating a key with no APP_ENCRYPTION_KEY fails clearly (400)."""
    monkeypatch.setattr(settings, "APP_ENCRYPTION_KEY", "")
    secret_cipher._get_cipher.cache_clear()
    body = {"provider": "gemini", "label": "k1", "api_key": "sk-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/admin/api-keys", json=body, headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert res.status_code == 400
    secret_cipher._get_cipher.cache_clear()


@pytest.mark.asyncio
async def test_create_key_rejects_unknown_provider(admin_token: str, cipher_key) -> None:
    """An unsupported provider is rejected with 400 before any DB write."""
    body = {"provider": "bogus", "label": "k1", "api_key": "sk-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/admin/api-keys", json=body, headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert res.status_code == 400
