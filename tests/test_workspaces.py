from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from contabila_ai.importing.models import ImportedTransaction  # noqa: E402
from contabila_ai.storage.store import SQLiteTransactionStore  # noqa: E402


class WorkspaceStoreTest(unittest.TestCase):
    def test_store_creates_and_lists_named_workspaces(self) -> None:
        db_path = ROOT / "test_workspaces.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)

            workspace_id = store.create_workspace("MobExc")
            workspaces = store.list_workspaces()

            self.assertEqual(len(workspaces), 1)
            self.assertEqual(workspaces[0]["id"], workspace_id)
            self.assertEqual(workspaces[0]["name"], "MobExc")
            self.assertEqual(workspaces[0]["status"], "needs_import")
            self.assertEqual(workspaces[0]["import_count"], 0)
            self.assertEqual(workspaces[0]["transaction_count"], 0)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_assigns_imports_to_workspace(self) -> None:
        db_path = ROOT / "test_workspace_imports.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")

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
                ],
                workspace_id=workspace_id,
            )

            workspaces = store.list_workspaces()
            imports = store.list_import_batches(workspace_id=workspace_id)

            self.assertEqual(result["inserted"], 1)
            self.assertEqual(len(workspaces), 1)
            self.assertEqual(workspaces[0]["import_count"], 1)
            self.assertEqual(workspaces[0]["transaction_count"], 1)
            self.assertEqual(len(imports), 1)
            self.assertEqual(imports[0]["workspace_id"], workspace_id)
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
