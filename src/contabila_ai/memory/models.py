from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BusinessFact:
    fact_type: str
    subject_name: str
    fact_value: str
    confidence: float = 1.0
    status: str = "accepted"
    extra_json: str | None = None
