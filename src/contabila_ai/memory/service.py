from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from contabila_ai.memory.models import BusinessFact

if TYPE_CHECKING:
    from contabila_ai.storage.store import SQLiteTransactionStore


ENTITY_TYPE_MAP = {
    "partener": "partner",
    "colaborator": "collaborator",
    "asociat": "owner",
    "banca": "bank",
    "stat": "state",
}
ENTITY_LABEL_PATTERN = "|".join(re.escape(label) for label in ENTITY_TYPE_MAP)


class BusinessMemoryService:
    def __init__(self, store: SQLiteTransactionStore) -> None:
        self._store = store

    def add_instruction(self, workspace_id: int, raw_text: str) -> dict[str, object]:
        facts = parse_instruction_to_facts(raw_text)
        instruction_id = self._store.add_business_instruction(workspace_id=workspace_id, raw_text=raw_text)
        inserted = self._store.add_business_facts(workspace_id=workspace_id, instruction_id=instruction_id, facts=facts)
        for fact in facts:
            self._apply_fact(workspace_id=workspace_id, raw_text=raw_text, fact=fact)
        self._store.reclassify_transactions()
        return {
            "instruction_id": instruction_id,
            "fact_count": inserted,
            "facts": self._store.list_business_facts(workspace_id),
        }

    def _apply_fact(self, *, workspace_id: int, raw_text: str, fact: BusinessFact) -> None:
        if fact.fact_type == "entity_type":
            entity_type = ENTITY_TYPE_MAP.get(fact.fact_value)
            if not entity_type:
                return
            self._store.upsert_entity_memory(
                entity_name=fact.subject_name,
                entity_type=entity_type,
                confidence=fact.confidence,
                notes=f"business memory: {raw_text}",
            )
            return
        if fact.fact_type != "category_rule":
            return
        extra_payload = {}
        if fact.extra_json:
            try:
                extra_payload = json.loads(fact.extra_json)
            except json.JSONDecodeError:
                extra_payload = {}
        for row in self._store.list_transactions_for_business_rule(
            workspace_id=workspace_id,
            keyword=fact.subject_name,
            date_start=extra_payload.get("date_start"),
            date_end=extra_payload.get("date_end"),
        ):
            self._store.create_change_review_item(
                workspace_id=workspace_id,
                transaction_id=int(row["id"]),
                field_name="analysis_category",
                old_value="",
                new_value=fact.fact_value,
                reason=f"business memory rule from instruction: {raw_text}",
                confidence=fact.confidence,
            )


def parse_instruction_to_facts(raw_text: str) -> list[BusinessFact]:
    text = " ".join(raw_text.split()).strip()
    for extractor in (
        _extract_entity_correction,
        _extract_entity_assertion,
        _extract_project_assignments,
        _extract_category_rule,
    ):
        facts = extractor(text)
        if facts:
            return facts

    return [BusinessFact(fact_type="note", subject_name="workspace", fact_value=text)]


def _extract_entity_correction(text: str) -> list[BusinessFact]:
    correction_match = re.search(
        rf"(?P<subject>.+?)\s+nu\s+e\s+(?P<old>{ENTITY_LABEL_PATTERN})\s*,?\s*(?:dar\s+)?e\s+(?P<new>{ENTITY_LABEL_PATTERN})(?:\b|$)",
        text,
        re.IGNORECASE,
    )
    if not correction_match:
        return []
    subject_name = correction_match.group("subject").strip(" ,.")
    corrected_label = correction_match.group("new").lower()
    if not subject_name:
        return []
    return [BusinessFact(fact_type="entity_type", subject_name=subject_name, fact_value=corrected_label)]


def _extract_entity_assertion(text: str) -> list[BusinessFact]:
    lowered = text.lower()
    entity_match = re.search(
        rf"(?P<subject>.+?)\s+(?:este|e)\s+(?P<label>{ENTITY_LABEL_PATTERN})(?:\b|$)",
        text,
        re.IGNORECASE,
    )
    if entity_match:
        subject_name = entity_match.group("subject").strip(" ,.")
        entity_label = entity_match.group("label").lower()
        if subject_name:
            return [BusinessFact(fact_type="entity_type", subject_name=subject_name, fact_value=entity_label)]

    for romanian_label in ENTITY_TYPE_MAP:
        suffix = f" e {romanian_label}"
        if lowered.endswith(suffix):
            subject_name = text[: len(text) - len(suffix)].strip(" ,.")
            if subject_name:
                return [BusinessFact(fact_type="entity_type", subject_name=subject_name, fact_value=romanian_label)]
    return []


def _extract_project_assignments(text: str) -> list[BusinessFact]:
    facts: list[BusinessFact] = []
    project_match = re.search(
        r"(?P<people>.+?)\s+lucreaza\s+(?:pe|pentru|la)\s+proiectul\s+(?P<project>.+)$",
        text,
        re.IGNORECASE,
    )
    if not project_match:
        return facts
    project_name = project_match.group("project").strip(" .")
    people_blob = project_match.group("people")
    people_blob = re.sub(r"^\s*(colaboratorii|colaboratorul)\s+", "", people_blob, flags=re.IGNORECASE)
    people = [item.strip(" ,.") for item in re.split(r"\s+si\s+|,", people_blob, flags=re.IGNORECASE) if item.strip(" ,.")]
    for person in people:
        facts.append(BusinessFact(fact_type="project_assignment", subject_name=person, fact_value=project_name))
    return facts


def _extract_category_rule(text: str) -> list[BusinessFact]:
    category_match = re.search(
        r"(?:pune|trece|muta)\s+.+?\s+la\s+categoria\s+(?P<category>[a-z0-9 .&_-]+?)(?:[?.!,]|$)",
        text,
        re.IGNORECASE,
    )
    if not category_match:
        return []
    category_name = category_match.group("category").strip(" ,.")
    if not category_name:
        return []
    period_match = re.search(r"intre\s+(?P<start>20\d{2})\s*-\s*(?P<end>20\d{2})", text, re.IGNORECASE)
    extra_payload: dict[str, object] = {}
    if period_match:
        extra_payload["date_start"] = f"{period_match.group('start')}-01-01"
        extra_payload["date_end"] = f"{period_match.group('end')}-12-31"
    subject_name = "workspace"
    if re.search(r"\bcasa\b", text, re.IGNORECASE):
        subject_name = "casa"
    return [
        BusinessFact(
            fact_type="category_rule",
            subject_name=subject_name,
            fact_value=category_name,
            extra_json=json.dumps(extra_payload, ensure_ascii=False) if extra_payload else None,
        )
    ]
