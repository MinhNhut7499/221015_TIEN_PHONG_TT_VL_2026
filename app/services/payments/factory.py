"""Payment gateway factory — maps a provider key to a gateway instance.

Add a provider = add a branch here plus its module. Gateways are cached per
provider so credentials are read once.
"""
from __future__ import annotations

from functools import lru_cache

from app.services.payments.base import PaymentGateway


@lru_cache()
def get_gateway(provider: str) -> PaymentGateway:
    """Return the gateway for ``provider`` (e.g. 'vnpay'). Raises on unknown."""
    key = (provider or "").lower()
    if key == "vnpay":
        from app.services.payments.vnpay import VnpayGateway

        return VnpayGateway()
    raise ValueError(f"Unsupported payment provider: {provider!r}")
