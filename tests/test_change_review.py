from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from contabila_ai.change_review.service import ChangeReviewService  # noqa: E402
from contabila_ai.importing.models import ImportedInvoice, ImportedTransaction  # noqa: E402
from contabila_ai.matching.service import MatchingService  # noqa: E402
from contabila_ai.storage.store import SQLiteTransactionStore  # noqa: E402


class ChangeReviewServiceTest(unittest.TestCase):
    def test_change_review_records_category_change_proposal(self) -> None:
        db_path = ROOT / "test_change_review.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            seed_import = store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-01-10",
                        description="Materiale casa deja clasificate",
                        amount=-300.0,
                        currency="RON",
                        balance=5000.0,
                        merchant="Casa Decor SRL",
                        source_file="seed.csv",
                        raw_payload='{"id":"seed-house"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-03-15",
                        description="Plata partiala factura Casa Decor",
                        amount=-500.0,
                        currency="RON",
                        balance=3200.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"needs-proposal"}',
                    ),
                ],
                workspace_id=workspace_id,
            )
            seed_rows = store.list_transactions(import_batch_id=seed_import["import_batch_id"], limit=10)
            seed_transaction_id = next(row["id"] for row in seed_rows if row["description"] == "Materiale casa deja clasificate")
            target_transaction_id = next(row["id"] for row in seed_rows if row["description"] == "Plata partiala factura Casa Decor")
            store.assign_analysis_category("casa", [seed_transaction_id])

            import_batch_id = store.create_document_import_batch(
                source_path=ROOT / "_change_review_invoice.json",
                workspace_id=workspace_id,
                source_type="received_invoice",
            )
            store.insert_invoices(
                workspace_id=workspace_id,
                import_batch_id=import_batch_id,
                role="received",
                invoices=[
                    ImportedInvoice(
                        invoice_number="R-0750",
                        issue_date="2025-03-10",
                        customer_name="Casa Decor SRL",
                        net_amount=630.25,
                        vat_amount=119.75,
                        total_amount=750.0,
                        currency="RON",
                        status="issued",
                        source_file="received.json",
                        raw_payload='{"invoice":"R-0750"}',
                    )
                ],
            )
            MatchingService(store).match_workspace(workspace_id=workspace_id)

            service = ChangeReviewService(store)
            proposals = service.refresh_for_workspace(workspace_id=workspace_id)
            category_items = [item for item in proposals if item["field_name"] == "analysis_category"]

            self.assertEqual(len(category_items), 1)
            self.assertEqual(category_items[0]["transaction_id"], target_transaction_id)
            self.assertEqual(category_items[0]["field_name"], "analysis_category")
            self.assertEqual(category_items[0]["old_value"], "")
            self.assertEqual(category_items[0]["new_value"], "casa")
            self.assertEqual(category_items[0]["status"], "pending")
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_change_review_accept_applies_category_to_transaction(self) -> None:
        db_path = ROOT / "test_change_review_accept.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-04-10",
                        description="Materiale casa noi",
                        amount=-450.0,
                        currency="RON",
                        balance=4100.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"accept-house"}',
                    )
                ],
                workspace_id=workspace_id,
            )
            transaction_id = store.list_transactions(limit=5)[0]["id"]
            item = store.create_change_review_item(
                workspace_id=workspace_id,
                transaction_id=transaction_id,
                field_name="analysis_category",
                old_value="",
                new_value="casa",
                reason="same counterparty category profile",
                confidence=0.82,
            )

            result = ChangeReviewService(store).apply_decision(item_id=item["id"], decision="accept")
            transaction_rows = store.list_transactions(limit=5)

            self.assertEqual(result["decision"], "accept")
            self.assertIn("casa", transaction_rows[0]["category_names"])
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_change_review_records_entity_type_proposal_for_received_invoice_match(self) -> None:
        db_path = ROOT / "test_change_review_entity_type.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-05-20",
                        description="Plata materiale Casa Decor",
                        amount=-2000.0,
                        currency="RON",
                        balance=7000.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"entity-type-proposal"}',
                    )
                ],
                workspace_id=workspace_id,
            )
            import_batch_id = store.create_document_import_batch(
                source_path=ROOT / "_change_review_entity_type_invoice.json",
                workspace_id=workspace_id,
                source_type="received_invoice",
            )
            store.insert_invoices(
                workspace_id=workspace_id,
                import_batch_id=import_batch_id,
                role="received",
                invoices=[
                    ImportedInvoice(
                        invoice_number="INV-ENTITY-001",
                        issue_date="2025-05-10",
                        customer_name="Casa Decor SRL",
                        net_amount=2000.0,
                        vat_amount=0.0,
                        total_amount=2000.0,
                        currency="RON",
                        status="issued",
                        source_file="received.json",
                        raw_payload='{"invoice":"INV-ENTITY-001"}',
                    )
                ],
            )
            MatchingService(store).match_workspace(workspace_id=workspace_id)

            proposals = ChangeReviewService(store).refresh_for_workspace(workspace_id=workspace_id)
            entity_type_items = [item for item in proposals if item["field_name"] == "entity_type"]

            self.assertEqual(len(entity_type_items), 1)
            self.assertEqual(entity_type_items[0]["old_value"], "")
            self.assertEqual(entity_type_items[0]["new_value"], "supplier")
            self.assertEqual(entity_type_items[0]["status"], "pending")
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_change_review_accept_applies_entity_type_to_transaction_and_memory(self) -> None:
        db_path = ROOT / "test_change_review_entity_type_accept.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-06-10",
                        description="Incasare client strategic",
                        amount=3000.0,
                        currency="RON",
                        balance=5000.0,
                        merchant="AI Excellence SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"entity-type-accept"}',
                    )
                ],
                workspace_id=workspace_id,
            )
            transaction_id = store.list_transactions(limit=5)[0]["id"]
            item = store.create_change_review_item(
                workspace_id=workspace_id,
                transaction_id=transaction_id,
                field_name="entity_type",
                old_value="",
                new_value="partner",
                reason="issued invoice points to a paying partner",
                confidence=0.79,
            )

            result = ChangeReviewService(store).apply_decision(item_id=item["id"], decision="accept")
            transaction = store.fetch_transaction_by_id(transaction_id)
            entity_memory = store.entity_memory_map()

            self.assertEqual(result["decision"], "accept")
            self.assertEqual(transaction["entity_type"], "partner")
            self.assertIn("ai excellence", entity_memory)
            self.assertEqual(entity_memory["ai excellence"]["entity_type"], "partner")
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
