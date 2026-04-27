from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from contabila_ai.importing.models import ImportedTransaction  # noqa: E402
from contabila_ai.memory import BusinessMemoryService  # noqa: E402
from contabila_ai.storage.store import SQLiteTransactionStore  # noqa: E402


class BusinessMemoryTest(unittest.TestCase):
    def test_add_business_instruction_creates_structured_fact(self) -> None:
        db_path = ROOT / "test_business_memory.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            service = BusinessMemoryService(store)

            result = service.add_instruction(workspace_id, "Ai Excellence e partener")
            facts = store.list_business_facts(workspace_id)

            self.assertGreater(result["instruction_id"], 0)
            self.assertEqual(result["fact_count"], 1)
            self.assertEqual(facts[0]["subject_name"], "Ai Excellence")
            self.assertEqual(facts[0]["fact_type"], "entity_type")
            self.assertEqual(facts[0]["fact_value"], "partener")
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_business_instruction_updates_entity_memory_and_reclassifies(self) -> None:
        db_path = ROOT / "test_business_memory_reclassify.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2026-01-10",
                        description="Transfer de la AI EXCELLENCE SRL",
                        amount=12000.0,
                        currency="RON",
                        balance=12000.0,
                        merchant="AI EXCELLENCE SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"memory-1"}',
                    )
                ],
                workspace_id=workspace_id,
            )

            before = store.query("SELECT entity_type, confidence FROM transactions WHERE raw_payload = '{\"id\":\"memory-1\"}'")[0]
            service = BusinessMemoryService(store)
            service.add_instruction(workspace_id, "Ai Excellence e partener")
            after = store.query("SELECT entity_type, confidence, reason FROM transactions WHERE raw_payload = '{\"id\":\"memory-1\"}'")[0]

            self.assertNotEqual(before["entity_type"], "partner")
            self.assertEqual(after["entity_type"], "partner")
            self.assertIn("entity memory", after["reason"])
        finally:
            if db_path.exists():
                db_path.unlink()
