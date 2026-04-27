from __future__ import annotations

from contextlib import closing
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from contabila_ai.classification import classify_transaction, normalize_entity_name
from contabila_ai.importing.models import ImportedInvoice, ImportedTransaction
from contabila_ai.memory.models import BusinessFact
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

    def insert_issued_invoices(
        self,
        invoices: Iterable[ImportedInvoice],
        *,
        workspace_id: int | None = None,
        import_batch_id: int | None = None,
    ) -> dict[str, int]:
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
                if workspace_id is not None:
                    self._insert_workspace_invoice_row(
                        connection,
                        workspace_id=int(workspace_id),
                        import_batch_id=import_batch_id,
                        role="issued",
                        invoice=invoice,
                    )
            connection.commit()
        return {"inserted": inserted, "skipped": skipped}

    def insert_invoices(
        self,
        *,
        workspace_id: int,
        import_batch_id: int | None,
        role: str,
        invoices: Iterable[ImportedInvoice],
    ) -> dict[str, int]:
        invoice_list = list(invoices)
        inserted = 0
        skipped = 0
        if not invoice_list:
            return {"inserted": 0, "skipped": 0}
        normalized_role = role.strip().lower() or "issued"
        with closing(self.connect()) as connection:
            for invoice in invoice_list:
                cursor = self._insert_workspace_invoice_row(
                    connection,
                    workspace_id=int(workspace_id),
                    import_batch_id=import_batch_id,
                    role=normalized_role,
                    invoice=invoice,
                )
                if cursor.rowcount:
                    inserted += 1
                else:
                    skipped += 1
            self._refresh_workspace_status(connection, int(workspace_id))
            connection.commit()
        return {"inserted": inserted, "skipped": skipped}

    def create_document_import_batch(
        self,
        *,
        source_path: Path | str,
        workspace_id: int,
        source_type: str,
    ) -> int:
        resolved_path = Path(source_path)
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO import_batches (source_file, source_path, source_type, workspace_id, transaction_count)
                VALUES (?, ?, ?, ?, 0)
                """,
                (
                    resolved_path.name or str(resolved_path),
                    str(resolved_path),
                    source_type,
                    int(workspace_id),
                ),
            )
            self._refresh_workspace_status(connection, int(workspace_id))
            connection.commit()
        return int(cursor.lastrowid)

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

    def add_business_instruction(self, *, workspace_id: int, raw_text: str) -> int:
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO business_instructions (workspace_id, raw_text)
                VALUES (?, ?)
                """,
                (int(workspace_id), raw_text),
            )
            connection.commit()
        return int(cursor.lastrowid)

    def add_business_facts(
        self,
        *,
        workspace_id: int,
        instruction_id: int,
        facts: Iterable[BusinessFact],
    ) -> int:
        fact_list = list(facts)
        inserted = 0
        with closing(self.connect()) as connection:
            for fact in fact_list:
                cursor = connection.execute(
                    """
                    INSERT INTO business_facts (
                        workspace_id,
                        instruction_id,
                        fact_type,
                        subject_name,
                        fact_value,
                        extra_json,
                        confidence,
                        status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(workspace_id),
                        int(instruction_id),
                        fact.fact_type,
                        fact.subject_name,
                        fact.fact_value,
                        fact.extra_json,
                        fact.confidence,
                        fact.status,
                    ),
                )
                inserted += int(cursor.rowcount)
            connection.commit()
        return inserted

    def list_business_facts(self, workspace_id: int) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    bf.id,
                    bf.workspace_id,
                    bf.instruction_id,
                    bf.fact_type,
                    bf.subject_name,
                    bf.fact_value,
                    bf.extra_json,
                    bf.confidence,
                    bf.status,
                    bf.created_at,
                    bi.raw_text
                FROM business_facts AS bf
                LEFT JOIN business_instructions AS bi
                    ON bi.id = bf.instruction_id
                WHERE bf.workspace_id = ?
                ORDER BY bf.created_at DESC, bf.id DESC
                """,
                (int(workspace_id),),
            ).fetchall()
        return [dict(row) for row in rows]

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
        workspace_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [category_name.lower()]
        filter_sql = ""
        if import_batch_id is not None:
            filter_sql += " AND t.import_batch_id = ?"
            params.append(int(import_batch_id))
        if workspace_id is not None:
            filter_sql += " AND t.import_batch_id IN (SELECT id FROM import_batches WHERE workspace_id = ?)"
            params.append(int(workspace_id))
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
            {filter_sql}
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

    def list_workspace_invoices(
        self,
        workspace_id: int,
        *,
        role: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [int(workspace_id)]
        role_sql = ""
        if role:
            role_sql = "AND role = ?"
            params.append(role.strip().lower())
        params.append(int(limit))
        with closing(self.connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    workspace_id,
                    import_batch_id,
                    role,
                    invoice_number,
                    issue_date,
                    counterparty_name,
                    net_amount,
                    vat_amount,
                    total_amount,
                    currency,
                    status,
                    source_file,
                    created_at
                FROM invoices
                WHERE workspace_id = ?
                {role_sql}
                ORDER BY issue_date DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_workspace_invoices_for_matching(self, workspace_id: int) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    i.id,
                    i.workspace_id,
                    i.import_batch_id,
                    i.role,
                    i.invoice_number,
                    i.issue_date,
                    i.counterparty_name,
                    i.total_amount,
                    i.currency,
                    ROUND(
                        COALESCE(
                            SUM(
                                CASE
                                    WHEN im.status IN ('proposed', 'accepted')
                                    THEN im.matched_amount
                                    ELSE 0
                                END
                            ),
                            0
                        ),
                        2
                    ) AS matched_amount,
                    ROUND(
                        i.total_amount - COALESCE(
                            SUM(
                                CASE
                                    WHEN im.status IN ('proposed', 'accepted')
                                    THEN im.matched_amount
                                    ELSE 0
                                END
                            ),
                            0
                        ),
                        2
                    ) AS remaining_amount
                FROM invoices AS i
                LEFT JOIN invoice_matches AS im
                    ON im.invoice_id = i.id
                WHERE i.workspace_id = ?
                  AND i.role = 'received'
                GROUP BY
                    i.id,
                    i.workspace_id,
                    i.import_batch_id,
                    i.role,
                    i.invoice_number,
                    i.issue_date,
                    i.counterparty_name,
                    i.total_amount,
                    i.currency
                HAVING remaining_amount > 0.01
                ORDER BY i.issue_date ASC, i.id ASC
                """,
                (int(workspace_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_unmatched_workspace_transactions(self, workspace_id: int) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    t.id,
                    t.transaction_date,
                    t.amount,
                    t.currency,
                    t.merchant,
                    t.description,
                    ib.workspace_id
                FROM transactions AS t
                INNER JOIN import_batches AS ib
                    ON ib.id = t.import_batch_id
                LEFT JOIN invoice_matches AS im
                    ON im.transaction_id = t.id
                   AND im.status IN ('proposed', 'accepted')
                WHERE ib.workspace_id = ?
                  AND im.id IS NULL
                  AND t.amount < 0
                ORDER BY t.transaction_date ASC, t.id ASC
                """,
                (int(workspace_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_invoice_match(
        self,
        *,
        workspace_id: int,
        transaction_id: int,
        invoice_id: int,
        match_kind: str,
        matched_amount: float,
        residual_amount: float,
        confidence: float,
        reasoning: str,
        status: str = "proposed",
    ) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO invoice_matches (
                    workspace_id,
                    transaction_id,
                    invoice_id,
                    match_kind,
                    matched_amount,
                    residual_amount,
                    confidence,
                    reasoning,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(workspace_id),
                    int(transaction_id),
                    int(invoice_id),
                    match_kind,
                    float(matched_amount),
                    float(residual_amount),
                    float(confidence),
                    reasoning,
                    status,
                ),
            )
            row = connection.execute(
                """
                SELECT
                    id,
                    workspace_id,
                    transaction_id,
                    invoice_id,
                    match_kind,
                    matched_amount,
                    residual_amount,
                    confidence,
                    reasoning,
                    status,
                    created_at
                FROM invoice_matches
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
            connection.commit()
        return dict(row)

    def list_invoice_matches(self, workspace_id: int) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    workspace_id,
                    transaction_id,
                    invoice_id,
                    match_kind,
                    matched_amount,
                    residual_amount,
                    confidence,
                    reasoning,
                    status,
                    created_at
                FROM invoice_matches
                WHERE workspace_id = ?
                ORDER BY id ASC
                """,
                (int(workspace_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_workspace_invoice_by_id(self, invoice_id: int) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    workspace_id,
                    import_batch_id,
                    role,
                    invoice_number,
                    issue_date,
                    counterparty_name,
                    net_amount,
                    vat_amount,
                    total_amount,
                    currency,
                    status,
                    source_file,
                    raw_payload,
                    created_at
                FROM invoices
                WHERE id = ?
                """,
                (int(invoice_id),),
            ).fetchone()
        return dict(row) if row is not None else None

    def fetch_transaction_by_id(self, transaction_id: int) -> dict[str, Any] | None:
        rows = self.fetch_transactions_by_ids([transaction_id])
        return rows[0] if rows else None

    def list_workspace_transactions_with_categories(self, workspace_id: int) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    t.id,
                    t.merchant,
                    COALESCE(GROUP_CONCAT(ac.name, ','), '') AS category_names
                FROM transactions AS t
                INNER JOIN import_batches AS ib
                    ON ib.id = t.import_batch_id
                LEFT JOIN transaction_category_links AS tcl
                    ON tcl.transaction_id = t.id
                LEFT JOIN analysis_categories AS ac
                    ON ac.id = tcl.category_id
                WHERE ib.workspace_id = ?
                GROUP BY t.id, t.merchant
                ORDER BY t.id ASC
                """,
                (int(workspace_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_change_review_item(
        self,
        *,
        workspace_id: int,
        transaction_id: int | None,
        field_name: str,
        old_value: str,
        new_value: str,
        reason: str,
        confidence: float,
    ) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            existing = connection.execute(
                """
                SELECT
                    id,
                    workspace_id,
                    transaction_id,
                    field_name,
                    old_value,
                    new_value,
                    reason,
                    confidence,
                    status,
                    created_at
                FROM change_review_items
                WHERE workspace_id = ?
                  AND transaction_id IS ?
                  AND field_name = ?
                  AND COALESCE(new_value, '') = COALESCE(?, '')
                  AND status = 'pending'
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    int(workspace_id),
                    None if transaction_id is None else int(transaction_id),
                    field_name,
                    new_value,
                ),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            cursor = connection.execute(
                """
                INSERT INTO change_review_items (
                    workspace_id,
                    transaction_id,
                    field_name,
                    old_value,
                    new_value,
                    reason,
                    confidence,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    int(workspace_id),
                    None if transaction_id is None else int(transaction_id),
                    field_name,
                    old_value,
                    new_value,
                    reason,
                    float(confidence),
                ),
            )
            row = connection.execute(
                """
                SELECT
                    id,
                    workspace_id,
                    transaction_id,
                    field_name,
                    old_value,
                    new_value,
                    reason,
                    confidence,
                    status,
                    created_at
                FROM change_review_items
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
            connection.commit()
        return dict(row)

    def list_change_review_items(self, workspace_id: int) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    workspace_id,
                    transaction_id,
                    field_name,
                    old_value,
                    new_value,
                    reason,
                    confidence,
                    status,
                    created_at
                FROM change_review_items
                WHERE workspace_id = ?
                ORDER BY status ASC, id DESC
                """,
                (int(workspace_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_change_review_item(self, item_id: int) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    workspace_id,
                    transaction_id,
                    field_name,
                    old_value,
                    new_value,
                    reason,
                    confidence,
                    status,
                    created_at
                FROM change_review_items
                WHERE id = ?
                """,
                (int(item_id),),
            ).fetchone()
        if row is None:
            raise ValueError("Change review item not found.")
        return dict(row)

    def set_change_review_status(self, item_id: int, status: str) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                UPDATE change_review_items
                SET status = ?
                WHERE id = ?
                """,
                (status, int(item_id)),
            )
            connection.commit()

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
        workspace_id: int | None = None,
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
        if workspace_id is not None:
            clauses.append("t.import_batch_id IN (SELECT id FROM import_batches WHERE workspace_id = ?)")
            params.append(int(workspace_id))
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
            connection.execute("DELETE FROM change_review_items")
            connection.execute("DELETE FROM invoice_matches")
            connection.execute("DELETE FROM invoices")
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
        if plan.metric == "invoice_residual_total":
            sql, params = self._build_invoice_residual_query(plan)
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
        workspace_id: int | None = None,
    ) -> QueryExecution:
        if plan.metric == "unsupported":
            return QueryExecution(plan=plan, sql="", params=(), rows=[])
        if plan.metric == "creditare_vs_recuperare":
            sql, params = self._build_creditare_recovery_query(
                plan,
                import_batch_id=import_batch_id,
                workspace_id=workspace_id,
            )
            rows = self.query(sql, params)
            return QueryExecution(plan=plan, sql=sql, params=params, rows=rows)
        if plan.metric == "invoice_residual_total":
            sql, params = self._build_invoice_residual_query(
                plan,
                workspace_id=workspace_id,
            )
            rows = self.query(sql, params)
            return QueryExecution(plan=plan, sql=sql, params=params, rows=rows)
        if plan.metric == "operational_income_estimate" and self._has_matching_issued_invoices(plan):
            sql, params = self._build_invoice_turnover_query(plan)
            rows = self.query(sql, params)
            return QueryExecution(plan=plan, sql=sql, params=params, rows=rows)
        if plan.mode == "search":
            sql, params = self._build_search_query(plan, import_batch_id=import_batch_id, workspace_id=workspace_id)
        else:
            sql, params = self._build_aggregate_query(plan, import_batch_id=import_batch_id, workspace_id=workspace_id)
        rows = self.query(sql, params)
        return QueryExecution(plan=plan, sql=sql, params=params, rows=rows)

    def list_matching_transactions_for_plan(
        self,
        plan: QueryPlan,
        import_batch_id: int | None = None,
        workspace_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if plan.metric == "unsupported":
            return []
        if plan.metric == "creditare_vs_recuperare":
            return self.query(
                *self._build_creditare_recovery_rows_query(
                    plan,
                    import_batch_id=import_batch_id,
                    workspace_id=workspace_id,
                )
            )
        if plan.metric == "invoice_residual_total":
            return self.query(
                *self._build_invoice_residual_rows_query(
                    plan,
                    workspace_id=workspace_id,
                )
            )
        if plan.metric == "operational_income_estimate" and self._has_matching_issued_invoices(plan):
            return self.query(*self._build_invoice_rows_query(plan))
        sql, params = self._build_search_query(plan, import_batch_id=import_batch_id, workspace_id=workspace_id)
        return self.query(sql, params)

    def summary(
        self,
        import_batch_id: int | None = None,
        *,
        workspace_id: int | None = None,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if import_batch_id is not None:
            clauses.append("import_batch_id = ?")
            params.append(int(import_batch_id))
        if workspace_id is not None:
            clauses.append("import_batch_id IN (SELECT id FROM import_batches WHERE workspace_id = ?)")
            params.append(int(workspace_id))
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
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
                tuple(params),
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

    def _insert_workspace_invoice_row(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: int,
        import_batch_id: int | None,
        role: str,
        invoice: ImportedInvoice,
    ) -> sqlite3.Cursor:
        return connection.execute(
            """
            INSERT OR IGNORE INTO invoices (
                workspace_id,
                import_batch_id,
                role,
                invoice_number,
                issue_date,
                counterparty_name,
                net_amount,
                vat_amount,
                total_amount,
                currency,
                status,
                source_file,
                raw_payload,
                row_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(workspace_id),
                int(import_batch_id) if import_batch_id is not None else None,
                role.strip().lower(),
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
        workspace_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._plan_filters(
            plan,
            table_alias="t",
            import_batch_id=import_batch_id,
            workspace_id=workspace_id,
        )
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
        workspace_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._plan_filters(
            plan,
            table_alias="t",
            import_batch_id=import_batch_id,
            workspace_id=workspace_id,
        )
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
        workspace_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._creditare_recovery_filters(
            plan,
            import_batch_id=import_batch_id,
            workspace_id=workspace_id,
        )
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
        workspace_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._creditare_recovery_filters(
            plan,
            import_batch_id=import_batch_id,
            workspace_id=workspace_id,
        )
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
        workspace_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses = ["economic_kind IN ('creditare', 'recuperare_creditare')"]
        params: list[Any] = []
        if import_batch_id is not None:
            clauses.append("import_batch_id = ?")
            params.append(int(import_batch_id))
        if workspace_id is not None:
            clauses.append(
                "import_batch_id IN (SELECT id FROM import_batches WHERE workspace_id = ?)"
            )
            params.append(int(workspace_id))
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

    def _build_invoice_residual_query(
        self,
        plan: QueryPlan,
        *,
        workspace_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._invoice_residual_filters(plan, workspace_id=workspace_id)
        group_select = "NULL AS group_key"
        group_by_sql = ""
        order_by_sql = ""
        if plan.group_by == "year":
            group_select = "strftime('%Y', issue_date) AS group_key"
            group_by_sql = "GROUP BY strftime('%Y', issue_date)"
            order_by_sql = "ORDER BY group_key ASC"
        sql = f"""
            SELECT
                {group_select},
                ROUND(COALESCE(SUM(remaining_amount), 0), 2) AS metric_value,
                COUNT(*) AS transaction_count,
                'received_invoices' AS source
            FROM (
                SELECT
                    i.id,
                    i.issue_date,
                    ROUND(
                        i.total_amount - COALESCE(
                            SUM(
                                CASE
                                    WHEN im.status IN ('proposed', 'accepted')
                                    THEN im.matched_amount
                                    ELSE 0
                                END
                            ),
                            0
                        ),
                        2
                    ) AS remaining_amount
                FROM invoices AS i
                LEFT JOIN invoice_matches AS im
                    ON im.invoice_id = i.id
                WHERE i.role = 'received'
                GROUP BY i.id, i.issue_date, i.total_amount
            ) AS residuals
            {where_sql}
            {group_by_sql}
            {order_by_sql}
        """
        return sql.strip(), params

    def _build_invoice_residual_rows_query(
        self,
        plan: QueryPlan,
        *,
        workspace_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        where_sql, params = self._invoice_residual_filters(plan, workspace_id=workspace_id)
        sql = f"""
            SELECT
                issue_date AS transaction_date,
                counterparty_name AS merchant,
                'Factura primita ' || invoice_number AS description,
                remaining_amount AS amount,
                currency,
                'invoice_residual' AS economic_kind,
                'outflow' AS direction
            FROM (
                SELECT
                    i.id,
                    i.invoice_number,
                    i.issue_date,
                    i.counterparty_name,
                    i.currency,
                    ROUND(
                        i.total_amount - COALESCE(
                            SUM(
                                CASE
                                    WHEN im.status IN ('proposed', 'accepted')
                                    THEN im.matched_amount
                                    ELSE 0
                                END
                            ),
                            0
                        ),
                        2
                    ) AS remaining_amount
                FROM invoices AS i
                LEFT JOIN invoice_matches AS im
                    ON im.invoice_id = i.id
                WHERE i.role = 'received'
                GROUP BY i.id, i.invoice_number, i.issue_date, i.counterparty_name, i.currency, i.total_amount
            ) AS residuals
            {where_sql}
            ORDER BY issue_date DESC, merchant ASC
            LIMIT {int(plan.limit)}
        """
        return sql.strip(), params

    def _invoice_residual_filters(
        self,
        plan: QueryPlan,
        *,
        workspace_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses = ["remaining_amount > 0.01"]
        params: list[Any] = []
        if workspace_id is not None:
            clauses.append(
                "id IN (SELECT i.id FROM invoices AS i WHERE i.workspace_id = ?)"
            )
            params.append(int(workspace_id))
        if plan.years:
            placeholders = ", ".join("?" for _ in plan.years)
            clauses.append(f"CAST(strftime('%Y', issue_date) AS INTEGER) IN ({placeholders})")
            params.extend(plan.years)
        return "WHERE " + " AND ".join(clauses), tuple(params)

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
        workspace_id: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses: list[str] = []
        params: list[Any] = []

        if import_batch_id is not None:
            clauses.append(f"{table_alias}.import_batch_id = ?")
            params.append(int(import_batch_id))
        if workspace_id is not None:
            clauses.append(
                f"{table_alias}.import_batch_id IN (SELECT id FROM import_batches WHERE workspace_id = ?)"
            )
            params.append(int(workspace_id))

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
                      AND (
                          ? IS NULL OR first_period.import_batch_id IN (
                              SELECT id
                              FROM import_batches
                              WHERE workspace_id = ?
                          )
                      )
                )
                """.strip()
            )
            params.extend([import_batch_id, import_batch_id, workspace_id, workspace_id])

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

        if plan.project_name:
            clauses.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM business_facts AS bf
                    WHERE bf.workspace_id = ?
                      AND bf.fact_type = 'project_assignment'
                      AND LOWER(bf.fact_value) = ?
                      AND LOWER(bf.subject_name) = LOWER(COALESCE({table_alias}.merchant, ''))
                )
                """.strip()
            )
            params.extend([int(workspace_id or plan.workspace_id or 0), plan.project_name.lower()])

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
