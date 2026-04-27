from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from contabila_ai.importing.models import ImportedInvoice, ImportedTransaction  # noqa: E402
from contabila_ai.matching.service import MatchingService  # noqa: E402
from contabila_ai.storage.store import SQLiteTransactionStore  # noqa: E402


class MatchingServiceTest(unittest.TestCase):
    def test_matching_service_matches_invoice_to_single_payment(self) -> None:
        db_path = ROOT / "test_matching_one_to_one.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-02-10",
                        description="Plata factura servicii Build House SRL",
                        amount=-1000.0,
                        currency="RON",
                        balance=5000.0,
                        merchant="Build House SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"tx-1000"}',
                    )
                ],
                workspace_id=workspace_id,
            )
            import_batch_id = store.create_document_import_batch(
                source_path=ROOT / "_received_one_to_one.json",
                workspace_id=workspace_id,
                source_type="received_invoice",
            )
            store.insert_invoices(
                workspace_id=workspace_id,
                import_batch_id=import_batch_id,
                role="received",
                invoices=[
                    ImportedInvoice(
                        invoice_number="R-1000",
                        issue_date="2025-02-01",
                        customer_name="Build House SRL",
                        net_amount=840.34,
                        vat_amount=159.66,
                        total_amount=1000.0,
                        currency="RON",
                        status="issued",
                        source_file="received.json",
                        raw_payload='{"invoice":"R-1000"}',
                    )
                ],
            )

            service = MatchingService(store)
            proposals = service.match_workspace(workspace_id=workspace_id)

            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0]["match_kind"], "one_to_one")
            self.assertEqual(proposals[0]["status"], "proposed")
            self.assertEqual(proposals[0]["matched_amount"], 1000.0)
            self.assertEqual(proposals[0]["residual_amount"], 0.0)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_matching_service_marks_clear_partial_payment(self) -> None:
        db_path = ROOT / "test_matching_partial.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-03-15",
                        description="Plata partiala factura Casa Decor",
                        amount=-500.0,
                        currency="RON",
                        balance=3200.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"tx-500"}',
                    )
                ],
                workspace_id=workspace_id,
            )
            import_batch_id = store.create_document_import_batch(
                source_path=ROOT / "_received_partial.json",
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

            service = MatchingService(store)
            proposals = service.match_workspace(workspace_id=workspace_id)

            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0]["match_kind"], "partial_payment")
            self.assertEqual(proposals[0]["matched_amount"], 500.0)
            self.assertEqual(proposals[0]["residual_amount"], 250.0)
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
