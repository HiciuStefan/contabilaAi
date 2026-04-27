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


@dataclass(frozen=True, slots=True)
class StatementValidation:
    available: bool
    passed: bool
    parser_name: str
    errors: tuple[str, ...]
    declared_transaction_count: int | None
    parsed_transaction_count: int
    declared_inflow_count: int | None
    parsed_inflow_count: int
    declared_outflow_count: int | None
    parsed_outflow_count: int
    declared_total_income: float | None
    parsed_total_income: float
    declared_total_expenses: float | None
    parsed_total_expenses: float
    declared_net_cashflow: float | None
    parsed_net_cashflow: float
    declared_opening_balance: float | None
    declared_closing_balance: float | None
    parsed_closing_balance: float | None
    inferred_transaction_count: int


@dataclass(frozen=True, slots=True)
class StatementParseResult:
    transactions: tuple[ImportedTransaction, ...]
    validation: StatementValidation
