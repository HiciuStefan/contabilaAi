from __future__ import annotations

from datetime import date
from typing import Any

from contabila_ai.classification import normalize_entity_name
from contabila_ai.storage.store import SQLiteTransactionStore


class MatchingService:
    def __init__(self, store: SQLiteTransactionStore) -> None:
        self._store = store

    def match_workspace(self, *, workspace_id: int) -> list[dict[str, Any]]:
        transactions = self._store.list_unmatched_workspace_transactions(workspace_id)
        invoices = self._store.list_workspace_invoices_for_matching(workspace_id)
        proposals: list[dict[str, Any]] = []
        available_invoices = list(invoices)
        for transaction in transactions:
            candidates = self._pick_invoice_candidates_for_transaction(transaction, available_invoices)
            if not candidates:
                continue
            for candidate in candidates:
                created = self._store.create_invoice_match(
                    workspace_id=workspace_id,
                    transaction_id=int(transaction["id"]),
                    invoice_id=int(candidate["invoice"]["id"]),
                    match_kind=str(candidate["match_kind"]),
                    matched_amount=float(candidate["matched_amount"]),
                    residual_amount=float(candidate["residual_amount"]),
                    confidence=float(candidate["confidence"]),
                    reasoning=str(candidate["reasoning"]),
                )
                proposals.append(created)
                available_invoices = self._consume_invoice_amount(
                    available_invoices=available_invoices,
                    invoice_id=int(candidate["invoice"]["id"]),
                    consumed_amount=float(candidate["matched_amount"]),
                )
        return proposals

    def _pick_invoice_candidates_for_transaction(
        self,
        transaction: dict[str, Any],
        invoices: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        tx_amount = abs(float(transaction["amount"]))
        eligible_invoices = self._eligible_invoices_for_transaction(transaction, invoices)
        if not eligible_invoices:
            return []

        best_single = self._pick_best_single_invoice_candidate(transaction, eligible_invoices)
        if best_single is not None:
            return [best_single]

        total_remaining = round(
            sum(float(invoice.get("remaining_amount") or invoice.get("total_amount") or 0.0) for invoice in eligible_invoices),
            2,
        )
        if tx_amount - total_remaining > 0.01:
            return []
        if len(eligible_invoices) < 2:
            return []

        remaining = tx_amount
        allocations: list[dict[str, Any]] = []
        for invoice in sorted(
            eligible_invoices,
            key=lambda item: (str(item.get("issue_date") or ""), int(item.get("id", 0))),
        ):
            if remaining <= 0.01:
                break
            invoice_total = float(invoice.get("total_amount") or 0.0)
            invoice_remaining = float(invoice.get("remaining_amount") or invoice_total)
            already_matched = round(invoice_total - invoice_remaining, 2)
            if invoice_remaining <= 0.01:
                continue
            matched_amount = round(min(invoice_remaining, remaining), 2)
            if matched_amount <= 0.01:
                continue
            residual_amount = round(invoice_remaining - matched_amount, 2)
            if matched_amount < invoice_remaining:
                match_kind = "installment_payment" if already_matched >= 0.01 else "partial_payment"
                confidence = 0.8
            else:
                match_kind = "installment_payment" if already_matched >= 0.01 else "bulk_settlement"
                confidence = 0.84
            allocations.append(
                {
                    "invoice": invoice,
                    "match_kind": match_kind,
                    "matched_amount": matched_amount,
                    "residual_amount": residual_amount,
                    "confidence": confidence,
                    "reasoning": "same counterparty and currency; payment split across multiple open received invoices",
                }
            )
            remaining = round(remaining - matched_amount, 2)

        if remaining > 0.01:
            return []
        return allocations

    def _eligible_invoices_for_transaction(
        self,
        transaction: dict[str, Any],
        invoices: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        tx_currency = str(transaction.get("currency") or "")
        tx_name = normalize_entity_name(transaction.get("merchant"))
        tx_date = self._parse_date(transaction.get("transaction_date"))
        eligible: list[dict[str, Any]] = []
        for invoice in invoices:
            if str(invoice.get("currency") or "") != tx_currency:
                continue
            invoice_name = normalize_entity_name(invoice.get("counterparty_name"))
            if tx_name and invoice_name and tx_name != invoice_name:
                continue
            invoice_total = float(invoice.get("total_amount") or 0)
            invoice_remaining = float(invoice.get("remaining_amount") or invoice_total)
            if invoice_total <= 0 or invoice_remaining <= 0:
                continue
            invoice_date = self._parse_date(invoice.get("issue_date"))
            if tx_date and invoice_date and abs((tx_date - invoice_date).days) > 45:
                continue
            eligible.append(invoice)
        return eligible

    def _pick_best_single_invoice_candidate(
        self,
        transaction: dict[str, Any],
        invoices: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        tx_amount = abs(float(transaction["amount"]))
        best: dict[str, Any] | None = None

        for invoice in invoices:
            invoice_total = float(invoice.get("total_amount") or 0)
            invoice_remaining = float(invoice.get("remaining_amount") or invoice_total)
            already_matched = round(invoice_total - invoice_remaining, 2)
            if invoice_total <= 0 or invoice_remaining <= 0:
                continue
            if tx_amount - invoice_remaining > 0.01:
                continue

            if abs(tx_amount - invoice_total) < 0.01 and already_matched < 0.01:
                candidate = {
                    "invoice": invoice,
                    "match_kind": "one_to_one",
                    "matched_amount": tx_amount,
                    "residual_amount": 0.0,
                    "confidence": 0.98,
                    "reasoning": "same counterparty, currency, and exact total amount",
                }
            elif abs(tx_amount - invoice_remaining) < 0.01 and already_matched >= 0.01:
                candidate = {
                    "invoice": invoice,
                    "match_kind": "installment_payment",
                    "matched_amount": tx_amount,
                    "residual_amount": 0.0,
                    "confidence": 0.92,
                    "reasoning": "same counterparty and currency, with final installment covering remaining invoice amount",
                }
            elif tx_amount < invoice_remaining:
                candidate = {
                    "invoice": invoice,
                    "match_kind": "installment_payment" if already_matched >= 0.01 else "partial_payment",
                    "matched_amount": tx_amount,
                    "residual_amount": round(invoice_remaining - tx_amount, 2),
                    "confidence": 0.88 if already_matched >= 0.01 else 0.86,
                    "reasoning": "same counterparty and currency with a clear partial payment amount",
                }
            else:
                continue

            if best is None or float(candidate["confidence"]) > float(best["confidence"]):
                best = candidate
        return best

    def _consume_invoice_amount(
        self,
        *,
        available_invoices: list[dict[str, Any]],
        invoice_id: int,
        consumed_amount: float,
    ) -> list[dict[str, Any]]:
        updated: list[dict[str, Any]] = []
        for invoice in available_invoices:
            if int(invoice["id"]) != int(invoice_id):
                updated.append(invoice)
                continue
            current_remaining = float(invoice.get("remaining_amount") or invoice.get("total_amount") or 0.0)
            new_remaining = round(current_remaining - consumed_amount, 2)
            if new_remaining > 0.01:
                updated_invoice = dict(invoice)
                updated_invoice["remaining_amount"] = new_remaining
                updated.append(updated_invoice)
        return updated

    def _parse_date(self, raw_value: Any) -> date | None:
        if not raw_value:
            return None
        try:
            return date.fromisoformat(str(raw_value))
        except ValueError:
            return None
