from __future__ import annotations

from pathlib import Path

from regnskap_agent.provider_prepare import (
    prepare_salary_transaction,
    prepare_unimicro_journal_entry,
    prepare_unimicro_supplier_invoice,
)


def test_prepare_salary_transaction_normalizes_period_and_warns_about_payroll_scope() -> None:
    result = prepare_salary_transaction(
        {
            "date": "2026-06-30",
            "employeeId": 42,
            "salaryTypeId": 101,
            "payload": {"date": "2026-06-30", "payslips": [{"employee": {"id": 42}}]},
        }
    )

    assert result["status"] == "ready"
    assert result["salary_payload"]["year"] == 2026
    assert result["salary_payload"]["month"] == 6
    assert "ikke en komplett lønnskjøring" in result["limitations"][0]


def test_prepare_salary_transaction_blocks_missing_period() -> None:
    result = prepare_salary_transaction({"employeeId": 42, "salaryTypeId": 101})

    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "missing_salary_period"


def test_prepare_unimicro_journal_entry_resolves_account_and_vat_ids() -> None:
    result = prepare_unimicro_journal_entry(
        {
            "draftLines": [
                {
                    "accountNumber": 6860,
                    "vatCode": "1",
                    "Amount": 1000.0,
                    "Description": "Kurs",
                    "FinancialDate": "2026-06-01",
                }
            ],
            "fileIds": [55],
        },
        accounts=[{"ID": 359, "AccountNumber": 6860, "AccountName": "Møter og kurs"}],
        vat_types=[{"ID": 2, "VatCode": "1", "VatPercent": 25.0}],
    )

    assert result["status"] == "ready"
    line = result["journal_entry_payload"][0]["DraftLines"][0]
    assert line["AccountID"] == 359
    assert line["VatTypeID"] == 2
    assert result["journal_entry_payload"][0]["FileIDs"] == [55]


def test_prepare_unimicro_supplier_invoice_validates_attachment(tmp_path: Path) -> None:
    receipt = tmp_path / "invoice.pdf"
    receipt.write_bytes(b"%PDF-1.4\n")

    result = prepare_unimicro_supplier_invoice({"SupplierID": 10, "InvoiceNumber": "1", "attachments": [str(receipt)]})

    assert result["status"] == "ready"
    assert result["supplier_invoice_payload"]["SupplierID"] == 10
    assert result["attachments"][0]["exists"] is True
