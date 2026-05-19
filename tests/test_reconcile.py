from __future__ import annotations

from datetime import date

from regnskap_agent.reconcile import default_start_date, reconcile_card_purchases


def card_event(
    *,
    merchant: str = "Example SaaS",
    amount: float = 490.0,
    event_id: str = "evt_1",
    booking_date: str = "2026-05-18",
    attachments: int = 0,
) -> dict:
    return {
        "id": event_id,
        "time": booking_date + "T12:00:00Z",
        "amount": {"amount": amount, "currency": "NOK"},
        "complete": True,
        "attachments": [{"id": f"att_{index}"} for index in range(attachments)],
        "cardAuthorization": {"merchantName": merchant},
        "transactions": [
            {
                "id": "txn_1",
                "bookingDate": booking_date,
                "description": merchant,
                "transactionAmount": {"amount": amount, "currency": "NOK"},
                "debtor": {"accountNumber": "15031234567"},
            }
        ],
    }


def purchase(*, attachments: int = 1, purchase_id: int = 42, identifier: str = "Example SaaS receipt") -> dict:
    return {
        "purchaseId": purchase_id,
        "transactionId": 84,
        "kind": "cash_purchase",
        "date": "2026-05-18",
        "identifier": identifier,
        "supplier": {"name": "Example SaaS"},
        "paid": True,
        "settled": True,
        "currency": "NOK",
        "payments": [{"amountInNok": 49000, "account": "1920"}],
        "lines": [
            {
                "description": "Example SaaS",
                "netPrice": 39200,
                "vat": 9800,
                "account": "6553",
                "vatType": "HIGH",
            }
        ],
        "purchaseAttachments": [{"identifier": "receipt.pdf"} for _ in range(attachments)],
    }


def inbox_document(*, name: str = "Example SaaS receipt.pdf", description: str = "Epost-emne: Example SaaS receipt") -> dict:
    return {
        "documentId": 100,
        "createdAt": "2026-05-18T12:00:00+02:00",
        "name": name,
        "filename": name,
        "description": description,
        "documentUrl": f"https://api.fiken.no/api/v2/files/{name}",
        "documentUrlWithFikenNormalUserCredentials": f"https://fiken.no/filer/{name}",
    }


def reconcile(**overrides):
    payload = {
        "folio_events": [card_event()],
        "purchases": [],
        "purchase_drafts": [],
        "inbox_documents": [],
        "bank_accounts": [{"bankAccountNumber": "15031234567", "accountCode": "1920"}],
        "start_date": "2026-05-01",
        "end_date": "2026-05-19",
    }
    payload.update(overrides)
    return reconcile_card_purchases(**payload)


def test_default_start_date() -> None:
    assert default_start_date(date(2026, 5, 19), days=45) == "2026-04-04"


def test_booked_purchase_with_attachment_needs_no_action() -> None:
    report = reconcile(purchases=[purchase()])
    assert report["counts"] == {"booked": 1}
    item = report["items"][0]
    assert item["needs_action"] is False
    match = item["purchase_matches"][0]
    assert match["purchaseId"] == 42
    assert match["kind"] == "cash_purchase"
    assert match["identifier"] == "Example SaaS receipt"
    assert match["account"] == "6553"
    assert match["vat_type"] == "HIGH"
    assert match["net_amount"] == 392.0
    assert match["vat_amount"] == 98.0
    assert match["gross_amount"] == 490.0
    assert match["payment_account"] == "1920"
    assert match["has_attachment"] is True
    assert match["lines"][0]["account"] == "6553"


def test_booked_purchase_without_attachment_needs_action() -> None:
    report = reconcile(purchases=[purchase(attachments=0)])
    assert report["counts"] == {"booked_missing_attachment": 1}
    assert report["items"][0]["needs_action"] is True


def test_missing_receipt_includes_gmail_query_but_no_hardcoded_account_guess() -> None:
    report = reconcile()
    item = report["items"][0]
    assert item["status"] == "missing_receipt"
    assert '"Example SaaS"' in item["suggested"]["gmail_query"]
    assert "account" not in item["suggested"]
    assert "account_name" not in item["suggested"]


def test_inbox_match_includes_document_fields() -> None:
    report = reconcile(
        inbox_documents=[
            inbox_document()
        ]
    )
    item = report["items"][0]
    assert item["status"] == "inbox_possible_match"
    match = item["inbox_matches"][0]
    assert match["documentId"] == 100
    assert match["name"] == "Example SaaS receipt.pdf"
    assert match["description"] == "Epost-emne: Example SaaS receipt"
    assert match["documentUrl"].startswith("https://api.fiken.no")


def test_only_needs_action_filters_booked_items() -> None:
    report = reconcile(purchases=[purchase()], only_needs_action=True)
    assert report["counts"] == {}
    assert report["items"] == []


def test_possible_duplicate_contains_enough_purchase_detail() -> None:
    report = reconcile(
        purchases=[
            purchase(purchase_id=42, identifier="receipt-1"),
            purchase(purchase_id=43, identifier="receipt-2"),
        ]
    )
    item = report["items"][0]
    assert item["status"] == "possible_duplicate"
    assert [match["identifier"] for match in item["purchase_matches"]] == ["receipt-1", "receipt-2"]
    assert all(match["account"] == "6553" for match in item["purchase_matches"])
    assert all(match["vat_type"] == "HIGH" for match in item["purchase_matches"])


def test_only_needs_action_filters_balanced_booked_duplicate_cluster() -> None:
    report = reconcile(
        folio_events=[
            card_event(event_id="evt_1"),
            card_event(event_id="evt_2"),
        ],
        purchases=[
            purchase(purchase_id=42, identifier="receipt-1"),
            purchase(purchase_id=43, identifier="receipt-2"),
        ],
        only_needs_action=True,
    )
    assert report["counts"] == {}
    assert report["items"] == []


def test_unbalanced_duplicate_cluster_still_needs_action() -> None:
    report = reconcile(
        folio_events=[
            card_event(event_id="evt_1"),
        ],
        purchases=[
            purchase(purchase_id=42, identifier="receipt-1"),
            purchase(purchase_id=43, identifier="receipt-2"),
        ],
        only_needs_action=True,
    )
    assert report["counts"] == {"possible_duplicate": 1}
    assert report["items"][0]["status"] == "possible_duplicate"


def test_only_needs_action_filters_credible_booked_match_with_irrelevant_inbox_hit() -> None:
    report = reconcile(
        folio_events=[
            card_event(merchant="CLAUDE.AI SUBSCRIPTION", amount=1998.16, booking_date="2026-04-07")
        ],
        purchases=[
            {
                **purchase(attachments=3, identifier="HBPQGZAW-0006"),
                "date": "2026-04-02",
                "supplier": {"name": "Anthropic, PBC"},
                "payments": [{"amountInNok": 199816, "account": "1920"}],
                "lines": [
                    {
                        "description": "Claude Max",
                        "netPrice": 199816,
                        "vat": 0,
                        "account": "6553",
                        "vatType": "HIGH_FOREIGN_SERVICE_DEDUCTIBLE",
                    }
                ],
            }
        ],
        inbox_documents=[
            inbox_document(name="Receipt-OpenAI.pdf", description="Epost-emne: Claude subscription")
        ],
        only_needs_action=True,
    )
    assert report["counts"] == {}
    assert report["items"] == []


def test_old_monthly_purchase_match_does_not_hide_current_inbox_hit() -> None:
    report = reconcile(
        folio_events=[
            card_event(merchant="Microsoft-G156241420", amount=134.10, booking_date="2026-05-05")
        ],
        purchases=[
            {
                **purchase(attachments=2, identifier="NO-TI2600108103"),
                "date": "2026-04-05",
                "supplier": {"name": "Microsoft Norge AS"},
                "payments": [{"amountInNok": 13410, "account": "1920"}],
                "lines": [
                    {
                        "description": "Microsoft 365 Business",
                        "netPrice": 10728,
                        "vat": 2682,
                        "account": "6553",
                        "vatType": "HIGH",
                    }
                ],
            }
        ],
        inbox_documents=[
            inbox_document(name="microsoft.pdf", description="Epost-emne: Microsoft invoice")
        ],
        only_needs_action=True,
    )
    assert report["counts"] == {"inbox_possible_match": 1}
