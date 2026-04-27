from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any


DATE_FORMATS = (
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
)


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")

    text = normalize_whitespace(str(value))
    if not text:
        return None

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{2}[./-]\d{2}[./-]\d{4})", text)
    if match:
        return parse_date(match.group(1))
    return None


def parse_amount(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)

    text = normalize_whitespace(str(value))
    if not text:
        return None

    text = text.replace("RON", "").replace("EUR", "").replace("USD", "").replace("GBP", "").strip()
    text = text.replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return float(text)
    except ValueError:
        match = re.search(r"-?\d+(?:[.,]\d+)?", text)
        if not match:
            return None
        return parse_amount(match.group(0))


def sign_amount(amount: float | None, debit: float | None, credit: float | None) -> float | None:
    if amount is not None:
        return amount
    if credit is not None and debit is not None:
        return credit - debit
    if credit is not None:
        return abs(credit)
    if debit is not None:
        return -abs(debit)
    return None


def merchant_from_description(description: str) -> str:
    text = normalize_whitespace(description)
    if not text:
        return "Unknown"

    text = re.sub(r"\b(card|transfer|pos|online|payment|plata|trx|ref)\b", "", text, flags=re.I)
    text = normalize_whitespace(text)
    parts = re.split(r"[,*;/|-]", text)
    candidate = normalize_whitespace(parts[0]) if parts else text
    return candidate[:80] if candidate else "Unknown"
