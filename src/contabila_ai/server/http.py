from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote_plus, urlparse

from contabila_ai.change_review import ChangeReviewService
from contabila_ai.importing import import_invoice_documents, parse_issued_invoices_path, parse_statement_bundle
from contabila_ai.matching import MatchingService
from contabila_ai.memory import BusinessMemoryService
from contabila_ai.planning import build_query_plan
from contabila_ai.review import ReviewService
from contabila_ai.storage.store import SQLiteTransactionStore
from contabila_ai.workspaces.service import WorkspaceService


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content: bytes


def build_app_services(
    data_dir: Path | None = None,
    initial_statement_path: Path | None = None,
) -> dict[str, Any]:
    root_dir = Path(__file__).resolve().parents[3]
    resolved_data_dir = Path(data_dir) if data_dir is not None else root_dir / "data"
    resolved_data_dir.mkdir(parents=True, exist_ok=True)
    db_path = resolved_data_dir / "contabila_ai.sqlite3"
    web_dir = root_dir / "web"
    store = SQLiteTransactionStore(db_path)
    review = ReviewService(store)
    memory = BusinessMemoryService(store)
    matching = MatchingService(store)
    change_review = ChangeReviewService(store)
    workspaces = WorkspaceService(store, review)
    services = {
        "root_dir": root_dir,
        "data_dir": resolved_data_dir,
        "db_path": db_path,
        "web_dir": web_dir,
        "store": store,
        "review": review,
        "memory": memory,
        "matching": matching,
        "change_review": change_review,
        "workspaces": workspaces,
        "startup_import": None,
    }
    if initial_statement_path is not None:
        source_path = Path(initial_statement_path).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f"Missing statement file: {source_path}")
        statement_bundle = parse_statement_bundle(source_path)
        _raise_on_failed_statement_validation(statement_bundle.validation)
        services["startup_import"] = {
            "path": str(source_path),
            "imported_count": len(statement_bundle.transactions),
            "result": store.insert_many(statement_bundle.transactions),
            "validation": _serialize_statement_validation(statement_bundle.validation),
        }
    return services


def run(
    host: str = "127.0.0.1",
    port: int = 8010,
    data_dir: Path | None = None,
    initial_statement_path: Path | None = None,
) -> None:
    services = build_app_services(data_dir=data_dir, initial_statement_path=initial_statement_path)
    handler = partial(ContabilaAiRequestHandler, services=services)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"ContabilaAi runs at http://{host}:{port}")
    if services["startup_import"] is not None:
        print(
            "Imported startup statement:",
            services["startup_import"]["path"],
            services["startup_import"]["result"],
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def import_document_path(
    services: dict[str, Any],
    source_path: Path,
    *,
    workspace_id: int | None = None,
) -> dict[str, Any]:
    if source_path.suffix.lower() == ".pdf":
        invoices = parse_issued_invoices_path(source_path)
        if invoices:
            if workspace_id is not None:
                invoice_result = import_invoice_documents(
                    store=services["store"],
                    workspace_id=workspace_id,
                    role="issued",
                    source_path=source_path,
                )
                return {
                    "document_type": "issued_invoices",
                    **invoice_result,
                    "invoice_summary": services["store"].issued_invoice_summary(),
                    "workspace_id": workspace_id,
                }
            result = services["store"].insert_issued_invoices(invoices)
            return {
                "document_type": "issued_invoices",
                "result": result,
                "imported_count": len(invoices),
                "invoice_summary": services["store"].issued_invoice_summary(),
            }

    statement_bundle = parse_statement_bundle(source_path)
    _raise_on_failed_statement_validation(statement_bundle.validation)
    result = services["store"].insert_many(statement_bundle.transactions, workspace_id=workspace_id)
    return {
        "document_type": "statement",
        "result": result,
        "imported_count": len(statement_bundle.transactions),
        "summary": services["store"].summary(import_batch_id=result["import_batch_id"]),
        "imports": services["store"].list_import_batches(workspace_id=workspace_id),
        "active_import_id": result["import_batch_id"],
        "workspace_id": workspace_id,
        "validation": _serialize_statement_validation(statement_bundle.validation),
    }


def parse_single_file_multipart(content_type: str, body: bytes) -> UploadedFile:
    boundary_match = re.search(r'boundary="?([^";]+)"?', content_type)
    if boundary_match is None:
        raise ValueError("Missing multipart boundary.")

    boundary = f"--{boundary_match.group(1)}".encode("utf-8")
    for part in body.split(boundary):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip(b"\r\n")
        header_blob, separator, content = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        headers = header_blob.decode("utf-8", errors="replace")
        if 'name="file"' not in headers:
            continue
        filename_match = re.search(r'filename="([^"]+)"', headers)
        filename = Path(filename_match.group(1)).name if filename_match else "upload"
        content = content.rstrip(b"\r\n")
        if not filename or not content:
            raise ValueError("Uploaded file is empty.")
        return UploadedFile(filename=filename, content=content)

    raise ValueError("Multipart body does not contain a file field.")


class ContabilaAiRequestHandler(BaseHTTPRequestHandler):
    server_version = "ContabilaAiHTTP/0.1"

    def __init__(self, *args: Any, services: dict[str, Any], **kwargs: Any) -> None:
        self.services = services
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/workspaces":
            self._send_json({"items": self.services["workspaces"].list_workspaces()})
            return
        if parsed.path == "/api/summary":
            self._send_json(
                self.services["store"].summary(
                    import_batch_id=self._parse_import_id(parsed.query),
                    workspace_id=self._parse_workspace_id(parsed.query),
                )
            )
            return
        if parsed.path == "/api/imports":
            self._send_json(
                {
                    "imports": self.services["store"].list_import_batches(
                        workspace_id=self._parse_workspace_id(parsed.query)
                    )
                }
            )
            return
        if parsed.path == "/api/categories":
            self._send_json({"categories": self.services["store"].list_analysis_categories()})
            return
        if parsed.path == "/api/invoices":
            workspace_id = self._parse_workspace_id(parsed.query)
            if workspace_id is None:
                raise ValueError("workspace_id is required.")
            role = self._parse_text_param(parsed.query, "role")
            self._send_json(
                {
                    "items": self.services["store"].list_workspace_invoices(
                        workspace_id,
                        role=role,
                    )
                }
            )
            return
        if parsed.path == "/api/invoice-matches":
            workspace_id = self._parse_workspace_id(parsed.query)
            if workspace_id is None:
                raise ValueError("workspace_id is required.")
            items = []
            for item in self.services["store"].list_invoice_matches(workspace_id):
                invoice = self.services["store"].fetch_workspace_invoice_by_id(int(item["invoice_id"]))
                transaction = self.services["store"].fetch_transaction_by_id(int(item["transaction_id"]))
                items.append(
                    {
                        **item,
                        "invoice_number": None if not invoice else invoice.get("invoice_number"),
                        "counterparty_name": None if not invoice else invoice.get("counterparty_name"),
                        "currency": (
                            invoice.get("currency")
                            if invoice and invoice.get("currency")
                            else (transaction.get("currency") if transaction else None)
                        ),
                        "merchant": None if not transaction else transaction.get("merchant"),
                    }
                )
            self._send_json({"items": items})
            return
        if parsed.path == "/api/change-review":
            workspace_id = self._parse_workspace_id(parsed.query)
            if workspace_id is None:
                raise ValueError("workspace_id is required.")
            self._send_json({"items": self.services["store"].list_change_review_items(workspace_id)})
            return
        if parsed.path == "/api/business-memory":
            workspace_id = self._parse_workspace_id(parsed.query)
            if workspace_id is None:
                raise ValueError("workspace_id is required.")
            self._send_json({"facts": self.services["store"].list_business_facts(workspace_id)})
            return
        if parsed.path == "/api/category-transactions":
            self._handle_category_transactions(parsed.query)
            return
        if parsed.path == "/api/transactions":
            self._handle_transactions(parsed.query)
            return
        if parsed.path == "/api/review":
            limit = self._parse_limit(parsed.query)
            import_batch_id = self._parse_import_id(parsed.query)
            workspace_id = self._parse_workspace_id(parsed.query)
            self._send_json(
                {
                    "rows": self.services["review"].candidates(
                        limit=limit,
                        import_batch_id=import_batch_id,
                        workspace_id=workspace_id,
                    ),
                    "groups": self.services["review"].candidate_groups(
                        limit=limit,
                        import_batch_id=import_batch_id,
                        workspace_id=workspace_id,
                    ),
                    "import_batch_id": import_batch_id,
                    "workspace_id": workspace_id,
                }
            )
            return
        if parsed.path in {"/", "/index.html"}:
            self._send_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_static("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._send_static("styles.css", "text/css; charset=utf-8")
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/upload-file":
                self._handle_upload_file()
                return
            payload = self._read_json()
            if parsed.path == "/api/upload":
                self._handle_upload(payload)
                return
            if parsed.path == "/api/workspaces":
                self._handle_create_workspace(payload)
                return
            if parsed.path == "/api/invoices/upload":
                self._handle_invoice_upload(payload)
                return
            if parsed.path == "/api/business-memory":
                self._handle_business_memory(payload)
                return
            if parsed.path == "/api/chat":
                self._handle_chat(payload)
                return
            if parsed.path == "/api/change-review/decision":
                self._handle_change_review_decision(payload)
                return
            if parsed.path == "/api/review/category":
                self._handle_apply_category(payload)
                return
            if parsed.path == "/api/categories/update":
                self._handle_update_category(payload)
                return
            if parsed.path == "/api/review/confirm":
                self._handle_confirm(payload)
                return
            if parsed.path == "/api/reset":
                self._handle_reset()
                return
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
        except FileNotFoundError as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.NOT_FOUND)
        except Exception as error:  # pragma: no cover - defensive server path
            self._send_json({"error": f"Internal server error: {error}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_upload(self, payload: dict[str, Any]) -> None:
        source_path = Path(str(payload.get("path") or "")).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f"Missing statement file: {source_path}")
        workspace_id = payload.get("workspace_id")
        resolved_workspace_id = None if workspace_id in (None, "") else int(workspace_id)
        self._import_statement_path(source_path, workspace_id=resolved_workspace_id)

    def _handle_upload_file(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length <= 0:
            raise ValueError("Upload body is empty.")
        uploaded = parse_single_file_multipart(
            content_type=self.headers.get("Content-Type", ""),
            body=self.rfile.read(content_length),
        )
        uploads_dir = Path(self.services["data_dir"]) / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(uploaded.filename).name).strip(" .")
        if not safe_name:
            safe_name = "statement"
        destination = uploads_dir / safe_name
        if destination.exists():
            destination = uploads_dir / f"{destination.stem}-{len(list(uploads_dir.glob(destination.stem + '*')))}{destination.suffix}"
        destination.write_bytes(uploaded.content)
        self._import_statement_path(destination, workspace_id=self._parse_workspace_id(urlparse(self.path).query))

    def _import_statement_path(self, source_path: Path, *, workspace_id: int | None = None) -> None:
        self._send_json(import_document_path(self.services, source_path, workspace_id=workspace_id))

    def _handle_create_workspace(self, payload: dict[str, Any]) -> None:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Workspace name is required.")
        workspace_id = self.services["workspaces"].create_workspace(name)
        self._send_json({"workspace_id": workspace_id, "items": self.services["workspaces"].list_workspaces()})

    def _handle_transactions(self, query: str) -> None:
        import_batch_id = self._parse_import_id(query)
        workspace_id = self._parse_workspace_id(query)
        min_abs_amount = self._parse_float_param(query, "min_abs_amount")
        max_abs_amount = self._parse_float_param(query, "max_abs_amount")
        direction = self._parse_text_param(query, "direction")
        economic_kind = self._parse_text_param(query, "economic_kind")
        search = self._parse_text_param(query, "search")
        limit = self._parse_limit(query)
        rows = self.services["store"].list_transactions(
            import_batch_id=import_batch_id,
            workspace_id=workspace_id,
            min_abs_amount=min_abs_amount,
            max_abs_amount=max_abs_amount,
            direction=direction,
            economic_kind=economic_kind,
            search=search,
            limit=limit,
        )
        self._send_json({"rows": rows})

    def _handle_category_transactions(self, query: str) -> None:
        category_name = self._parse_text_param(query, "category_name")
        if not category_name:
            raise ValueError("category_name is required.")
        import_batch_id = self._parse_import_id(query)
        workspace_id = self._parse_workspace_id(query)
        limit = self._parse_limit(query)
        rows = self.services["store"].list_transactions_for_category(
            category_name,
            import_batch_id=import_batch_id,
            workspace_id=workspace_id,
            limit=limit,
        )
        self._send_json({"rows": rows, "category_name": category_name})

    def _handle_invoice_upload(self, payload: dict[str, Any]) -> None:
        source_path = Path(str(payload.get("path") or "")).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f"Missing invoice file: {source_path}")
        workspace_id = payload.get("workspace_id")
        if workspace_id in (None, ""):
            raise ValueError("workspace_id is required.")
        role = str(payload.get("role") or "issued").strip() or "issued"
        result = import_invoice_documents(
            store=self.services["store"],
            workspace_id=int(workspace_id),
            role=role,
            source_path=source_path,
        )
        matches = self.services["matching"].match_workspace(workspace_id=int(workspace_id))
        change_items = self.services["change_review"].refresh_for_workspace(workspace_id=int(workspace_id))
        self._send_json(
            {
                **result,
                "matches": matches,
                "change_review_items": change_items,
                "invoice_summary": self.services["store"].issued_invoice_summary(),
                "workspace_id": int(workspace_id),
                "role": role,
            }
        )

    def _handle_chat(self, payload: dict[str, Any]) -> None:
        question = str(payload.get("question") or "").strip()
        if not question:
            raise ValueError("Question is required.")
        store = self.services["store"]
        import_batch_id = payload.get("import_batch_id")
        workspace_id = payload.get("workspace_id")
        resolved_import_batch_id = None if import_batch_id in (None, "") else int(import_batch_id)
        resolved_workspace_id = None if workspace_id in (None, "") else int(workspace_id)
        if resolved_workspace_id is not None and self.services["review"].has_blocking_items(workspace_id=resolved_workspace_id):
            self._send_json(
                {
                    "answer": "Mai ai tranzactii cu severitate critical sau high de revizuit inainte de intrebari serioase.",
                    "import_batch_id": resolved_import_batch_id,
                    "workspace_id": resolved_workspace_id,
                    "plan": {
                        "mode": "aggregate",
                        "metric": "unsupported",
                        "metric_label": "review gate",
                        "support_level": "blocked",
                    },
                    "rows": [],
                    "transaction_rows": [],
                    "review_counts": self.services["review"].severity_counts(workspace_id=resolved_workspace_id),
                }
            )
            return
        plan = build_query_plan(question)
        if plan.support_level in {"clarify", "unsupported"}:
            self._send_json(
                {
                    "answer": render_answer(plan, []),
                    "import_batch_id": resolved_import_batch_id,
                    "workspace_id": resolved_workspace_id,
                    "plan": {
                        "mode": plan.mode,
                        "metric": plan.metric,
                        "metric_label": plan.metric_label,
                        "support_level": plan.support_level,
                        "group_by": plan.group_by,
                        "years": plan.years,
                        "direction": plan.direction,
                        "economic_kind": plan.economic_kind,
                        "analysis_category": plan.analysis_category,
                        "entity_name": plan.entity_name,
                        "project_name": plan.project_name,
                        "creditare_focus": getattr(plan, "creditare_focus", None),
                        "include_creditare_balance": getattr(plan, "include_creditare_balance", False),
                    },
                    "rows": [],
                    "transaction_rows": [],
                    "review_counts": self.services["review"].severity_counts(workspace_id=resolved_workspace_id)
                    if resolved_workspace_id is not None
                    else None,
                }
            )
            return
        execution = store.execute_plan_for_import(
            plan,
            import_batch_id=resolved_import_batch_id,
            workspace_id=resolved_workspace_id,
        )
        transaction_rows = store.list_matching_transactions_for_plan(
            plan,
            import_batch_id=resolved_import_batch_id,
            workspace_id=resolved_workspace_id,
        )
        self._send_json(
            {
                "answer": render_answer(plan, execution.rows),
                "import_batch_id": resolved_import_batch_id,
                "workspace_id": resolved_workspace_id,
                "plan": {
                    "mode": plan.mode,
                    "metric": plan.metric,
                    "metric_label": plan.metric_label,
                    "support_level": plan.support_level,
                    "years": plan.years,
                    "group_by": plan.group_by,
                    "economic_kind": plan.economic_kind,
                    "excluded_economic_kinds": plan.excluded_economic_kinds,
                    "analysis_category": plan.analysis_category,
                    "entity_name": plan.entity_name,
                    "project_name": getattr(plan, "project_name", None),
                    "direction": plan.direction,
                    "requested_profit": plan.requested_profit,
                    "creditare_focus": getattr(plan, "creditare_focus", None),
                    "include_creditare_balance": getattr(plan, "include_creditare_balance", False),
                },
                "rows": execution.rows,
                "transaction_rows": transaction_rows,
                "review_counts": self.services["review"].severity_counts(workspace_id=resolved_workspace_id)
                if resolved_workspace_id is not None
                else None,
            }
        )

    def _handle_apply_category(self, payload: dict[str, Any]) -> None:
        category_name = str(payload.get("category_name") or "").strip()
        transaction_ids = payload.get("transaction_ids") or []
        if not category_name:
            raise ValueError("Category name is required.")
        if not isinstance(transaction_ids, list) or not transaction_ids:
            raise ValueError("transaction_ids must be a non-empty list.")
        import_batch_id = payload.get("import_batch_id")
        result = self.services["review"].apply_category(
            category_name=category_name,
            transaction_ids=[int(item) for item in transaction_ids],
            apply_to_similar=bool(payload.get("apply_to_similar", True)),
            import_batch_id=None if import_batch_id in (None, "") else int(import_batch_id),
            description=str(payload.get("description") or "").strip() or None,
            operational_scope=str(payload.get("operational_scope") or "unassigned").strip() or "unassigned",
            replace_existing=bool(payload.get("replace_existing", False)),
        )
        self._send_json(
            {
                "result": result,
                "categories": self.services["store"].list_analysis_categories(),
                "rows": self.services["review"].candidates(
                    import_batch_id=None if import_batch_id in (None, "") else int(import_batch_id)
                ),
                "groups": self.services["review"].candidate_groups(
                    import_batch_id=None if import_batch_id in (None, "") else int(import_batch_id)
                ),
                "summary": self.services["store"].summary(
                    import_batch_id=None if import_batch_id in (None, "") else int(import_batch_id)
                ),
            }
        )

    def _handle_update_category(self, payload: dict[str, Any]) -> None:
        category_name = str(payload.get("category_name") or "").strip()
        if not category_name:
            raise ValueError("Category name is required.")
        category = self.services["store"].update_analysis_category(
            category_name,
            description=str(payload.get("description") or "").strip() or None,
            operational_scope=str(payload.get("operational_scope") or "unassigned").strip() or "unassigned",
        )
        self._send_json(
            {
                "status": "ok",
                "category": category,
                "categories": self.services["store"].list_analysis_categories(),
            }
        )

    def _handle_business_memory(self, payload: dict[str, Any]) -> None:
        workspace_id = payload.get("workspace_id")
        if workspace_id in (None, ""):
            raise ValueError("workspace_id is required.")
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("text is required.")
        self._send_json(self.services["memory"].add_instruction(int(workspace_id), text))

    def _handle_confirm(self, payload: dict[str, Any]) -> None:
        transaction_id = payload.get("transaction_id")
        if transaction_id is None:
            raise ValueError("transaction_id is required.")
        import_batch_id = payload.get("import_batch_id")
        self.services["review"].confirm_transaction(int(transaction_id))
        self._send_json(
            {
                "status": "ok",
                "rows": self.services["review"].candidates(
                    import_batch_id=None if import_batch_id in (None, "") else int(import_batch_id)
                ),
                "groups": self.services["review"].candidate_groups(
                    import_batch_id=None if import_batch_id in (None, "") else int(import_batch_id)
                ),
            }
        )

    def _handle_change_review_decision(self, payload: dict[str, Any]) -> None:
        item_id = payload.get("item_id")
        decision = str(payload.get("decision") or "").strip()
        if item_id is None:
            raise ValueError("item_id is required.")
        if not decision:
            raise ValueError("decision is required.")
        self._send_json(self.services["change_review"].apply_decision(item_id=int(item_id), decision=decision))

    def _handle_reset(self) -> None:
        self.services["store"].reset_all_data()
        self._send_json(
            {
                "status": "ok",
                "imports": [],
                "summary": self.services["store"].summary(),
                "rows": [],
            }
        )

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON body: {error.msg}") from error
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def _send_static(self, filename: str, content_type: str) -> None:
        file_path = Path(self.services["web_dir"]) / filename
        if not file_path.exists():
            self._send_json({"error": f"Missing asset: {filename}"}, status=HTTPStatus.NOT_FOUND)
            return
        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _parse_limit(self, query: str) -> int:
        if "limit=" not in query:
            return 25
        for item in query.split("&"):
            if not item.startswith("limit="):
                continue
            try:
                return max(1, min(100, int(item.split("=", 1)[1])))
            except ValueError:
                break
        return 25

    def _parse_import_id(self, query: str) -> int | None:
        if "import_id=" not in query:
            return None
        for item in query.split("&"):
            if not item.startswith("import_id="):
                continue
            try:
                value = item.split("=", 1)[1]
                if value == "":
                    return None
                return int(value)
            except ValueError:
                break
        return None

    def _parse_workspace_id(self, query: str) -> int | None:
        if "workspace_id=" not in query:
            return None
        for item in query.split("&"):
            if not item.startswith("workspace_id="):
                continue
            try:
                value = item.split("=", 1)[1]
                if value == "":
                    return None
                return int(value)
            except ValueError:
                break
        return None

    def _parse_text_param(self, query: str, name: str) -> str | None:
        prefix = f"{name}="
        for item in query.split("&"):
            if item.startswith(prefix):
                value = unquote_plus(item.split("=", 1)[1]).strip()
                return value or None
        return None

    def _parse_float_param(self, query: str, name: str) -> float | None:
        raw_value = self._parse_text_param(query, name)
        if raw_value is None:
            return None
        try:
            return float(raw_value)
        except ValueError:
            return None


def _render_answer_legacy_mojibake(plan: Any, rows: list[dict[str, Any]]) -> str:
    if getattr(plan, "support_level", "exact") == "unsupported":
        return (
            f"Nu pot calcula {getattr(plan, 'metric_label', 'această metrică')} exact doar din extrasul bancar. "
            "Pot răspunde corect la metrici de cashflow și pot oferi estimări operaționale atunci când există suficiente indicii în tranzacții."
        )
    if plan.requested_profit:
        if not rows:
            return "Nu am găsit tranzacții pentru perioada cerută, deci nu pot estima netul de cashflow."
        if plan.group_by:
            parts = [f"{row['group_key']}: {row['metric_value']}" for row in rows]
            return (
                "Profitul contabil exact nu se poate deduce doar din extrasul de cont. "
                f"Ca aproximație de cashflow net: {'; '.join(parts)}."
            )
        return (
            "Profitul contabil exact nu se poate deduce doar din extrasul de cont. "
            f"Cashflow-ul net pentru selecția cerută este {rows[0]['metric_value']}."
        )
    if plan.metric == "creditare_vs_recuperare":
        if not rows:
            return "Nu am găsit tranzacții de creditare sau recuperare creditare în selecția cerută."
        values = {row["group_key"]: row for row in rows}
        creditare = values.get("creditare", {}).get("metric_value", 0)
        recuperare = values.get("recuperare_creditare", {}).get("metric_value", 0)
        return (
            f"Creditare totală: {creditare}. "
            f"Recuperare creditare totală: {recuperare}."
        )
    if getattr(plan, "support_level", "exact") == "estimated":
        if not rows:
            return (
                f"Nu am găsit suficiente tranzacții pentru a estima {getattr(plan, 'metric_label', 'această metrică')} "
                "în perioada cerută."
            )
        if plan.group_by:
            parts = [f"{row['group_key']}: {row['metric_value']}" for row in rows]
            if rows and rows[0].get("source") == "issued_invoices":
                return (
                    f"Din facturile emise, {getattr(plan, 'metric_label', 'această metrică')} este: "
                    f"{'; '.join(parts)}."
                )
            return (
                f"Estimarea din extras pentru {getattr(plan, 'metric_label', 'această metrică')} este: "
                f"{'; '.join(parts)}."
            )
        if rows and rows[0].get("source") == "issued_invoices":
            return (
                f"Din facturile emise, {getattr(plan, 'metric_label', 'această metrică')} "
                f"este {rows[0]['metric_value']}."
            )
        return (
            f"Estimarea din extras pentru {getattr(plan, 'metric_label', 'această metrică')} "
            f"este {rows[0]['metric_value']}."
        )
    if not rows:
        return "Nu am găsit date pentru întrebarea asta în tranzacțiile importate."
    if plan.mode == "search":
        return f"Am găsit {len(rows)} tranzacții relevante."
    if plan.group_by:
        parts = [f"{row['group_key']}: {row['metric_value']}" for row in rows]
        return "; ".join(parts)
    metric_value = rows[0]["metric_value"]
    return f"Rezultatul pentru întrebarea ta este {metric_value}."


def render_answer(plan: Any, rows: list[dict[str, Any]]) -> str:
    if getattr(plan, "support_level", "exact") == "clarify":
        entity_name = getattr(plan, "entity_name", None)
        if entity_name:
            return (
                f"Nu sunt sigur ce inseamna exact situatia lui {entity_name}. "
                "Pot sa-ti spun incasarile, platile, netul relatiei sau tranzactiile asociate, "
                "daca reformulezi mai specific."
            )
        return (
            "Nu sunt sigur ce vrei sa calculez exact. "
            "Pot sa raspund corect daca imi ceri mai specific incasari, plati, net sau tranzactii."
        )
    if getattr(plan, "metric", "") == "entity_relationship_summary":
        if not rows:
            entity_name = getattr(plan, "entity_name", "entitatea ceruta")
            project_name = getattr(plan, "project_name", None)
            if project_name:
                return f"Nu am gasit tranzactii pentru relatia cu {entity_name} pe proiectul {project_name}."
            return f"Nu am gasit tranzactii pentru relatia cu {entity_name}."
        row = rows[0]
        entity_name = getattr(plan, "entity_name", "entitatea ceruta")
        entity_type = row.get("entity_type") or "necunoscut"
        project_name = getattr(plan, "project_name", None)
        scope_text = f" pe proiectul {project_name}" if project_name else ""
        return (
            f"Relatia cu {entity_name}{scope_text}: incasari {row.get('income_total', 0)}, "
            f"plati {row.get('expense_total', 0)}, net {row.get('net_value', 0)}. "
            f"Tip entitate observat: {entity_type}."
        )
    if getattr(plan, "support_level", "exact") == "unsupported":
        return (
            f"Nu pot calcula {getattr(plan, 'metric_label', 'aceasta metrica')} exact doar din extrasul bancar. "
            "Pot raspunde corect la metrici de cashflow si pot oferi estimari operationale "
            "atunci cand exista suficiente indicii in tranzactii."
        )
    if plan.requested_profit:
        if not rows:
            return "Nu am gasit tranzactii pentru perioada ceruta, deci nu pot estima netul de cashflow."
        if plan.group_by:
            parts = [f"{row['group_key']}: {row['metric_value']}" for row in rows]
            return (
                "Profitul contabil exact nu se poate deduce doar din extrasul de cont. "
                f"Ca aproximatie de cashflow net: {'; '.join(parts)}."
            )
        return (
            "Profitul contabil exact nu se poate deduce doar din extrasul de cont. "
            f"Cashflow-ul net pentru selectia ceruta este {rows[0]['metric_value']}."
        )
    if plan.metric == "creditare_vs_recuperare":
        if not rows:
            return "Nu am gasit tranzactii de creditare sau recuperare creditare in selectia ceruta."
        if plan.group_by == "year":
            parts = []
            for row in rows:
                creditare = float(row.get("creditare_value", 0) or 0)
                recuperare = float(row.get("recuperare_value", 0) or 0)
                remaining = round(creditare - recuperare, 2)
                parts.append(
                    f"{row['group_key']}: creditare {creditare}, recuperare {recuperare}, ramas {remaining}"
                )
            return "Breakdown anual creditare vs recuperare: " + "; ".join(parts)
        values = {row["group_key"]: row for row in rows}
        creditare = float(values.get("creditare", {}).get("metric_value", 0) or 0)
        recuperare = float(values.get("recuperare_creditare", {}).get("metric_value", 0) or 0)
        remaining = round(creditare - recuperare, 2)
        creditare_count = values.get("creditare", {}).get("transaction_count", 0)
        recuperare_count = values.get("recuperare_creditare", {}).get("transaction_count", 0)
        focus = getattr(plan, "creditare_focus", "summary")
        include_balance = bool(getattr(plan, "include_creditare_balance", True))
        if focus == "remaining":
            return (
                "Calcul exact din liniile extrasului bancar. "
                f"Mai ai de recuperat {remaining} "
                f"(creditat {creditare}, recuperat {recuperare})."
            )
        if focus == "recovered":
            answer = (
                "Calcul exact din liniile extrasului bancar. "
                f"Ai recuperat {recuperare} ({recuperare_count} tranzactii). "
                f"Creditat total: {creditare} ({creditare_count} tranzactii)."
            )
            if include_balance:
                answer += f" Ramas de recuperat: {remaining}."
            return answer
        if focus == "credited":
            answer = (
                "Calcul exact din liniile extrasului bancar. "
                f"Ai creditat {creditare} ({creditare_count} tranzactii). "
                f"Recuperat: {recuperare} ({recuperare_count} tranzactii)."
            )
            if include_balance:
                answer += f" Ramas de recuperat: {remaining}."
            return answer
        answer = (
            "Calcul exact din liniile extrasului bancar. "
            f"Creditare totala: {creditare} ({creditare_count} tranzactii). "
            f"Recuperare creditare totala: {recuperare} ({recuperare_count} tranzactii)."
        )
        if include_balance:
            answer += f" Ramas de recuperat: {remaining}."
        return answer
    if plan.metric == "invoice_residual_total":
        if not rows:
            return "Nu am gasit facturi primite cu sold restant in selectia ceruta."
        if plan.group_by:
            parts = [
                f"{row['group_key']}: {row['metric_value']} ({row.get('transaction_count', 0)} facturi)"
                for row in rows
            ]
            return "Sold facturi primite neacoperite (calcul exact): " + "; ".join(parts)
        metric_value = rows[0]["metric_value"]
        invoice_count = rows[0].get("transaction_count", 0)
        return (
            "Calcul exact din facturi primite si plati asociate. "
            f"Sold facturi primite neacoperite: {metric_value} "
            f"(din {invoice_count} facturi)."
        )
    if getattr(plan, "support_level", "exact") == "estimated":
        if not rows:
            return (
                f"Nu am gasit suficiente tranzactii pentru a estima {getattr(plan, 'metric_label', 'aceasta metrica')} "
                "in perioada ceruta."
            )
        if plan.group_by:
            parts = [f"{row['group_key']}: {row['metric_value']}" for row in rows]
            if rows and rows[0].get("source") == "issued_invoices":
                return (
                    f"Din facturile emise, {getattr(plan, 'metric_label', 'aceasta metrica')} este: "
                    f"{'; '.join(parts)}."
                )
            return (
                f"Estimarea din extras pentru {getattr(plan, 'metric_label', 'aceasta metrica')} este: "
                f"{'; '.join(parts)}."
            )
        if rows and rows[0].get("source") == "issued_invoices":
            return (
                f"Din facturile emise, {getattr(plan, 'metric_label', 'aceasta metrica')} "
                f"este {rows[0]['metric_value']}."
            )
        return (
            f"Estimarea din extras pentru {getattr(plan, 'metric_label', 'aceasta metrica')} "
            f"este {rows[0]['metric_value']}."
        )
    if not rows:
        return "Nu am gasit date pentru intrebarea asta in tranzactiile importate."
    if plan.mode == "search":
        return f"Am gasit {len(rows)} tranzactii relevante."
    if plan.group_by:
        parts = [
            f"{row['group_key']}: {row['metric_value']} ({row.get('transaction_count', 0)} tranzactii)"
            for row in rows
        ]
        return "Calcul exact din liniile extrasului bancar: " + "; ".join(parts)
    metric_value = rows[0]["metric_value"]
    transaction_count = rows[0].get("transaction_count", 0)
    return (
        "Calcul exact din liniile extrasului bancar. "
        f"Rezultatul pentru intrebarea ta este {metric_value} "
        f"(din {transaction_count} tranzactii)."
    )


def _serialize_statement_validation(validation: Any) -> dict[str, Any]:
    return {
        "available": bool(validation.available),
        "passed": bool(validation.passed),
        "parser_name": validation.parser_name,
        "errors": list(validation.errors),
        "declared_transaction_count": validation.declared_transaction_count,
        "parsed_transaction_count": validation.parsed_transaction_count,
        "declared_inflow_count": validation.declared_inflow_count,
        "parsed_inflow_count": validation.parsed_inflow_count,
        "declared_outflow_count": validation.declared_outflow_count,
        "parsed_outflow_count": validation.parsed_outflow_count,
        "declared_total_income": validation.declared_total_income,
        "parsed_total_income": validation.parsed_total_income,
        "declared_total_expenses": validation.declared_total_expenses,
        "parsed_total_expenses": validation.parsed_total_expenses,
        "declared_net_cashflow": validation.declared_net_cashflow,
        "parsed_net_cashflow": validation.parsed_net_cashflow,
        "declared_opening_balance": validation.declared_opening_balance,
        "declared_closing_balance": validation.declared_closing_balance,
        "parsed_closing_balance": validation.parsed_closing_balance,
        "inferred_transaction_count": validation.inferred_transaction_count,
    }


def _raise_on_failed_statement_validation(validation: Any) -> None:
    if not validation.available:
        return
    if validation.passed:
        return
    parser_name = getattr(validation, "parser_name", "statement")
    errors = ", ".join(getattr(validation, "errors", ()) or ("validation_failed",))
    raise ValueError(
        f"Validarea extrasului a esuat pentru {parser_name}: {errors}. "
        "Importul a fost oprit ca sa nu folosim valori citite gresit sau inferate."
    )
