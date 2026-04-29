from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Iterable

from contabila_ai.classification import normalize_entity_name, normalize_text
from contabila_ai.storage.store import SQLiteTransactionStore


LEGAL_SUFFIX_TOKENS = {
    "srl",
    "sa",
    "sca",
    "scs",
    "pfa",
    "ii",
    "if",
    "ltd",
    "llc",
}

DESCRIPTION_STOPWORDS = {
    "transfer",
    "online",
    "interbancar",
    "beneficiar",
    "detalii",
    "plata",
    "incasare",
    "ordin",
    "factura",
    "roc",
    "cv",
    "msgid",
}


class ReviewService:
    def __init__(
        self,
        store: SQLiteTransactionStore,
        *,
        confidence_threshold: float = 0.75,
    ) -> None:
        self.store = store
        self.confidence_threshold = confidence_threshold

    def candidates(
        self,
        limit: int = 25,
        import_batch_id: int | None = None,
        workspace_id: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.store.list_review_candidates(
            limit=limit,
            confidence_threshold=self.confidence_threshold,
            import_batch_id=import_batch_id,
            workspace_id=workspace_id,
        )
        for row in rows:
            category_names = row.pop("category_names", "") or ""
            row["analysis_categories"] = [
                name for name in category_names.split(",") if name
            ]
            row["severity"] = self._severity_for_row(row)
        return rows

    def candidate_groups(
        self,
        limit: int = 25,
        import_batch_id: int | None = None,
        workspace_id: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.candidates(limit=limit, import_batch_id=import_batch_id, workspace_id=workspace_id)
        category_profiles = self._category_profiles(import_batch_id=import_batch_id)
        groups: dict[str, dict[str, Any]] = {}

        for row in rows:
            group_key = self._group_key_for_row(row)
            existing = groups.get(group_key)
            if existing is None:
                existing = {
                    "group_key": group_key,
                    "group_label": row.get("merchant") or row.get("description") or "Tranzactii similare",
                    "transaction_count": 0,
                    "transaction_ids": [],
                    "analysis_categories": [],
                    "suggested_category": None,
                    "suggested_categories": [],
                    "min_confidence": row.get("confidence"),
                    "total_amount": 0.0,
                    "samples": [],
                    "severity": row.get("severity") or "low",
                }
                groups[group_key] = existing

            existing["transaction_count"] += 1
            existing["transaction_ids"].append(int(row["id"]))
            existing["total_amount"] = round(float(existing["total_amount"]) + float(row["amount"]), 2)
            if existing["min_confidence"] is None or (
                row.get("confidence") is not None and float(row["confidence"]) < float(existing["min_confidence"])
            ):
                existing["min_confidence"] = row.get("confidence")
            for category_name in row.get("analysis_categories", []):
                if category_name not in existing["analysis_categories"]:
                    existing["analysis_categories"].append(category_name)
            if len(existing["samples"]) < 3:
                existing["samples"].append(row)
            existing["severity"] = self._max_severity(existing["severity"], row.get("severity") or "low")
            suggestions = self._suggest_categories_for_row(row, category_profiles)
            for suggestion in suggestions:
                if suggestion not in existing["suggested_categories"]:
                    existing["suggested_categories"].append(suggestion)

        grouped_rows = list(groups.values())
        grouped_rows.sort(
            key=lambda item: (
                float(item["min_confidence"]) if item["min_confidence"] is not None else 0.0,
                self._severity_rank(item["severity"]),
                -int(item["transaction_count"]),
                str(item["group_label"]),
            )
        )
        for item in grouped_rows:
            item["transaction_ids"].sort()
            item["suggested_categories"] = item["suggested_categories"][:3]
            item["suggested_category"] = (
                item["suggested_categories"][0] if item["suggested_categories"] else None
            )
        return grouped_rows

    def severity_counts(
        self,
        *,
        workspace_id: int | None = None,
        import_batch_id: int | None = None,
        limit: int = 1000,
    ) -> dict[str, int]:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for row in self.candidates(limit=limit, import_batch_id=import_batch_id, workspace_id=workspace_id):
            severity = row.get("severity") or "low"
            counts[severity] = counts.get(severity, 0) + 1
        return counts

    def has_blocking_items(
        self,
        *,
        workspace_id: int | None = None,
        import_batch_id: int | None = None,
    ) -> bool:
        counts = self.severity_counts(workspace_id=workspace_id, import_batch_id=import_batch_id)
        return counts.get("critical", 0) > 0 or counts.get("high", 0) > 0

    def apply_category(
        self,
        category_name: str,
        transaction_ids: Iterable[int],
        apply_to_similar: bool = True,
        import_batch_id: int | None = None,
        description: str | None = None,
        operational_scope: str = "unassigned",
        replace_existing: bool = False,
    ) -> dict[str, int]:
        target_rows = self.store.fetch_transactions_by_ids(transaction_ids)
        resolved_ids = {int(row["id"]) for row in target_rows}
        if not resolved_ids:
            return {"updated_count": 0}

        if apply_to_similar:
            similar_ids = self._find_similar_transaction_ids(resolved_ids, import_batch_id=import_batch_id)
            resolved_ids.update(similar_ids)

        updated_count = self.store.assign_analysis_category(
            category_name,
            resolved_ids,
            description=description,
            operational_scope=operational_scope,
            replace_existing=replace_existing,
        )
        learned_rule = self._learn_category_rule(category_name, target_rows)
        if learned_rule:
            self.store.reclassify_transactions()
        return {"updated_count": updated_count, "learned_rule": int(learned_rule)}

    def confirm_transaction(self, transaction_id: int) -> None:
        self.store.confirm_transaction_review(transaction_id)

    def find_category_name_conflict(self, category_name: str) -> dict[str, Any] | None:
        normalized_target = self._normalize_category_key(category_name)
        if not normalized_target:
            return None

        best_match: dict[str, Any] | None = None
        for category in self.store.list_analysis_categories():
            existing_name = str(category.get("name") or "")
            existing_key = self._normalize_category_key(existing_name)
            if not existing_key:
                continue
            if existing_name.strip().lower() == str(category_name).strip().lower():
                continue
            similarity = 1.0 if existing_key == normalized_target else SequenceMatcher(
                None,
                normalized_target,
                existing_key,
            ).ratio()
            if similarity < 0.82:
                continue
            candidate = {
                "existing_category": existing_name,
                "similarity": round(similarity, 2),
            }
            if best_match is None or candidate["similarity"] > best_match["similarity"]:
                best_match = candidate
        return best_match

    def _find_similar_transaction_ids(
        self,
        transaction_ids: set[int],
        import_batch_id: int | None = None,
    ) -> set[int]:
        target_rows = self.store.fetch_transactions_by_ids(transaction_ids)
        merchant_keys = {
            self._merchant_fingerprint(row.get("merchant"))
            for row in target_rows
            if self._merchant_fingerprint(row.get("merchant"))
        }
        description_keys = {
            self._description_fingerprint(row.get("description"))
            for row in target_rows
            if self._description_fingerprint(row.get("description"))
        }
        if not merchant_keys and not description_keys:
            return set(transaction_ids)

        similar_ids = set(transaction_ids)
        for row in self.store.list_transactions_for_similarity():
            row_batch_id = row.get("import_batch_id")
            if import_batch_id is not None and row_batch_id != int(import_batch_id):
                continue
            merchant_key = self._merchant_fingerprint(row.get("merchant"))
            description_key = self._description_fingerprint(row.get("description"))
            if merchant_key and merchant_key in merchant_keys:
                similar_ids.add(int(row["id"]))
                continue
            if description_key and description_key in description_keys:
                similar_ids.add(int(row["id"]))
        return similar_ids

    def _learn_category_rule(
        self,
        category_name: str,
        target_rows: Iterable[dict[str, Any]],
    ) -> bool:
        rows = list(target_rows)
        if not rows:
            return False

        merchant_keys = {
            self._merchant_fingerprint(row.get("merchant"))
            for row in rows
            if self._merchant_fingerprint(row.get("merchant"))
        }
        description_keys = {
            self._description_fingerprint(row.get("description"))
            for row in rows
            if self._description_fingerprint(row.get("description"))
        }

        match_field = ""
        pattern = ""
        if len(merchant_keys) == 1:
            match_field = "merchant"
            pattern = next(iter(merchant_keys))
        elif len(description_keys) == 1:
            match_field = "description"
            pattern = next(iter(description_keys))
        if not match_field or not pattern:
            return False

        existing_rules = self.store.list_classification_rules()
        for rule in existing_rules:
            if not bool(rule.get("is_active", True)):
                continue
            if str(rule.get("match_field") or "") != match_field:
                continue
            if str(rule.get("pattern") or "") != pattern:
                continue
            if str(rule.get("analysis_category") or "") != category_name:
                continue
            return False

        self.store.add_classification_rule(
            match_field,
            pattern,
            analysis_category=category_name,
            priority=60,
            confidence=0.93,
        )
        return True

    def _group_key_for_row(self, row: dict[str, Any]) -> str:
        merchant_key = self._merchant_fingerprint(row.get("merchant"))
        if merchant_key:
            return f"merchant:{merchant_key}"
        description_key = self._description_fingerprint(row.get("description"))
        if description_key:
            return f"description:{description_key}"
        return f"transaction:{int(row['id'])}"

    def _merchant_fingerprint(self, value: str | None) -> str:
        normalized = normalize_entity_name(value)
        if not normalized:
            return ""
        compacted = re.sub(r"\bs\s*\.?\s*r\s*\.?\s*l\b", "srl", normalized)
        compacted = re.sub(r"\bs\s*\.?\s*a\b", "sa", compacted)
        cleaned = re.sub(r"[^a-z0-9]+", " ", compacted)
        tokens = [
            token
            for token in cleaned.split()
            if token and token not in LEGAL_SUFFIX_TOKENS and not token.isdigit()
        ]
        return " ".join(tokens)

    def _description_fingerprint(self, value: str | None) -> str:
        normalized = normalize_text(value)
        if not normalized:
            return ""
        cleaned = re.sub(r"[^a-z0-9]+", " ", normalized)
        tokens = []
        for token in cleaned.split():
            if token in DESCRIPTION_STOPWORDS:
                continue
            if token.isdigit():
                continue
            if len(token) < 3:
                continue
            tokens.append(token)
        return " ".join(tokens[:8])

    def _category_profiles(self, import_batch_id: int | None = None) -> dict[str, dict[str, dict[str, int]]]:
        params: list[Any] = []
        where_sql = ""
        if import_batch_id is not None:
            where_sql = "WHERE t.import_batch_id = ?"
            params.append(int(import_batch_id))
        rows = self.store.query(
            f"""
            SELECT
                t.merchant,
                t.description,
                ac.name AS category_name
            FROM transaction_category_links AS tcl
            INNER JOIN transactions AS t
                ON t.id = tcl.transaction_id
            INNER JOIN analysis_categories AS ac
                ON ac.id = tcl.category_id
            {where_sql}
            """,
            tuple(params),
        )
        profiles = {
            "merchant": {},
            "description": {},
        }
        for row in rows:
            category_name = str(row.get("category_name") or "").strip()
            if not category_name:
                continue
            merchant_key = self._merchant_fingerprint(row.get("merchant"))
            description_key = self._description_fingerprint(row.get("description"))
            if merchant_key:
                profiles["merchant"].setdefault(merchant_key, {})
                profiles["merchant"][merchant_key][category_name] = (
                    profiles["merchant"][merchant_key].get(category_name, 0) + 3
                )
            if description_key:
                profiles["description"].setdefault(description_key, {})
                profiles["description"][description_key][category_name] = (
                    profiles["description"][description_key].get(category_name, 0) + 2
                )
        return profiles

    def _suggest_categories_for_row(
        self,
        row: dict[str, Any],
        category_profiles: dict[str, dict[str, dict[str, int]]],
    ) -> list[str]:
        scores: dict[str, int] = {}
        merchant_key = self._merchant_fingerprint(row.get("merchant"))
        description_key = self._description_fingerprint(row.get("description"))

        for key, weight_map in (
            (merchant_key, category_profiles["merchant"].get(merchant_key, {})),
            (description_key, category_profiles["description"].get(description_key, {})),
        ):
            if not key:
                continue
            for category_name, score in weight_map.items():
                scores[category_name] = scores.get(category_name, 0) + score

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0].lower()))
        return [name for name, _ in ranked[:3]]

    def _normalize_category_key(self, value: str | None) -> str:
        normalized = normalize_text(value)
        if not normalized:
            return ""
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        tokens = [token for token in normalized.split() if token]
        stemmed_tokens = []
        for token in tokens:
            if token.endswith("i") and len(token) > 4:
                token = token[:-1]
            elif token.endswith("e") and len(token) > 4:
                token = token[:-1]
            elif token.endswith("uri") and len(token) > 5:
                token = token[:-3]
            stemmed_tokens.append(token)
        return " ".join(stemmed_tokens)

    def _severity_for_row(self, row: dict[str, Any]) -> str:
        amount_abs = abs(float(row.get("amount") or 0))
        confidence = float(row.get("confidence") or 0)
        has_category = bool(row.get("analysis_categories"))
        if row.get("direction") in (None, "", "both"):
            return "critical"
        if amount_abs >= 10000 and not has_category:
            return "critical"
        if amount_abs >= 2500 or confidence < 0.4:
            return "high"
        if amount_abs >= 500 or confidence < 0.6:
            return "medium"
        return "low"

    def _severity_rank(self, severity: str) -> int:
        ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return ranks.get(severity, 99)

    def _max_severity(self, left: str, right: str) -> str:
        return left if self._severity_rank(left) <= self._severity_rank(right) else right
