from __future__ import annotations

import re

from contabila_ai.classification import normalize_text

from .models import QueryPlan
from .semantic import merge_semantic_plan


SEARCH_TOKENS = (
    "arata",
    "arata",
    "listeaza",
    "listeaza",
    "tranzactiile",
    "tranzactiile",
    "tranzactii",
    "tranzactii",
)
COUNT_TOKENS = ("cate", "cate", "numar", "numar")
EXPENSE_TOKENS = (
    "cheltuiala",
    "cheltuieli",
    "cheltuit",
    "plata",
    "plati",
    "plati",
    "iesiri",
    "iesiri",
    "iesire",
    "iesire",
)
INCOME_TOKENS = (
    "incasari",
    "incasari",
    "incasare",
    "incasare",
    "intrari",
    "intrari",
    "venit",
    "venituri",
)
HALF_YEAR_TOKENS = (
    "pe jumatate de an",
    "pe jumatati de an",
    "pe jumatati",
    "semestrial",
    "semestru",
)
YEAR_GROUP_TOKENS = (
    "in fiecare an",
    "pe ani",
    "toti anii",
    "fiecare an",
    "pe fiecare an",
    "per an",
    "anual",
    "an de an",
    "de cand ai informatii",
    "de cand exista informatii",
    "de cand ai date",
    "de cand exista date",
)
AMBIGUOUS_ENTITY_SUMMARY_TOKENS = (
    "situatia lui",
    "situatia cu",
    "relatia cu",
    "relatia lui",
)
CLARIFY_TOKENS = (
    "care e situatia",
    "cum stau",
    "ce se intampla",
)
FIRST_YEAR_TOKENS = (
    "primul an",
    "primul an fiscal",
    "primul an de activitate",
    "anul initial",
    "anul de inceput",
)
ECONOMIC_KIND_PATTERNS = (
    ("recuperare creditare", "recuperare_creditare"),
    ("recuperari creditare", "recuperare_creditare"),
    ("recuperari creditare", "recuperare_creditare"),
    ("recuperat", "recuperare_creditare"),
    ("recuperate", "recuperare_creditare"),
    ("creditare", "creditare"),
    ("creditari", "creditare"),
    ("creditari", "creditare"),
    ("creditat", "creditare"),
    ("creditate", "creditare"),
    ("furnizor", "supplier_payment"),
    ("client", "client_receipt"),
    ("taxe", "tax_payment"),
    ("impozit", "tax_payment"),
    ("comision", "bank_fee"),
)
UNSUPPORTED_METRIC_PATTERNS = (
    ("tva", "TVA"),
    ("bilant", "bilant"),
    ("bilant", "bilant"),
    ("cont de profit si pierdere", "cont de profit si pierdere"),
    ("profit si pierdere", "cont de profit si pierdere"),
    ("p&l", "cont de profit si pierdere"),
)
ESTIMATED_METRIC_PATTERNS = (
    ("cifra de afaceri", "operational_income_estimate", "cifra de afaceri"),
    ("turnover", "operational_income_estimate", "cifra de afaceri"),
    ("incasari operationale", "operational_income_estimate", "incasari operationale"),
    ("incasari operationale", "operational_income_estimate", "incasari operationale"),
    ("venituri operationale", "operational_income_estimate", "venituri operationale"),
    ("plati operationale", "operational_expense_estimate", "plati operationale"),
    ("plati operationale", "operational_expense_estimate", "plati operationale"),
    ("cheltuieli operationale", "operational_expense_estimate", "cheltuieli operationale"),
    ("cheltuieli operationale", "operational_expense_estimate", "cheltuieli operationale"),
)
OUTSTANDING_INVOICE_TOKENS = (
    "facturi neplatite",
    "facturi neachitate",
    "sold facturi",
    "rest de plata pe facturi",
    "cat mai am de platit pe facturile primite",
    "cat mai am de platit la furnizori",
)
OPERATIONAL_INCOME_EXCLUSIONS = ["creditare", "internal_transfer"]
OPERATIONAL_EXPENSE_EXCLUSIONS = ["recuperare_creditare", "internal_transfer"]
CREDITARE_FOCUS_RECOVERY_TOKENS = ("recuper", "inapoi", "return")
CREDITARE_FOCUS_REMAINING_TOKENS = ("ramas", "rest", "mai am", "neincasat", "de recuperat")
CREDITARE_FOCUS_CREDITED_TOKENS = ("creditat", "creditare", "imprumutat", "bagat")
MONTH_NAME_MAP = {
    "ianuarie": 1,
    "februarie": 2,
    "martie": 3,
    "aprilie": 4,
    "mai": 5,
    "iunie": 6,
    "iulie": 7,
    "august": 8,
    "septembrie": 9,
    "octombrie": 10,
    "noiembrie": 11,
    "decembrie": 12,
}


def build_query_plan(question: str, semantic_provider=None) -> QueryPlan:
    normalized = _normalize_question(question)
    years = _extract_years(normalized)
    months = _extract_months(normalized)
    relative_period = _detect_relative_period(normalized)
    requested_profit = "profit" in normalized
    metric_info = _detect_metric_info(normalized, requested_profit)
    economic_kind = _detect_economic_kind(normalized)
    if metric_info["metric"] == "creditare_vs_recuperare":
        economic_kind = None
    analysis_category = _detect_analysis_category(normalized)
    project_name = _detect_project_name(normalized)
    mode = _detect_mode(normalized, analysis_category)
    entity_name = _detect_entity_name(normalized, mode, analysis_category)
    direction = _detect_direction(normalized, economic_kind, requested_profit, str(metric_info["metric"]))
    group_by = _detect_group_by(normalized, years)
    creditare_focus = _detect_creditare_focus(normalized, str(metric_info["metric"]))
    include_creditare_balance = _should_include_creditare_balance(normalized, str(metric_info["metric"]))

    plan = QueryPlan(
        raw_question=question,
        mode=mode,
        metric=str(metric_info["metric"]),
        metric_label=str(metric_info["label"]),
        support_level=str(metric_info["support_level"]),
        years=years,
        months=months,
        relative_period=relative_period,
        group_by=group_by,
        economic_kind=economic_kind,
        excluded_economic_kinds=list(metric_info["excluded_economic_kinds"]),
        analysis_category=analysis_category,
        entity_name=entity_name,
        project_name=project_name,
        direction=direction,
        requested_profit=requested_profit,
        creditare_focus=creditare_focus,
        include_creditare_balance=include_creditare_balance,
    )
    if semantic_provider is not None and _should_try_semantic_intent(plan, normalized):
        try:
            payload = semantic_provider.resolve(question)
        except Exception:
            payload = {}
        plan = merge_semantic_plan(plan, payload if isinstance(payload, dict) else {})
    return plan


def _normalize_question(question: str) -> str:
    normalized = normalize_text(question)
    replacements = {
        "ă": "a",
        "â": "a",
        "î": "i",
        "ș": "s",
        "ş": "s",
        "ț": "t",
        "ţ": "t",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


def _extract_years(question: str) -> list[int]:
    return [int(year) for year in sorted(set(re.findall(r"\b(20\d{2})\b", question)))]


def _extract_months(question: str) -> list[int]:
    months: list[int] = []
    for name, month_number in MONTH_NAME_MAP.items():
        if name == "mai":
            pattern = r"(?:\bin\s+mai\b|\bpe\s+mai\b|\bluna\s+mai\b|\bdin\s+mai\b)"
        else:
            pattern = rf"\b{name}\b"
        if re.search(pattern, question) and month_number not in months:
            months.append(month_number)
    return months


def _detect_mode(question: str, analysis_category: str | None) -> str:
    if any(token in question for token in SEARCH_TOKENS):
        if "cat " not in question and "cat " not in question and "cat am avut" not in question:
            return "search"
        if analysis_category is None and "tranzacti" in question:
            return "search"
    return "aggregate"


def _detect_group_by(question: str, years: list[int]) -> str | None:
    if any(token in question for token in HALF_YEAR_TOKENS):
        return "half_year"
    if len(years) > 1 or any(token in question for token in YEAR_GROUP_TOKENS):
        return "year"
    return None


def _detect_relative_period(question: str) -> str | None:
    if any(token in question for token in FIRST_YEAR_TOKENS):
        return "first_year"
    return None


def _detect_metric(question: str, direction: str, requested_profit: bool) -> str:
    if requested_profit:
        return "net_cashflow"
    if any(token in question for token in COUNT_TOKENS):
        return "transaction_count"
    if any(token in question for token in EXPENSE_TOKENS):
        return "expense_total"
    if any(token in question for token in INCOME_TOKENS):
        return "income_total"
    if direction == "both":
        return "total_amount"
    return "total_amount"


def _detect_metric_info(question: str, requested_profit: bool) -> dict[str, object]:
    if _is_ambiguous_entity_summary_question(question):
        return {
            "metric": "entity_relationship_summary",
            "label": "situatia relatiei",
            "support_level": "exact",
            "excluded_economic_kinds": [],
        }
    if _needs_clarification(question):
        return {
            "metric": "total_amount",
            "label": "clarificare",
            "support_level": "clarify",
            "excluded_economic_kinds": [],
        }

    if _mentions_creditare(question) and _mentions_creditare_recovery(question):
        return {
            "metric": "creditare_vs_recuperare",
            "label": "creditare si recuperare creditare",
            "support_level": "exact",
            "excluded_economic_kinds": [],
        }
    if any(token in question for token in OUTSTANDING_INVOICE_TOKENS):
        return {
            "metric": "invoice_residual_total",
            "label": "sold facturi primite",
            "support_level": "exact",
            "excluded_economic_kinds": [],
        }

    for token, label in UNSUPPORTED_METRIC_PATTERNS:
        if token in question:
            return {
                "metric": "unsupported",
                "label": label,
                "support_level": "unsupported",
                "excluded_economic_kinds": [],
            }

    if "profit contabil" in question:
        return {
            "metric": "unsupported",
            "label": "profit contabil",
            "support_level": "unsupported",
            "excluded_economic_kinds": [],
        }

    for token, metric, label in ESTIMATED_METRIC_PATTERNS:
        if token in question:
            exclusions = (
                OPERATIONAL_INCOME_EXCLUSIONS
                if metric == "operational_income_estimate"
                else OPERATIONAL_EXPENSE_EXCLUSIONS
            )
            return {
                "metric": metric,
                "label": label,
                "support_level": "estimated",
                "excluded_economic_kinds": exclusions,
            }

    if requested_profit:
        return {
            "metric": "net_cashflow",
            "label": "profit",
            "support_level": "estimated",
            "excluded_economic_kinds": [],
        }

    direction = _detect_direction(question, None, requested_profit, None)
    metric = _detect_metric(question, direction, requested_profit)
    return {
        "metric": metric,
        "label": _default_metric_label(metric),
        "support_level": "exact",
        "excluded_economic_kinds": [],
    }


def _detect_economic_kind(question: str) -> str | None:
    for token, economic_kind in ECONOMIC_KIND_PATTERNS:
        if token in question:
            return economic_kind
    return None


def _detect_analysis_category(question: str) -> str | None:
    patterns = (
        r"cheltuiel(?:i|ile)\s+cu\s+([a-z0-9 .&_-]+?)(?:[?.!,]|$)",
        r"categoria\s+([a-z0-9 .&_-]+?)(?:[?.!,]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            return _clean_capture(match.group(1))
    return None


def _detect_project_name(question: str) -> str | None:
    match = re.search(r"proiectul\s+([a-z0-9 .&_-]+?)(?:[?.!,]|$)", question)
    if not match:
        return None
    return _clean_capture(match.group(1))


def _detect_entity_name(
    question: str,
    mode: str,
    analysis_category: str | None,
) -> str | None:
    ambiguous_patterns = (
        r"situatia\s+lui\s+([a-z0-9 .&_-]+?)(?:[?.!,]|$)",
        r"situatia\s+cu\s+([a-z0-9 .&_-]+?)(?:[?.!,]|$)",
        r"relatia\s+cu\s+([a-z0-9 .&_-]+?)(?:[?.!,]|$)",
    )
    for pattern in ambiguous_patterns:
        match = re.search(pattern, question)
        if match:
            candidate = _strip_project_suffix(_clean_capture(match.group(1)))
            if candidate and candidate != analysis_category:
                return candidate

    patterns = (
        r"tranzacti(?:ile|iile|i|ile)\s+(?:cu|catre|catre)\s+([a-z0-9 .&_-]+?)(?:[?.!,]|$)",
        r"(?:cu|catre|catre)\s+([a-z0-9 .&_-]+?)(?:[?.!,]|$)",
        r"de\s+la\s+([a-z0-9 .&_-]+?)(?:[?.!,]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, question)
        if not match:
            continue
        candidate = _strip_project_suffix(_clean_capture(match.group(1)))
        if candidate and candidate != analysis_category:
            return candidate

    if mode != "search":
        return None
    return None


def _detect_direction(
    question: str,
    economic_kind: str | None,
    requested_profit: bool,
    metric: str | None,
) -> str:
    if metric == "operational_income_estimate":
        return "inflow"
    if metric == "operational_expense_estimate":
        return "outflow"
    if metric == "creditare_vs_recuperare":
        return "both"
    if requested_profit:
        return "both"
    if economic_kind == "creditare":
        return "inflow"
    if economic_kind == "recuperare_creditare":
        return "outflow"
    if any(token in question for token in EXPENSE_TOKENS):
        return "outflow"
    if any(token in question for token in INCOME_TOKENS):
        return "inflow"
    return "both"


def _default_metric_label(metric: str) -> str:
    labels = {
        "transaction_count": "numar de tranzactii",
        "expense_total": "plati",
        "income_total": "incasari",
        "net_cashflow": "cashflow net",
        "invoice_residual_total": "sold facturi primite",
        "total_amount": "suma",
        "creditare_vs_recuperare": "creditare si recuperare creditare",
        "entity_relationship_summary": "situatia relatiei",
    }
    return labels.get(metric, "suma")


def _mentions_creditare(question: str) -> bool:
    return any(token in question for token in ("creditare", "creditari", "creditat", "creditate"))


def _mentions_creditare_recovery(question: str) -> bool:
    return any(token in question for token in ("recuperare", "recuperari", "recuperat", "recuperate"))


def _clean_capture(value: str) -> str:
    return normalize_text(value).strip(" ?!.,:;")


def _strip_project_suffix(value: str) -> str:
    return re.sub(r"\s+pe proiectul\s+[a-z0-9 .&_-]+$", "", value).strip()


def _detect_creditare_focus(question: str, metric: str) -> str | None:
    if metric != "creditare_vs_recuperare":
        return None
    if any(token in question for token in CREDITARE_FOCUS_REMAINING_TOKENS):
        return "remaining"
    if any(token in question for token in CREDITARE_FOCUS_RECOVERY_TOKENS):
        return "recovered"
    if any(token in question for token in CREDITARE_FOCUS_CREDITED_TOKENS):
        return "credited"
    return "summary"


def _should_include_creditare_balance(question: str, metric: str) -> bool:
    if metric != "creditare_vs_recuperare":
        return False
    if any(token in question for token in CREDITARE_FOCUS_REMAINING_TOKENS):
        return True
    # Include balance by default for this metric because it is the key business signal.
    return True


def _is_ambiguous_entity_summary_question(question: str) -> bool:
    return any(token in question for token in AMBIGUOUS_ENTITY_SUMMARY_TOKENS)


def _needs_clarification(question: str) -> bool:
    if not any(token in question for token in CLARIFY_TOKENS):
        return False
    if _is_ambiguous_entity_summary_question(question):
        return False
    if any(token in question for token in COUNT_TOKENS):
        return False
    if any(token in question for token in EXPENSE_TOKENS):
        return False
    if any(token in question for token in INCOME_TOKENS):
        return False
    if any(token in question for token, _ in ECONOMIC_KIND_PATTERNS):
        return False
    if any(token in question for token, _, _ in ESTIMATED_METRIC_PATTERNS):
        return False
    if any(token in question for token, _ in UNSUPPORTED_METRIC_PATTERNS):
        return False
    if any(token in question for token in OUTSTANDING_INVOICE_TOKENS):
        return False
    if "profit" in question or "proiectul " in question or "categoria " in question:
        return False
    return True


def _should_try_semantic_intent(plan: QueryPlan, normalized_question: str) -> bool:
    if plan.support_level == "clarify":
        return True
    if plan.analysis_category is None and re.search(r"\bcu\s+[a-z0-9_-]{3,}\b", normalized_question):
        if plan.metric in {"expense_total", "income_total", "transaction_count", "total_amount"}:
            return True
    if not plan.months and any(re.search(rf"\b{name}\b", normalized_question) for name in MONTH_NAME_MAP):
        return True
    return False
