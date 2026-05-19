from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def default_start_date(today: date | None = None, days: int = 45) -> str:
    today = today or date.today()
    return (today - timedelta(days=days)).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def reconcile_card_purchases(
    *,
    folio_events: list[dict[str, Any]],
    purchases: list[dict[str, Any]],
    purchase_drafts: list[dict[str, Any]],
    inbox_documents: list[dict[str, Any]],
    bank_accounts: list[dict[str, Any]],
    start_date: str,
    end_date: str,
    max_days_diff: int = 3,
    only_needs_action: bool = False,
) -> dict[str, Any]:
    account_codes = account_codes_by_number(bank_accounts)
    purchase_summaries = [summarize_purchase(purchase) for purchase in purchases]
    draft_summaries = [summarize_draft(draft) for draft in purchase_drafts]
    inbox_summaries = [summarize_inbox(document) for document in inbox_documents]

    event_summaries = [
        summarize_card_event(event, account_codes)
        for event in folio_events
        if event.get("cardAuthorization")
    ]

    items: list[dict[str, Any]] = []
    for event_summary in event_summaries:
        purchase_matches = best_matches(event_summary, purchase_summaries, max_days_diff=max_days_diff)
        draft_matches = best_matches(event_summary, draft_summaries, max_days_diff=max_days_diff)
        inbox_matches = best_inbox_matches(event_summary, inbox_summaries)
        item = classify_event(
            event_summary,
            purchase_matches,
            draft_matches,
            inbox_matches,
            peer_events=event_summaries,
            max_days_diff=max_days_diff,
        )
        if not only_needs_action or item["needs_action"]:
            items.append(item)

    counts: dict[str, int] = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1

    return {
        "ok": True,
        "start_date": start_date,
        "end_date": end_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "items": items,
    }


def summarize_card_event(event: dict[str, Any], account_codes: dict[str, str]) -> dict[str, Any]:
    authorization = event.get("cardAuthorization") or {}
    transactions = event.get("transactions") or []
    first_transaction = transactions[0] if transactions else {}
    amount = event.get("amount") or {}
    transaction_amount = first_transaction.get("transactionAmount") or {}
    account_number = (
        (first_transaction.get("debtor") or {}).get("accountNumber")
        or (first_transaction.get("creditor") or {}).get("accountNumber")
        or ""
    )
    merchant = str(authorization.get("merchantName") or "")
    description = str(first_transaction.get("description") or "")
    event_time = str(event.get("time") or "")
    event_date = parse_date(first_transaction.get("bookingDate")) or parse_datetime_date(event_time)
    nok_amount = cents_from_amount(transaction_amount.get("amount") or amount.get("amount"))
    attachment_count = len(event.get("attachments") or [])
    transaction_ids = [transaction.get("id") for transaction in transactions if transaction.get("id")]

    return {
        "id": event.get("id"),
        "time": event_time,
        "date": event_date.isoformat() if event_date else None,
        "booking_date": first_transaction.get("bookingDate"),
        "merchant": merchant,
        "description": description,
        "amount": cents_to_float(nok_amount),
        "amount_cents": nok_amount,
        "currency": amount.get("currency") or transaction_amount.get("currency"),
        "complete": bool(event.get("complete")),
        "attachment_count": attachment_count,
        "transaction_ids": transaction_ids,
        "account_number": account_number,
        "account_code": account_codes.get(account_number),
        "tokens": tokens(" ".join([merchant, description])),
    }


def summarize_purchase(purchase: dict[str, Any]) -> dict[str, Any]:
    supplier = purchase.get("supplier") or {}
    payments = purchase.get("payments") or []
    lines = purchase.get("lines") or []
    line_summaries = summarize_lines(lines)
    amount_cents = sum(payment_amount_cents(payment) for payment in payments)
    text = " ".join(
        str(value or "")
        for value in [
            purchase.get("identifier"),
            supplier.get("name"),
            *(line.get("description") for line in lines),
        ]
    )
    return {
        "type": "purchase",
        "purchaseId": purchase.get("purchaseId"),
        "transactionId": purchase.get("transactionId"),
        "kind": purchase.get("kind"),
        "date": purchase.get("date"),
        "identifier": purchase.get("identifier"),
        "supplier": supplier.get("name"),
        "paid": purchase.get("paid"),
        "settled": purchase.get("settled"),
        "currency": purchase.get("currency"),
        "line_description": line_summaries[0].get("description") if line_summaries else None,
        "account": first_present(line_summaries, "account"),
        "vat_type": first_present(line_summaries, "vat_type"),
        "net_amount": cents_to_float(sum(int(line.get("net_amount_cents") or 0) for line in line_summaries)),
        "vat_amount": cents_to_float(sum(int(line.get("vat_amount_cents") or 0) for line in line_summaries)),
        "gross_amount": cents_to_float(sum(int(line.get("gross_amount_cents") or 0) for line in line_summaries)),
        "lines": public_lines(line_summaries),
        "amount": cents_to_float(amount_cents),
        "amount_cents": amount_cents,
        "payment_account": payments[0].get("account") if payments else None,
        "payment_amount": cents_to_float(amount_cents),
        "attachment_count": len(purchase.get("purchaseAttachments") or []),
        "has_attachment": len(purchase.get("purchaseAttachments") or []) > 0,
        "tokens": tokens(text),
    }


def summarize_draft(draft: dict[str, Any]) -> dict[str, Any]:
    payments = draft.get("payments") or []
    lines = draft.get("lines") or []
    line_summaries = summarize_lines(lines)
    amount_cents = sum(payment_amount_cents(payment) for payment in payments)
    text = " ".join(
        str(value or "")
        for value in [
            draft.get("draftId"),
            draft.get("uuid"),
            *(attachment.get("filename") or attachment.get("name") for attachment in draft.get("attachments") or []),
        ]
    )
    return {
        "type": "purchase_draft",
        "draftId": draft.get("draftId"),
        "uuid": draft.get("uuid"),
        "kind": draft.get("kind"),
        "date": draft.get("invoiceIssueDate"),
        "amount": cents_to_float(amount_cents),
        "amount_cents": amount_cents,
        "currency": draft.get("currency"),
        "payment_account": payments[0].get("account") if payments else None,
        "payment_amount": cents_to_float(amount_cents),
        "attachment_count": len(draft.get("attachments") or []),
        "has_attachment": len(draft.get("attachments") or []) > 0,
        "line_description": line_summaries[0].get("description") if line_summaries else None,
        "account": first_present(line_summaries, "account"),
        "vat_type": first_present(line_summaries, "vat_type"),
        "net_amount": cents_to_float(sum(int(line.get("net_amount_cents") or 0) for line in line_summaries)),
        "vat_amount": cents_to_float(sum(int(line.get("vat_amount_cents") or 0) for line in line_summaries)),
        "gross_amount": cents_to_float(sum(int(line.get("gross_amount_cents") or 0) for line in line_summaries)),
        "lines": public_lines(line_summaries),
        "tokens": tokens(text),
    }


def summarize_inbox(document: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        str(value or "")
        for value in [
            document.get("name"),
            document.get("filename"),
            document.get("description"),
        ]
    )
    return {
        "type": "inbox",
        "documentId": document.get("documentId"),
        "createdAt": document.get("createdAt"),
        "name": document.get("name"),
        "filename": document.get("filename"),
        "description": document.get("description"),
        "documentUrl": document.get("documentUrl"),
        "documentUrlWithFikenNormalUserCredentials": document.get("documentUrlWithFikenNormalUserCredentials"),
        "tokens": tokens(text),
    }


def classify_event(
    event: dict[str, Any],
    purchase_matches: list[dict[str, Any]],
    draft_matches: list[dict[str, Any]],
    inbox_matches: list[dict[str, Any]],
    *,
    peer_events: list[dict[str, Any]] | None = None,
    max_days_diff: int = 3,
) -> dict[str, Any]:
    high_purchase_matches = [match for match in purchase_matches if match["score"] >= 80]
    high_draft_matches = [match for match in draft_matches if match["score"] >= 80]

    if len(high_purchase_matches) > 1:
        if booked_cluster_is_balanced(
            high_purchase_matches,
            peer_events or [event],
            max_days_diff=max_days_diff,
        ):
            status = "booked"
            action = "Ingen handling."
            needs_action = False
        else:
            status = "possible_duplicate"
            action = "Kontroller flere mulige Fiken-kjøp før du gjør noe."
            needs_action = True
    elif high_purchase_matches:
        match = high_purchase_matches[0]
        if match.get("attachment_count", 0) > 0:
            status = "booked"
            action = "Ingen handling."
            needs_action = False
        else:
            status = "booked_missing_attachment"
            action = "Finn eller last opp bilag på eksisterende Fiken-kjøp."
            needs_action = True
    elif high_draft_matches:
        status = "purchase_draft"
        action = "Kontroller og bokfør eksisterende kjøpsutkast i Fiken."
        needs_action = True
    elif inbox_matches and has_credible_booked_purchase_match(event, purchase_matches):
        status = "booked"
        action = "Ingen handling."
        needs_action = False
    elif inbox_matches and event["attachment_count"] == 0:
        status = "inbox_possible_match"
        action = "Koble inbox-bilag til kjøp eller bokfør fra inbox."
        needs_action = True
    elif event["attachment_count"] > 0:
        status = "ready_to_book"
        action = "Bilag finnes i Folio. Kontroller MVA og før kjøpet."
        needs_action = True
    else:
        status = "missing_receipt"
        action = "Søk etter kvittering eller be om bilag før bokføring."
        needs_action = True

    return {
        "status": status,
        "needs_action": needs_action,
        "action": action,
        "event": public_event(event),
        "purchase_matches": public_matches(purchase_matches),
        "draft_matches": public_matches(draft_matches),
        "inbox_matches": public_matches(inbox_matches),
        "suggested": suggest_next_step(event),
    }


def best_matches(
    event: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    max_days_diff: int,
) -> list[dict[str, Any]]:
    matches = []
    for candidate in candidates:
        score, reasons = match_score(event, candidate, max_days_diff=max_days_diff)
        if score <= 0:
            continue
        match = {key: value for key, value in candidate.items() if key != "tokens"}
        match["score"] = score
        match["reasons"] = reasons
        matches.append(match)
    return sorted(matches, key=lambda item: item["score"], reverse=True)[:5]


def best_inbox_matches(event: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    event_tokens = set(event["tokens"])
    for candidate in candidates:
        overlap = event_tokens & set(candidate["tokens"])
        useful_overlap = sorted(token for token in overlap if len(token) >= 4)
        if not useful_overlap:
            continue
        match = {key: value for key, value in candidate.items() if key != "tokens"}
        match["score"] = min(70, 20 + 10 * len(useful_overlap))
        match["reasons"] = [f"token overlap: {', '.join(useful_overlap[:5])}"]
        matches.append(match)
    return sorted(matches, key=lambda item: item["score"], reverse=True)[:5]


def match_score(event: dict[str, Any], candidate: dict[str, Any], *, max_days_diff: int) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    event_amount = event.get("amount_cents")
    candidate_amount = candidate.get("amount_cents")
    if event_amount and candidate_amount:
        diff = abs(int(event_amount) - int(candidate_amount))
        if diff == 0:
            score += 60
            reasons.append("exact amount")
        elif diff <= 100:
            score += 45
            reasons.append("amount within 1 NOK")
        else:
            return 0, []

    days = date_diff(event.get("date"), candidate.get("date"))
    if days is not None:
        if days == 0:
            score += 25
            reasons.append("same date")
        elif days <= max_days_diff:
            score += max(5, 20 - days * 5)
            reasons.append(f"date within {days} days")
        else:
            score -= 20

    if event.get("account_code") and event.get("account_code") == candidate.get("payment_account"):
        score += 10
        reasons.append("same payment account")

    overlap = set(event["tokens"]) & set(candidate["tokens"])
    useful_overlap = sorted(token for token in overlap if len(token) >= 4)
    if useful_overlap:
        score += min(20, len(useful_overlap) * 8)
        reasons.append(f"token overlap: {', '.join(useful_overlap[:5])}")

    return score, reasons


def booked_cluster_is_balanced(
    purchase_matches: list[dict[str, Any]],
    peer_events: list[dict[str, Any]],
    *,
    max_days_diff: int,
) -> bool:
    if not purchase_matches:
        return False
    if any(int(match.get("attachment_count") or 0) <= 0 for match in purchase_matches):
        return False

    matching_events = [
        event
        for event in peer_events
        if any(event_purchase_shape_matches(event, purchase, max_days_diff=max_days_diff) for purchase in purchase_matches)
    ]
    return len(matching_events) >= len(purchase_matches)


def event_purchase_shape_matches(
    event: dict[str, Any],
    purchase: dict[str, Any],
    *,
    max_days_diff: int,
) -> bool:
    event_amount = event.get("amount_cents")
    purchase_amount = purchase.get("amount_cents")
    if not event_amount or not purchase_amount:
        return False
    if abs(int(event_amount) - int(purchase_amount)) > 100:
        return False

    days = date_diff(event.get("date"), purchase.get("date"))
    if days is not None and days > max_days_diff:
        return False

    if event.get("account_code") and purchase.get("payment_account"):
        return event.get("account_code") == purchase.get("payment_account")
    return True


def has_credible_booked_purchase_match(event: dict[str, Any], purchase_matches: list[dict[str, Any]]) -> bool:
    for match in purchase_matches:
        if int(match.get("attachment_count") or 0) <= 0:
            continue
        if "exact amount" not in match.get("reasons", []):
            continue
        if "same payment account" not in match.get("reasons", []):
            continue
        if not any(str(reason).startswith("token overlap:") for reason in match.get("reasons", [])):
            continue
        days = date_diff(event.get("date"), match.get("date"))
        if days is not None and days <= 10:
            return True
    return False


def suggest_next_step(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "gmail_query": gmail_query(event),
        "note": "Bruk bilaget og Fikens kontohjelp for konto/MVA. Ikke bokfør uten bilag hvis grunnlaget er uklart.",
    }


def gmail_query(event: dict[str, Any]) -> str:
    parts = [
        event.get("merchant"),
        event.get("amount"),
        event.get("date"),
    ]
    merchant_tokens = [token for token in event.get("tokens", []) if len(token) >= 5][:4]
    quoted = [quote_query_part(part) for part in [*parts, *merchant_tokens] if part]
    return "-in:spam -in:trash newer_than:120d (" + " OR ".join(quoted) + ")"


def public_event(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key not in {"tokens", "amount_cents"}}


def public_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in match.items() if key not in {"amount_cents"}} for match in matches]


def summarize_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for line in lines:
        net_cents = int(line.get("netPrice") or line.get("netAmount") or 0)
        vat_cents = int(line.get("vat") or line.get("vatAmount") or 0)
        gross_cents = int(line.get("grossAmount") or line.get("grossPrice") or net_cents + vat_cents)
        summaries.append(
            {
                "description": line.get("description"),
                "account": line.get("account") or line.get("incomeAccount"),
                "vat_type": line.get("vatType"),
                "net_amount": cents_to_float(net_cents),
                "net_amount_cents": net_cents,
                "vat_amount": cents_to_float(vat_cents),
                "vat_amount_cents": vat_cents,
                "gross_amount": cents_to_float(gross_cents),
                "gross_amount_cents": gross_cents,
            }
        )
    return summaries


def public_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in line.items()
            if key not in {"net_amount_cents", "vat_amount_cents", "gross_amount_cents"}
        }
        for line in lines
    ]


def first_present(items: list[dict[str, Any]], key: str) -> Any:
    values = [item.get(key) for item in items if item.get(key)]
    if not values:
        return None
    first = values[0]
    if all(value == first for value in values):
        return first
    return "flere"


def account_codes_by_number(bank_accounts: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(account.get("bankAccountNumber")): str(account.get("accountCode"))
        for account in bank_accounts
        if account.get("bankAccountNumber") and account.get("accountCode")
    }


def payment_amount_cents(payment: dict[str, Any]) -> int:
    return int(payment.get("amountInNok") or payment.get("amount") or 0)


def cents_from_amount(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int((abs(Decimal(str(value))) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return 0


def cents_to_float(value: int) -> float:
    return float(Decimal(value) / Decimal(100))


def parse_datetime_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def date_diff(first: Any, second: Any) -> int | None:
    first_date = parse_date(first)
    second_date = parse_date(second)
    if not first_date or not second_date:
        return None
    return abs((first_date - second_date).days)


def tokens(text: str) -> list[str]:
    return sorted(set(re.findall(r"[a-z0-9æøå]+", text.lower())))


def quote_query_part(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    return '"' + text.replace('"', '\\"') + '"'
