from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any


def prepare_salary_transaction(
    candidate: dict[str, Any],
    *,
    existing_transactions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = normalize_salary_transaction(candidate)
    issues: list[dict[str, str]] = []

    if not payload.get("date") and (not payload.get("year") or not payload.get("month")):
        issues.append(error("missing_salary_period", "Lønnstransaksjon må ha date eller year/month."))
    if payload.get("month") is not None and not 1 <= int(payload["month"]) <= 12:
        issues.append(error("invalid_month", "month må være mellom 1 og 12."))
    if not candidate.get("employeeId") and not candidate.get("employee") and not payload.get("payslips"):
        issues.append(warning("employee_not_explicit", "Ingen eksplisitt employeeId/payslip-linje er oppgitt."))
    if not candidate.get("salaryTypeId") and not candidate.get("salaryType") and not payload.get("payslips"):
        issues.append(warning("salary_type_not_explicit", "Ingen eksplisitt salaryType er oppgitt."))

    duplicates = salary_duplicate_status(payload, existing_transactions or [])
    issues.extend(duplicates["issues"])

    if any(issue["severity"] == "error" for issue in issues):
        status = "blocked"
    elif any(issue["severity"] == "warning" for issue in issues):
        status = "needs_clarification"
    else:
        status = "ready"

    return {
        "ok": True,
        "status": status,
        "issues": issues,
        "salary_payload": payload,
        "duplicates": {key: value for key, value in duplicates.items() if key != "issues"},
        "limitations": [
            "Dette forbereder Tripletex salary/transaction, ikke en komplett lønnskjøring.",
            "Altinn/A-melding/ID-porten-submission utføres ikke av CLI-en.",
        ],
    }


def normalize_salary_transaction(candidate: dict[str, Any]) -> dict[str, Any]:
    if isinstance(candidate.get("payload"), dict):
        payload = deepcopy(candidate["payload"])
    else:
        allowed = {
            "date",
            "year",
            "month",
            "isHistorical",
            "paySlipsAvailableDate",
            "payslips",
            "comment",
            "description",
        }
        payload = {key: deepcopy(value) for key, value in candidate.items() if key in allowed}
    if payload.get("date") and (not payload.get("year") or not payload.get("month")):
        parsed = parse_date(payload["date"])
        if parsed:
            payload.setdefault("year", parsed.year)
            payload.setdefault("month", parsed.month)
    return payload


def salary_duplicate_status(
    payload: dict[str, Any],
    existing_transactions: list[dict[str, Any]],
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    date_value = payload.get("date")
    for transaction in existing_transactions:
        if date_value and transaction.get("date") == date_value:
            match = {
                "id": transaction.get("id"),
                "date": transaction.get("date"),
                "year": transaction.get("year"),
                "month": transaction.get("month"),
            }
            matches.append(match)
            issues.append(warning("possible_duplicate_salary_transaction", f"Mulig lønnstransaksjon finnes allerede: {match}"))
    if not existing_transactions:
        status = "not_checked"
    elif matches:
        status = "possible"
    else:
        status = "none"
    return {"status": status, "matches": matches, "issues": issues}


def prepare_unimicro_journal_entry(
    candidate: dict[str, Any],
    *,
    accounts: list[dict[str, Any]] | None = None,
    vat_types: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    account_map = account_lookup(accounts or [])
    vat_map = vat_lookup(vat_types or [])
    draft_lines = candidate.get("DraftLines") or candidate.get("draftLines") or []
    if not isinstance(draft_lines, list) or not draft_lines:
        issues.append(error("missing_draft_lines", "Journal entry må ha DraftLines."))
        draft_lines = []
    normalized_lines: list[dict[str, Any]] = []

    for index, line in enumerate(draft_lines):
        normalized = deepcopy(line)
        prefix = f"Linje {index + 1}"
        if not normalized.get("AccountID"):
            account_number = normalized.pop("AccountNumber", None) or normalized.pop("accountNumber", None)
            if account_number is not None and str(account_number) in account_map:
                normalized["AccountID"] = account_map[str(account_number)]["ID"]
            else:
                issues.append(error("missing_account_id", f"{prefix} mangler AccountID eller kjent accountNumber."))
        if not normalized.get("VatTypeID"):
            vat_code = normalized.pop("VatCode", None) or normalized.pop("vatCode", None)
            if vat_code is not None and str(vat_code) in vat_map:
                normalized["VatTypeID"] = vat_map[str(vat_code)]["ID"]
            elif vat_code is not None:
                issues.append(error("unknown_vat_code", f"{prefix} har ukjent VatCode {vat_code}."))
        for field in ["Amount", "Description", "FinancialDate"]:
            if normalized.get(field) in (None, ""):
                issues.append(error(f"missing_{field}", f"{prefix} mangler {field}."))
        normalized_lines.append(normalized)

    payload = [{"DraftLines": normalized_lines}]
    file_ids = candidate.get("FileIDs") or candidate.get("fileIds")
    if file_ids:
        payload[0]["FileIDs"] = file_ids

    return {
        "ok": True,
        "status": "blocked" if any(issue["severity"] == "error" for issue in issues) else "ready",
        "issues": issues,
        "journal_entry_payload": payload,
    }


def prepare_unimicro_supplier_invoice(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(candidate.get("payload") or {})
    issues: list[dict[str, str]] = []
    if not payload:
        for key in [
            "SupplierID",
            "InvoiceNumber",
            "PaymentDueDate",
            "TaxInclusiveAmountCurrency",
            "CurrencyCodeID",
            "DefaultDimensions",
        ]:
            if key in candidate:
                payload[key] = deepcopy(candidate[key])
    if not payload.get("SupplierID"):
        issues.append(error("missing_supplier_id", "Leverandørfaktura må ha SupplierID."))
    attachments = attachment_status(candidate)
    issues.extend(attachment_issues(attachments))
    return {
        "ok": True,
        "status": "blocked" if any(issue["severity"] == "error" for issue in issues) else "ready",
        "issues": issues,
        "supplier_invoice_payload": payload,
        "attachments": attachments,
    }


def account_lookup(accounts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for account in accounts:
        number = account.get("AccountNumber") or account.get("accountNumber")
        if number is not None:
            result[str(number)] = account
    return result


def vat_lookup(vat_types: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for vat in vat_types:
        code = vat.get("VatCode") or vat.get("vatCode")
        if code is not None:
            result[str(code)] = vat
    return result


def attachment_status(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    attachments = candidate.get("attachments") or candidate.get("attachmentFiles") or []
    if isinstance(attachments, (str, Path)):
        attachments = [attachments]
    result: list[dict[str, Any]] = []
    for item in attachments:
        path = Path(item).expanduser().resolve()
        result.append({"path": str(path), "exists": path.exists() and path.is_file()})
    return result


def attachment_issues(attachments: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [error("attachment_not_found", f"Bilagsfil finnes ikke: {item['path']}") for item in attachments if not item["exists"]]


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[0:10]).date()
    except ValueError:
        return None


def error(code: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "message": message}


def warning(code: str, message: str) -> dict[str, str]:
    return {"severity": "warning", "code": code, "message": message}
