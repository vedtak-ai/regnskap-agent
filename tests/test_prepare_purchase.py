from __future__ import annotations

from pathlib import Path

from regnskap_agent.purchase_prepare import prepare_purchase


def test_prepare_purchase_computes_high_vat(tmp_path: Path) -> None:
    receipt = tmp_path / "microsoft.pdf"
    receipt.write_bytes(b"%PDF-1.4\n")
    result = prepare_purchase(
        {
            "identifier": "NO-TI2600142222",
            "date": "2026-05-05",
            "kind": "supplier",
            "supplierId": 11785380966,
            "paid": True,
            "paymentAccount": "1920:10003",
            "paymentDate": "2026-05-05",
            "receiptSource": "leverandør-PDF",
            "attachments": [str(receipt)],
            "lines": [
                {
                    "description": "Microsoft 365 Business Basic",
                    "account": "6553",
                    "vatType": "HIGH",
                    "netPrice": 10728,
                }
            ],
        }
    )

    assert result["status"] == "ready"
    assert result["purchase_payload"]["lines"][0]["vat"] == 2682
    assert result["contact"]["status"] == "existing"
    assert result["attachments"][0]["source"] == "leverandør-PDF"


def test_prepare_purchase_blocks_wrong_high_vat(tmp_path: Path) -> None:
    receipt = tmp_path / "domeneshop.pdf"
    receipt.write_bytes(b"%PDF-1.4\n")
    result = prepare_purchase(
        {
            "identifier": "1166245",
            "date": "2026-05-19",
            "kind": "supplier",
            "supplierId": 12145324048,
            "paid": True,
            "paymentAccount": "1920:10003",
            "paymentDate": "2026-05-19",
            "receiptSource": "leverandør-PDF",
            "attachments": [str(receipt)],
            "lines": [
                {
                    "description": "Domeneregistrering",
                    "account": "7601",
                    "vatType": "HIGH",
                    "netPrice": 3920,
                    "vat": 900,
                }
            ],
        }
    )

    assert result["status"] == "blocked"
    assert any(issue["code"] == "vat_mismatch" for issue in result["issues"])


def test_prepare_purchase_accepts_foreign_service_with_zero_vat(tmp_path: Path) -> None:
    receipt = tmp_path / "openai.pdf"
    receipt.write_bytes(b"%PDF-1.4\n")
    result = prepare_purchase(
        {
            "identifier": "GIIAHOCL-0002",
            "date": "2026-04-27",
            "kind": "cash_purchase",
            "paid": True,
            "paymentAccount": "1920:10003",
            "paymentDate": "2026-04-27",
            "receiptSource": "leverandør-PDF",
            "attachments": [str(receipt)],
            "lines": [
                {
                    "description": "ChatGPT Team",
                    "account": "6553",
                    "vatType": "HIGH_FOREIGN_SERVICE_DEDUCTIBLE",
                    "netPrice": 95200,
                }
            ],
        }
    )

    assert result["status"] == "ready"
    assert result["purchase_payload"]["lines"][0]["vat"] == 0
    assert result["contact"]["status"] == "not_required"


def test_prepare_purchase_allows_email_receipt_documented_as_pdf(tmp_path: Path) -> None:
    receipt = tmp_path / "airbnb-HM5YFQFKBR.pdf"
    receipt.write_bytes(b"%PDF-1.4\n")
    result = prepare_purchase(
        {
            "identifier": "HM5YFQFKBR",
            "date": "2026-05-13",
            "kind": "cash_purchase",
            "paid": True,
            "paymentAccount": "1920:10003",
            "paymentDate": "2026-05-13",
            "receiptSource": "e-postkvittering dokumentert som PDF",
            "attachments": [str(receipt)],
            "lines": [
                {
                    "description": "Airbnb overnatting",
                    "account": "7140",
                    "vatType": "NONE",
                    "netPrice": 178824,
                }
            ],
        }
    )

    assert result["status"] == "ready"
    assert result["purchase_payload"]["lines"][0]["vat"] == 0
    assert result["attachments"][0]["source"] == "e-postkvittering dokumentert som PDF"


def test_prepare_purchase_ehf_notice_blocks_concrete_vat_without_original_document() -> None:
    result = prepare_purchase(
        {
            "identifier": "14777",
            "date": "2026-05-19",
            "dueDate": "2026-06-18",
            "kind": "supplier",
            "paid": False,
            "currency": "NOK",
            "kid": "0000001477710",
            "bankAccountNumber": "15200175686",
            "receiptSource": "Fiken EHF-varsel",
            "sourceLimitations": "Original EHF/PDF er ikke hentet via API.",
            "supplier": {
                "name": "Z Event AS",
                "organizationNumber": "992324821",
                "supplier": True,
                "customer": False,
            },
            "lines": [
                {
                    "description": "Digitaliseringskonferansen 2026",
                    "account": "6860",
                    "vatType": "HIGH",
                    "netPrice": 1548000,
                }
            ],
        }
    )

    assert result["status"] == "blocked"
    assert result["purchase_payload"]["identifier"] == "14777"
    assert result["purchase_payload"]["dueDate"] == "2026-06-18"
    assert result["purchase_payload"]["kid"] == "0000001477710"
    assert result["purchase_payload"]["lines"][0]["vat"] == 387000
    assert result["source"]["receiptSource"] == "Fiken EHF-varsel"
    assert result["source"]["bankAccountNumber"] == "15200175686"
    assert any(issue["code"] == "ehf_notice_requires_original" for issue in result["issues"])


def test_prepare_purchase_ehf_notice_can_wait_for_original_without_vat_lines() -> None:
    result = prepare_purchase(
        {
            "identifier": "14777",
            "date": "2026-05-19",
            "dueDate": "2026-06-18",
            "kind": "supplier",
            "paid": False,
            "currency": "NOK",
            "kid": "0000001477710",
            "bankAccountNumber": "15200175686",
            "receiptSource": "Fiken EHF-varsel",
            "sourceLimitations": "Original EHF/PDF er ikke hentet via API.",
            "supplier": {
                "name": "Z Event AS",
                "organizationNumber": "992324821",
                "supplier": True,
                "customer": False,
            },
            "lines": [
                {
                    "description": "Digitaliseringskonferansen 2026",
                    "account": "må avklares",
                    "vatType": "må avklares",
                    "netPrice": 1935000,
                }
            ],
        }
    )

    assert result["status"] == "needs_clarification"
    assert any(issue["code"] == "ehf_notice_without_original" for issue in result["issues"])
    assert not any(issue["severity"] == "error" for issue in result["issues"])


def test_prepare_purchase_blocks_supplier_without_contact() -> None:
    result = prepare_purchase(
        {
            "identifier": "123",
            "date": "2026-05-19",
            "kind": "supplier",
            "paid": False,
            "receiptSource": "Fiken inbox",
            "lines": [
                {
                    "description": "Ukjent leverandør",
                    "account": "6553",
                    "vatType": "HIGH",
                    "netPrice": 10000,
                }
            ],
        }
    )

    assert result["status"] == "blocked"
    assert result["contact"]["status"] == "missing"
    assert any(issue["code"] == "missing_supplier" for issue in result["issues"])


def test_prepare_purchase_duplicate_identifier_blocks(tmp_path: Path) -> None:
    receipt = tmp_path / "microsoft.pdf"
    receipt.write_bytes(b"%PDF-1.4\n")
    result = prepare_purchase(
        {
            "identifier": "NO-TI2600142222",
            "date": "2026-05-05",
            "kind": "supplier",
            "supplierId": 11785380966,
            "paid": True,
            "paymentAccount": "1920:10003",
            "paymentDate": "2026-05-05",
            "receiptSource": "leverandør-PDF",
            "attachments": [str(receipt)],
            "lines": [
                {
                    "description": "Microsoft 365 Business Basic",
                    "account": "6553",
                    "vatType": "HIGH",
                    "netPrice": 10728,
                }
            ],
        },
        existing_purchases=[
            {
                "purchaseId": 12145867216,
                "identifier": "NO-TI2600142222",
                "date": "2026-05-05",
                "kind": "supplier",
                "supplierId": 11785380966,
                "supplier": {"name": "Microsoft Norge AS"},
                "payments": [{"account": "1920:10003", "amount": 13410}],
                "purchaseAttachments": [{}],
                "lines": [
                    {
                        "description": "Microsoft 365 Business Basic",
                        "account": "6553",
                        "vatType": "HIGH",
                        "netPrice": 10728,
                        "vat": 2682,
                    }
                ],
            }
        ],
    )

    assert result["status"] == "blocked"
    assert result["duplicates"]["status"] == "duplicate"
    assert result["duplicates"]["matches"][0]["purchaseId"] == 12145867216


def test_prepare_purchase_same_amount_near_date_warns(tmp_path: Path) -> None:
    receipt = tmp_path / "bus.pdf"
    receipt.write_bytes(b"%PDF-1.4\n")
    result = prepare_purchase(
        {
            "identifier": "2665750",
            "date": "2026-05-12",
            "kind": "cash_purchase",
            "paid": True,
            "paymentAccount": "1920:10003",
            "paymentDate": "2026-05-12",
            "receiptSource": "leverandør-PDF",
            "attachments": [str(receipt)],
            "lines": [
                {
                    "description": "Værnesekspressen",
                    "account": "7140",
                    "vatType": "LOW",
                    "netPrice": 18661,
                    "vat": 2239,
                }
            ],
        },
        existing_purchases=[
            {
                "purchaseId": 12097232162,
                "identifier": "2665742",
                "date": "2026-05-12",
                "kind": "cash_purchase",
                "payments": [{"account": "1920:10003", "amount": 20900}],
                "purchaseAttachments": [{}],
                "lines": [
                    {
                        "description": "Værnesekspressen",
                        "account": "7140",
                        "vatType": "LOW",
                        "netPrice": 18661,
                        "vat": 2239,
                    }
                ],
            }
        ],
    )

    assert result["status"] == "needs_clarification"
    assert result["duplicates"]["status"] == "possible"
    assert any(issue["code"] == "possible_duplicate" for issue in result["issues"])
