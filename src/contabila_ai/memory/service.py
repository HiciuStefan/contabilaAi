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


class BusinessMemoryService:
    def __init__(self, store: SQLiteTransactionStore) -> None:
        self._store = store

    def add_instruction(self, workspace_id: int, raw_text: str) -> dict[str, object]:
        facts = parse_instruction_to_facts(raw_text)
        instruction_id = self._store.add_business_instruction(workspace_id=workspace_id, raw_text=raw_text)
        inserted = self._store.add_business_facts(workspace_id=workspace_id, instruction_id=instruction_id, facts=facts)
        for fact in facts:
            if fact.fact_type != "entity_type":
                continue
            entity_type = ENTITY_TYPE_MAP.get(fact.fact_value)
            if not entity_type:
                continue
            self._store.upsert_entity_memory(
                entity_name=fact.subject_name,
                entity_type=entity_type,
                confidence=fact.confidence,
                notes=f"business memory: {raw_text}",
            )
        self._store.reclassify_transactions()
        return {
            "instruction_id": instruction_id,
            "fact_count": inserted,
            "facts": self._store.list_business_facts(workspace_id),
        }


def parse_instruction_to_facts(raw_text: str) -> list[BusinessFact]:
    text = " ".join(raw_text.split()).strip()
    lowered = text.lower()
    facts: list[BusinessFact] = []

    for romanian_label in ENTITY_TYPE_MAP:
        suffix = f" e {romanian_label}"
        if lowered.endswith(suffix):
            subject_name = text[: len(text) - len(suffix)].strip(" ,.")
            if subject_name:
                facts.append(BusinessFact(fact_type="entity_type", subject_name=subject_name, fact_value=romanian_label))
                return facts

    project_match = re.search(r"(?P<people>.+?)\s+lucreaza pe proiectul\s+(?P<project>.+)$", text, re.IGNORECASE)
    if project_match:
        project_name = project_match.group("project").strip(" .")
        people_blob = project_match.group("people")
        people_blob = re.sub(r"^\s*(colaboratorii|colaboratorul)\s+", "", people_blob, flags=re.IGNORECASE)
        people = [item.strip(" ,.") for item in re.split(r"\s+si\s+|,", people_blob, flags=re.IGNORECASE) if item.strip(" ,.")]
        for person in people:
            facts.append(
                BusinessFact(
                    fact_type="project_assignment",
                    subject_name=person,
                    fact_value=project_name,
                )
            )
        if facts:
            return facts

    return [BusinessFact(fact_type="note", subject_name="workspace", fact_value=text)]
