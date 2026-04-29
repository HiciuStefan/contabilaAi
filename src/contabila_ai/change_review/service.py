from __future__ import annotations

from contabila_ai.classification import normalize_entity_name
from contabila_ai.review.service import ReviewService
from contabila_ai.storage.store import SQLiteTransactionStore


class ChangeReviewService:
    def __init__(self, store: SQLiteTransactionStore) -> None:
        self._store = store

    def refresh_for_workspace(self, *, workspace_id: int) -> list[dict[str, object]]:
        created: list[dict[str, object]] = []
        matches = self._store.list_invoice_matches(workspace_id)
        category_profiles = self._build_category_profiles(workspace_id)
        entity_type_profiles = self._build_entity_type_profiles()

        for match in matches:
            transaction = self._store.fetch_transaction_by_id(int(match["transaction_id"]))
            invoice = self._store.fetch_workspace_invoice_by_id(int(match["invoice_id"]))
            if not transaction or not invoice:
                continue
            profile_key = normalize_entity_name(invoice.get("counterparty_name") or transaction.get("merchant"))
            if not transaction.get("category_names"):
                suggested_category = category_profiles.get(profile_key)
                if suggested_category:
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

            suggested_entity_type = entity_type_profiles.get(profile_key) or self._infer_entity_type_from_invoice(invoice)
            current_entity_type = str(transaction.get("entity_type") or "").strip()
            if suggested_entity_type and current_entity_type != suggested_entity_type:
                item = self._store.create_change_review_item(
                    workspace_id=workspace_id,
                    transaction_id=int(transaction["id"]),
                    field_name="entity_type",
                    old_value="" if current_entity_type in {"", "unknown"} else current_entity_type,
                    new_value=suggested_entity_type,
                    reason="matched invoice suggests a stronger entity relationship type for this counterparty",
                    confidence=0.79,
                )
                if item["status"] == "pending":
                    created.append(item)
        return created

    def apply_decision(self, *, item_id: int, decision: str) -> dict[str, object]:
        item = self._store.get_change_review_item(item_id)
        normalized_decision = decision.strip().lower()
        if normalized_decision == "accept" and item["field_name"] == "analysis_category":
            ReviewService(self._store).apply_category(
                str(item["new_value"]),
                [int(item["transaction_id"])],
                apply_to_similar=True,
                replace_existing=False,
            )
        if normalized_decision == "accept" and item["field_name"] == "entity_type":
            transaction = self._store.fetch_transaction_by_id(int(item["transaction_id"]))
            if transaction and transaction.get("merchant"):
                self._store.upsert_entity_memory(
                    str(transaction["merchant"]),
                    str(item["new_value"]),
                    confidence=max(float(item.get("confidence") or 0), 0.95),
                    notes="accepted from change review",
                )
                self._store.reclassify_transactions()
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

    def _build_entity_type_profiles(self) -> dict[str, str]:
        profiles: dict[str, str] = {}
        for normalized_name, row in self._store.entity_memory_map().items():
            entity_type = str(row.get("entity_type") or "").strip()
            if normalized_name and entity_type:
                profiles[normalized_name] = entity_type
        return profiles

    def _infer_entity_type_from_invoice(self, invoice: dict[str, object]) -> str | None:
        role = str(invoice.get("role") or "").strip().lower()
        if role == "issued":
            return "partner"
        if role == "received":
            return "supplier"
        return None
