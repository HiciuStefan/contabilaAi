from __future__ import annotations

from pathlib import Path
from typing import Any

from contabila_ai.importing.parsers import parse_issued_invoices_path
from contabila_ai.storage.store import SQLiteTransactionStore


def import_invoice_documents(
    *,
    store: SQLiteTransactionStore,
    workspace_id: int,
    role: str,
    source_path: Path,
) -> dict[str, Any]:
    resolved_path = Path(source_path).expanduser()
    invoices = parse_issued_invoices_path(resolved_path)
    import_batch_id = store.create_document_import_batch(
        source_path=resolved_path,
        workspace_id=workspace_id,
        source_type=f"{role.strip().lower() or 'issued'}_invoice",
    )
    result = store.insert_invoices(
        workspace_id=workspace_id,
        import_batch_id=import_batch_id,
        role=role,
        invoices=invoices,
    )
    return {
        "invoice_count": len(invoices),
        "imported_count": len(invoices),
        "import_batch_id": import_batch_id,
        "result": result,
        "items": store.list_workspace_invoices(workspace_id, role=role),
    }
