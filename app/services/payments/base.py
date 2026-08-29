"""Provider-agnostic payment gateway interface and data contracts.

Concrete gateways (VNPay, MoMo, Stripe…) implement ``PaymentGateway``. The
billing core never imports a concrete gateway directly — it goes through
``factory.get_gateway`` and these dataclasses, so adding a provider is a new file
plus a factory branch (mirrors the project's ``BaseLLMService`` pattern).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class CheckoutContext:
    """Everything a gateway needs to build a redirect/checkout URL."""

    order_ref: str          # our internal order id (e.g. vnp_TxnRef)
    amount: int             # amount in the currency's base unit (VND = đồng)
    currency: str
    order_info: str         # human description shown on the gateway
    client_ip: str
    return_url: str         # where the gateway redirects the browser afterwards


@dataclass
class VerifiedCallback:
    """Normalised result of verifying a gateway callback (IPN or return).

    ``valid`` is purely the signature check. Business cross-checks (amount,
    merchant code, transaction-status) are done by the payment service against
    ``params`` so they are uniform across providers.
    """

    valid: bool
    success: bool                       # gateway reports the payment succeeded
    order_ref: Optional[str] = None
    provider_txn_id: Optional[str] = None
    amount: Optional[int] = None        # base unit, already un-scaled
    response_code: Optional[str] = None
    params: Dict[str, str] = field(default_factory=dict)
    raw: str = ""                       # raw query string, stored for forensics


@dataclass
class QueryResult:
    """Result of querying a transaction's status server-to-server (reconcile)."""

    found: bool
    success: bool
    amount: Optional[int] = None
    provider_txn_id: Optional[str] = None
    raw: str = ""


class PaymentGateway(ABC):
    """Abstract payment provider."""

    provider: str = "base"

    @abstractmethod
    def create_payment(self, ctx: CheckoutContext) -> str:
        """Return a redirect URL that takes the user to the gateway to pay."""

    @abstractmethod
    def verify_callback(self, params: Dict[str, str]) -> VerifiedCallback:
        """Verify a callback's signature and extract its normalised fields."""

    @abstractmethod
    async def query_status(self, order_ref: str, *, amount: int, client_ip: str) -> QueryResult:
        """Query the gateway for a transaction's final status (reconciliation)."""

    async def refund(
        self, *, order_ref: str, provider_txn_id: Optional[str], amount: int,
        original_amount: int, client_ip: str, created_by: str,
    ) -> QueryResult:
        """Request a (full/partial) refund. Default: provider does not support it."""
        raise NotImplementedError(f"{self.provider} does not support refunds")
