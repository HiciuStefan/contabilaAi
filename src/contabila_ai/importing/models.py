from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImportedTransaction:
    transaction_date: str
    description: str
    amount: float
    currency: str
    balance: float | None
    merchant: str | None
    source_file: str
    raw_payload: str


@dataclass(frozen=True, slots=True)
class ImportedInvoice:
    invoice_number: str
    issue_date: str
    customer_name: str
    net_amount: float
    vat_amount: float | None
    total_amount: float
    currency: str
    status: str
    source_file: str
    raw_payload: str
