from __future__ import annotations

import json
import os
from typing import Any, Protocol

from .models import QueryPlan


ALLOWED_METRICS = {
    "total_amount",
    "expense_total",
    "income_total",
    "net_cashflow",
    "transaction_count",
    "invoice_residual_total",
    "operational_income_estimate",
    "operational_expense_estimate",
    "creditare_vs_recuperare",
    "entity_relationship_summary",
    "unsupported",
}
ALLOWED_SUPPORT_LEVELS = {"exact", "estimated", "unsupported", "clarify"}
ALLOWED_MODES = {"aggregate", "search"}
ALLOWED_GROUPINGS = {"year", "half_year"}
ALLOWED_DIRECTIONS = {"inflow", "outflow", "both"}


class SemanticIntentProvider(Protocol):
    def resolve(self, raw_text: str) -> dict[str, Any]:
        ...


class OpenAIIntentProvider:
    def __init__(self, model: str, *, base_url: str | None = None, api_key: str | None = None) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key or os.getenv("OPENAI_API_KEY") or "local"

    def resolve(self, raw_text: str) -> dict[str, Any]:
        try:
            from openai import OpenAI
        except Exception:
            return {}
        client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        prompt = (
            "Extrage intentul unei intrebari financiare in JSON object. "
            "Chei permise: mode, metric, metric_label, support_level, years, months, group_by, "
            "economic_kind, analysis_category, entity_name, project_name, direction, requested_profit. "
            "Nu inventa daca nu esti sigur."
        )
        try:
            response = client.responses.create(
                model=self._model,
                input=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": raw_text},
                ],
            )
            payload = json.loads(getattr(response, "output_text", "") or "{}")
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}


def build_default_intent_provider() -> SemanticIntentProvider | None:
    if os.getenv("CONTABILA_AI_ENABLE_SEMANTIC_INTENT", "").strip().lower() not in {"1", "true", "yes"}:
        return None
    model = os.getenv("CONTABILA_AI_INTENT_MODEL", "").strip() or "gpt-4.1-mini"
    base_url = os.getenv("CONTABILA_AI_OPENAI_BASE_URL", "").strip() or None
    api_key = os.getenv("CONTABILA_AI_INTENT_API_KEY", "").strip() or None
    return OpenAIIntentProvider(model, base_url=base_url, api_key=api_key)


def validate_semantic_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    mode = str(payload.get("mode") or "").strip()
    if mode in ALLOWED_MODES:
        normalized["mode"] = mode
    metric = str(payload.get("metric") or "").strip()
    if metric in ALLOWED_METRICS:
        normalized["metric"] = metric
    metric_label = str(payload.get("metric_label") or "").strip()
    if metric_label:
        normalized["metric_label"] = metric_label
    support_level = str(payload.get("support_level") or "").strip()
    if support_level in ALLOWED_SUPPORT_LEVELS:
        normalized["support_level"] = support_level
    normalized["years"] = _normalize_int_list(payload.get("years"), lower=2000, upper=2100)
    normalized["months"] = _normalize_int_list(payload.get("months"), lower=1, upper=12)
    group_by = str(payload.get("group_by") or "").strip()
    if group_by in ALLOWED_GROUPINGS:
        normalized["group_by"] = group_by
    for key in ("economic_kind", "analysis_category", "entity_name", "project_name"):
        value = str(payload.get(key) or "").strip()
        if value:
            normalized[key] = value
    direction = str(payload.get("direction") or "").strip()
    if direction in ALLOWED_DIRECTIONS:
        normalized["direction"] = direction
    if isinstance(payload.get("requested_profit"), bool):
        normalized["requested_profit"] = payload["requested_profit"]
    return normalized


def merge_semantic_plan(base_plan: QueryPlan, semantic_payload: dict[str, Any]) -> QueryPlan:
    validated = validate_semantic_plan_payload(semantic_payload)
    if not validated:
        return base_plan
    merged_analysis_category = str(validated.get("analysis_category") or base_plan.analysis_category or "") or None
    merged_entity_name = str(validated.get("entity_name") or base_plan.entity_name or "") or None
    if merged_analysis_category and not validated.get("entity_name") and merged_entity_name:
        lowered_entity = merged_entity_name.lower()
        lowered_category = merged_analysis_category.lower()
        if lowered_entity == lowered_category or lowered_entity.startswith(f"{lowered_category} pe "):
            merged_entity_name = None
    return QueryPlan(
        raw_question=base_plan.raw_question,
        mode=str(validated.get("mode") or base_plan.mode),
        metric=str(validated.get("metric") or base_plan.metric),
        metric_label=str(validated.get("metric_label") or base_plan.metric_label),
        support_level=str(validated.get("support_level") or base_plan.support_level),
        years=list(validated.get("years") or base_plan.years),
        months=list(validated.get("months") or base_plan.months),
        relative_period=base_plan.relative_period,
        group_by=validated.get("group_by") or base_plan.group_by,
        economic_kind=str(validated.get("economic_kind") or base_plan.economic_kind or "") or None,
        excluded_economic_kinds=base_plan.excluded_economic_kinds,
        analysis_category=merged_analysis_category,
        entity_name=merged_entity_name,
        project_name=str(validated.get("project_name") or base_plan.project_name or "") or None,
        workspace_id=base_plan.workspace_id,
        direction=str(validated.get("direction") or base_plan.direction),
        requested_profit=bool(validated.get("requested_profit", base_plan.requested_profit)),
        creditare_focus=base_plan.creditare_focus,
        include_creditare_balance=base_plan.include_creditare_balance,
        limit=base_plan.limit,
    )


def _normalize_int_list(value: Any, *, lower: int, upper: int) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    normalized: list[int] = []
    for item in value:
        try:
            resolved = int(item)
        except (TypeError, ValueError):
            continue
        if lower <= resolved <= upper and resolved not in normalized:
            normalized.append(resolved)
    return normalized
