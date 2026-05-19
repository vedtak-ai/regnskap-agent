from __future__ import annotations

import json
from pathlib import Path

from regnskap_agent.cli import main, parse_filters
from regnskap_agent.docs import search_accounts


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
