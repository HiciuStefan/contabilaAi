from __future__ import annotations

import json
from functools import partial
from http.server import ThreadingHTTPServer
import sys
from pathlib import Path
import threading
import unittest
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from contabila_ai.review import ReviewService  # noqa: E402
from contabila_ai.server.http import (  # noqa: E402
    ContabilaAiRequestHandler,
    build_app_services,
    import_document_path,
    parse_single_file_multipart,
)
from contabila_ai.storage.store import SQLiteTransactionStore  # noqa: E402


class HttpSmokeTest(unittest.TestCase):
    def test_index_contains_workspace_home_shell(self) -> None:
        index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="workspace-home"', index_html)
        self.assertIn('id="workspace-list"', index_html)
        self.assertIn('id="workspace-create-form"', index_html)

    def test_workspaces_endpoint_creates_and_lists_workspace(self) -> None:
        data_dir = ROOT / "test_http_data_workspaces"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            services = build_app_services(data_dir=data_dir)
            handler = partial(ContabilaAiRequestHandler, services=services)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                create_request = Request(
                    f"{base_url}/api/workspaces",
                    data=json.dumps({"name": "MobExc"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(create_request, timeout=5) as response:
                    create_payload = json.loads(response.read().decode("utf-8"))

                with urlopen(f"{base_url}/api/workspaces", timeout=5) as response:
                    list_payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertGreater(create_payload["workspace_id"], 0)
            self.assertEqual(list_payload["items"][0]["name"], "MobExc")
            self.assertEqual(list_payload["items"][0]["status"], "needs_import")
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()

    def test_parse_single_file_multipart_extracts_uploaded_statement(self) -> None:
        boundary = "----ContabilaAiBoundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="extras.json"\r\n'
            "Content-Type: application/json\r\n"
            "\r\n"
            '{"transactions": []}\r\n'
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        uploaded = parse_single_file_multipart(
            content_type=f"multipart/form-data; boundary={boundary}",
            body=body,
        )

        self.assertEqual(uploaded.filename, "extras.json")
        self.assertEqual(uploaded.content, b'{"transactions": []}')

    def test_http_services_bootstrap(self) -> None:
        data_dir = ROOT / "test_http_data"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            services = build_app_services(data_dir=data_dir)

            self.assertIn("store", services)
            self.assertIn("review", services)
            self.assertIn("web_dir", services)
            self.assertIsInstance(services["store"], SQLiteTransactionStore)
            self.assertIsInstance(services["review"], ReviewService)
            self.assertTrue(Path(services["web_dir"]).exists())
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()

    def test_http_services_can_import_statement_during_startup(self) -> None:
        data_dir = ROOT / "test_http_data_import"
        statement_path = ROOT / "_startup_import.json"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            statement_path.write_text(
                json.dumps(
                    {
                        "transactions": [
                            {
                                "date": "2026-04-23",
                                "description": "Startup import salary",
                                "amount": 1200.0,
                                "currency": "RON",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            services = build_app_services(data_dir=data_dir, initial_statement_path=statement_path)

            self.assertEqual(services["startup_import"]["result"]["inserted"], 1)
            self.assertEqual(services["startup_import"]["result"]["skipped"], 0)
            self.assertEqual(services["store"].summary()["transaction_count"], 1)
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()
            if statement_path.exists():
                statement_path.unlink()

    def test_import_document_path_detects_invoice_pdf_before_statement_parser(self) -> None:
        invoice_paths = sorted((ROOT / "Date" / "DigExc").glob("f_*.pdf"))
        if not invoice_paths:
            self.skipTest("DigExc invoice PDF fixtures are missing from Date/DigExc.")

        data_dir = ROOT / "test_http_data_invoice_pdf"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            services = build_app_services(data_dir=data_dir)

            payload = import_document_path(services, invoice_paths[0])

            self.assertEqual(payload["document_type"], "issued_invoices")
            self.assertEqual(payload["imported_count"], 1)
            self.assertEqual(payload["result"]["inserted"], 1)
            self.assertEqual(services["store"].summary()["transaction_count"], 0)
            self.assertEqual(services["store"].issued_invoice_summary()["invoice_count"], 1)
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()

    def test_http_services_start_without_forced_startup_import(self) -> None:
        data_dir = ROOT / "test_http_data_empty_start"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            services = build_app_services(data_dir=data_dir)

            self.assertIsNone(services["startup_import"])
            self.assertEqual(services["store"].summary()["transaction_count"], 0)
            self.assertEqual(services["store"].list_import_batches(), [])
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()

    def test_http_services_reset_clears_saved_imports(self) -> None:
        data_dir = ROOT / "test_http_data_reset"
        statement_path = ROOT / "_startup_import_reset.json"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            statement_path.write_text(
                json.dumps(
                    {
                        "transactions": [
                            {
                                "date": "2026-04-23",
                                "description": "Reset me",
                                "amount": 1200.0,
                                "currency": "RON",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            services = build_app_services(data_dir=data_dir, initial_statement_path=statement_path)
            self.assertEqual(services["store"].summary()["transaction_count"], 1)

            services["store"].reset_all_data()

            self.assertEqual(services["store"].summary()["transaction_count"], 0)
            self.assertEqual(services["store"].list_import_batches(), [])
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()
            if statement_path.exists():
                statement_path.unlink()


if __name__ == "__main__":
    unittest.main()
