"""Unit tests for wallet_service pure logic (cost/benefits parsing).

The atomic guarantees of ``apply_ledger`` (conditional UPDATE rowcount, the
UNIQUE-idempotency-key SAVEPOINT race) cannot be exercised against the mocked
session used by the rest of the suite — they require a real SQL Server. Those
are covered by ``test/integration/test_wallet_integration.py`` (opt-in via the
RUN_DB_INTEGRATION env var), per the plan's verification section (Issue 17).
"""
from app.config import settings
from app.models.orm_models import Plan
from app.services import wallet_service


def _plan(benefits_json):
    """Build a detached Plan ORM instance carrying the given BenefitsJson."""
    return Plan(
        PlanCode="pro",
        PlanName="Pro",
        PlanType="subscription",
        PriceAmount=99000,
        Currency="VND",
        TokenAmount=500,
        DurationDays=30,
        BenefitsJson=benefits_json,
    )


def test_parse_benefits_handles_null_and_malformed():
    assert wallet_service._parse_benefits(None) == {}
    assert wallet_service._parse_benefits("") == {}
    assert wallet_service._parse_benefits("not json") == {}
    assert wallet_service._parse_benefits('[1,2,3]') == {}  # not a dict
    assert wallet_service._parse_benefits('{"cost_per_analysis": 0.5}') == {
        "cost_per_analysis": 0.5
    }


def test_effective_cost_default_when_no_plan():
    assert wallet_service.effective_cost(None, plan_active=False) == float(
        settings.TOKEN_COST_PER_ANALYSIS
    )


def test_effective_cost_default_when_plan_expired():
    plan = _plan('{"cost_per_analysis": 0.5}')
    # Even though the tier discounts, an expired tier falls back to default.
    assert wallet_service.effective_cost(plan, plan_active=False) == float(
        settings.TOKEN_COST_PER_ANALYSIS
    )


def test_effective_cost_uses_active_tier_discount():
    plan = _plan('{"cost_per_analysis": 0.5}')
    assert wallet_service.effective_cost(plan, plan_active=True) == 0.5


def test_effective_cost_ignores_malformed_or_negative_benefit():
    assert wallet_service.effective_cost(_plan("garbage"), plan_active=True) == float(
        settings.TOKEN_COST_PER_ANALYSIS
    )
    assert wallet_service.effective_cost(
        _plan('{"cost_per_analysis": -3}'), plan_active=True
    ) == float(settings.TOKEN_COST_PER_ANALYSIS)


def test_signup_bonus_uses_deterministic_idempotency_key(monkeypatch):
    """grant_signup_bonus must key on the user id so it can only apply once."""
    captured = {}

    async def _fake_apply_ledger(db, **kwargs):
        captured.update(kwargs)
        from app.services.wallet_service import LedgerOutcome, LedgerStatus

        return LedgerOutcome(LedgerStatus.APPLIED, balance_after=10)

    monkeypatch.setattr(wallet_service, "apply_ledger", _fake_apply_ledger)

    import asyncio

    asyncio.run(wallet_service.grant_signup_bonus(db=None, user_id="user-123"))
    assert captured["idempotency_key"] == "signup:user-123"
    assert captured["reason"] == "signup_bonus"
    assert captured["delta"] == settings.SIGNUP_BONUS_TOKENS
