from __future__ import annotations

from contabila_ai.review import ReviewService
from contabila_ai.storage.store import SQLiteTransactionStore


class WorkspaceService:
    def __init__(self, store: SQLiteTransactionStore, review: ReviewService) -> None:
        self._store = store
        self._review = review

    def create_workspace(self, name: str) -> int:
        return self._store.create_workspace(name)

    def list_workspaces(self) -> list[dict[str, object]]:
        items = self._store.list_workspaces()
        for item in items:
            workspace_id = int(item["id"])
            if int(item.get("import_count") or 0) == 0:
                item["status"] = "needs_import"
                continue
            item["review_counts"] = self._review.severity_counts(workspace_id=workspace_id)
            item["status"] = "needs_review" if self._review.has_blocking_items(workspace_id=workspace_id) else "ready"
        return items
