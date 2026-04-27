from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import pandas as pd
from pypdf import PdfReader

from .models import ImportedInvoice, ImportedTransaction, StatementParseResult, StatementValidation
from .normalize import merchant_from_description, parse_amount, parse_date, sign_amount


DATE_LINE_RE = re.compile(
    r"(?P<date>\d{2}[./-]\d{2}[./-]\d{4}|\d{4}[./-]\d{2}[./-]\d{2}).*?(?P<amount>-?\d[\d.,]*)"
)
STANDALONE_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
INLINE_TRANSACTION_RE = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<description>.+?)\s+(?P<amount>-?\d[\d,]*\.\d{2})\s+RON\s+(?P<balance>-?\d[\d,]*\.\d{2})\s+RON$"
)
AMOUNT_BALANCE_RE = re.compile(r"^(?P<amount>-?\d[\d,]*\.\d{2})\s+RON\s+(?P<balance>-?\d[\d,]*\.\d{2})\s+RON$")
ING_AMOUNT_BALANCE_RE = re.compile(r"^(?P<amount>-?\d[\d,]*\.\d{2})\s+(?P<balance>-?\d[\d,]*\.\d{2})$")


def detect_currency(text: str) -> str:
    upper = text.upper()
    for currency in ("RON", "EUR", "USD", "GBP"):
        if currency in upper:
            return currency
    return "RON"


def parse_statement_path(path: str | Path) -> list[ImportedTransaction]:
    return list(parse_statement_bundle(path).transactions)


def parse_statement_bundle(path: str | Path) -> StatementParseResult:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        transactions = parse_csv(file_path)
        return StatementParseResult(
            transactions=tuple(transactions),
            validation=_validation_unavailable("csv"),
        )
    if suffix == ".json":
        transactions = parse_json(file_path)
        return StatementParseResult(
            transactions=tuple(transactions),
            validation=_validation_unavailable("json"),
        )
    if suffix == ".pdf":
        return parse_pdf_bundle(file_path)
    raise ValueError(f"Unsupported file type: {file_path.suffix}")


def parse_issued_invoices_path(path: str | Path) -> list[ImportedInvoice]:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(file_path)
        return dataframe_to_issued_invoices(frame, file_path)
    if suffix == ".json":
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for key in ("invoices", "issued_invoices", "items", "data"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        frame = pd.DataFrame(payload)
        return dataframe_to_issued_invoices(frame, file_path)
    if suffix == ".pdf":
        return parse_issued_invoice_pdf(file_path)
    raise ValueError(f"Unsupported invoice file type: {file_path.suffix}")


def parse_csv(path: Path) -> list[ImportedTransaction]:
    frame = pd.read_csv(path)
    return dataframe_to_transactions(frame, path)


def parse_json(path: Path) -> list[ImportedTransaction]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        for key in ("transactions", "items", "data"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    frame = pd.DataFrame(payload)
    return dataframe_to_transactions(frame, path)


def parse_issued_invoice_pdf(path: Path) -> list[ImportedInvoice]:
    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    invoice_number = text_match(text, r"\bNumber\s+(?P<value>[A-Za-z0-9._/-]+)")
    issue_date = parse_date(text_match(text, r"\bDate\s+(?P<value>\d{2}[./-]\d{2}[./-]\d{4})"))
    customer_name = invoice_pdf_customer_name(lines)
    currency = text_match(text, r"-\s*(?P<value>[A-Z]{3})\s*-") or "RON"

    ron_summary = re.search(
        r"Sume in RON \(curs (?P<exchange_rate>[\d.,]+)\):\s*"
        r"Valoare\s+(?P<net>[\d\s.,]+)\s+RON,\s*"
        r"TVA\s+(?P<vat>[\d\s.,]+)\s+RON,\s*"
        r"TOTAL\s+(?P<total>[\d\s.,]+)\s+RON",
        text,
    )
    if not (invoice_number and issue_date and customer_name and ron_summary):
        return []

    net_amount = parse_amount(ron_summary.group("net"))
    vat_amount = parse_amount(ron_summary.group("vat"))
    total_amount = parse_amount(ron_summary.group("total"))
    if net_amount is None or total_amount is None:
        return []

    return [
        ImportedInvoice(
            invoice_number=invoice_number,
            issue_date=issue_date,
            customer_name=customer_name,
            net_amount=float(net_amount),
            vat_amount=None if vat_amount is None else float(vat_amount),
            total_amount=float(total_amount),
            currency=currency,
            status="issued",
            source_file=str(path),
            raw_payload=json.dumps(
                {
                    "type": "issued_invoice_pdf",
                    "invoice_number": invoice_number,
                    "issue_date": issue_date,
                    "customer_name": customer_name,
                    "currency": currency,
                    "exchange_rate": parse_amount(ron_summary.group("exchange_rate")),
                    "net_amount_ron": net_amount,
                    "vat_amount_ron": vat_amount,
                    "total_amount_ron": total_amount,
                    "lines": lines,
                },
                ensure_ascii=False,
            ),
        )
    ]


def text_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group("value")).strip()


def invoice_pdf_customer_name(lines: list[str]) -> str:
    for index, line in enumerate(lines):
        if line.startswith("Number ") and index > 0:
            return lines[index - 1]
    return lines[0] if lines else ""


def parse_pdf(path: Path) -> list[ImportedTransaction]:
    return list(parse_pdf_bundle(path).transactions)


def parse_pdf_bundle(path: Path) -> StatementParseResult:
    reader = PdfReader(str(path))
    first_page_text = reader.pages[0].extract_text() or ""
    if is_garanti_statement(first_page_text):
        transactions = parse_garanti_pdf(reader, path)
        validation = validate_garanti_statement(reader, transactions)
        return StatementParseResult(transactions=tuple(transactions), validation=validation)
    if is_ing_statement(first_page_text):
        transactions = parse_ing_pdf(reader, path)
        validation = validate_ing_statement(reader, transactions)
        return StatementParseResult(transactions=tuple(transactions), validation=validation)

    rows: list[ImportedTransaction] = []
    currency = "RON"
    for page in reader.pages:
        text = page.extract_text() or ""
        currency = detect_currency(text) or currency
        for line in text.splitlines():
            cleaned = re.sub(r"\s+", " ", line).strip()
            if not cleaned:
                continue
            match = DATE_LINE_RE.search(cleaned)
            if not match:
                continue
            tx_date = parse_date(match.group("date"))
            amounts = [parse_amount(item) for item in re.findall(r"-?\d[\d.,]*", cleaned)]
            amounts = [item for item in amounts if item is not None]
            if not tx_date or not amounts:
                continue
            amount = amounts[-1]
            description = cleaned.replace(match.group("date"), "", 1)
            description = description.rsplit(match.group("amount"), 1)[0].strip(" -")
            if not description:
                description = cleaned
            rows.append(
                ImportedTransaction(
                    transaction_date=tx_date,
                    description=description,
                    amount=float(amount),
                    currency=currency,
                    balance=None,
                    merchant=merchant_from_description(description),
                    source_file=str(path),
                    raw_payload=json.dumps({"line": cleaned}, ensure_ascii=False),
                )
            )
    return StatementParseResult(
        transactions=tuple(rows),
        validation=_validation_unavailable("generic_pdf"),
    )


def add_ing_balance_adjustments(
    rows: list[ImportedTransaction],
    path: Path,
    closing_balance: float | None = None,
) -> list[ImportedTransaction]:
    adjusted: list[ImportedTransaction] = []
    previous_balance = 0.0
    for row in rows:
        if row.balance is not None:
            expected_balance = round(previous_balance + row.amount, 2)
            gap = round(row.balance - expected_balance, 2)
            if abs(gap) > 0.01:
                adjusted.append(
                    ImportedTransaction(
                        transaction_date=row.transaction_date,
                        description="ING balance adjustment inferred from statement balance",
                        amount=gap,
                        currency=row.currency,
                        balance=round(previous_balance + gap, 2),
                        merchant="ING Bank Romania",
                        source_file=str(path),
                        raw_payload=json.dumps(
                            {
                                "type": "ing_balance_adjustment",
                                "related_reference": json.loads(row.raw_payload).get("reference_number"),
                                "gap": gap,
                                "previous_balance": previous_balance,
                                "reported_balance_after_transaction": row.balance,
                            },
                            ensure_ascii=False,
                        ),
                    )
                )
                previous_balance = round(previous_balance + gap, 2)
        adjusted.append(row)
        if row.balance is not None:
            previous_balance = row.balance
    if closing_balance is not None and rows:
        final_gap = round(closing_balance - previous_balance, 2)
        if abs(final_gap) > 0.01:
            adjusted.append(
                ImportedTransaction(
                    transaction_date=rows[-1].transaction_date,
                    description="ING closing balance adjustment inferred from statement summary",
                    amount=final_gap,
                    currency=rows[-1].currency,
                    balance=closing_balance,
                    merchant="ING Bank Romania",
                    source_file=str(path),
                    raw_payload=json.dumps(
                        {
                            "type": "ing_closing_balance_adjustment",
                            "gap": final_gap,
                            "previous_balance": previous_balance,
                            "closing_balance": closing_balance,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
    return adjusted


def is_garanti_statement(text: str) -> bool:
    normalized = text.lower()
    return ("garanti bank" in normalized and "extras de cont" in normalized) or "garantibbva.ro" in normalized


def is_ing_statement(text: str) -> bool:
    normalized = text.lower()
    return "account statement" in normalized and "ing bank" in normalized and "book date" in normalized


def parse_garanti_pdf(reader: PdfReader, path: Path) -> list[ImportedTransaction]:
    lines: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            cleaned = re.sub(r"\s+", " ", raw_line).strip()
            if cleaned:
                lines.append(cleaned)

    rows: list[ImportedTransaction] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if should_skip_garanti_line(line):
            i += 1
            continue

        inline_match = INLINE_TRANSACTION_RE.match(line)
        if inline_match:
            tx = garanti_inline_transaction(inline_match, path)
            if tx:
                rows.append(tx)
            i += 1
            continue

        if STANDALONE_DATE_RE.match(line):
            tx_date = parse_date(line)
            detail_lines: list[str] = []
            i += 1
            while i < len(lines):
                current = lines[i]
                if should_skip_garanti_line(current):
                    i += 1
                    continue
                if INLINE_TRANSACTION_RE.match(current) or STANDALONE_DATE_RE.match(current):
                    break
                amount_match = AMOUNT_BALANCE_RE.match(current)
                if amount_match:
                    tx = garanti_block_transaction(tx_date, detail_lines, amount_match, path)
                    if tx:
                        rows.append(tx)
                    i += 1
                    break
                detail_lines.append(current)
                i += 1
            continue

        i += 1

    return rows


def parse_ing_pdf(reader: PdfReader, path: Path) -> list[ImportedTransaction]:
    lines: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            cleaned = re.sub(r"\s+", " ", raw_line).strip()
            if cleaned:
                lines.append(cleaned)

    rows: list[ImportedTransaction] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", line):
            i += 1
            continue

        tx_date = parse_date(line)
        reference_number = ""
        i += 1
        while i < len(lines):
            current = lines[i]
            if re.match(r"^\d{2}\.\d{2}\.\d{4}$", current):
                break
            if should_skip_ing_line(current):
                i += 1
                continue
            reference_number = current
            i += 1
            break
        if not reference_number:
            continue

        detail_lines: list[str] = []
        while i < len(lines):
            current = lines[i]
            amount_match = ING_AMOUNT_BALANCE_RE.match(current)
            if amount_match:
                tx = ing_transaction(tx_date, reference_number, detail_lines, amount_match, path)
                if tx:
                    rows.append(tx)
                i += 1
                break
            if re.match(r"^\d{2}\.\d{2}\.\d{4}$", current) and i + 1 < len(lines) and re.match(r"^\d+$", lines[i + 1]):
                break
            if not should_skip_ing_line(current):
                detail_lines.append(current)
            i += 1
        continue

    # Keep ING parsing strict: return only rows explicitly present in the
    # statement and let validation fail when totals don't match.
    return rows


def validate_garanti_statement(reader: PdfReader, transactions: list[ImportedTransaction]) -> StatementValidation:
    lines = _reader_lines(reader)
    opening_balance = _find_amount_in_lines(lines, "Sold inițial :")
    closing_balance = _find_amount_in_lines(lines, "Soldul final :")
    inflow_summary = _find_count_amount_pair(lines, "Total intrări :")
    outflow_summary = _find_count_amount_pair(lines, "Total ieșiri :")
    return _build_validation(
        parser_name="garanti_pdf",
        transactions=transactions,
        declared_inflow_count=inflow_summary[0] if inflow_summary else None,
        declared_total_income=inflow_summary[1] if inflow_summary else None,
        declared_outflow_count=outflow_summary[0] if outflow_summary else None,
        declared_total_expenses=outflow_summary[1] if outflow_summary else None,
        declared_opening_balance=opening_balance,
        declared_closing_balance=closing_balance,
    )


def validate_ing_statement(reader: PdfReader, transactions: list[ImportedTransaction]) -> StatementValidation:
    lines = _reader_lines(reader)
    opening_balance = None
    closing_balance = None
    inflow_summary = None
    outflow_summary = None
    for line in lines:
        if opening_balance is None:
            opening_balance = _match_ing_opening_balance(line)
        if closing_balance is None:
            closing_balance = _match_ing_closing_balance(line)
        if inflow_summary is None:
            inflow_summary = _match_ing_total_line(line, "Total Credits:")
        if outflow_summary is None:
            outflow_summary = _match_ing_total_line(line, "Total Debits:")
    return _build_validation(
        parser_name="ing_pdf",
        transactions=transactions,
        declared_inflow_count=inflow_summary[0] if inflow_summary else None,
        declared_total_income=inflow_summary[1] if inflow_summary else None,
        declared_outflow_count=outflow_summary[0] if outflow_summary else None,
        declared_total_expenses=outflow_summary[1] if outflow_summary else None,
        declared_opening_balance=opening_balance,
        declared_closing_balance=closing_balance,
    )


def ing_closing_balance(lines: list[str]) -> float | None:
    for line in lines:
        match = re.match(r"^\d{2}\.\d{2}\.\d{4}\s+Closing Balance:\s+(?P<balance>-?\d[\d,]*\.\d{2})$", line)
        if match:
            return parse_amount(match.group("balance"))
    return None


def _match_ing_opening_balance(line: str) -> float | None:
    match = re.match(r"^\d{2}\.\d{2}\.\d{4}\s+Opening Balance:\s+(?P<balance>-?\d[\d,]*\.\d{2})$", line)
    return parse_amount(match.group("balance")) if match else None


def _match_ing_closing_balance(line: str) -> float | None:
    match = re.match(r"^\d{2}\.\d{2}\.\d{4}\s+Closing Balance:\s+(?P<balance>-?\d[\d,]*\.\d{2})$", line)
    return parse_amount(match.group("balance")) if match else None


def _match_ing_total_line(line: str, prefix: str) -> tuple[int, float] | None:
    pattern = rf"^{re.escape(prefix)}\s+(?P<count>\d+)\s+(?P<amount>-?[\d,\s]+\.\d{{2}})$"
    match = re.match(pattern, line)
    if not match:
        return None
    amount = parse_amount(match.group("amount"))
    if amount is None:
        return None
    return int(match.group("count")), abs(float(amount))


def should_skip_ing_line(line: str) -> bool:
    prefixes = (
        "Account Statement",
        "ING Bank N.V.",
        "54A Aviator",
        "TR:",
        "Tel:",
        "BIC code",
        "Page ",
        "This document was issued",
        "without signature",
        "Account number:",
        "Account name:",
        "Currency:",
        "Book date",
        "Summary",
        "Date Count Amount",
        "Total Credits:",
        "Total Debits:",
        "Transactions",
        "Book date Counterparty",
        "Bank Reference Transaction Description Debit Credit Balance after",
    )
    if line.startswith(prefixes):
        return True
    if "Opening Balance:" in line or "Closing Balance:" in line:
        return True
    return False


def ing_transaction(
    tx_date: str | None,
    reference_number: str,
    detail_lines: list[str],
    amount_match: re.Match[str],
    path: Path,
) -> ImportedTransaction | None:
    amount = parse_amount(amount_match.group("amount"))
    balance = parse_amount(amount_match.group("balance"))
    if tx_date is None or amount is None:
        return None

    merchant = ing_merchant(detail_lines)
    description = ing_description(detail_lines, merchant)
    return ImportedTransaction(
        transaction_date=tx_date,
        description=description,
        amount=amount,
        currency="RON",
        balance=balance,
        merchant=merchant,
        source_file=str(path),
        raw_payload=json.dumps(
            {
                "type": "ing_statement",
                "reference_number": reference_number,
                "lines": detail_lines,
                "amount": amount,
                "balance": balance,
            },
            ensure_ascii=False,
        ),
    )


def ing_merchant(detail_lines: list[str]) -> str:
    for line in detail_lines:
        if re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,}$", line.replace(" ", "")):
            continue
        if line.startswith("INGB ") or line.startswith("BTRA "):
            continue
        if re.match(r"^\d+$", line):
            continue
        return line
    return "Unknown"


def ing_description(detail_lines: list[str], merchant: str) -> str:
    meaningful = [
        line for line in detail_lines[1:]
        if line != merchant and not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,}$", line.replace(" ", ""))
    ]
    return " | ".join(meaningful[:5]) if meaningful else merchant


def should_skip_garanti_line(line: str) -> bool:
    if re.match(r"^\d+\s*/\s*\d+$", line):
        return True

    prefixes = (
        "Garanti Bank S.A.",
        "Șos. Fabrica de Glucoză",
        "Sector 2, Bucuresti",
        "Număr de ordine",
        "Cod de înregistrare fiscală",
        "www.garantibbva.ro",
        "Data:",
        "Ora:",
        "Nume client :",
        "Număr cont :",
        "RO54UGBI",
        "Valuta :",
        "Tipul contului :",
        "De la :",
        "Până la :",
        "Sold inițial :",
        "Soldul final :",
        "Sold disponibil :",
        "Număr Suma",
        "Total intrări :",
        "Total ieșiri :",
        "Extras de cont",
        "Data Detalii Suma Sold",
    )
    if line.startswith(prefixes):
        return True
    if "înregistrări găsite între" in line:
        return True
    return False


def garanti_inline_transaction(match: re.Match[str], path: Path) -> ImportedTransaction | None:
    tx_date = parse_date(match.group("date"))
    description = match.group("description").strip()
    amount = parse_amount(match.group("amount"))
    balance = parse_amount(match.group("balance"))
    if tx_date is None or amount is None:
        return None

    merchant = garanti_merchant(description, [])
    return ImportedTransaction(
        transaction_date=tx_date,
        description=description,
        amount=amount,
        currency="RON",
        balance=balance,
        merchant=merchant,
        source_file=str(path),
        raw_payload=json.dumps(
            {
                "type": "garanti_inline",
                "description": description,
                "amount": amount,
                "balance": balance,
            },
            ensure_ascii=False,
        ),
    )


def garanti_block_transaction(
    tx_date: str | None, detail_lines: list[str], amount_match: re.Match[str], path: Path
) -> ImportedTransaction | None:
    amount = parse_amount(amount_match.group("amount"))
    balance = parse_amount(amount_match.group("balance"))
    if tx_date is None or amount is None:
        return None

    description = garanti_description(detail_lines)
    merchant = garanti_merchant(description, detail_lines)
    return ImportedTransaction(
        transaction_date=tx_date,
        description=description,
        amount=amount,
        currency="RON",
        balance=balance,
        merchant=merchant,
        source_file=str(path),
        raw_payload=json.dumps(
            {
                "type": "garanti_block",
                "lines": detail_lines,
                "amount": amount,
                "balance": balance,
            },
            ensure_ascii=False,
        ),
    )


def garanti_description(detail_lines: list[str]) -> str:
    if not detail_lines:
        return "Unknown transaction"
    headline = detail_lines[0]
    extras = [line for line in detail_lines[1:] if line.startswith(("Beneficiar:", "Ordonator:", "Detalii:", "Agentie:"))]
    if extras:
        return " | ".join([headline, *extras[:3]])
    return headline


def garanti_merchant(description: str, detail_lines: list[str]) -> str:
    for prefix in ("Beneficiar:", "Ordonator:"):
        for line in detail_lines:
            if line.startswith(prefix):
                candidate = line.split(":", 1)[1].strip()
                if candidate:
                    return candidate
    return merchant_from_description(description)


def dataframe_to_transactions(frame: pd.DataFrame, path: Path) -> list[ImportedTransaction]:
    if frame.empty:
        return []

    columns = {column.lower().strip(): column for column in frame.columns}
    date_col = first_match(columns, ("date", "transaction date", "booking date", "data", "posted date"))
    desc_col = first_match(columns, ("description", "details", "narrative", "descriere", "merchant"))
    amount_col = first_match(columns, ("amount", "sum", "valoare"))
    debit_col = first_match(columns, ("debit", "withdrawal", "out"))
    credit_col = first_match(columns, ("credit", "deposit", "in"))
    balance_col = first_match(columns, ("balance", "sold"))
    currency_col = first_match(columns, ("currency", "ccy", "moneda"))

    rows: list[ImportedTransaction] = []
    for record in frame.to_dict(orient="records"):
        tx_date = parse_date(record.get(date_col)) if date_col else None
        description = str(record.get(desc_col) or "").strip()
        debit = parse_amount(record.get(debit_col)) if debit_col else None
        credit = parse_amount(record.get(credit_col)) if credit_col else None
        amount = parse_amount(record.get(amount_col)) if amount_col else None
        signed_amount = sign_amount(amount, debit, credit)
        if tx_date is None or signed_amount is None:
            continue

        currency = str(record.get(currency_col) or "RON").strip() if currency_col else "RON"
        balance = parse_amount(record.get(balance_col)) if balance_col else None
        merchant = merchant_from_description(description)
        rows.append(
            ImportedTransaction(
                transaction_date=tx_date,
                description=description or merchant,
                amount=signed_amount,
                currency=currency or "RON",
                balance=balance,
                merchant=merchant,
                source_file=str(path),
                raw_payload=json.dumps(record, default=str, ensure_ascii=False),
            )
        )
    return rows


def dataframe_to_issued_invoices(frame: pd.DataFrame, path: Path) -> list[ImportedInvoice]:
    if frame.empty:
        return []

    columns = {column.lower().strip(): column for column in frame.columns}
    number_col = first_match(columns, ("invoice_number", "number", "numar", "număr", "nr", "serie si numar"))
    date_col = first_match(columns, ("issue_date", "date", "data", "data emitere", "issued_at"))
    customer_col = first_match(columns, ("customer", "customer_name", "client", "beneficiar", "cumparator"))
    net_col = first_match(columns, ("net", "net_amount", "subtotal", "valoare neta", "baza", "amount_without_vat"))
    vat_col = first_match(columns, ("vat", "vat_amount", "tva"))
    total_col = first_match(columns, ("total", "total_amount", "valoare", "valoare totala", "amount"))
    currency_col = first_match(columns, ("currency", "ccy", "moneda"))
    status_col = first_match(columns, ("status", "stare"))

    rows: list[ImportedInvoice] = []
    for record in frame.to_dict(orient="records"):
        issue_date = parse_date(record.get(date_col)) if date_col else None
        invoice_number = str(record.get(number_col) or "").strip() if number_col else ""
        customer_name = str(record.get(customer_col) or "").strip() if customer_col else ""
        vat_amount = parse_amount(record.get(vat_col)) if vat_col else None
        total_amount = parse_amount(record.get(total_col)) if total_col else None
        net_amount = parse_amount(record.get(net_col)) if net_col else None

        if net_amount is None and total_amount is not None and vat_amount is not None:
            net_amount = round(total_amount - vat_amount, 2)
        if total_amount is None and net_amount is not None:
            total_amount = round(net_amount + (vat_amount or 0), 2)

        if not issue_date or not invoice_number or not customer_name or net_amount is None or total_amount is None:
            continue

        currency = str(record.get(currency_col) or "RON").strip() if currency_col else "RON"
        status = str(record.get(status_col) or "issued").strip().lower() if status_col else "issued"
        rows.append(
            ImportedInvoice(
                invoice_number=invoice_number,
                issue_date=issue_date,
                customer_name=customer_name,
                net_amount=float(net_amount),
                vat_amount=None if vat_amount is None else float(vat_amount),
                total_amount=float(total_amount),
                currency=currency or "RON",
                status=status or "issued",
                source_file=str(path),
                raw_payload=json.dumps(record, default=str, ensure_ascii=False),
            )
        )
    return rows


def first_match(columns: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return columns[candidate]
    return None


def _validation_unavailable(parser_name: str) -> StatementValidation:
    return StatementValidation(
        available=False,
        passed=False,
        parser_name=parser_name,
        errors=("statement_totals_unavailable",),
        declared_transaction_count=None,
        parsed_transaction_count=0,
        declared_inflow_count=None,
        parsed_inflow_count=0,
        declared_outflow_count=None,
        parsed_outflow_count=0,
        declared_total_income=None,
        parsed_total_income=0.0,
        declared_total_expenses=None,
        parsed_total_expenses=0.0,
        declared_net_cashflow=None,
        parsed_net_cashflow=0.0,
        declared_opening_balance=None,
        declared_closing_balance=None,
        parsed_closing_balance=None,
        inferred_transaction_count=0,
    )


def _reader_lines(reader: PdfReader) -> list[str]:
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _find_amount_in_lines(lines: list[str], prefix: str) -> float | None:
    for line in lines:
        if line.startswith(prefix):
            match = re.search(r"(-?[\d,.]+)\s+[A-Z]{3}$", line)
            if match:
                return parse_amount(match.group(1))
    return None


def _find_count_amount_pair(lines: list[str], prefix: str) -> tuple[int, float] | None:
    for line in lines:
        if not line.startswith(prefix):
            continue
        match = re.search(rf"^{re.escape(prefix)}\s*(?P<count>\d+)\s+(?P<amount>-?[\d,.]+)\s+[A-Z]{{3}}$", line)
        if not match:
            continue
        amount = parse_amount(match.group("amount"))
        if amount is None:
            continue
        return int(match.group("count")), abs(float(amount))
    return None


def _build_validation(
    *,
    parser_name: str,
    transactions: list[ImportedTransaction],
    declared_inflow_count: int | None,
    declared_total_income: float | None,
    declared_outflow_count: int | None,
    declared_total_expenses: float | None,
    declared_opening_balance: float | None,
    declared_closing_balance: float | None,
) -> StatementValidation:
    parsed_transaction_count = len(transactions)
    parsed_inflow_count = sum(1 for row in transactions if row.amount > 0)
    parsed_outflow_count = sum(1 for row in transactions if row.amount < 0)
    parsed_total_income = round(sum(row.amount for row in transactions if row.amount > 0), 2)
    parsed_total_expenses = round(sum(-row.amount for row in transactions if row.amount < 0), 2)
    parsed_net_cashflow = round(sum(row.amount for row in transactions), 2)
    parsed_closing_balance = transactions[-1].balance if transactions and transactions[-1].balance is not None else None
    inferred_transaction_count = sum(
        1
        for row in transactions
        if '"type": "ing_balance_adjustment"' in row.raw_payload or '"type": "ing_closing_balance_adjustment"' in row.raw_payload
    )
    declared_transaction_count = None
    if declared_inflow_count is not None and declared_outflow_count is not None:
        declared_transaction_count = declared_inflow_count + declared_outflow_count

    errors: list[str] = []
    available = any(
        value is not None
        for value in (
            declared_inflow_count,
            declared_outflow_count,
            declared_total_income,
            declared_total_expenses,
            declared_closing_balance,
        )
    )
    if not available:
        errors.append("statement_totals_unavailable")
    if declared_transaction_count is not None and declared_transaction_count != parsed_transaction_count:
        errors.append("transaction_count_mismatch")
    if declared_inflow_count is not None and declared_inflow_count != parsed_inflow_count:
        errors.append("inflow_count_mismatch")
    if declared_outflow_count is not None and declared_outflow_count != parsed_outflow_count:
        errors.append("outflow_count_mismatch")
    if declared_total_income is not None and round(declared_total_income, 2) != parsed_total_income:
        errors.append("income_total_mismatch")
    if declared_total_expenses is not None and round(declared_total_expenses, 2) != parsed_total_expenses:
        errors.append("expense_total_mismatch")
    declared_net_cashflow = None
    if declared_total_income is not None and declared_total_expenses is not None:
        declared_net_cashflow = round(declared_total_income - declared_total_expenses, 2)
        if declared_net_cashflow != parsed_net_cashflow:
            errors.append("net_cashflow_mismatch")
    if declared_opening_balance is not None and declared_closing_balance is not None and declared_net_cashflow is not None:
        expected_closing_balance = round(declared_opening_balance + declared_net_cashflow, 2)
        if round(declared_closing_balance, 2) != expected_closing_balance:
            errors.append("declared_balance_summary_inconsistent")
    if declared_closing_balance is not None and parsed_closing_balance is not None:
        if round(declared_closing_balance, 2) != round(parsed_closing_balance, 2):
            errors.append("closing_balance_mismatch")
    if inferred_transaction_count:
        errors.append("contains_inferred_transactions")
    return StatementValidation(
        available=available,
        passed=available and not errors,
        parser_name=parser_name,
        errors=tuple(errors),
        declared_transaction_count=declared_transaction_count,
        parsed_transaction_count=parsed_transaction_count,
        declared_inflow_count=declared_inflow_count,
        parsed_inflow_count=parsed_inflow_count,
        declared_outflow_count=declared_outflow_count,
        parsed_outflow_count=parsed_outflow_count,
        declared_total_income=declared_total_income,
        parsed_total_income=parsed_total_income,
        declared_total_expenses=declared_total_expenses,
        parsed_total_expenses=parsed_total_expenses,
        declared_net_cashflow=declared_net_cashflow,
        parsed_net_cashflow=parsed_net_cashflow,
        declared_opening_balance=declared_opening_balance,
        declared_closing_balance=declared_closing_balance,
        parsed_closing_balance=parsed_closing_balance,
        inferred_transaction_count=inferred_transaction_count,
    )
