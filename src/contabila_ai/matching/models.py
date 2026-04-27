from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MatchProposal:
    workspace_id: int
    transaction_id: int
    invoice_id: int
    match_kind: str
    matched_amount: float
    residual_amount: float
    confidence: float
    reasoning: str
    status: str = "proposed"
