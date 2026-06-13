from __future__ import annotations

import json

from regnskap_agent.tripletex import detect_tripletex_capabilities
from regnskap_agent.unimicro import unimicro_capabilities


def test_tripletex_capabilities_detect_salary_without_fake_payroll_run() -> None:
    openapi = {
        "info": {"version": "test"},
        "paths": {
            "/salary/transaction": {"post": {}},
            "/salary/transaction/{id}/attachment": {"post": {}},
            "/salary/payslip": {"get": {}},
            "/salary/payslip/{id}/pdf": {"get": {}},
            "/supplierInvoice": {"get": {}},
            "/supplierInvoice/{invoiceId}/:approve": {"put": {}},
            "/supplierInvoice/{invoiceId}/pdf": {"get": {}},
            "/ledger/voucher": {"get": {}, "post": {}},
            "/ledger/voucher/{voucherId}/attachment": {"post": {}},
            "/bank/reconciliation": {"get": {}, "post": {}},
            "/bank/statement": {"get": {}},
            "/travelExpense": {"get": {}, "post": {}},
        },
    }

    result = detect_tripletex_capabilities(json.dumps(openapi))

    assert result["modules"]["salary"]["write"] is True
    assert result["modules"]["salary"]["attachments"] is True
    assert result["modules"]["salary"]["payroll_run"] is False
    assert "Ikke kall dette en full lønnskjøring" in result["modules"]["salary"]["limitations"][1]
    assert result["modules"]["supplier_invoices"]["write"] is True
    assert result["modules"]["bank_reconciliation"]["read"] is True
    assert result["modules"]["vouchers"]["write"] is True


def test_tripletex_capabilities_detect_payroll_run_when_documented() -> None:
    result = detect_tripletex_capabilities({"info": {}, "paths": {"/salary/payrollRun": {"post": {}}}})

    assert result["modules"]["salary"]["payroll_run"] is True


def test_unimicro_capabilities_are_conservative_for_payroll() -> None:
    result = unimicro_capabilities()

    assert result["modules"]["supplier_invoices"]["write"] is True
    assert result["modules"]["supplier_invoices"]["ocr"] is True
    assert result["modules"]["journal_entries"]["write"] is True
    assert result["modules"]["payroll"]["write"] == "unknown"
