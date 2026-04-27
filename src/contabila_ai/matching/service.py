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
            candidate = self._pick_best_invoice_candidate(transaction, available_invoices)
            if candidate is None:
                continue
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
            available_invoices = [
                invoice
                for invoice in available_invoices
                if int(invoice["id"]) != int(candidate["invoice"]["id"])
            ]
        return proposals

    def _pick_best_invoice_candidate(
        self,
        transaction: dict[str, Any],
        invoices: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        tx_amount = abs(float(transaction["amount"]))
        tx_currency = str(transaction.get("currency") or "")
        tx_name = normalize_entity_name(transaction.get("merchant"))
        tx_date = self._parse_date(transaction.get("transaction_date"))
        best: dict[str, Any] | None = None

        for invoice in invoices:
            if str(invoice.get("role") or "") != "received":
                continue
            if str(invoice.get("currency") or "") != tx_currency:
                continue
            invoice_name = normalize_entity_name(invoice.get("counterparty_name"))
            if tx_name and invoice_name and tx_name != invoice_name:
                continue
            invoice_total = float(invoice.get("total_amount") or 0)
            if invoice_total <= 0:
                continue
            invoice_date = self._parse_date(invoice.get("issue_date"))
            if tx_date and invoice_date and abs((tx_date - invoice_date).days) > 45:
                continue

            if abs(tx_amount - invoice_total) < 0.01:
                candidate = {
                    "invoice": invoice,
                    "match_kind": "one_to_one",
                    "matched_amount": tx_amount,
                    "residual_amount": 0.0,
                    "confidence": 0.98,
                    "reasoning": "same counterparty, currency, and exact total amount",
                }
            elif tx_amount < invoice_total and tx_amount >= invoice_total * 0.5:
                candidate = {
                    "invoice": invoice,
                    "match_kind": "partial_payment",
                    "matched_amount": tx_amount,
                    "residual_amount": round(invoice_total - tx_amount, 2),
                    "confidence": 0.86,
                    "reasoning": "same counterparty and currency with a clear partial payment amount",
                }
            else:
                continue

            if best is None or float(candidate["confidence"]) > float(best["confidence"]):
                best = candidate
        return best

    def _parse_date(self, raw_value: Any) -> date | None:
        if not raw_value:
            return None
        try:
            return date.fromisoformat(str(raw_value))
        except ValueError:
            return None
