"""Payment gateway abstraction.

A single ``PaymentGateway`` interface (see ``base``) lets the billing core stay
provider-agnostic; concrete gateways (VNPay today, MoMo/Stripe later) plug in via
``factory.get_gateway``.
"""
from app.services.payments.base import (
    CheckoutContext,
    PaymentGateway,
    QueryResult,
    VerifiedCallback,
)
from app.services.payments.factory import get_gateway

__all__ = [
    "CheckoutContext",
    "PaymentGateway",
    "QueryResult",
    "VerifiedCallback",
    "get_gateway",
]
