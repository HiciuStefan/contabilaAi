from __future__ import annotations

import json
from functools import partial
from http.server import ThreadingHTTPServer
import sys
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
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
from contabila_ai.importing.models import ImportedTransaction, StatementParseResult, StatementValidation  # noqa: E402
from contabila_ai.storage.store import SQLiteTransactionStore  # noqa: E402


class HttpSmokeTest(unittest.TestCase):
    def test_index_contains_workspace_home_shell(self) -> None:
        index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="workspace-home"', index_html)
        self.assertIn('id="workspace-list"', index_html)
        self.assertIn('id="workspace-create-form"', index_html)

    def test_index_contains_workspace_and_onboarding_sections(self) -> None:
        index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="workspace-home"', index_html)
        self.assertIn('id="onboarding-wizard"', index_html)
        self.assertIn('id="workspace-app"', index_html)
        self.assertIn('id="business-memory-panel"', index_html)
        self.assertIn('id="invoice-hub-panel"', index_html)
        self.assertIn('id="change-review-panel"', index_html)
        self.assertIn('id="business-memory-form"', index_html)
        self.assertIn('id="business-memory-input"', index_html)
        self.assertIn('data-tab="invoices"', index_html)
        self.assertIn('data-tab="memory"', index_html)
        self.assertIn('data-tab="review"', index_html)

    def test_index_contains_onboarding_checklist_sections(self) -> None:
        index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="onboarding-checklist"', index_html)
        self.assertIn('id="onboarding-imports"', index_html)
        self.assertIn('id="onboarding-memory"', index_html)
        self.assertIn('id="onboarding-review"', index_html)
        self.assertIn('id="onboarding-change-review"', index_html)

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

    def test_chat_blocks_when_workspace_has_critical_review_items(self) -> None:
        data_dir = ROOT / "test_http_data_review_gate"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            services = build_app_services(data_dir=data_dir)
            workspace_id = services["store"].create_workspace("MobExc")
            services["store"].insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-06-01",
                        description="Plata contractor major fara categorie",
                        amount=-15000.0,
                        currency="RON",
                        balance=8500.0,
                        merchant="Contractor Mare SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"sev-1"}',
                    )
                ],
                workspace_id=workspace_id,
            )

            handler = partial(ContabilaAiRequestHandler, services=services)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                request = Request(
                    f"{base_url}/api/chat",
                    data=json.dumps(
                        {
                            "workspace_id": workspace_id,
                            "question": "cat am platit catre contractor mare",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(payload["plan"]["support_level"], "blocked")
            self.assertIn("critical", payload["review_counts"])
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()

    def test_chat_returns_entity_relationship_summary_for_entity_status_question(self) -> None:
        data_dir = ROOT / "test_http_data_chat_clarify"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            services = build_app_services(data_dir=data_dir)
            workspace_id = services["store"].create_workspace("MobExc")
            services["store"].insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-06-01",
                        description="Incasare proiect",
                        amount=3000.0,
                        currency="RON",
                        balance=3000.0,
                        merchant="AI Excellence SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"relationship-in"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-06-15",
                        description="Plata subcontractor",
                        amount=-1000.0,
                        currency="RON",
                        balance=2000.0,
                        merchant="1/AI EXCELLENCE S.R.L.",
                        source_file="statement.csv",
                        raw_payload='{"id":"relationship-out"}',
                    ),
                ],
                workspace_id=workspace_id,
            )
            for row in services["store"].list_transactions(workspace_id=workspace_id, limit=10):
                services["review"].confirm_transaction(int(row["id"]))

            handler = partial(ContabilaAiRequestHandler, services=services)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                request = Request(
                    f"{base_url}/api/chat",
                    data=json.dumps(
                        {
                            "workspace_id": workspace_id,
                            "question": "care e situatia lui ai excellence",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(payload["plan"]["metric"], "entity_relationship_summary")
            self.assertEqual(payload["plan"]["support_level"], "exact")
            self.assertEqual(payload["rows"][0]["income_total"], 3000.0)
            self.assertEqual(payload["rows"][0]["expense_total"], 1000.0)
            self.assertEqual(len(payload["transaction_rows"]), 2)
            self.assertIn("relatia cu ai excellence", payload["answer"].lower())
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()

    def test_business_memory_endpoint_stores_facts(self) -> None:
        data_dir = ROOT / "test_http_data_business_memory"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            services = build_app_services(data_dir=data_dir)
            workspace_id = services["store"].create_workspace("MobExc")
            handler = partial(ContabilaAiRequestHandler, services=services)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                request = Request(
                    f"{base_url}/api/business-memory",
                    data=json.dumps(
                        {
                            "workspace_id": workspace_id,
                            "text": "Ai Excellence e partener",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(payload["fact_count"], 1)
            self.assertEqual(payload["facts"][0]["fact_type"], "entity_type")
            self.assertEqual(payload["facts"][0]["fact_value"], "partener")
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()

    def test_invoice_workspace_endpoints_upload_and_list_items(self) -> None:
        data_dir = ROOT / "test_http_data_invoice_workspace"
        invoice_path = ROOT / "_http_workspace_invoice.json"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            invoice_path.write_text(
                json.dumps(
                    {
                        "invoices": [
                            {
                                "invoice_number": "INV-HTTP-001",
                                "issue_date": "2025-03-01",
                                "customer": "Ai Excellence SRL",
                                "total": "2380",
                                "vat": "380",
                                "currency": "RON",
                                "status": "issued",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            services = build_app_services(data_dir=data_dir)
            workspace_id = services["store"].create_workspace("MobExc")
            handler = partial(ContabilaAiRequestHandler, services=services)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                upload_request = Request(
                    f"{base_url}/api/invoices/upload",
                    data=json.dumps(
                        {
                            "workspace_id": workspace_id,
                            "role": "issued",
                            "path": str(invoice_path),
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(upload_request, timeout=5) as response:
                    upload_payload = json.loads(response.read().decode("utf-8"))

                with urlopen(
                    f"{base_url}/api/invoices?workspace_id={workspace_id}&role=issued",
                    timeout=5,
                ) as response:
                    list_payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(upload_payload["imported_count"], 1)
            self.assertEqual(upload_payload["result"]["inserted"], 1)
            self.assertEqual(upload_payload["items"][0]["role"], "issued")
            self.assertEqual(len(list_payload["items"]), 1)
            self.assertEqual(list_payload["items"][0]["invoice_number"], "INV-HTTP-001")
            self.assertEqual(list_payload["items"][0]["counterparty_name"], "Ai Excellence SRL")
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()
            if invoice_path.exists():
                invoice_path.unlink()

    def test_invoice_upload_triggers_matching_proposals_for_workspace(self) -> None:
        data_dir = ROOT / "test_http_data_invoice_matching"
        invoice_path = ROOT / "_http_workspace_matching_invoice.json"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            invoice_path.write_text(
                json.dumps(
                    {
                        "invoices": [
                            {
                                "invoice_number": "INV-MATCH-001",
                                "issue_date": "2025-03-01",
                                "customer": "Casa Decor SRL",
                                "total": "750",
                                "vat": "0",
                                "currency": "RON",
                                "status": "issued",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            services = build_app_services(data_dir=data_dir)
            workspace_id = services["store"].create_workspace("MobExc")
            services["store"].insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-03-15",
                        description="Plata partiala factura Casa Decor",
                        amount=-500.0,
                        currency="RON",
                        balance=3200.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"http-match-tx"}',
                    )
                ],
                workspace_id=workspace_id,
            )
            handler = partial(ContabilaAiRequestHandler, services=services)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                upload_request = Request(
                    f"{base_url}/api/invoices/upload",
                    data=json.dumps(
                        {
                            "workspace_id": workspace_id,
                            "role": "received",
                            "path": str(invoice_path),
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(upload_request, timeout=5) as response:
                    upload_payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(upload_payload["matches"][0]["match_kind"], "partial_payment")
            self.assertEqual(upload_payload["matches"][0]["matched_amount"], 500.0)
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()
            if invoice_path.exists():
                invoice_path.unlink()

    def test_invoice_matches_endpoint_returns_enriched_match_rows(self) -> None:
        data_dir = ROOT / "test_http_data_invoice_matches_endpoint"
        invoice_path = ROOT / "_http_workspace_invoice_matches.json"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            invoice_path.write_text(
                json.dumps(
                    {
                        "invoices": [
                            {
                                "invoice_number": "INV-MATCH-ENRICHED",
                                "issue_date": "2025-03-01",
                                "customer": "Casa Decor SRL",
                                "total": "750",
                                "vat": "0",
                                "currency": "RON",
                                "status": "issued",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            services = build_app_services(data_dir=data_dir)
            workspace_id = services["store"].create_workspace("MobExc")
            services["store"].insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-03-15",
                        description="Plata partiala factura Casa Decor",
                        amount=-500.0,
                        currency="RON",
                        balance=3200.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"http-match-list"}',
                    )
                ],
                workspace_id=workspace_id,
            )
            handler = partial(ContabilaAiRequestHandler, services=services)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                upload_request = Request(
                    f"{base_url}/api/invoices/upload",
                    data=json.dumps(
                        {
                            "workspace_id": workspace_id,
                            "role": "received",
                            "path": str(invoice_path),
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(upload_request, timeout=5):
                    pass
                with urlopen(
                    f"{base_url}/api/invoice-matches?workspace_id={workspace_id}",
                    timeout=5,
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["invoice_number"], "INV-MATCH-ENRICHED")
            self.assertEqual(payload["items"][0]["counterparty_name"], "Casa Decor SRL")
            self.assertEqual(payload["items"][0]["merchant"], "Casa Decor SRL")
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()
            if invoice_path.exists():
                invoice_path.unlink()

    def test_change_review_endpoints_list_and_apply_decision(self) -> None:
        data_dir = ROOT / "test_http_data_change_review"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            services = build_app_services(data_dir=data_dir)
            workspace_id = services["store"].create_workspace("MobExc")
            services["store"].insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-04-10",
                        description="Materiale casa noi",
                        amount=-450.0,
                        currency="RON",
                        balance=4100.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"http-change-review"}',
                    )
                ],
                workspace_id=workspace_id,
            )
            transaction_id = services["store"].list_transactions(limit=5)[0]["id"]
            item = services["store"].create_change_review_item(
                workspace_id=workspace_id,
                transaction_id=transaction_id,
                field_name="analysis_category",
                old_value="",
                new_value="casa",
                reason="same counterparty category profile",
                confidence=0.82,
            )
            handler = partial(ContabilaAiRequestHandler, services=services)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(f"{base_url}/api/change-review?workspace_id={workspace_id}", timeout=5) as response:
                    list_payload = json.loads(response.read().decode("utf-8"))

                decision_request = Request(
                    f"{base_url}/api/change-review/decision",
                    data=json.dumps({"item_id": item["id"], "decision": "accept"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(decision_request, timeout=5) as response:
                    decision_payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(len(list_payload["items"]), 1)
            self.assertEqual(list_payload["items"][0]["new_value"], "casa")
            self.assertEqual(decision_payload["decision"], "accept")
            self.assertEqual(decision_payload["item"]["status"], "accept")
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()

    def test_transactions_endpoint_is_scoped_by_workspace(self) -> None:
        data_dir = ROOT / "test_http_data_transactions_workspace_scope"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            services = build_app_services(data_dir=data_dir)
            workspace_a = services["store"].create_workspace("MobExc")
            workspace_b = services["store"].create_workspace("DigExc")
            services["store"].insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-04-10",
                        description="Plata colaborator MobExc",
                        amount=-1000.0,
                        currency="RON",
                        balance=1000.0,
                        merchant="Vendor MobExc",
                        source_file="mob.csv",
                        raw_payload='{"id":"mob-1"}',
                    )
                ],
                workspace_id=workspace_a,
            )
            services["store"].insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-04-11",
                        description="Plata colaborator DigExc",
                        amount=-2000.0,
                        currency="RON",
                        balance=2000.0,
                        merchant="Vendor DigExc",
                        source_file="dig.csv",
                        raw_payload='{"id":"dig-1"}',
                    )
                ],
                workspace_id=workspace_b,
            )

            handler = partial(ContabilaAiRequestHandler, services=services)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(
                    f"{base_url}/api/transactions?workspace_id={workspace_a}&limit=50",
                    timeout=5,
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(len(payload["rows"]), 1)
            self.assertEqual(payload["rows"][0]["merchant"], "Vendor MobExc")
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

    def test_import_document_path_rejects_invalid_statement_validation(self) -> None:
        data_dir = ROOT / "test_http_data_invalid_validation"
        statement_path = ROOT / "_invalid_statement.json"
        if data_dir.exists():
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
        else:
            data_dir.mkdir(parents=True)
        try:
            statement_path.write_text("{}", encoding="utf-8")
            services = build_app_services(data_dir=data_dir)
            with patch(
                "contabila_ai.server.http.parse_statement_bundle",
                return_value=StatementParseResult(
                    transactions=tuple(),
                    validation=StatementValidation(
                        available=True,
                        passed=False,
                        parser_name="test",
                        errors=("income_total_mismatch", "transaction_count_mismatch"),
                        declared_transaction_count=10,
                        parsed_transaction_count=9,
                        declared_inflow_count=2,
                        parsed_inflow_count=2,
                        declared_outflow_count=8,
                        parsed_outflow_count=7,
                        declared_total_income=100.0,
                        parsed_total_income=90.0,
                        declared_total_expenses=50.0,
                        parsed_total_expenses=50.0,
                        declared_net_cashflow=50.0,
                        parsed_net_cashflow=40.0,
                        declared_opening_balance=0.0,
                        declared_closing_balance=50.0,
                        parsed_closing_balance=40.0,
                        inferred_transaction_count=0,
                    ),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "Validarea extrasului a esuat"):
                    import_document_path(services, statement_path)
        finally:
            db_path = data_dir / "contabila_ai.sqlite3"
            if db_path.exists():
                db_path.unlink()
            if data_dir.exists():
                data_dir.rmdir()
            if statement_path.exists():
                statement_path.unlink()

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

    def test_workspace_can_progress_from_import_to_ready_flow(self) -> None:
        data_dir = ROOT / "test_http_data_workspace_flow"
        statement_path = ROOT / "_workspace_flow_statement.json"
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
                                "date": "2025-01-10",
                                "description": "Incasare partener AI Excellence",
                                "amount": 3200.0,
                                "currency": "RON",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            services = build_app_services(data_dir=data_dir)
            workspace_id = services["store"].create_workspace("MobExc")

            import_document_path(services, statement_path, workspace_id=workspace_id)
            services["memory"].add_instruction(workspace_id, "AI Excellence e partener")

            status = services["workspaces"].list_workspaces()[0]["status"]

            self.assertIn(status, {"needs_review", "ready"})
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
