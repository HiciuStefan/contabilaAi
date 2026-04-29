from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from contabila_ai.importing.models import ImportedTransaction


IMPORT_BATCHES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'bank_statement',
    workspace_id INTEGER,
    transaction_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL
)
"""

WORKSPACES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'needs_import',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

ACCOUNTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    currency TEXT,
    account_kind TEXT NOT NULL DEFAULT 'bank',
    external_ref TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, name),
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
)
"""

BUSINESS_INSTRUCTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS business_instructions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
)
"""

BUSINESS_FACTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS business_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    instruction_id INTEGER,
    fact_type TEXT NOT NULL,
    subject_name TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    extra_json TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'accepted',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(instruction_id) REFERENCES business_instructions(id) ON DELETE SET NULL
)
"""

TRANSACTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id INTEGER,
    transaction_date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    balance REAL,
    merchant TEXT,
    source_file TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    row_hash TEXT NOT NULL,
    economic_kind TEXT,
    direction TEXT,
    entity_type TEXT,
    confidence REAL,
    reason TEXT,
    FOREIGN KEY(import_batch_id) REFERENCES import_batches(id) ON DELETE SET NULL,
    UNIQUE(import_batch_id, row_hash)
)
"""

ENTITY_MEMORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS entity_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_name TEXT NOT NULL,
    entity_name_normalized TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL,
    economic_kind TEXT,
    direction TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

ANALYSIS_CATEGORIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS analysis_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    operational_scope TEXT NOT NULL DEFAULT 'unassigned',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CLASSIFICATION_RULES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS classification_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL DEFAULT 'contains',
    match_field TEXT NOT NULL DEFAULT 'text',
    pattern TEXT NOT NULL,
    economic_kind TEXT,
    direction TEXT,
    entity_type TEXT,
    analysis_category TEXT,
    priority INTEGER NOT NULL DEFAULT 100,
    confidence REAL NOT NULL DEFAULT 0.78,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

TRANSACTION_CATEGORY_LINKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transaction_category_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    rule_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(transaction_id, category_id),
    FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
    FOREIGN KEY(category_id) REFERENCES analysis_categories(id) ON DELETE CASCADE,
    FOREIGN KEY(rule_id) REFERENCES classification_rules(id) ON DELETE SET NULL
)
"""

ISSUED_INVOICES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS issued_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT NOT NULL,
    issue_date TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    net_amount REAL NOT NULL,
    vat_amount REAL,
    total_amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'issued',
    source_file TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    row_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

INVOICES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    import_batch_id INTEGER,
    role TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    issue_date TEXT NOT NULL,
    counterparty_name TEXT NOT NULL,
    net_amount REAL NOT NULL,
    vat_amount REAL,
    total_amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'issued',
    source_file TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    row_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, role, row_hash),
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(import_batch_id) REFERENCES import_batches(id) ON DELETE SET NULL
)
"""

INVOICE_MATCHES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS invoice_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    transaction_id INTEGER NOT NULL,
    invoice_id INTEGER NOT NULL,
    match_kind TEXT NOT NULL,
    matched_amount REAL NOT NULL,
    residual_amount REAL NOT NULL DEFAULT 0,
    confidence REAL NOT NULL,
    reasoning TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
)
"""

CHANGE_REVIEW_ITEMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS change_review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    transaction_id INTEGER,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
)
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.execute(WORKSPACES_TABLE_SQL)
    connection.execute(ACCOUNTS_TABLE_SQL)
    connection.execute(BUSINESS_INSTRUCTIONS_TABLE_SQL)
    connection.execute(BUSINESS_FACTS_TABLE_SQL)
    connection.execute(IMPORT_BATCHES_TABLE_SQL)
    _ensure_import_batches_table_shape(connection)
    connection.execute(TRANSACTIONS_TABLE_SQL)
    _ensure_transactions_table_shape(connection)
    connection.execute(ENTITY_MEMORY_TABLE_SQL)
    connection.execute(ANALYSIS_CATEGORIES_TABLE_SQL)
    _ensure_analysis_categories_table_shape(connection)
    connection.execute(CLASSIFICATION_RULES_TABLE_SQL)
    connection.execute(TRANSACTION_CATEGORY_LINKS_TABLE_SQL)
    connection.execute(ISSUED_INVOICES_TABLE_SQL)
    connection.execute(INVOICES_TABLE_SQL)
    connection.execute(INVOICE_MATCHES_TABLE_SQL)
    connection.execute(CHANGE_REVIEW_ITEMS_TABLE_SQL)
    _ensure_transaction_category_links_shape(connection)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_transaction_date ON transactions(transaction_date)"
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_transactions_row_hash ON transactions(row_hash)")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_import_batch ON transactions(import_batch_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_import_batches_created_at ON import_batches(created_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_import_batches_workspace ON import_batches(workspace_id, created_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspaces_status ON workspaces(status, created_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_business_instructions_workspace ON business_instructions(workspace_id, created_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_business_facts_workspace ON business_facts(workspace_id, fact_type, subject_name)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_memory_normalized ON entity_memory(entity_name_normalized)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_classification_rules_priority ON classification_rules(priority, is_active)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_transaction_category_links_transaction ON transaction_category_links(transaction_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_transaction_category_links_category ON transaction_category_links(category_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_categories_scope ON analysis_categories(operational_scope, name)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_issued_invoices_issue_date ON issued_invoices(issue_date)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_issued_invoices_customer ON issued_invoices(customer_name)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoices_workspace_role ON invoices(workspace_id, role, issue_date DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoices_counterparty ON invoices(counterparty_name)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoice_matches_workspace ON invoice_matches(workspace_id, status, created_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoice_matches_transaction ON invoice_matches(transaction_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoice_matches_invoice ON invoice_matches(invoice_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_change_review_workspace ON change_review_items(workspace_id, status, created_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_change_review_transaction ON change_review_items(transaction_id)"
    )


def _ensure_transactions_table_shape(connection: sqlite3.Connection) -> None:
    columns = [row[1] for row in connection.execute("PRAGMA table_info(transactions)").fetchall()]
    unique_indexes = connection.execute("PRAGMA index_list(transactions)").fetchall()
    foreign_keys = connection.execute("PRAGMA foreign_key_list(transactions)").fetchall()
    has_legacy_row_hash_unique = False
    has_batch_row_hash_unique = False
    import_batch_fk_targets = [row[2] for row in foreign_keys if row[3] == "import_batch_id"]

    for index in unique_indexes:
        if not index[2]:
            continue
        index_columns = [
            row[2]
            for row in connection.execute(f"PRAGMA index_info({index[1]!r})").fetchall()
        ]
        if index_columns == ["row_hash"]:
            has_legacy_row_hash_unique = True
        if index_columns == ["import_batch_id", "row_hash"]:
            has_batch_row_hash_unique = True

    if (
        "import_batch_id" in columns
        and has_batch_row_hash_unique
        and not has_legacy_row_hash_unique
        and import_batch_fk_targets == ["import_batches"]
    ):
        return

    select_import_batch = (
        """
        CASE
            WHEN import_batch_id IS NULL THEN NULL
            WHEN EXISTS (SELECT 1 FROM import_batches WHERE id = import_batch_id) THEN import_batch_id
            ELSE NULL
        END AS import_batch_id
        """.strip()
        if "import_batch_id" in columns
        else "NULL AS import_batch_id"
    )
    connection.execute("ALTER TABLE transactions RENAME TO transactions_legacy")
    connection.execute(TRANSACTIONS_TABLE_SQL)
    connection.execute(
        f"""
        INSERT INTO transactions (
            id,
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
        )
        SELECT
            id,
            {select_import_batch},
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
        FROM transactions_legacy
        """
    )
    connection.execute("DROP TABLE transactions_legacy")


def _ensure_import_batches_table_shape(connection: sqlite3.Connection) -> None:
    columns = [row[1] for row in connection.execute("PRAGMA table_info(import_batches)").fetchall()]
    if "workspace_id" in columns and "source_type" in columns:
        return

    select_source_type = "'bank_statement' AS source_type" if "source_type" not in columns else "source_type"
    select_workspace_id = "NULL AS workspace_id" if "workspace_id" not in columns else "workspace_id"
    connection.execute("ALTER TABLE import_batches RENAME TO import_batches_legacy")
    connection.execute(IMPORT_BATCHES_TABLE_SQL)
    connection.execute(
        f"""
        INSERT INTO import_batches (
            id,
            source_file,
            source_path,
            source_type,
            workspace_id,
            transaction_count,
            created_at
        )
        SELECT
            id,
            source_file,
            source_path,
            {select_source_type},
            {select_workspace_id},
            transaction_count,
            created_at
        FROM import_batches_legacy
        """
    )
    connection.execute("DROP TABLE import_batches_legacy")


def _ensure_transaction_category_links_shape(connection: sqlite3.Connection) -> None:
    foreign_keys = connection.execute(
        "PRAGMA foreign_key_list(transaction_category_links)"
    ).fetchall()
    transaction_fk_targets = [
        row[2]
        for row in foreign_keys
        if row[3] == "transaction_id"
    ]

    if transaction_fk_targets == ["transactions"]:
        return

    connection.execute("ALTER TABLE transaction_category_links RENAME TO transaction_category_links_legacy")
    connection.execute(TRANSACTION_CATEGORY_LINKS_TABLE_SQL)
    connection.execute(
        """
        INSERT INTO transaction_category_links (
            id,
            transaction_id,
            category_id,
            rule_id,
            created_at
        )
        SELECT
            tcl.id,
            tcl.transaction_id,
            tcl.category_id,
            tcl.rule_id,
            tcl.created_at
        FROM transaction_category_links_legacy AS tcl
        INNER JOIN transactions AS t
            ON t.id = tcl.transaction_id
        INNER JOIN analysis_categories AS ac
            ON ac.id = tcl.category_id
        """
    )
    connection.execute("DROP TABLE transaction_category_links_legacy")


def _ensure_analysis_categories_table_shape(connection: sqlite3.Connection) -> None:
    columns = [row[1] for row in connection.execute("PRAGMA table_info(analysis_categories)").fetchall()]
    if "operational_scope" not in columns:
        connection.execute(
            """
            ALTER TABLE analysis_categories
            ADD COLUMN operational_scope TEXT NOT NULL DEFAULT 'unassigned'
            """
        )


def transaction_row_hash(transaction: ImportedTransaction) -> str:
    payload: dict[str, Any] = {
        "transaction_date": transaction.transaction_date,
        "description": transaction.description,
        "amount": f"{transaction.amount:.2f}",
        "currency": transaction.currency,
        "balance": None if transaction.balance is None else f"{transaction.balance:.2f}",
        "merchant": transaction.merchant,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def invoice_row_hash(invoice: Any) -> str:
    payload: dict[str, Any] = {
        "invoice_number": invoice.invoice_number,
        "issue_date": invoice.issue_date,
        "customer_name": invoice.customer_name,
        "net_amount": f"{invoice.net_amount:.2f}",
        "vat_amount": None if invoice.vat_amount is None else f"{invoice.vat_amount:.2f}",
        "total_amount": f"{invoice.total_amount:.2f}",
        "currency": invoice.currency,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
