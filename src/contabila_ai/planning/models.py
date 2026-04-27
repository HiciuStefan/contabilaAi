from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PLANNER_MODES = ("aggregate", "search")
PLANNER_METRICS = (
    "total_amount",
    "expense_total",
    "income_total",
    "net_cashflow",
    "transaction_count",
    "operational_income_estimate",
    "operational_expense_estimate",
    "creditare_vs_recuperare",
    "unsupported",
)
PLANNER_GROUPINGS = ("year", "half_year")
PLANNER_SUPPORT_LEVELS = ("exact", "estimated", "unsupported", "clarify", "blocked")


@dataclass(frozen=True, slots=True)
class QueryPlan:
    raw_question: str
    mode: str = "aggregate"
    metric: str = "total_amount"
    metric_label: str = "suma"
    support_level: str = "exact"
    years: list[int] = field(default_factory=list)
    relative_period: str | None = None
    group_by: str | None = None
    economic_kind: str | None = None
    excluded_economic_kinds: list[str] = field(default_factory=list)
    analysis_category: str | None = None
    entity_name: str | None = None
    direction: str = "both"
    requested_profit: bool = False
    creditare_focus: str | None = None
    include_creditare_balance: bool = False
    limit: int = 50


@dataclass(frozen=True, slots=True)
class QueryExecution:
    plan: QueryPlan
    sql: str
    params: tuple[Any, ...]
    rows: list[dict[str, Any]]
