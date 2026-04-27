from __future__ import annotations

import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from contabila_ai.importing.parsers import parse_csv, parse_issued_invoices_path, parse_pdf, parse_statement_path  # noqa: E402
from contabila_ai.storage.store import SQLiteTransactionStore  # noqa: E402


def canonical_garanti_pdf_path() -> Path | None:
    candidates = (
        Path(r"C:\Users\stefan\Downloads\ExtrasDeCont.pdf"),
        Path(r"C:\Users\stefan\Downloads\Date\ExtrasDeCont.pdf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def canonical_ing_pdf_path() -> Path | None:
    candidate = ROOT / "Date" / "MobExc" / "ING Statement.pdf"
    return candidate if candidate.exists() else None


def canonical_digexc_invoice_pdf_paths() -> list[Path]:
    invoice_dir = ROOT / "Date" / "DigExc"
    if not invoice_dir.exists():
        return []
    return sorted(invoice_dir.glob("f_*.pdf"))


class ImporterTest(unittest.TestCase):
    def test_parse_statement_path_dispatches_by_suffix(self) -> None:
        csv_path = ROOT / "_importer_dispatch.csv"
        json_path = ROOT / "_importer_dispatch.json"
        pdf_path = ROOT / "_importer_dispatch.pdf"
        try:
            csv_path.write_text("date,description,amount\n2026-04-22,CSV row,10.00\n", encoding="utf-8")
            json_path.write_text(
                json.dumps({"transactions": [{"date": "2026-04-22", "description": "JSON row", "amount": 20.0}]}),
                encoding="utf-8",
            )
            pdf_path.write_text("placeholder", encoding="utf-8")

            with (
                patch("contabila_ai.importing.parsers.parse_csv", return_value=["csv"]) as csv_mock,
                patch("contabila_ai.importing.parsers.parse_json", return_value=["json"]) as json_mock,
                patch("contabila_ai.importing.parsers.parse_pdf", return_value=["pdf"]) as pdf_mock,
            ):
                self.assertEqual(parse_statement_path(csv_path), ["csv"])
                self.assertEqual(parse_statement_path(json_path), ["json"])
                self.assertEqual(parse_statement_path(pdf_path), ["pdf"])

            csv_mock.assert_called_once_with(csv_path)
            json_mock.assert_called_once_with(json_path)
            pdf_mock.assert_called_once_with(pdf_path)
        finally:
            for path in (csv_path, json_path, pdf_path):
                if path.exists():
                    path.unlink()

    def test_parse_csv_extracts_basic_fields(self) -> None:
        path = ROOT / "_importer_fields.csv"
        try:
            path.write_text(
                "\n".join(
                    [
                        "Date,Description,Debit,Credit,Balance,Currency",
                        "22/04/2026,Daily Brew card payment,24.50,,975.50,RON",
                    ]
                ),
                encoding="utf-8",
            )
            transactions = parse_csv(path)
            self.assertEqual(len(transactions), 1)
            tx = transactions[0]
            self.assertEqual(tx.transaction_date, "2026-04-22")
            self.assertEqual(tx.description, "Daily Brew card payment")
            self.assertEqual(tx.amount, -24.5)
            self.assertEqual(tx.currency, "RON")
            self.assertEqual(tx.balance, 975.5)
            self.assertEqual(tx.merchant, "Daily Brew")
        finally:
            if path.exists():
                path.unlink()

    def test_parse_json_extracts_basic_fields(self) -> None:
        path = ROOT / "_importer_fields.json"
        try:
            path.write_text(
                json.dumps(
                    {
                        "transactions": [
                            {
                                "booking date": "2026-04-22T10:15:00",
                                "details": "Salary payroll",
                                "credit": "3500.00",
                                "balance": "4500.00",
                                "currency": "RON",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            transactions = parse_statement_path(path)
            self.assertEqual(len(transactions), 1)
            tx = transactions[0]
            self.assertEqual(tx.transaction_date, "2026-04-22")
            self.assertEqual(tx.description, "Salary payroll")
            self.assertEqual(tx.amount, 3500.0)
            self.assertEqual(tx.currency, "RON")
            self.assertEqual(tx.balance, 4500.0)
            self.assertEqual(tx.merchant, "Salary payroll")
        finally:
            if path.exists():
                path.unlink()

    def test_parse_issued_invoices_json_extracts_invoice_fields(self) -> None:
        path = ROOT / "_issued_invoices.json"
        try:
            path.write_text(
                json.dumps(
                    {
                        "invoices": [
                            {
                                "invoice_number": "INV-001",
                                "issue_date": "2025-01-15",
                                "customer": "Client Alpha SRL",
                                "total": "11900",
                                "vat": "1900",
                                "currency": "RON",
                                "status": "issued",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            invoices = parse_issued_invoices_path(path)

            self.assertEqual(len(invoices), 1)
            invoice = invoices[0]
            self.assertEqual(invoice.invoice_number, "INV-001")
            self.assertEqual(invoice.issue_date, "2025-01-15")
            self.assertEqual(invoice.customer_name, "Client Alpha SRL")
            self.assertEqual(invoice.total_amount, 11900.0)
            self.assertEqual(invoice.vat_amount, 1900.0)
            self.assertEqual(invoice.net_amount, 10000.0)
            self.assertEqual(invoice.currency, "RON")
            self.assertEqual(invoice.status, "issued")
        finally:
            if path.exists():
                path.unlink()

    def test_real_digexc_invoice_pdfs_extract_invoice_fields(self) -> None:
        paths = canonical_digexc_invoice_pdf_paths()
        if not paths:
            self.skipTest("DigExc invoice PDF fixtures are missing from Date/DigExc.")

        invoices = []
        for path in paths:
            invoices.extend(parse_issued_invoices_path(path))

        self.assertEqual(len(invoices), 3)
        by_number = {invoice.invoice_number: invoice for invoice in invoices}
        self.assertEqual(set(by_number), {"6", "9", "12"})

        invoice_6 = by_number["6"]
        self.assertEqual(invoice_6.issue_date, "2024-12-04")
        self.assertEqual(invoice_6.customer_name, "TECHENABLED LLC.A GEORGIA, USA CORPORATION")
        self.assertEqual(invoice_6.currency, "USD")
        self.assertEqual(invoice_6.net_amount, 19717.97)
        self.assertEqual(invoice_6.vat_amount, 0.0)
        self.assertEqual(invoice_6.total_amount, 19717.97)

        self.assertAlmostEqual(sum(invoice.total_amount for invoice in invoices), 96347.63, places=2)

    def test_real_garanti_pdf_returns_many_transactions(self) -> None:
        path = canonical_garanti_pdf_path()
        if path is None:
            self.skipTest("Canonical Garanti PDF fixture is missing from Downloads.")

        transactions = parse_pdf(path)

        self.assertEqual(len(transactions), 623)
        first = transactions[0]
        self.assertEqual(first.transaction_date, "2024-09-13")
        self.assertEqual(first.description, "DEPUNERE NUMERAR | Agentie: SIBIU | Detalii: incas diverse")
        self.assertEqual(first.amount, 50.0)
        self.assertEqual(first.currency, "RON")
        self.assertEqual(first.balance, 50.0)
        self.assertEqual(first.merchant, "DEPUNERE NUMERAR")
        self.assertEqual(first.source_file, str(path))

    def test_real_ing_pdf_returns_many_transactions(self) -> None:
        path = canonical_ing_pdf_path()
        if path is None:
            self.skipTest("MobExc ING PDF fixture is missing from Date/MobExc.")

        transactions = parse_pdf(path)

        self.assertEqual(len(transactions), 3322)
        self.assertAlmostEqual(sum(tx.amount for tx in transactions if tx.amount > 0), 26716896.81, places=2)
        self.assertAlmostEqual(sum(-tx.amount for tx in transactions if tx.amount < 0), 26662604.83, places=2)
        self.assertAlmostEqual(sum(tx.amount for tx in transactions), 54291.98, places=2)
        first = transactions[0]
        self.assertEqual(first.transaction_date, "2020-05-14")
        self.assertEqual(first.description, "Incoming funds | Capital social Hiciu Stefan | 371663778")
        self.assertEqual(first.amount, 190.0)
        self.assertEqual(first.currency, "RON")
        self.assertEqual(first.balance, 190.0)
        self.assertEqual(first.merchant, "Hiciu Stefan")
        self.assertEqual(first.source_file, str(path))

    def test_imported_statement_summary_matches_statement_totals(self) -> None:
        path = canonical_garanti_pdf_path()
        if path is None:
            self.skipTest("Canonical Garanti PDF fixture is missing from Downloads.")

        db_path = ROOT / "test_real_statement_summary.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            transactions = parse_statement_path(path)
            store = SQLiteTransactionStore(db_path)

            result = store.insert_many(transactions)
            summary = store.summary()

            self.assertEqual(result["inserted"], 623)
            self.assertEqual(result["skipped"], 0)
            self.assertGreater(result["import_batch_id"], 0)
            self.assertEqual(summary["transaction_count"], 623)
            self.assertAlmostEqual(summary["total_income"], 2225700.95, places=2)
            self.assertAlmostEqual(summary["total_expenses"], 2161702.50, places=2)
            self.assertAlmostEqual(summary["net_cashflow"], 63998.45, places=2)
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
