from __future__ import annotations

import json
import os
from typing import Any, Protocol

from .models import BusinessFact


ENTITY_TYPE_ALIASES = {
    "partener": "partener",
    "partner": "partener",
    "client": "client",
    "colaborator": "colaborator",
    "collaborator": "colaborator",
    "furnizor": "furnizor",
    "supplier": "furnizor",
    "asociat": "asociat",
    "owner": "asociat",
    "banca": "banca",
    "bank": "banca",
    "stat": "stat",
    "state": "stat",
}
SUPPORTED_FACT_TYPES = {"entity_type", "project_assignment", "category_rule", "note"}
ALLOWED_EXTRA_KEYS = {"date_start", "date_end"}


class SemanticMemoryProvider(Protocol):
    def extract(self, raw_text: str) -> list[dict[str, Any]]:
        ...


class OpenAISemanticMemoryProvider:
    def __init__(self, model: str) -> None:
        self._model = model

    def extract(self, raw_text: str) -> list[dict[str, Any]]:
        try:
            from openai import OpenAI
        except Exception:
            return []
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return []
        client = OpenAI(api_key=api_key)
        prompt = (
            "Extrage fapte de business structurate din instructiunea utilizatorului. "
            "Raspunde doar JSON array. Fiecare element poate avea: fact_type, subject_name, "
            "fact_value, confidence, extra_json. Fact types permise: entity_type, project_assignment, "
            "category_rule, note."
        )
        try:
            response = client.responses.create(
                model=self._model,
                input=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": raw_text},
                ],
            )
            raw_output = getattr(response, "output_text", "") or ""
            payload = json.loads(raw_output)
        except Exception:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []


def build_default_semantic_provider() -> SemanticMemoryProvider | None:
    if os.getenv("CONTABILA_AI_ENABLE_SEMANTIC_MEMORY", "").strip().lower() not in {"1", "true", "yes"}:
        return None
    model = os.getenv("CONTABILA_AI_MEMORY_MODEL", "").strip() or "gpt-4.1-mini"
    return OpenAISemanticMemoryProvider(model)


def validate_semantic_proposals(proposals: list[dict[str, Any]]) -> list[BusinessFact]:
    facts: list[BusinessFact] = []
    for item in proposals:
        fact_type = str(item.get("fact_type") or "").strip()
        if fact_type not in SUPPORTED_FACT_TYPES:
            continue
        subject_name = str(item.get("subject_name") or "").strip()
        fact_value = str(item.get("fact_value") or "").strip()
        confidence = item.get("confidence", 0.86)
        try:
            confidence_value = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence_value = 0.86

        extra_json = _normalize_extra_json(item.get("extra_json"))
        if fact_type == "entity_type":
            normalized_value = ENTITY_TYPE_ALIASES.get(fact_value.lower())
            if not subject_name or not normalized_value:
                continue
            facts.append(
                BusinessFact(
                    fact_type="entity_type",
                    subject_name=subject_name,
                    fact_value=normalized_value,
                    confidence=confidence_value,
                )
            )
            continue
        if fact_type == "project_assignment":
            if not subject_name or not fact_value:
                continue
            facts.append(
                BusinessFact(
                    fact_type="project_assignment",
                    subject_name=subject_name,
                    fact_value=fact_value,
                    confidence=confidence_value,
                )
            )
            continue
        if fact_type == "category_rule":
            if not fact_value:
                continue
            facts.append(
                BusinessFact(
                    fact_type="category_rule",
                    subject_name=subject_name or "workspace",
                    fact_value=fact_value,
                    confidence=confidence_value,
                    extra_json=extra_json,
                )
            )
            continue
        if not fact_value:
            continue
        facts.append(
            BusinessFact(
                fact_type="note",
                subject_name=subject_name or "workspace",
                fact_value=fact_value,
                confidence=confidence_value,
            )
        )
    return _dedupe_facts(facts)


def _normalize_extra_json(value: Any) -> str | None:
    payload: dict[str, Any]
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        if not isinstance(decoded, dict):
            return None
        payload = decoded
    elif isinstance(value, dict):
        payload = value
    else:
        return None
    filtered = {
        key: str(raw_value)
        for key, raw_value in payload.items()
        if key in ALLOWED_EXTRA_KEYS and str(raw_value).strip()
    }
    if not filtered:
        return None
    return json.dumps(filtered, ensure_ascii=False)


def _dedupe_facts(facts: list[BusinessFact]) -> list[BusinessFact]:
    seen: set[tuple[str, str, str, str | None]] = set()
    deduped: list[BusinessFact] = []
    for fact in facts:
        key = (fact.fact_type, fact.subject_name.lower(), fact.fact_value.lower(), fact.extra_json)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped
