from __future__ import annotations

from dataclasses import dataclass, field


CLASSIFICATION_KINDS = (
    "creditare",
    "recuperare_creditare",
    "supplier_payment",
    "client_receipt",
    "tax_payment",
    "bank_fee",
    "dividend_payment",
    "internal_transfer",
    "other_inflow",
    "other_outflow",
)


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    economic_kind: str
    direction: str
    entity_type: str | None
    confidence: float
    reason: str
    analysis_categories: list[str] = field(default_factory=list)
