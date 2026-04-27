from __future__ import annotations

from contabila_ai.classification import normalize_entity_name
from contabila_ai.storage.store import SQLiteTransactionStore


class ChangeReviewService:
    def __init__(self, store: SQLiteTransactionStore) -> None:
        self._store = store

    def refresh_for_workspace(self, *, workspace_id: int) -> list[dict[str, object]]:
        created: list[dict[str, object]] = []
        matches = self._store.list_invoice_matches(workspace_id)
        category_profiles = self._build_category_profiles(workspace_id)

        for match in matches:
            transaction = self._store.fetch_transaction_by_id(int(match["transaction_id"]))
            invoice = self._store.fetch_workspace_invoice_by_id(int(match["invoice_id"]))
            if not transaction or not invoice:
                continue
            if transaction.get("category_names"):
                continue
            profile_key = normalize_entity_name(invoice.get("counterparty_name") or transaction.get("merchant"))
            suggested_category = category_profiles.get(profile_key)
            if not suggested_category:
                continue
            item = self._store.create_change_review_item(
                workspace_id=workspace_id,
                transaction_id=int(transaction["id"]),
                field_name="analysis_category",
                old_value="",
                new_value=suggested_category,
                reason="matched invoice aligns with an existing category profile for this counterparty",
                confidence=0.82,
            )
            if item["status"] == "pending":
                created.append(item)
        return created

    def apply_decision(self, *, item_id: int, decision: str) -> dict[str, object]:
        item = self._store.get_change_review_item(item_id)
        normalized_decision = decision.strip().lower()
        if normalized_decision == "accept" and item["field_name"] == "analysis_category":
            self._store.assign_analysis_category(item["new_value"], [int(item["transaction_id"])], replace_existing=False)
        self._store.set_change_review_status(item_id, normalized_decision)
        updated = self._store.get_change_review_item(item_id)
        return {"ok": True, "decision": normalized_decision, "item": updated}

    def _build_category_profiles(self, workspace_id: int) -> dict[str, str]:
        profiles: dict[str, str] = {}
        for row in self._store.list_workspace_transactions_with_categories(workspace_id):
            if not row.get("category_names"):
                continue
            key = normalize_entity_name(row.get("merchant"))
            if not key:
                continue
            category_name = str(row["category_names"]).split(",")[0]
            profiles.setdefault(key, category_name)
        return profiles
