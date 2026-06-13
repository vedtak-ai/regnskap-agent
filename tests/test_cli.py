from __future__ import annotations

import json
import ssl
from pathlib import Path

from regnskap_agent.cli import list_params_for_resource, main, parse_filters
from regnskap_agent.docs import search_accounts
from regnskap_agent.fiken import FikenClient


def test_setup_reads_token_from_stdin(tmp_path: Path, monkeypatch, capsys) -> None:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "secret-token\n"})())
    code = main(["setup", "--token-stdin", "--company", "vedtak-as"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["default_company"] == "vedtak-as"
    saved = json.loads((config_home / "regnskap-agent" / "config.json").read_text())
    assert saved["fiken_api_token"] == "secret-token"


def test_setup_can_set_company_without_reentering_token(tmp_path: Path, monkeypatch, capsys) -> None:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    main(["setup", "--token", "secret-token"])
    capsys.readouterr()

    code = main(["setup", "--company", "vedtak-as"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["default_company"] == "vedtak-as"
    saved = json.loads((config_home / "regnskap-agent" / "config.json").read_text())
    assert saved["fiken_api_token"] == "secret-token"
    assert saved["default_company"] == "vedtak-as"


def test_folio_setup_preserves_fiken_config(tmp_path: Path, monkeypatch, capsys) -> None:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    main(["setup", "--token", "fiken-token", "--company", "vedtak-as"])
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "folio-token\n"})())

    code = main(["folio", "setup", "--token-stdin", "--base-url", "https://folio.example.test/api"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["folio_base_url"] == "https://folio.example.test/api"
    saved = json.loads((config_home / "regnskap-agent" / "config.json").read_text())
    assert saved["fiken_api_token"] == "fiken-token"
    assert saved["default_company"] == "vedtak-as"
    assert saved["folio_api_token"] == "folio-token"
    assert saved["folio_base_url"] == "https://folio.example.test/api"


def test_folio_doctor_reports_env(monkeypatch, capsys) -> None:
    monkeypatch.setenv("FOLIO_API_TOKEN", "token")
    monkeypatch.setenv("FOLIO_API_BASE_URL", "https://folio.example.test/api")
    code = main(["folio", "doctor"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_token"] is True
    assert payload["token_source"] == "env"
    assert payload["has_base_url"] is True
    assert payload["base_url_source"] == "env"


def test_folio_setup_uses_default_base_url(tmp_path: Path, monkeypatch, capsys) -> None:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "folio-token\n"})())
    code = main(["folio", "setup", "--token-stdin"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["folio_base_url"] == "https://api.folio.no/v2"


def test_tripletex_setup_reads_tokens_from_stdin(tmp_path: Path, monkeypatch, capsys) -> None:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "consumer\nemployee\n"})())

    code = main(["tripletex", "setup", "--consumer-token-stdin", "--employee-token-stdin", "--company-id", "123"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tripletex_company_id"] == "123"
    saved = json.loads((config_home / "regnskap-agent" / "config.json").read_text())
    assert saved["tripletex_consumer_token"] == "consumer"
    assert saved["tripletex_employee_token"] == "employee"
    assert saved["tripletex_company_id"] == "123"


def test_tripletex_doctor_reports_env(monkeypatch, capsys) -> None:
    monkeypatch.setenv("TRIPLETEX_CONSUMER_TOKEN", "consumer")
    monkeypatch.setenv("TRIPLETEX_EMPLOYEE_TOKEN", "employee")
    monkeypatch.setenv("TRIPLETEX_COMPANY_ID", "123")

    code = main(["tripletex", "doctor"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_tokens"] is True
    assert payload["token_source"] == "env"
    assert payload["company_id"] == "123"


def test_tripletex_salary_transaction_is_dry_run(capsys) -> None:
    payload = {"date": "2026-06-30", "year": 2026, "month": 6, "payslips": []}

    code = main(["tripletex", "salary-transaction", "--json", json.dumps(payload)])

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["dry_run"] is True
    assert result["provider"] == "tripletex"
    assert result["path"] == "/salary/transaction"
    assert result["json"] == payload


def test_tripletex_raw_put_is_dry_run(capsys) -> None:
    code = main(["tripletex", "put", "/supplierInvoice/1/:approve", "--filter", "comment=ok"])

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["dry_run"] is True
    assert result["method"] == "PUT"
    assert result["params"] == {"comment": "ok"}


def test_unimicro_setup_reads_token_from_stdin(tmp_path: Path, monkeypatch, capsys) -> None:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "uni-token\n"})())

    code = main(["unimicro", "setup", "--token-stdin", "--company-key", "company-key"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unimicro_company_key"] == "company-key"
    saved = json.loads((config_home / "regnskap-agent" / "config.json").read_text())
    assert saved["unimicro_api_token"] == "uni-token"
    assert saved["unimicro_company_key"] == "company-key"


def test_unimicro_journal_entry_is_dry_run(capsys) -> None:
    payload = [{"DraftLines": [{"AccountID": 1, "Amount": 10.0, "Description": "Test", "FinancialDate": "2026-06-01"}]}]

    code = main(["unimicro", "journal-entry", "--json", json.dumps(payload)])

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["dry_run"] is True
    assert result["provider"] == "unimicro"
    assert result["path"] == "/api/biz/journalentries"
    assert result["params"] == {"action": "book-journal-entries"}


def test_providers_capabilities_can_use_tripletex_fixture(tmp_path: Path, capsys) -> None:
    openapi = tmp_path / "tripletex.json"
    openapi.write_text(json.dumps({"info": {"version": "x"}, "paths": {"/salary/transaction": {"post": {}}}}), encoding="utf-8")

    code = main(["providers", "capabilities", "--provider", "tripletex", "--tripletex-openapi-file", str(openapi)])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["providers"]["tripletex"]["modules"]["salary"]["write"] is True


def test_fiken_client_uses_certifi_ssl_context(monkeypatch) -> None:
    contexts = []

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b"{}"

    def fake_urlopen(request, *, timeout, context):
        contexts.append(context)
        return Response()

    monkeypatch.setattr("regnskap_agent.fiken.urllib.request.urlopen", fake_urlopen)
    response = FikenClient("token").get("/user")
    assert response.status == 200
    assert isinstance(contexts[0], ssl.SSLContext)


def test_folio_upload_attachment_is_dry_run(tmp_path: Path, capsys) -> None:
    receipt = tmp_path / "receipt.pdf"
    receipt.write_bytes(b"%PDF-1.4\n")
    code = main(
        [
            "folio",
            "upload-attachment",
            "event-id",
            "--file",
            str(receipt),
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["path"] == "/events/event-id/attachments"


def test_folio_create_payment_is_dry_run(capsys) -> None:
    payment = {
        "creditor": {"name": "Leverandør AS", "accountNumber": "12345678901"},
        "debtorAccountNumber": "98765432109",
        "currencyAmount": {"amount": "1000.00", "currency": "NOK"},
        "executionDate": "2026-06-11",
        "kid": "123456789",
    }
    code = main(["folio", "create-payment", "--json", json.dumps(payment)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["method"] == "POST"
    assert payload["path"] == "/payments"
    assert payload["json"] == payment
    assert "bankutkast" in payload["warning"]


def test_folio_cancel_payment_is_dry_run(capsys) -> None:
    code = main(["folio", "cancel-payment", "payment-id"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["method"] == "DELETE"
    assert payload["path"] == "/payments/payment-id"


def test_docs_add_and_search(tmp_path: Path, monkeypatch, capsys) -> None:
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("REGNSKAP_DOCS_OFFLINE", "1")
    code = main(
        [
            "docs",
            "add",
            "--title",
            "Purchases",
            "--source-url",
            "https://fiken.no/api/v2/documentation#/purchases",
            "--text",
            "Create purchase lines with vatType and netPrice in cents.",
        ]
    )
    assert code == 0
    capsys.readouterr()

    code = main(["docs", "search", "vatType"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["title"] == "Purchases"


def test_account_help_search_uses_fiken_account_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        "regnskap_agent.docs.fetch_account_groups",
        lambda refresh=False: [
            {
                "nummer": 65,
                "navn": "Verktøy, inventar og driftsmaterialer",
                "kontoer": [
                    {
                        "kontonummer": 6540,
                        "navn": "Inventar",
                        "kunForOrgForm": ["AS"],
                        "metaData": {
                            "hjelpetekst": "Kjøp av kontorstol og annet inventar.",
                            "gyldigeMvakoder": ["0", "1"],
                            "defaultMvakode": None,
                            "defaultMvakodeErIngen": True,
                            "sokeord": ["kontorstol"],
                        },
                    }
                ],
            }
        ],
    )
    results = search_accounts("kontorstol", org_form="AS")
    assert results[0]["account_number"] == 6540
    assert results[0]["valid_vat_codes"] == ["0", "1"]


def test_parse_filters_types() -> None:
    assert parse_filters(["settled=false", "page=2", "name=Vedtak"]) == {
        "settled": False,
        "page": 2,
        "name": "Vedtak",
    }


def test_list_inbox_defaults_to_unused_documents() -> None:
    params, defaults = list_params_for_resource("inbox", [])
    assert params["status"] == "unused"
    assert defaults == {"status": "unused"}


def test_list_inbox_status_filter_overrides_default() -> None:
    params, defaults = list_params_for_resource("inbox", ["status=all"])
    assert params["status"] == "all"
    assert defaults == {}


def test_list_other_resources_do_not_get_inbox_default() -> None:
    params, defaults = list_params_for_resource("purchases", [])
    assert "status" not in params
    assert defaults == {}


def test_upload_inbox_is_dry_run(tmp_path: Path, capsys) -> None:
    receipt = tmp_path / "bilag.pdf"
    receipt.write_bytes(b"%PDF-1.4\n")
    code = main(
        [
            "fiken",
            "upload-inbox",
            "--company",
            "vedtak-as",
            "--file",
            str(receipt),
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["path"] == "/companies/vedtak-as/inbox"


def test_invoice_draft_is_dry_run(capsys) -> None:
    code = main(
        [
            "fiken",
            "invoice-draft",
            "--company",
            "vedtak-as",
            "--json",
            '{"issueDate":"2026-05-19","customerId":1,"lines":[]}',
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["method"] == "POST"
    assert payload["path"] == "/companies/vedtak-as/invoices/drafts"


def test_prepare_purchase_is_read_only_preflight(tmp_path: Path, capsys) -> None:
    receipt = tmp_path / "microsoft.pdf"
    receipt.write_bytes(b"%PDF-1.4\n")
    code = main(
        [
            "fiken",
            "prepare-purchase",
            "--company",
            "vedtak-as",
            "--skip-duplicates",
            "--json",
            json.dumps(
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
            ),
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"
    assert payload["purchase_payload"]["lines"][0]["vat"] == 2682
    assert payload["duplicates"]["status"] == "not_checked"


def test_ehf_capabilities_uses_openapi_file_without_probing(tmp_path: Path, capsys) -> None:
    openapi = tmp_path / "swagger.yaml"
    openapi.write_text(
        """
paths:
  /companies/{companySlug}/purchases:
    post: {}
  /companies/{companySlug}/purchases/drafts:
    get: {}
  /companies/{companySlug}/inbox:
    get: {}
""",
        encoding="utf-8",
    )

    code = main(
        [
            "fiken",
            "ehf-capabilities",
            "--company",
            "vedtak-as",
            "--openapi-file",
            str(openapi),
            "--skip-probes",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["purchase_api_supported"] is True
    assert payload["purchase_drafts_supported"] is True
    assert payload["inbox_supported"] is True
    assert payload["ehf_overview_api_supported"] is False
