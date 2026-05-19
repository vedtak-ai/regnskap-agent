from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .reconcile import summarize_purchase


HIGH_VAT_RATE = 0.25
ZERO_VAT_TYPES = {
    "NONE",
    "HIGH_FOREIGN_SERVICE_DEDUCTIBLE",
    "HIGH_FOREIGN_SERVICE_NO_DEDUCTION",
    "HIGH_FOREIGN_GOODS_DEDUCTIBLE",
    "HIGH_FOREIGN_GOODS_NO_DEDUCTION",
}

RECEIPT_SOURCES = {
    "leverandør-PDF",
    "e-postkvittering",
    "e-postkvittering dokumentert som PDF",
    "Fiken inbox",
    "Fiken EHF",
    "Fiken EHF-varsel",
    "mangler bilag",
}


def prepare_purchase(
    candidate: dict[str, Any],
    *,
    existing_purchases: list[dict[str, Any]] | None = None,
    duplicate_days: int = 10,
) -> dict[str, Any]:
    payload = normalize_purchase_payload(candidate)
    issues: list[dict[str, str]] = []
    issues.extend(validate_required_payload(payload))
    issues.extend(normalize_vat(payload))
    contact = contact_status(candidate, payload)
    issues.extend(contact["issues"])
    attachments = attachment_status(candidate)
    issues.extend(attachment_issues(attachments, candidate.get("receiptSource")))
    issues.extend(ehf_notice_issues(candidate, payload, attachments))
    duplicates = duplicate_status(
        payload,
        existing_purchases=existing_purchases or [],
        duplicate_days=duplicate_days,
    )
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
        "purchase_payload": payload,
        "contact": {key: value for key, value in contact.items() if key != "issues"},
        "attachments": attachments,
        "source": source_status(candidate),
        "duplicates": {key: value for key, value in duplicates.items() if key != "issues"},
    }


def normalize_purchase_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "identifier",
        "date",
        "dueDate",
        "kind",
        "supplierId",
        "kid",
        "paid",
        "currency",
        "paymentAccount",
        "paymentDate",
        "lines",
    }
    payload = {key: deepcopy(value) for key, value in candidate.items() if key in allowed}
    payload.setdefault("currency", "NOK")
    if "paid" not in payload:
        payload["paid"] = bool(payload.get("paymentAccount") or payload.get("paymentDate"))
    return payload


def validate_required_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for field in ["date", "kind", "currency"]:
        if not payload.get(field):
            issues.append(error(f"missing_{field}", f"Mangler feltet {field}."))
    lines = payload.get("lines")
    if not isinstance(lines, list) or not lines:
        issues.append(error("missing_lines", "Mangler minst én kjøpslinje."))
        return issues
    for index, line in enumerate(lines):
        prefix = f"Linje {index + 1}"
        for field in ["description", "account", "vatType", "netPrice"]:
            if line.get(field) in (None, ""):
                issues.append(error(f"missing_line_{field}", f"{prefix} mangler {field}."))
        if line.get("netPrice") is not None and not isinstance(line.get("netPrice"), int):
            issues.append(error("invalid_line_netPrice", f"{prefix} må ha netPrice som heltall i øre."))
    if payload.get("paid") and (not payload.get("paymentAccount") or not payload.get("paymentDate")):
        issues.append(error("missing_payment", "Betalt kjøp må ha paymentAccount og paymentDate."))
    return issues


def normalize_vat(payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for index, line in enumerate(payload.get("lines") or []):
        if not isinstance(line.get("netPrice"), int):
            continue
        vat_type = str(line.get("vatType") or "")
        if vat_type == "HIGH":
            expected = round(line["netPrice"] * HIGH_VAT_RATE)
            if line.get("vat") is None:
                line["vat"] = expected
                issues.append(info("vat_computed", f"Linje {index + 1}: MVA beregnet til {expected} øre for HIGH."))
            elif line.get("vat") != expected:
                issues.append(
                    error(
                        "vat_mismatch",
                        f"Linje {index + 1}: MVA {line.get('vat')} øre stemmer ikke med HIGH-beløp {expected} øre.",
                    )
                )
        elif vat_type in ZERO_VAT_TYPES:
            if line.get("vat") is None:
                line["vat"] = 0
            elif line.get("vat") != 0:
                issues.append(error("vat_mismatch", f"Linje {index + 1}: {vat_type} skal ha MVA 0 øre."))
        elif line.get("vat") is None:
            issues.append(
                warning(
                    "vat_required",
                    f"Linje {index + 1}: ukjent MVA-type {vat_type}; oppgi eksplisitt vat i øre.",
                )
            )
    return issues


def contact_status(candidate: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind")
    supplier = candidate.get("supplier") or candidate.get("proposedContact")
    if kind == "cash_purchase":
        return {"status": "not_required", "issues": []}
    if payload.get("supplierId"):
        return {"status": "existing", "supplierId": payload["supplierId"], "issues": []}
    if isinstance(supplier, dict) and supplier.get("name"):
        return {"status": "proposed", "contact_payload": supplier, "issues": []}
    if kind == "supplier":
        return {
            "status": "missing",
            "issues": [error("missing_supplier", "Leverandørkjøp må ha supplierId eller foreslått kontakt.")],
        }
    return {"status": "not_required", "issues": []}


def attachment_status(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    source = candidate.get("receiptSource")
    attachments = candidate.get("attachments") or candidate.get("attachmentFiles") or []
    if isinstance(attachments, (str, Path)):
        attachments = [attachments]
    result: list[dict[str, Any]] = []
    for item in attachments:
        path = Path(item).expanduser().resolve()
        result.append(
            {
                "path": str(path),
                "exists": path.exists() and path.is_file(),
                "source": source,
            }
        )
    return result


def attachment_issues(attachments: list[dict[str, Any]], receipt_source: Any) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if receipt_source and receipt_source not in RECEIPT_SOURCES:
        issues.append(warning("unknown_receipt_source", f"Ukjent bilagsproveniens: {receipt_source}."))
    if receipt_source == "mangler bilag":
        issues.append(warning("missing_receipt", "Kandidaten er merket som mangler bilag."))
    if receipt_source != "Fiken inbox" and not attachments:
        issues.append(warning("missing_attachment", "Ingen lokal bilagsfil er oppgitt."))
    for attachment in attachments:
        if not attachment["exists"]:
            issues.append(error("attachment_not_found", f"Bilagsfil finnes ikke: {attachment['path']}"))
    return issues


def ehf_notice_issues(
    candidate: dict[str, Any],
    payload: dict[str, Any],
    attachments: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if candidate.get("receiptSource") != "Fiken EHF-varsel" or attachments:
        return []
    if has_concrete_vat_lines(payload):
        return [
            error(
                "ehf_notice_requires_original",
                "Fiken EHF-varsel er bare metadata. Les original EHF/PDF før du lager eller validerer konkrete MVA-linjer.",
            )
        ]
    return [
        warning(
            "ehf_notice_without_original",
            "EHF-varsel er funnet, men original EHF/PDF er ikke hentet. Be brukeren laste opp/hente PDF-en før endelig føring.",
        )
    ]


def has_concrete_vat_lines(payload: dict[str, Any]) -> bool:
    for line in payload.get("lines") or []:
        if line.get("vatType") and line.get("vatType") != "må avklares":
            return True
        if line.get("vat") is not None:
            return True
    return False


def source_status(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "receiptSource",
        "sourceLimitations",
        "bankAccountNumber",
        "inboxDocumentId",
        "sourceDocumentId",
    ]
    return {key: candidate.get(key) for key in keys if candidate.get(key) is not None}


def duplicate_status(
    payload: dict[str, Any],
    *,
    existing_purchases: list[dict[str, Any]],
    duplicate_days: int,
) -> dict[str, Any]:
    candidate_identifier = str(payload.get("identifier") or "").strip().lower()
    candidate_date = parse_date(payload.get("date"))
    candidate_total = payload_total_cents(payload)
    candidate_supplier_id = payload.get("supplierId")
    matches: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    for purchase in existing_purchases:
        summary = summarize_purchase(purchase)
        reasons: list[str] = []
        severity = "warning"
        identifier = str(summary.get("identifier") or "").strip().lower()
        if candidate_identifier and identifier and candidate_identifier == identifier:
            reasons.append("same identifier")
            severity = "error"
        if candidate_total is not None and summary.get("amount_cents") == candidate_total:
            reasons.append("same amount")
        purchase_date = parse_date(summary.get("date"))
        if candidate_date and purchase_date and abs((candidate_date - purchase_date).days) <= duplicate_days:
            reasons.append("near date")
        if candidate_supplier_id and purchase.get("supplierId") == candidate_supplier_id:
            reasons.append("same supplier")
        if severity == "error" or ("same amount" in reasons and "near date" in reasons):
            match = public_duplicate_match(summary, reasons, severity)
            matches.append(match)
            issues.append(
                {
                    "severity": severity,
                    "code": "duplicate_purchase" if severity == "error" else "possible_duplicate",
                    "message": duplicate_message(match),
                }
            )

    if not existing_purchases:
        status = "not_checked"
    elif any(match["severity"] == "error" for match in matches):
        status = "duplicate"
    elif matches:
        status = "possible"
    else:
        status = "none"
    return {"status": status, "matches": matches, "issues": issues}


def payload_total_cents(payload: dict[str, Any]) -> int | None:
    lines = payload.get("lines")
    if not isinstance(lines, list) or not lines:
        return None
    total = 0
    for line in lines:
        if not isinstance(line.get("netPrice"), int) or not isinstance(line.get("vat"), int):
            return None
        total += line["netPrice"] + line["vat"]
    return total


def duplicate_message(match: dict[str, Any]) -> str:
    identifier = f" {match['identifier']}" if match.get("identifier") else ""
    return f"Mulig eksisterende Fiken-kjøp{identifier} ({match.get('date')}, {match.get('gross_amount')})."


def public_duplicate_match(summary: dict[str, Any], reasons: list[str], severity: str) -> dict[str, Any]:
    return {
        "severity": severity,
        "purchaseId": summary.get("purchaseId"),
        "date": summary.get("date"),
        "identifier": summary.get("identifier"),
        "supplier": summary.get("supplier"),
        "kind": summary.get("kind"),
        "gross_amount": summary.get("gross_amount") or summary.get("amount"),
        "payment_account": summary.get("payment_account"),
        "attachment_count": summary.get("attachment_count"),
        "reasons": reasons,
    }


def duplicate_date_window(value: Any, days: int) -> tuple[str, str] | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    return ((parsed - timedelta(days=days)).isoformat(), (parsed + timedelta(days=days)).isoformat())


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


def info(code: str, message: str) -> dict[str, str]:
    return {"severity": "info", "code": code, "message": message}
