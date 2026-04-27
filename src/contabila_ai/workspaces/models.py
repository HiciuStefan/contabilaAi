from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkspaceSummary:
    id: int
    name: str
    status: str
    import_count: int
    transaction_count: int
