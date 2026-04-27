from __future__ import annotations

from contextlib import closing
import sqlite3
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contabila_ai.importing.models import ImportedTransaction
from contabila_ai.storage.schema import transaction_row_hash
from contabila_ai.storage.store import SQLiteTransactionStore


class StorageTest(unittest.TestCase):
    def test_store_reclassifies_existing_dividend_rows_with_current_rules(self) -> None:
        db_path = ROOT / "test_store_reclassify_dividends.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            transaction = ImportedTransaction(
                transaction_date="2025-12-31",
                description="TRANSFER ONLINE INTERBANCAR | Beneficiar: ELENA CRISTINA PALADE | Detalii: /ROC/DIVIDENDE",
                amount=-11000.0,
                currency="RON",
                balance=1000.0,
                merchant="ELENA CRISTINA PALADE",
                source_file="statement.csv",
                raw_payload='{"id":"dividend-existing"}',
            )
            store.insert_many([transaction])
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    UPDATE transactions
                    SET economic_kind = 'other_outflow',
                        confidence = 0.55,
                        reason = 'fallback classification'
                    """
                )
                connection.execute("DELETE FROM transaction_category_links")
                connection.commit()

            result = store.reclassify_transactions()

            rows = store.query(
                """
                SELECT t.economic_kind, t.confidence, ac.name AS category_name
                FROM transactions AS t
                LEFT JOIN transaction_category_links AS tcl
                    ON tcl.transaction_id = t.id
                LEFT JOIN analysis_categories AS ac
                    ON ac.id = tcl.category_id
                """
            )
            self.assertEqual(result["updated_count"], 1)
            self.assertEqual(rows[0]["economic_kind"], "dividend_payment")
            self.assertGreaterEqual(rows[0]["confidence"], 0.9)
            self.assertEqual(rows[0]["category_name"], "dividende")
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_imported_transaction_fields_match_bootstrap_contract(self) -> None:
        tx = ImportedTransaction(
            transaction_date="2026-04-22",
            description="Coffee shop card payment",
            amount=-24.5,
            currency="RON",
            balance=975.5,
            merchant="Daily Brew",
            source_file="statement.csv",
            raw_payload='{"id":"abc123"}',
        )

        self.assertEqual(tx.transaction_date, "2026-04-22")
        self.assertEqual(tx.description, "Coffee shop card payment")
        self.assertEqual(tx.amount, -24.5)
        self.assertEqual(tx.currency, "RON")
        self.assertEqual(tx.balance, 975.5)
        self.assertEqual(tx.merchant, "Daily Brew")
        self.assertEqual(tx.source_file, "statement.csv")
        self.assertEqual(tx.raw_payload, '{"id":"abc123"}')

    def test_store_insert_many_query_and_summary(self) -> None:
        db_path = ROOT / "test_store_insert_many.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            tx = ImportedTransaction(
                transaction_date="2026-04-22",
                description="Coffee shop card payment",
                amount=-24.5,
                currency="RON",
                balance=975.5,
                merchant="Daily Brew",
                source_file="statement.csv",
                raw_payload='{"id":"abc123"}',
            )

            result = store.insert_many([tx])
            rows = store.query(
                """
                SELECT
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
                FROM transactions
                """
            )
            summary = store.summary()

            self.assertEqual(result["inserted"], 1)
            self.assertEqual(result["skipped"], 0)
            self.assertGreater(result["import_batch_id"], 0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["description"], "Coffee shop card payment")
            self.assertEqual(rows[0]["raw_payload"], '{"id":"abc123"}')
            self.assertEqual(rows[0]["row_hash"], transaction_row_hash(tx))
            self.assertEqual(summary["transaction_count"], 1)
            self.assertEqual(summary["first_transaction_date"], "2026-04-22")
            self.assertEqual(summary["last_transaction_date"], "2026-04-22")
            self.assertEqual(summary["total_expenses"], 24.5)
            self.assertEqual(summary["total_income"], 0.0)
            self.assertEqual(summary["net_cashflow"], -24.5)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_skips_duplicate_transactions_by_row_hash(self) -> None:
        db_path = ROOT / "test_store_duplicates.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            tx_one = ImportedTransaction(
                transaction_date="2026-04-22",
                description="Coffee shop card payment",
                amount=-24.5,
                currency="RON",
                balance=975.5,
                merchant="Daily Brew",
                source_file="statement.csv",
                raw_payload='{"id":"abc123"}',
            )
            tx_two = ImportedTransaction(
                transaction_date="2026-04-22",
                description="Coffee shop card payment",
                amount=-24.5,
                currency="RON",
                balance=975.5,
                merchant="Daily Brew",
                source_file="renamed-statement.csv",
                raw_payload='{"id":"abc123"}',
            )

            self.assertEqual(transaction_row_hash(tx_one), transaction_row_hash(tx_two))

            result = store.insert_many([tx_one, tx_two])
            rows = store.query("SELECT row_hash FROM transactions")

            self.assertEqual(result["inserted"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(len(rows), 1)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_schema_creates_expected_columns(self) -> None:
        db_path = ROOT / "test_schema_columns.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            SQLiteTransactionStore(db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(transactions)")]

            self.assertEqual(
                columns,
                [
                    "id",
                    "import_batch_id",
                    "transaction_date",
                    "description",
                    "amount",
                    "currency",
                    "balance",
                    "merchant",
                    "source_file",
                    "raw_payload",
                    "row_hash",
                    "economic_kind",
                    "direction",
                    "entity_type",
                    "confidence",
                    "reason",
                ],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_groups_uploaded_transactions_into_separate_import_batches(self) -> None:
        db_path = ROOT / "test_import_batches.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            first_batch = store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2026-04-22",
                        description="Coffee shop card payment",
                        amount=-24.5,
                        currency="RON",
                        balance=975.5,
                        merchant="Daily Brew",
                        source_file="statement-one.csv",
                        raw_payload='{"id":"one"}',
                    )
                ]
            )
            second_batch = store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2026-04-23",
                        description="Salary payroll",
                        amount=3500.0,
                        currency="RON",
                        balance=4475.5,
                        merchant="Salary payroll",
                        source_file="statement-two.csv",
                        raw_payload='{"id":"two"}',
                    )
                ]
            )

            imports = store.list_import_batches()
            first_summary = store.summary(import_batch_id=first_batch["import_batch_id"])
            second_summary = store.summary(import_batch_id=second_batch["import_batch_id"])
            all_summary = store.summary()

            self.assertEqual(len(imports), 2)
            self.assertEqual(imports[0]["source_file"], "statement-two.csv")
            self.assertEqual(imports[1]["source_file"], "statement-one.csv")
            self.assertEqual(first_summary["transaction_count"], 1)
            self.assertEqual(first_summary["total_expenses"], 24.5)
            self.assertEqual(second_summary["transaction_count"], 1)
            self.assertEqual(second_summary["total_income"], 3500.0)
            self.assertEqual(all_summary["transaction_count"], 2)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_allows_same_statement_to_be_imported_into_multiple_batches(self) -> None:
        db_path = ROOT / "test_same_statement_multiple_batches.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            tx = ImportedTransaction(
                transaction_date="2026-04-22",
                description="Coffee shop card payment",
                amount=-24.5,
                currency="RON",
                balance=975.5,
                merchant="Daily Brew",
                source_file="statement.csv",
                raw_payload='{"id":"abc123"}',
            )

            first_result = store.insert_many([tx])
            second_result = store.insert_many([tx])
            imports = store.list_import_batches()
            first_summary = store.summary(import_batch_id=first_result["import_batch_id"])
            second_summary = store.summary(import_batch_id=second_result["import_batch_id"])

            self.assertEqual(first_result["inserted"], 1)
            self.assertEqual(second_result["inserted"], 1)
            self.assertEqual(len(imports), 2)
            self.assertEqual(first_summary["transaction_count"], 1)
            self.assertEqual(second_summary["transaction_count"], 1)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_backfills_import_batches_for_legacy_transactions(self) -> None:
        db_path = ROOT / "test_legacy_import_backfill.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    CREATE TABLE transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        transaction_date TEXT NOT NULL,
                        description TEXT NOT NULL,
                        amount REAL NOT NULL,
                        currency TEXT NOT NULL,
                        balance REAL,
                        merchant TEXT,
                        source_file TEXT NOT NULL,
                        raw_payload TEXT NOT NULL,
                        row_hash TEXT NOT NULL UNIQUE,
                        economic_kind TEXT,
                        direction TEXT,
                        entity_type TEXT,
                        confidence REAL,
                        reason TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO transactions (
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "2026-04-22",
                        "Legacy payment",
                        -100.0,
                        "RON",
                        900.0,
                        "Legacy Merchant",
                        r"C:\legacy\statement.csv",
                        '{"id":"legacy"}',
                        "legacy-row-hash",
                        "other_outflow",
                        "outflow",
                        None,
                        0.55,
                        "fallback classification",
                    ),
                )
                connection.commit()

            store = SQLiteTransactionStore(db_path)
            imports = store.list_import_batches()
            summary = store.summary(import_batch_id=imports[0]["id"])
            rows = store.query("SELECT import_batch_id FROM transactions")

            self.assertEqual(len(imports), 1)
            self.assertEqual(imports[0]["source_file"], "statement.csv")
            self.assertEqual(summary["transaction_count"], 1)
            self.assertIsNotNone(rows[0]["import_batch_id"])
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_can_reset_all_saved_data(self) -> None:
        db_path = ROOT / "test_reset_all.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            result = store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2026-04-22",
                        description="Coffee shop card payment",
                        amount=-24.5,
                        currency="RON",
                        balance=975.5,
                        merchant="Daily Brew",
                        source_file="statement.csv",
                        raw_payload='{"id":"abc123"}',
                    )
                ]
            )

            self.assertEqual(store.summary()["transaction_count"], 1)
            self.assertGreater(result["import_batch_id"], 0)

            store.reset_all_data()

            self.assertEqual(store.summary()["transaction_count"], 0)
            self.assertEqual(store.list_import_batches(), [])
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_lists_transactions_filtered_by_absolute_amount(self) -> None:
        db_path = ROOT / "test_transaction_register_filter.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            result = store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2026-04-20",
                        description="Small payment",
                        amount=-50.0,
                        currency="RON",
                        balance=950.0,
                        merchant="Small Supplier",
                        source_file="statement.csv",
                        raw_payload='{"id":"small"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2026-04-21",
                        description="Large payment",
                        amount=-5000.0,
                        currency="RON",
                        balance=-4050.0,
                        merchant="Large Supplier",
                        source_file="statement.csv",
                        raw_payload='{"id":"large"}',
                    ),
                ]
            )

            rows = store.list_transactions(
                import_batch_id=result["import_batch_id"],
                min_abs_amount=1000,
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["merchant"], "Large Supplier")
            self.assertEqual(rows[0]["amount"], -5000.0)
            self.assertEqual(rows[0]["review_status"], "needs_review")
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_repairs_category_links_after_transactions_table_migration(self) -> None:
        db_path = ROOT / "test_category_link_migration.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(
                    """
                    CREATE TABLE transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        transaction_date TEXT NOT NULL,
                        description TEXT NOT NULL,
                        amount REAL NOT NULL,
                        currency TEXT NOT NULL,
                        balance REAL,
                        merchant TEXT,
                        source_file TEXT NOT NULL,
                        raw_payload TEXT NOT NULL,
                        row_hash TEXT NOT NULL UNIQUE,
                        economic_kind TEXT,
                        direction TEXT,
                        entity_type TEXT,
                        confidence REAL,
                        reason TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE analysis_categories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE classification_rules (
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
                )
                connection.execute(
                    """
                    CREATE TABLE transaction_category_links (
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
                )
                connection.execute(
                    """
                    INSERT INTO transactions (
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "2026-04-22",
                        "Legacy payment",
                        -100.0,
                        "RON",
                        900.0,
                        "Legacy Merchant",
                        "statement.csv",
                        '{"id":"legacy"}',
                        "legacy-row-hash",
                        "other_outflow",
                        "outflow",
                        None,
                        0.55,
                        "fallback classification",
                    ),
                )
                connection.commit()

            store = SQLiteTransactionStore(db_path)
            row = store.query("SELECT id FROM transactions WHERE raw_payload = '{\"id\":\"legacy\"}'")[0]

            updated_count = store.assign_analysis_category("casa", [row["id"]])
            links = store.query(
                """
                SELECT ac.name
                FROM transaction_category_links AS tcl
                INNER JOIN analysis_categories AS ac
                    ON ac.id = tcl.category_id
                WHERE tcl.transaction_id = ?
                """,
                (row["id"],),
            )
            foreign_keys = store.query("PRAGMA foreign_key_list(transaction_category_links)")

            self.assertEqual(updated_count, 1)
            self.assertEqual([link["name"] for link in links], ["casa"])
            self.assertIn("transactions", [fk["table"] for fk in foreign_keys])
            self.assertNotIn("transactions_legacy", [fk["table"] for fk in foreign_keys])
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_lists_categories_with_metadata_and_transactions(self) -> None:
        db_path = ROOT / "test_category_metadata.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            result = store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2026-04-22",
                        description="Materiale pentru casa",
                        amount=-240.0,
                        currency="RON",
                        balance=760.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"house-meta"}',
                    )
                ]
            )
            transaction_id = store.query("SELECT id FROM transactions")[0]["id"]

            store.assign_analysis_category(
                "casa",
                [transaction_id],
                description="Cheltuieli legate de casa, non-operationale pentru firma.",
                operational_scope="non_operational",
            )

            categories = store.list_analysis_categories()
            category_rows = store.list_transactions_for_category(
                "casa",
                import_batch_id=result["import_batch_id"],
            )

            self.assertEqual(len(categories), 1)
            self.assertEqual(categories[0]["name"], "casa")
            self.assertEqual(categories[0]["operational_scope"], "non_operational")
            self.assertIn("non-operationale", categories[0]["description"])
            self.assertEqual(categories[0]["transaction_count"], 1)
            self.assertEqual(len(category_rows), 1)
            self.assertEqual(category_rows[0]["merchant"], "Casa Decor SRL")
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
