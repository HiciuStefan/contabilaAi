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


from contabila_ai.classification.engine import classify_transaction, normalize_entity_name  # noqa: E402
from contabila_ai.storage.store import SQLiteTransactionStore  # noqa: E402


class ClassificationTest(unittest.TestCase):
    def test_normalize_entity_name_merges_numeric_prefix_and_legal_suffix_variants(self) -> None:
        self.assertEqual(
            normalize_entity_name("1/MOBILE EXCELLENCE S.R.L."),
            normalize_entity_name("Mobile Excellence SRL"),
        )
        self.assertEqual(normalize_entity_name("1.MobileExcellence"), "mobileexcellence")

    def test_normalize_entity_name_handles_common_vendor_variants(self) -> None:
        self.assertEqual(
            normalize_entity_name("METRO CASH & CARRY ROMANIA S.R.L."),
            normalize_entity_name("Metro Cash and Carry Romania SRL"),
        )

    def test_negative_credit_recovery_is_not_classified_as_creditare(self) -> None:
        result = classify_transaction(
            merchant="COMPANY OWNER",
            description="Recuperare creditare asociat",
            amount=-5000.0,
            entity_memory={},
            analysis_rules=[],
        )

        self.assertEqual(result.economic_kind, "recuperare_creditare")
        self.assertEqual(result.direction, "outflow")
        self.assertIsNone(result.entity_type)
        self.assertIn("recovery", result.reason.lower())

    def test_positive_crediting_is_classified_as_creditare(self) -> None:
        result = classify_transaction(
            merchant="COMPANY OWNER",
            description="Creditare firma asociat",
            amount=25000.0,
            entity_memory={},
            analysis_rules=[],
        )

        self.assertEqual(result.economic_kind, "creditare")
        self.assertEqual(result.direction, "inflow")
        self.assertIsNone(result.entity_type)
        self.assertGreaterEqual(result.confidence, 0.9)

    def test_generic_banking_credit_wording_does_not_trigger_creditare(self) -> None:
        result = classify_transaction(
            merchant="BANCA EXEMPLE",
            description="Rambursare rata credit bancar",
            amount=-1200.0,
            entity_memory={},
            analysis_rules=[],
        )

        self.assertEqual(result.economic_kind, "other_outflow")
        self.assertEqual(result.direction, "outflow")
        self.assertNotEqual(result.economic_kind, "creditare")
        self.assertNotEqual(result.economic_kind, "recuperare_creditare")

    def test_dividend_payment_is_classified_as_owner_distribution(self) -> None:
        result = classify_transaction(
            merchant="ELENA CRISTINA PALADE",
            description="TRANSFER ONLINE INTERBANCAR | Beneficiar: ELENA CRISTINA PALADE | Detalii: /ROC/DIVIDENDE",
            amount=-11000.0,
            entity_memory={},
            analysis_rules=[],
        )

        self.assertEqual(result.economic_kind, "dividend_payment")
        self.assertEqual(result.direction, "outflow")
        self.assertGreaterEqual(result.confidence, 0.9)
        self.assertIn("dividend", result.reason.lower())

    def test_entity_memory_influences_supplier_payment_classification(self) -> None:
        result = classify_transaction(
            merchant="Dedeman SRL",
            description="Plata materiale constructie",
            amount=-850.0,
            entity_memory={
                "dedeman srl": {
                    "entity_type": "supplier",
                }
            },
            analysis_rules=[],
        )

        self.assertEqual(result.economic_kind, "supplier_payment")
        self.assertEqual(result.direction, "outflow")
        self.assertEqual(result.entity_type, "supplier")
        self.assertIn("memory", result.reason.lower())

    def test_analysis_rule_can_attach_analysis_category(self) -> None:
        result = classify_transaction(
            merchant="PETROM",
            description="Plata combustibil flota",
            amount=-300.0,
            entity_memory={},
            analysis_rules=[
                {
                    "match_field": "description",
                    "pattern": "combustibil",
                    "analysis_category": "motorina",
                }
            ],
        )

        self.assertEqual(result.economic_kind, "other_outflow")
        self.assertEqual(result.analysis_categories, ["motorina"])

    def test_house_wording_does_not_trigger_tax_classification_from_cas_token(self) -> None:
        result = classify_transaction(
            merchant="Casa Decor SRL",
            description="Materiale pentru casa",
            amount=-300.0,
            entity_memory={},
            analysis_rules=[],
        )

        self.assertEqual(result.economic_kind, "other_outflow")
        self.assertNotEqual(result.economic_kind, "tax_payment")

    def test_store_creates_classification_foundation_tables(self) -> None:
        db_path = ROOT / "test_classification_foundations.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            SQLiteTransactionStore(db_path)
            with closing(sqlite3.connect(db_path)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

            self.assertTrue(
                {
                    "transactions",
                    "entity_memory",
                    "analysis_categories",
                    "classification_rules",
                    "transaction_category_links",
                }.issubset(tables)
            )
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
