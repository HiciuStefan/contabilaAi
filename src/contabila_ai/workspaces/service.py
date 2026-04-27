from __future__ import annotations

from contabila_ai.storage.store import SQLiteTransactionStore


class WorkspaceService:
    def __init__(self, store: SQLiteTransactionStore) -> None:
        self._store = store

    def create_workspace(self, name: str) -> int:
        return self._store.create_workspace(name)

    def list_workspaces(self) -> list[dict[str, object]]:
        return self._store.list_workspaces()
