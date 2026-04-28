from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from contabila_ai.importing.models import ImportedTransaction  # noqa: E402
from contabila_ai.memory import BusinessMemoryService, parse_instruction_to_facts  # noqa: E402
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

    def test_business_instruction_supports_entity_type_correction_wording(self) -> None:
        db_path = ROOT / "test_business_memory_correction.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            service = BusinessMemoryService(store)

            result = service.add_instruction(workspace_id, "AI Excellence nu e partener, e colaborator")
            facts = result["facts"]

            self.assertEqual(result["fact_count"], 1)
            self.assertEqual(facts[0]["fact_type"], "entity_type")
            self.assertEqual(facts[0]["subject_name"], "AI Excellence")
            self.assertEqual(facts[0]["fact_value"], "colaborator")
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_business_instruction_supports_project_assignment_with_pentru_proiectul(self) -> None:
        db_path = ROOT / "test_business_memory_project_phrase.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            service = BusinessMemoryService(store)

            result = service.add_instruction(
                workspace_id,
                "colaboratorii Casa Decor SRL si Sergiu Munteanu lucreaza pentru proiectul Casa Noua",
            )
            facts = result["facts"]

            self.assertEqual(result["fact_count"], 2)
            self.assertEqual({fact["fact_type"] for fact in facts}, {"project_assignment"})
            self.assertEqual({fact["fact_value"] for fact in facts}, {"Casa Noua"})
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_parse_instruction_to_facts_extracts_house_category_rule_with_period(self) -> None:
        facts = parse_instruction_to_facts(
            "am facut o casa intre 2020-2024, pune cheltuielile astea la categoria casa"
        )

        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].fact_type, "category_rule")
        self.assertEqual(facts[0].fact_value, "casa")
        self.assertIsInstance(facts[0].extra_json, str)

    def test_parse_instruction_to_facts_supports_free_form_project_sentence(self) -> None:
        facts = parse_instruction_to_facts(
            "Sergiu Munteanu si Casa Decor SRL lucreaza pentru proiectul Atlas"
        )

        self.assertEqual(len(facts), 2)
        self.assertEqual({fact.fact_type for fact in facts}, {"project_assignment"})
        self.assertEqual({fact.fact_value for fact in facts}, {"Atlas"})

    def test_business_memory_category_rule_creates_change_review_for_matching_transactions(self) -> None:
        db_path = ROOT / "test_business_memory_category_rule.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2023-05-10",
                        description="Materiale pentru casa",
                        amount=-1200.0,
                        currency="RON",
                        balance=5000.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"house-1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2023-05-12",
                        description="Abonament software",
                        amount=-200.0,
                        currency="RON",
                        balance=4800.0,
                        merchant="Software Vendor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"software-1"}',
                    ),
                ],
                workspace_id=workspace_id,
            )
            service = BusinessMemoryService(store)

            result = service.add_instruction(
                workspace_id,
                "am facut o casa intre 2020-2024, pune cheltuielile astea la categoria casa",
            )
            items = store.list_change_review_items(workspace_id)

            self.assertEqual(result["fact_count"], 1)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["field_name"], "analysis_category")
            self.assertEqual(items[0]["new_value"], "casa")
        finally:
            if db_path.exists():
                db_path.unlink()
