from __future__ import annotations

import re
from typing import Any

from .models import ClassificationResult


FEE_TOKENS = ("comision", "fee", "taxa administrare", "speza")
TAX_TOKENS = ("anaf", "impozit", "taxa", "tva", "bugetul de stat", "cas", "cass", "contribut")
INTERNAL_TRANSFER_TOKENS = ("transfer intern", "transfer intre conturi", "virament intern", "own account")
RECOVERY_TOKENS = (
    "recuperare",
    "recuperari",
    "recuperat",
    "recuperate",
    "restituire",
    "restituiri",
    "return",
)
CREDIT_SUPPORT_TOKENS = ("creditare", "asociat", "aport", "imprumut firma", "finantare firma")
DIVIDEND_TOKENS = ("dividend", "dividende")
LEGAL_ENTITY_SUFFIXES = {
    "srl",
    "sa",
    "sca",
    "scs",
    "pfa",
    "ii",
    "if",
    "ltd",
    "llc",
    "inc",
}
ENTITY_JOINER_TOKENS = {
    "and",
    "si",
}


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def normalize_entity_name(value: str | None) -> str:
    normalized = normalize_text(value)
    if not normalized:
        return ""

    # Normalize common legal-form variants before tokenization.
    normalized = re.sub(r"\bs\s*\.?\s*r\s*\.?\s*l\b", "srl", normalized)
    normalized = re.sub(r"\bs\s*\.?\s*a\b", "sa", normalized)
    normalized = re.sub(r"&", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)

    tokens = [token for token in normalized.split() if token]
    while tokens and tokens[0].isdigit():
        tokens.pop(0)
    if not tokens:
        return ""

    filtered = [
        token for token in tokens
        if token not in LEGAL_ENTITY_SUFFIXES and token not in ENTITY_JOINER_TOKENS
    ]
    return " ".join(filtered if filtered else tokens)


def classify_transaction(
    merchant: str | None,
    description: str | None,
    amount: float,
    entity_memory: dict[str, dict[str, object]],
    analysis_rules: list[dict[str, object]],
) -> ClassificationResult:
    merchant_text = normalize_entity_name(merchant)
    merchant_legacy_text = normalize_text(merchant)
    description_text = normalize_text(description)
    combined_text = " ".join(part for part in (merchant_text, description_text) if part)
    memory = entity_memory.get(merchant_text) or entity_memory.get(merchant_legacy_text, {})

    result = _classify_from_core_rules(combined_text, amount, memory)
    result = _apply_analysis_rules(result, merchant_text, description_text, combined_text, analysis_rules)
    return result


def _classify_from_core_rules(
    combined_text: str,
    amount: float,
    memory: dict[str, object],
) -> ClassificationResult:
    direction = "inflow" if amount > 0 else "outflow"
    entity_type = _optional_text(memory.get("entity_type"))
    reasons: list[str] = []

    if entity_type:
        reasons.append(f"entity memory marks counterparty as {entity_type}")

    if amount < 0 and _contains_recovery_crediting_language(combined_text):
        return ClassificationResult(
            economic_kind="recuperare_creditare",
            direction="outflow",
            entity_type=entity_type,
            confidence=0.96,
            reason=_join_reason(reasons, "negative amount with recovery + crediting wording"),
            analysis_categories=["recuperare_creditare"],
        )

    if amount > 0 and _contains_crediting_language(combined_text):
        return ClassificationResult(
            economic_kind="creditare",
            direction="inflow",
            entity_type=entity_type,
            confidence=0.95,
            reason=_join_reason(reasons, "positive amount with crediting wording"),
            analysis_categories=["creditare"],
        )

    if amount < 0 and _contains_any_token(combined_text, FEE_TOKENS):
        return ClassificationResult(
            economic_kind="bank_fee",
            direction="outflow",
            entity_type=entity_type,
            confidence=0.9,
            reason=_join_reason(reasons, "bank fee wording"),
            analysis_categories=["comisioane_bancare"],
        )

    if amount < 0 and _contains_any_token(combined_text, TAX_TOKENS):
        return ClassificationResult(
            economic_kind="tax_payment",
            direction="outflow",
            entity_type=entity_type,
            confidence=0.9,
            reason=_join_reason(reasons, "tax payment wording"),
            analysis_categories=["taxe"],
        )

    if amount < 0 and _contains_any_token(combined_text, DIVIDEND_TOKENS):
        return ClassificationResult(
            economic_kind="dividend_payment",
            direction="outflow",
            entity_type=entity_type,
            confidence=0.94,
            reason=_join_reason(reasons, "dividend distribution wording"),
            analysis_categories=["dividende"],
        )

    if _contains_any_token(combined_text, INTERNAL_TRANSFER_TOKENS):
        return ClassificationResult(
            economic_kind="internal_transfer",
            direction=direction,
            entity_type=entity_type,
            confidence=0.82,
            reason=_join_reason(reasons, "internal transfer wording"),
            analysis_categories=["transfer_intern"],
        )

    memory_kind = _optional_text(memory.get("economic_kind"))
    memory_direction = _optional_text(memory.get("direction"))
    if memory_kind:
        return ClassificationResult(
            economic_kind=memory_kind,
            direction=memory_direction or direction,
            entity_type=entity_type,
            confidence=0.84,
            reason=_join_reason(reasons, "economic kind inferred from entity memory"),
            analysis_categories=[],
        )

    if entity_type == "supplier" and amount < 0:
        return ClassificationResult(
            economic_kind="supplier_payment",
            direction="outflow",
            entity_type=entity_type,
            confidence=0.87,
            reason=_join_reason(reasons, "supplier payment inferred from entity memory"),
            analysis_categories=["furnizori"],
        )

    if entity_type == "client" and amount > 0:
        return ClassificationResult(
            economic_kind="client_receipt",
            direction="inflow",
            entity_type=entity_type,
            confidence=0.87,
            reason=_join_reason(reasons, "client receipt inferred from entity memory"),
            analysis_categories=["clienti"],
        )

    return ClassificationResult(
        economic_kind="other_inflow" if amount > 0 else "other_outflow",
        direction=direction,
        entity_type=entity_type,
        confidence=0.55,
        reason=_join_reason(reasons, "fallback classification"),
        analysis_categories=[],
    )


def _apply_analysis_rules(
    result: ClassificationResult,
    merchant_text: str,
    description_text: str,
    combined_text: str,
    analysis_rules: list[dict[str, object]],
) -> ClassificationResult:
    economic_kind = result.economic_kind
    direction = result.direction
    entity_type = result.entity_type
    confidence = result.confidence
    analysis_categories = list(result.analysis_categories)
    reasons = [result.reason]

    active_rules = [
        rule for rule in analysis_rules if bool(rule.get("is_active", True))
    ]
    active_rules.sort(key=lambda rule: int(rule.get("priority", 100)))

    for rule in active_rules:
        if not _rule_matches(rule, merchant_text, description_text, combined_text):
            continue

        if _optional_text(rule.get("economic_kind")):
            economic_kind = str(rule["economic_kind"])
        if _optional_text(rule.get("direction")):
            direction = str(rule["direction"])
        if _optional_text(rule.get("entity_type")):
            entity_type = str(rule["entity_type"])
        category = _optional_text(rule.get("analysis_category"))
        if category and category not in analysis_categories:
            analysis_categories.append(category)
        confidence = max(confidence, float(rule.get("confidence", 0.78)))
        reasons.append(f"matched rule pattern '{rule.get('pattern', '')}'")

    return ClassificationResult(
        economic_kind=economic_kind,
        direction=direction,
        entity_type=entity_type,
        confidence=confidence,
        reason="; ".join(reasons),
        analysis_categories=analysis_categories,
    )


def _rule_matches(
    rule: dict[str, object],
    merchant_text: str,
    description_text: str,
    combined_text: str,
) -> bool:
    pattern = normalize_text(_optional_text(rule.get("pattern")))
    if not pattern:
        return False

    match_field = normalize_text(_optional_text(rule.get("match_field")) or "text")
    if match_field == "merchant":
        haystack = merchant_text
    elif match_field == "description":
        haystack = description_text
    else:
        haystack = combined_text
    return pattern in haystack


def _contains_recovery_crediting_language(value: str) -> bool:
    return _contains_any_token(value, RECOVERY_TOKENS) and _contains_crediting_language(value)


def _contains_crediting_language(value: str) -> bool:
    if _contains_any_token(value, ("creditare",)):
        return True
    if not _contains_any_token(value, ("credit",)):
        return False
    support_hits = sum(1 for token in CREDIT_SUPPORT_TOKENS if _contains_any_token(value, (token,)))
    return support_hits >= 2


def _contains_any_token(value: str, tokens: tuple[str, ...]) -> bool:
    for token in tokens:
        pattern = r"\b" + re.escape(token) + r"\b"
        if re.search(pattern, value):
            return True
    return False


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _join_reason(parts: list[str], final_reason: str) -> str:
    if not parts:
        return final_reason
    return "; ".join([*parts, final_reason])
