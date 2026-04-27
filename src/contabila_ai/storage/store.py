from __future__ import annotations

from contextlib import closing
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from contabila_ai.classification import classify_transaction, normalize_entity_name
from contabila_ai.importing.models import ImportedInvoice, ImportedTransaction
from contabila_ai.planning.models import QueryExecution, QueryPlan

from .schema import initialize_schema, invoice_row_hash, transaction_row_hash


class SQLiteTransactionStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self.connect()) as connection:
            initialize_schema(connection)
            self._backfill_legacy_import_batches(connection)
            self._prune_empty_import_batches(connection)
            connection.commit()
        self.reclassify_transactions()

    def create_workspace(self, name: str) -> int:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Workspace name is required.")
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO workspaces (name, status)
                VALUES (?, 'needs_import')
                """,
                (normalized_name,),
            )
            connection.commit()
        return int(cursor.lastrowid)

    def list_workspaces(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    w.id,
                    w.name,
                    w.status,
                    w.created_at,
                    w.updated_at,
                    COUNT(DISTINCT ib.id) AS import_count,
                    COUNT(t.id) AS transaction_count
                FROM workspaces AS w
                LEFT JOIN import_batches AS ib
                    ON ib.workspace_id = w.id
                LEFT JOIN transactions AS t
                    ON t.import_batch_id = ib.id
                GROUP BY w.id, w.name, w.status, w.created_at, w.updated_at
                ORDER BY w.created_at DESC, w.id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_many(
        self,
        transactions: Iterable[ImportedTransaction],
        *,
        workspace_id: int | None = None,
    ) -> dict[str, int]:
        transaction_list = list(transactions)
        if not transaction_list:
            return {"inserted": 0, "skipped": 0, "import_batch_id": 0}
        inserted = 0
        skipped = 0
        with closing(self.connect()) as connection:
            entity_memory = self._entity_memory_map(connection)
            analysis_rules = self._list_classification_rules(connection)
            import_batch_id = self._create_import_batch(
                connection,
                transaction_list[0],
                workspace_id=workspace_id,
                source_type="bank_statement",
            )
            for transaction in transaction_list:
                classification = classify_transaction(
                    merchant=transaction.merchant,
                    description=transaction.description,
                    amount=transaction.amount,
                    entity_memory=entity_memory,
                    analysis_rules=analysis_rules,
                )
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO transactions (
                        import_batch_id,
                        transaction_date,
                        description,
                        amount,
                        currency,
                        balance,
                        merchant,
                        source_file,
                        raw_payload,
                        row_hash,
                        economic_kind,
                        direction,
                        entity_type,
                        confidence,
                        reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        import_batch_id,
                        transaction.transaction_date,
                        transaction.description,
                        transaction.amount,
                        transaction.currency,
                        transaction.balance,
                        transaction.merchant,
                        transaction.source_file,
                        transaction.raw_payload,
                        transaction_row_hash(transaction),
                        classification.economic_kind,
                        classification.direction,
                        classification.entity_type,
                        classification.confidence,
                        classification.reason,
                    ),
                )
                if cursor.rowcount:
                    inserted += 1
                    for category_name in classification.analysis_categories:
                        self._link_transaction_category(connection, cursor.lastrowid, category_name)
                else:
                    skipped += 1
            connection.execute(
                """
                UPDATE import_batches
                SET transaction_count = ?
                WHERE id = ?
                """,
                (inserted, import_batch_id),
            )
            if workspace_id is not None:
                self._refresh_workspace_status(connection, workspace_id)
            connection.commit()
        return {"inserted": inserted, "skipped": skipped, "import_batch_id": import_batch_id}

    def insert_issued_invoices(self, invoices: Iterable[ImportedInvoice]) -> dict[str, int]:
        invoice_list = list(invoices)
        inserted = 0
        skipped = 0
        if not invoice_list:
            return {"inserted": 0, "skipped": 0}
        with closing(self.connect()) as connection:
            for invoice in invoice_list:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO issued_invoices (
                        invoice_number,
                        issue_date,
                        customer_name,
                        net_amount,
                        vat_amount,
                        total_amount,
                        currency,
                        status,
                        source_file,
                        raw_payload,
                        row_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice.invoice_number,
                        invoice.issue_date,
                        invoice.customer_name,
                        invoice.net_amount,
                        invoice.vat_amount,
                        invoice.total_amount,
                        invoice.currency,
                        invoice.status,
                        invoice.source_file,
                        invoice.raw_payload,
                        invoice_row_hash(invoice),
                    ),
                )
                if cursor.rowcount:
                    inserted += 1
                else:
                    skipped += 1
            connection.commit()
        return {"inserted": inserted, "skipped": skipped}

    def reclassify_transactions(self, import_batch_id: int | None = None) -> dict[str, int]:
        clauses: list[str] = []
        params: list[Any] = []
        if import_batch_id is not None:
            clauses.append("import_batch_id = ?")
            params.append(int(import_batch_id))
        where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
        updated = 0
        with closing(self.connect()) as connection:
            entity_memory = self._entity_memory_map(connection)
            analysis_rules = self._list_classification_rules(connection)
            rows = connection.execute(
                f"""
                SELECT id, merchant, description, amount
                FROM transactions
                {where_sql}
                ORDER BY id ASC
                """,
                tuple(params),
            ).fetchall()
            for row in rows:
                classification = classify_transaction(
                    merchant=row["merchant"],
                    description=row["description"],
                    amount=float(row["amount"]),
                    entity_memory=entity_memory,
                    analysis_rules=analysis_rules,
                )
                cursor = connection.execute(
                    """
                    UPDATE transactions
                    SET economic_kind = ?,
                        direction = ?,
                        entity_type = ?,
                        confidence = ?,
                        reason = ?
                    WHERE id = ?
                    """,
                    (
                        classification.economic_kind,
                        classification.direction,
                        classification.entity_type,
                        classification.confidence,
                        classification.reason,
                        int(row["id"]),
                    ),
                )
                updated += int(cursor.rowcount)
                for category_name in classification.analysis_categories:
                    self._link_transaction_category(connection, int(row["id"]), category_name)
            connection.commit()
        return {"updated_count": updated}

    def upsert_entity_memory(
        self,
        entity_name: str,
        entity_type: str,
        economic_kind: str | None = None,
        direction: str | None = None,
        confidence: float = 1.0,
        notes: str | None = None,
    ) -> None:
        normalized_name = normalize_entity_name(entity_name)
        with closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT INTO entity_memory (
                    entity_name,
                    entity_name_normalized,
                    entity_type,
                    economic_kind,
                    direction,
                    confidence,
                    notes,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(entity_name_normalized) DO UPDATE SET
                    entity_name=excluded.entity_name,
                    entity_type=excluded.entity_type,
                    economic_kind=excluded.economic_kind,
                    direction=excluded.direction,
                    confidence=excluded.confidence,
                    notes=excluded.notes,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (entity_name, normalized_name, entity_type, economic_kind, direction, confidence, notes),
            )
            connection.commit()

    def add_analysis_category(
        self,
        name: str,
        description: str | None = None,
        operational_scope: str = "unassigned",
    ) -> int:
        with closing(self.connect()) as connection:
            self._upsert_analysis_category_row(
                connection,
                name,
                description=description,
                operational_scope=operational_scope,
            )
            row = connection.execute(
                "SELECT id FROM analysis_categories WHERE name = ?",
                (name,),
            ).fetchone()
            connection.commit()
        return int(row["id"])

    def update_analysis_category(
        self,
        name: str,
        *,
        description: str | None = None,
        operational_scope: str | None = None,
    ) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            self._upsert_analysis_category_row(
                connection,
                name,
                description=description,
                operational_scope=operational_scope or "unassigned",
            )
            row = connection.execute(
                """
                SELECT id, name, description, operational_scope, created_at
                FROM analysis_categories
                WHERE name = ?
                """,
                (name,),
            ).fetchone()
            connection.commit()
        return dict(row)

    def add_classification_rule(
        self,
        match_field: str,
        pattern: str,
        *,
        rule_type: str = "contains",
        economic_kind: str | None = None,
        direction: str | None = None,
        entity_type: str | None = None,
        analysis_category: str | None = None,
        priority: int = 100,
        confidence: float = 0.78,
        is_active: bool = True,
    ) -> int:
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO classification_rules (
                    rule_type,
                    match_field,
                    pattern,
                    economic_kind,
                    direction,
                    entity_type,
                    analysis_category,
                    priority,
                    confidence,
                    is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule_type,
                    match_field,
                    pattern,
                    economic_kind,
                    direction,
                    entity_type,
                    analysis_category,
                    priority,
                    confidence,
                    1 if is_active else 0,
                ),
            )
            connection.commit()
        return int(cursor.lastrowid)

    def entity_memory_map(self) -> dict[str, dict[str, Any]]:
        with closing(self.connect()) as connection:
            return self._entity_memory_map(connection)

    def list_analysis_categories(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    ac.id,
                    ac.name,
                    ac.description,
                    ac.operational_scope,
                    ac.created_at,
                    COUNT(DISTINCT tcl.transaction_id) AS transaction_count,
                    COALESCE(ROUND(SUM(t.amount), 2), 0) AS net_amount,
                    COALESCE(ROUND(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 2), 0) AS total_expenses,
                    COALESCE(ROUND(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END), 2), 0) AS total_income
                FROM analysis_categories AS ac
                LEFT JOIN transaction_category_links AS tcl
                    ON tcl.category_id = ac.id
                LEFT JOIN transactions AS t
                    ON t.id = tcl.transaction_id
                GROUP BY ac.id, ac.name, ac.description, ac.operational_scope, ac.created_at
                ORDER BY name ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_transactions_for_category(
        self,
        category_name: str,
        *,
        import_batch_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [category_name.lower()]
        import_sql = ""
        if import_batch_id is not None:
            import_sql = "AND t.import_batch_id = ?"
            params.append(int(import_batch_id))
        params.append(int(limit))
        return self.query(
            f"""
            SELECT
                t.id,
                t.import_batch_id,
                t.transaction_date,
                t.amount,
                t.currency,
                t.balance,
                t.merchant,
                t.description,
                t.economic_kind,
                t.direction,
                t.entity_type,
                t.confidence,
                t.reason,
                COALESCE(GROUP_CONCAT(ac_all.name, ','), '') AS category_names
            FROM transactions AS t
            INNER JOIN transaction_category_links AS tcl
                ON tcl.transaction_id = t.id
            INNER JOIN analysis_categories AS ac_filter
                ON ac_filter.id = tcl.category_id
            LEFT JOIN transaction_category_links AS tcl_all
                ON tcl_all.transaction_id = t.id
            LEFT JOIN analysis_categories AS ac_all
                ON ac_all.id = tcl_all.category_id
            WHERE LOWER(ac_filter.name) = ?
            {import_sql}
            GROUP BY
                t.id,
                t.import_batch_id,
                t.transaction_date,
                t.amount,
                t.currency,
                t.balance,
                t.merchant,
                t.description,
                t.economic_kind,
                t.direction,
                t.entity_type,
                t.confidence,
                t.reason
            ORDER BY t.transaction_date DESC, t.id DESC
            LIMIT ?
            """,
            tuple(params),
        )

    def list_classification_rules(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            return self._list_classification_rules(connection)

    def list_import_batches(self, *, workspace_id: int | None = None) -> list[dict[str, Any]]:
        where_sql = ""
        params: tuple[Any, ...] = ()
        if workspace_id is not None:
            where_sql = "WHERE ib.workspace_id = ?"
            params = (int(workspace_id),)
        with closing(self.connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    ib.id,
                    ib.source_file,
                    ib.source_path,
                    ib.source_type,
                    ib.workspace_id,
                    ib.transaction_count,
                    ib.created_at,
                    MIN(t.transaction_date) AS first_transaction_date,
                    MAX(t.transaction_date) AS last_transaction_date
                FROM import_batches AS ib
                LEFT JOIN transactions AS t
                    ON t.import_batch_id = ib.id
                {where_sql}
                GROUP BY
                    ib.id,
                    ib.source_file,
                    ib.source_path,
                    ib.source_type,
                    ib.workspace_id,
                    ib.transaction_count,
                    ib.created_at
                ORDER BY ib.id DESC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_review_candidates(
        self,
        *,
        limit: int = 25,
        confidence_threshold: float = 0.75,
        import_batch_id: int | None = None,
        workspace_id: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = [
            "(COALESCE(t.confidence, 0) < ? OR t.direction IS NULL)",
            "LOWER(COALESCE(t.reason, '')) NOT LIKE '%review confirmed%'",
            "NOT EXISTS (SELECT 1 FROM transaction_category_links AS existing_tcl WHERE existing_tcl.transaction_id = t.id)",
        ]
        params: list[Any] = [confidence_threshold]
        if import_batch_id is not None:
            clauses.append("t.import_batch_id = ?")
            params.append(int(import_batch_id))
        if workspace_id is not None:
            clauses.append(
                """
                EXISTS (
                    SELECT 1
                    FROM import_batches AS ib
                    WHERE ib.id = t.import_batch_id
                      AND ib.workspace_id = ?
                )
                """.strip()
            )
            params.append(int(workspace_id))
        with closing(self.connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    t.id,
                    t.import_batch_id,
                    t.transaction_date,
                    t.amount,
                    t.currency,
                    t.merchant,
                    t.description,
                    t.economic_kind,
                    t.direction,
                    t.confidence,
                    t.reason,
                    COALESCE(GROUP_CONCAT(ac.name, ','), '') AS category_names
                FROM transactions AS t
                LEFT JOIN transaction_category_links AS tcl
                    ON tcl.transaction_id = t.id
                LEFT JOIN analysis_categories AS ac
                    ON ac.id = tcl.category_id
                WHERE {' AND '.join(clauses)}
                GROUP BY
                    t.id,
                    t.import_batch_id,
                    t.transaction_date,
                    t.amount,
                    t.currency,
                    t.merchant,
                    t.description,
                    t.economic_kind,
                    t.direction,
                    t.confidence,
                    t.reason
                ORDER BY COALESCE(t.confidence, 0) ASC, t.transaction_date DESC, t.id DESC
                LIMIT ?
                """,
                (*params, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_transactions_by_ids(
        self,
        transaction_ids: Iterable[int],
    ) -> list[dict[str, Any]]:
        resolved_ids = [int(transaction_id) for transaction_id in transaction_ids]
        if not resolved_ids:
            return []
        placeholders = ", ".join("?" for _ in resolved_ids)
        with closing(self.connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT id, merchant, description, confidence, reason
                FROM transactions
                WHERE id IN ({placeholders})
                ORDER BY id ASC
                """,
                tuple(resolved_ids),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_transactions_for_similarity(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, import_batch_id, merchant, description
                FROM transactions
                ORDER BY id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_transactions(
        self,
        *,
        import_batch_id: int | None = None,
        min_abs_amount: float | None = None,
        max_abs_amount: float | None = None,
        direction: str | None = None,
        economic_kind: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if import_batch_id is not None:
            clauses.append("t.import_batch_id = ?")
            params.append(int(import_batch_id))
        if min_abs_amount is not None:
            clauses.append("ABS(t.amount) >= ?")
            params.append(float(min_abs_amount))
        if max_abs_amount is not None:
            clauses.append("ABS(t.amount) <= ?")
            params.append(float(max_abs_amount))
        if direction in {"inflow", "outflow"}:
            clauses.append("t.direction = ?")
            params.append(direction)
        if economic_kind:
            clauses.append("t.economic_kind = ?")
            params.append(economic_kind)
        if search:
            clauses.append("(LOWER(COALESCE(t.merchant, '')) LIKE ? OR LOWER(t.description) LIKE ?)")
            pattern = f"%{search.lower()}%"
            params.extend([pattern, pattern])
        where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
        with closing(self.connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    t.id,
                    t.import_batch_id,
                    t.transaction_date,
                    t.amount,
                    t.currency,
                    t.balance,
                    t.merchant,
                    t.description,
                    t.economic_kind,
                    t.direction,
                    t.entity_type,
                    t.confidence,
                    t.reason,
                    COALESCE(GROUP_CONCAT(ac.name, ','), '') AS category_names,
                    CASE
                        WHEN COALESCE(t.confidence, 0) >= 0.75 THEN 'classified'
                        ELSE 'needs_review'
                    END AS review_status
                FROM transactions AS t
                LEFT JOIN transaction_category_links AS tcl
                    ON tcl.transaction_id = t.id
                LEFT JOIN analysis_categories AS ac
                    ON ac.id = tcl.category_id
                {where_sql}
                GROUP BY
                    t.id,
                    t.import_batch_id,
                    t.transaction_date,
                    t.amount,
                    t.currency,
                    t.balance,
                    t.merchant,
                    t.description,
                    t.economic_kind,
                    t.direction,
                    t.entity_type,
                    t.confidence,
                    t.reason
                ORDER BY ABS(t.amount) DESC, t.transaction_date DESC, t.id DESC
                LIMIT ?
                """,
                (*params, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def assign_analysis_category(
        self,
        category_name: str,
        transaction_ids: Iterable[int],
        *,
        description: str | None = None,
        operational_scope: str = "unassigned",
        replace_existing: bool = False,
    ) -> int:
        resolved_ids = sorted({int(transaction_id) for transaction_id in transaction_ids})
        if not resolved_ids:
            return 0
        with closing(self.connect()) as connection:
            self._upsert_analysis_category_row(
                connection,
                category_name,
                description=description,
                operational_scope=operational_scope,
            )
            if replace_existing:
                placeholders = ", ".join("?" for _ in resolved_ids)
                connection.execute(
                    f"""
                    DELETE FROM transaction_category_links
                    WHERE transaction_id IN ({placeholders})
                    """,
                    tuple(resolved_ids),
                )
            for transaction_id in resolved_ids:
                self._link_transaction_category(connection, transaction_id, category_name)
            connection.commit()
        return len(resolved_ids)

    def confirm_transaction_review(self, transaction_id: int) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                UPDATE transactions
                SET
                    confidence = CASE
                        WHEN confidence IS NULL OR confidence < 0.99 THEN 0.99
                        ELSE confidence
                    END,
                    reason = CASE
                        WHEN COALESCE(reason, '') = '' THEN 'review confirmed'
                        WHEN LOWER(reason) LIKE '%review confirmed%' THEN reason
                        ELSE reason || '; review confirmed'
                    END
                WHERE id = ?
                """,
                (int(transaction_id),),
            )
            connection.commit()

    def reset_all_data(self) -> None:
        with closing(self.connect()) as connection:
            connection.execute("DELETE FROM transaction_category_links")
            connection.execute("DELETE FROM transactions")
            connection.execute("DELETE FROM import_batches")
            connection.execute("DELETE FROM analysis_categories")
            connection.execute("DELETE FROM issued_invoices")
            connection.execute("DELETE FROM accounts")
            connection.execute("DELETE FROM workspaces")
            connection.commit()

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def execute_plan(self, plan: QueryPlan) -> QueryExecution:
        if plan.metric == "unsupported":
            return QueryExecution(plan=plan, sql="", params=(), rows=[])
        if plan.metric == "creditare_vs_recuperare":
            sql, params = self._build_creditare_recovery_query(plan)
            rows = self.query(sql, params)
            return QueryExecution(plan=plan, sql=sql, params=params, rows=rows)
        if plan.metric == "operational_income_estimate" and self._has_matching_issued_invoices(plan):
            sql, params = self._build_invoice_turnover_query(plan)
            rows = self.query(sql, params)
            return QueryExecution(plan=plan, sql=sql, params=params, rows=rows)
        if plan.mode == "search":
            sql, params = self._build_search_query(plan)
        else:
            sql, params = self._build_aggregate_query(plan)
        rows = self.query(sql, params)
        return QueryExecution(plan=plan, sql=sql, params=params, rows=rows)

    def execute_plan_for_import(
        self,
        plan: QueryPlan,
        import_batch_id: int | None = None,
    ) -> QueryExecution:
        if plan.metric == "unsupported":
            return QueryExecution(plan=plan, sql="", params=(), rows=[])
        if plan.metric == "creditare_vs_recuperare":
            sql, params = self._build_creditare_recovery_query(plan, import_batch_id=import_batch_id)
            rows = self.query(sql, params)
            return QueryExecution(plan=plan, sql=sql, params=params, rows=rows)
        if plan.metric == "operational_income_estimate" and self._has_matching_issued_invoices(plan):
            sql, params = self._build_invoice_turnover_query(plan)
            rows = self.query(sql, params)
            return QueryExecution(plan=plan, sql=sql, params=params, rows=rows)
        if plan.mode == "search":
            sql, params = self._build_search_query(plan, import_batch_id=import_batch_id)
        else:
            sql, params = self._build_aggregate_query(plan, import_batch_id=import_batch_id)
        rows = self.query(sql, params)
        return QueryExecution(plan=plan, sql=sql, params=params, rows=rows)

    def list_matching_transactions_for_plan(
        self,
        plan: QueryPlan,
        import_batch_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if plan.metric == "unsupported":
            return []
        if plan.metric == "creditare_vs_recuperare":
            return self.query(*self._build_creditare_recovery_rows_query(plan, import_batch_id=import_batch_id))
        if plan.metric == "operational_income_estimate" and self._has_matching_issued_invoices(plan):
            return self.query(*self._build_invoice_rows_query(plan))
        sql, params = self._build_search_query(plan, import_batch_id=import_batch_id)
        return self.query(sql, params)

    def summary(self, import_batch_id: int | None = None) -> dict[str, Any]:
        where_sql = ""
        params: tuple[Any, ...] = ()
        if import_batch_id is not None:
            where_sql = "WHERE import_batch_id = ?"
            params = (int(import_batch_id),)
        with closing(self.connect()) as connection:
            row = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS transaction_count,
                    MIN(transaction_date) AS first_transaction_date,
                    MAX(transaction_date) AS last_transaction_date,
                    COALESCE(ROUND(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 2), 0) AS total_expenses,
                    COALESCE(ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2), 0) AS total_income,
                    COALESCE(ROUND(SUM(amount), 2), 0) AS net_cashflow
                FROM transactions
                {where_sql}
                """,
                params,
            ).fetchone()
        return dict(row)

    def issued_invoice_summary(self) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS invoice_count,
                    MIN(issue_date) AS first_invoice_date,
                    MAX(issue_date) AS last_invoice_date,
                    COALESCE(ROUND(SUM(net_amount), 2), 0) AS net_revenue,
                    COALESCE(ROUND(SUM(vat_amount), 2), 0) AS vat_total,
                    COALESCE(ROUND(SUM(total_amount), 2), 0) AS gross_total
                FROM issued_invoices
                WHERE LOWER(status) NOT IN ('cancelled', 'canceled', 'stornata', 'storno')
                """
            ).fetchone()
        return dict(row)

    def _entity_memory_map(self, connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT
                entity_name_normalized,
                entity_name,
                entity_type,
                economic_kind,
                direction,
                confidence,
                notes
            FROM entity_memory
            """
        ).fetchall()
        return {
            row["entity_name_normalized"]: dict(row)
            for row in rows
        }

    def _list_classification_rules(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT
                id,
                rule_type,
                match_field,
                pattern,
                economic_kind,
                direction,
                entity_type,
                analysis_category,
                priority,
                confidence,
                is_active
            FROM classification_rules
            ORDER BY priority ASC, id ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def _backfill_legacy_import_batches(self, connection: sqlite3.Connection) -> None:
        legacy_rows = connection.execute(
            """
            SELECT source_file, COUNT(*) AS transaction_count
            FROM transactions
            WHERE import_batch_id IS NULL
            GROUP BY source_file
            ORDER BY source_file ASC
            """
        ).fetchall()
        for row in legacy_rows:
            source_file = str(row["source_file"] or "legacy-import")
            cursor = connection.execute(
                """
                INSERT INTO import_batches (source_file, source_path, source_type, workspace_id, transaction_count)
                VALUES (?, ?, 'bank_statement', NULL, ?)
                """,
                (
                    Path(source_file).name or source_file,
                    source_file,
                    int(row["transaction_count"]),
                ),
            )
            connection.execute(
                """
                UPDATE transactions
                SET import_batch_id = ?
                WHERE import_batch_id IS NULL
                  AND source_file = ?
                """,
                (int(cursor.lastrowid), source_file),
            )

    def _prune_empty_import_batches(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM import_batches
            WHERE id IN (
                SELECT ib.id
                FROM import_batches AS ib
                LEFT JOIN transactions AS t
                    ON t.import_batch_id = ib.id
                GROUP BY ib.id
                HAVING COUNT(t.id) = 0
            )
            """
        )

    def _create_import_batch(
        self,
        connection: sqlite3.Connection,
        transaction: ImportedTransaction,
        *,
        workspace_id: int | None = None,
        source_type: str = "bank_statement",
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO import_batches (source_file, source_path, source_type, workspace_id, transaction_count)
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                Path(transaction.source_file).name or transaction.source_file,
                str(transaction.source_file),
                source_type,
                workspace_id,
            ),
        )
        return int(cursor.lastrowid)

    def _refresh_workspace_status(self, connection: sqlite3.Connection, workspace_id: int) -> None:
        row = connection.execute(
            """
            SELECT COUNT(*) AS import_count
            FROM import_batches
            WHERE workspace_id = ?
            """,
            (int(workspace_id),),
        ).fetchone()
        import_count = int(row["import_count"] or 0)
        status = "ready" if import_count > 0 else "needs_import"
        connection.execute(
            """
            UPDATE workspaces
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, int(workspace_id)),
        )

    def _link_transaction_category(
        self,
        connection: sqlite3.Connection,
        transaction_id: int,
        category_name: str,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO analysis_categories (name, operational_scope)
            VALUES (?, 'unassigned')
            """,
            (category_name,),
        )
        category_row = connection.execute(
            "SELECT id FROM analysis_categories WHERE name = ?",
            (category_name,),
        ).fetchone()
        connection.execute(
            """
            INSERT OR IGNORE INTO transaction_category_links (transaction_id, category_id)
            VALUES (?, ?)
            """,
            (transaction_id, category_row["id"]),
        )

    def _upsert_analysis_category_row(
        self,
        connection: sqlite3.Connection,
        name: str,
        *,
        description: str | None = None,
        operational_scope: str = "unassigned",
    ) -> None:
        connection.execute(
            """
            INSERT INTO analysis_categories (name, description, operational_scope)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = CASE
                    WHEN excluded.description IS NULL OR excluded.description = ''
                    THEN analysis_categories.description
                    ELSE excluded.description
                END,
                operational_scope = CASE
                    WHEN excluded.operational_scope IS NULL OR excluded.operational_scope = ''
                    THEN analysis_categories.operational_scope
                    ELSE excluded.operational_scope
                END
            """,
            (name, description, operational_scope),
        )

    def _build_search_query(
        self,
        plan: QueryPlan,
        *,
        import_batch_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._plan_filters(plan, table_alias="t", import_batch_id=import_batch_id)
        sql = f"""
            SELECT
                t.transaction_date,
                t.merchant,
                t.description,
                t.amount,
                t.currency,
                t.economic_kind,
                t.direction
            FROM transactions AS t
            {where_sql}
            ORDER BY t.transaction_date DESC, t.id DESC
            LIMIT {int(plan.limit)}
        """
        return sql.strip(), params

    def _build_aggregate_query(
        self,
        plan: QueryPlan,
        *,
        import_batch_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._plan_filters(plan, table_alias="t", import_batch_id=import_batch_id)
        group_select = "NULL AS group_key"
        group_by_sql = ""
        order_by_sql = ""

        if plan.group_by == "year":
            group_select = "strftime('%Y', t.transaction_date) AS group_key"
            group_by_sql = "GROUP BY strftime('%Y', t.transaction_date)"
            order_by_sql = "ORDER BY group_key ASC"
        elif plan.group_by == "half_year":
            group_select = (
                "strftime('%Y', t.transaction_date) || '-H' || "
                "CASE WHEN CAST(strftime('%m', t.transaction_date) AS INTEGER) <= 6 "
                "THEN '1' ELSE '2' END AS group_key"
            )
            group_by_sql = (
                "GROUP BY strftime('%Y', t.transaction_date), "
                "CASE WHEN CAST(strftime('%m', t.transaction_date) AS INTEGER) <= 6 THEN 1 ELSE 2 END"
            )
            order_by_sql = "ORDER BY group_key ASC"

        sql = f"""
            SELECT
                {group_select},
                {self._metric_sql(plan.metric)} AS metric_value,
                COUNT(*) AS transaction_count
            FROM transactions AS t
            {where_sql}
            {group_by_sql}
            {order_by_sql}
        """
        return sql.strip(), params

    def _build_invoice_turnover_query(self, plan: QueryPlan) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._invoice_filters(plan)
        group_select = "NULL AS group_key"
        group_by_sql = ""
        order_by_sql = ""
        if plan.group_by == "year":
            group_select = "strftime('%Y', issue_date) AS group_key"
            group_by_sql = "GROUP BY strftime('%Y', issue_date)"
            order_by_sql = "ORDER BY group_key ASC"
        elif plan.group_by == "half_year":
            group_select = (
                "strftime('%Y', issue_date) || '-H' || "
                "CASE WHEN CAST(strftime('%m', issue_date) AS INTEGER) <= 6 THEN '1' ELSE '2' END AS group_key"
            )
            group_by_sql = (
                "GROUP BY strftime('%Y', issue_date), "
                "CASE WHEN CAST(strftime('%m', issue_date) AS INTEGER) <= 6 THEN 1 ELSE 2 END"
            )
            order_by_sql = "ORDER BY group_key ASC"
        sql = f"""
            SELECT
                {group_select},
                ROUND(COALESCE(SUM(net_amount), 0), 2) AS metric_value,
                COUNT(*) AS transaction_count,
                'issued_invoices' AS source
            FROM issued_invoices
            {where_sql}
            {group_by_sql}
            {order_by_sql}
        """
        return sql.strip(), params

    def _build_creditare_recovery_query(
        self,
        plan: QueryPlan,
        *,
        import_batch_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._creditare_recovery_filters(plan, import_batch_id=import_batch_id)
        sql = f"""
            SELECT
                economic_kind AS group_key,
                ROUND(COALESCE(SUM(ABS(amount)), 0), 2) AS metric_value,
                COUNT(*) AS transaction_count
            FROM transactions
            {where_sql}
            GROUP BY economic_kind
            ORDER BY CASE economic_kind
                WHEN 'creditare' THEN 1
                WHEN 'recuperare_creditare' THEN 2
                ELSE 3
            END
        """
        return sql.strip(), params

    def _build_creditare_recovery_rows_query(
        self,
        plan: QueryPlan,
        *,
        import_batch_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._creditare_recovery_filters(plan, import_batch_id=import_batch_id)
        sql = f"""
            SELECT
                transaction_date,
                merchant,
                description,
                amount,
                currency,
                economic_kind,
                direction
            FROM transactions
            {where_sql}
            ORDER BY transaction_date DESC, id DESC
            LIMIT {int(plan.limit)}
        """
        return sql.strip(), params

    def _creditare_recovery_filters(
        self,
        plan: QueryPlan,
        *,
        import_batch_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses = ["economic_kind IN ('creditare', 'recuperare_creditare')"]
        params: list[Any] = []
        if import_batch_id is not None:
            clauses.append("import_batch_id = ?")
            params.append(int(import_batch_id))
        if plan.years:
            placeholders = ", ".join("?" for _ in plan.years)
            clauses.append(f"CAST(strftime('%Y', transaction_date) AS INTEGER) IN ({placeholders})")
            params.extend(plan.years)
        return "WHERE " + " AND ".join(clauses), tuple(params)

    def _build_invoice_rows_query(self, plan: QueryPlan) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._invoice_filters(plan)
        sql = f"""
            SELECT
                issue_date AS transaction_date,
                customer_name AS merchant,
                'Factura emisa ' || invoice_number AS description,
                net_amount AS amount,
                currency,
                'issued_invoice' AS economic_kind,
                'inflow' AS direction
            FROM issued_invoices
            {where_sql}
            ORDER BY issue_date DESC, id DESC
            LIMIT {int(plan.limit)}
        """
        return sql.strip(), params

    def _invoice_filters(self, plan: QueryPlan) -> tuple[str, tuple[Any, ...]]:
        clauses = ["LOWER(status) NOT IN ('cancelled', 'canceled', 'stornata', 'storno')"]
        params: list[Any] = []
        if plan.years:
            placeholders = ", ".join("?" for _ in plan.years)
            clauses.append(f"CAST(strftime('%Y', issue_date) AS INTEGER) IN ({placeholders})")
            params.extend(plan.years)
        return "WHERE " + " AND ".join(clauses), tuple(params)

    def _has_matching_issued_invoices(self, plan: QueryPlan) -> bool:
        where_sql, params = self._invoice_filters(plan)
        rows = self.query(
            f"""
            SELECT COUNT(*) AS invoice_count
            FROM issued_invoices
            {where_sql}
            """,
            params,
        )
        return bool(rows and int(rows[0]["invoice_count"]) > 0)

    def _plan_filters(
        self,
        plan: QueryPlan,
        table_alias: str,
        *,
        import_batch_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses: list[str] = []
        params: list[Any] = []

        if import_batch_id is not None:
            clauses.append(f"{table_alias}.import_batch_id = ?")
            params.append(int(import_batch_id))

        if plan.years:
            placeholders = ", ".join("?" for _ in plan.years)
            clauses.append(
                f"CAST(strftime('%Y', {table_alias}.transaction_date) AS INTEGER) IN ({placeholders})"
            )
            params.extend(plan.years)
        elif getattr(plan, "relative_period", None) == "first_year":
            clauses.append(
                f"""
                CAST(strftime('%Y', {table_alias}.transaction_date) AS INTEGER) = (
                    SELECT MIN(CAST(strftime('%Y', first_period.transaction_date) AS INTEGER))
                    FROM transactions AS first_period
                    WHERE (? IS NULL OR first_period.import_batch_id = ?)
                )
                """.strip()
            )
            params.extend([import_batch_id, import_batch_id])

        if plan.economic_kind:
            clauses.append(f"{table_alias}.economic_kind = ?")
            params.append(plan.economic_kind)

        if plan.excluded_economic_kinds:
            placeholders = ", ".join("?" for _ in plan.excluded_economic_kinds)
            clauses.append(
                f"({table_alias}.economic_kind IS NULL OR {table_alias}.economic_kind NOT IN ({placeholders}))"
            )
            params.extend(plan.excluded_economic_kinds)

        if plan.analysis_category:
            clauses.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM transaction_category_links AS tcl
                    INNER JOIN analysis_categories AS ac
                        ON ac.id = tcl.category_id
                    WHERE tcl.transaction_id = {table_alias}.id
                      AND LOWER(ac.name) = ?
                )
                """.strip()
            )
            params.append(plan.analysis_category)

        if plan.entity_name:
            clauses.append(f"LOWER(COALESCE({table_alias}.merchant, '')) LIKE ?")
            params.append(f"%{plan.entity_name.lower()}%")

        if plan.direction == "inflow":
            clauses.append(f"{table_alias}.amount > 0")
        elif plan.direction == "outflow":
            clauses.append(f"{table_alias}.amount < 0")

        if not clauses:
            return "", ()
        return "WHERE " + " AND ".join(clauses), tuple(params)

    def _metric_sql(self, metric: str) -> str:
        if metric == "transaction_count":
            return "COUNT(*)"
        if metric == "expense_total":
            return "ROUND(COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0), 2)"
        if metric == "income_total":
            return "ROUND(COALESCE(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END), 0), 2)"
        if metric == "operational_income_estimate":
            return "ROUND(COALESCE(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END), 0), 2)"
        if metric == "operational_expense_estimate":
            return "ROUND(COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0), 2)"
        return "ROUND(COALESCE(SUM(t.amount), 0), 2)"
