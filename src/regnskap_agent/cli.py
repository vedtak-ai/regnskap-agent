from __future__ import annotations

import argparse
import getpass
import json
import os
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Any

import certifi

from .config import (
    Config,
    DEFAULT_FOLIO_BASE_URL,
    DEFAULT_TRIPLETEX_BASE_URL,
    DEFAULT_UNIMICRO_API_BASE_URL,
    DEFAULT_UNIMICRO_FILE_BASE_URL,
    load_config,
    resolve_company,
    resolve_folio_base_url,
    resolve_folio_token,
    resolve_token,
    resolve_tripletex_base_url,
    resolve_tripletex_company_id,
    resolve_tripletex_consumer_token,
    resolve_tripletex_employee_token,
    resolve_unimicro_api_base_url,
    resolve_unimicro_api_token,
    resolve_unimicro_company_key,
    resolve_unimicro_file_base_url,
    save_config,
)
from .docs import (
    ACCOUNT_HELP_DATA_URL,
    API_DOCS_URL,
    DOCS_URL,
    HELP_INDEX_URL,
    add_doc,
    context_for_query,
    get_help_article,
    list_docs,
    search_accounts,
    search_docs,
)
from .ehf_capabilities import KNOWN_EHF_READ_PATHS, detect_ehf_capabilities
from .fiken import FikenClient, FikenError, company_path
from .folio import API_DOCS_URL as FOLIO_API_DOCS_URL
from .folio import OPENAPI_URL as FOLIO_OPENAPI_URL
from .folio import FolioClient, FolioError
from .http_client import ApiError
from .provider_prepare import (
    prepare_salary_transaction,
    prepare_unimicro_journal_entry,
    prepare_unimicro_supplier_invoice,
)
from .purchase_prepare import duplicate_date_window, prepare_purchase
from .reconcile import default_start_date, reconcile_card_purchases, today_iso
from .tripletex import (
    OPENAPI_URL as TRIPLETEX_OPENAPI_URL,
    TRIPLETEX_RESOURCE_ALIASES,
    TripletexClient,
    detect_tripletex_capabilities,
    session_is_valid,
)
from .unimicro import UNIMICRO_RESOURCE_ALIASES, UniMicroClient, unimicro_capabilities


FIKEN_OPENAPI_URL = "https://api.fiken.no/api/v2/docs/swagger.yaml"


RESOURCE_ALIASES = {
    "accounts": "accounts",
    "account-balances": "accountBalances",
    "bank-accounts": "bankAccounts",
    "bank-balances": "bankBalances",
    "contacts": "contacts",
    "credit-notes": "creditNotes",
    "credit-note-drafts": "creditNotes/drafts",
    "inbox": "inbox",
    "invoices": "invoices",
    "invoice-drafts": "invoices/drafts",
    "journal-entries": "journalEntries",
    "offers": "offers",
    "offer-drafts": "offers/drafts",
    "order-confirmations": "orderConfirmations",
    "products": "products",
    "projects": "projects",
    "purchases": "purchases",
    "purchase-drafts": "purchases/drafts",
    "sales": "sales",
    "sale-drafts": "sales/drafts",
    "time-entries": "timeEntries",
    "activities": "activities",
    "time-users": "timeUsers",
    "transactions": "transactions",
}

WRITE_COMMANDS = {
    "post",
    "patch",
    "upload-inbox",
    "attach-purchase",
    "create-contact",
    "invoice-draft",
    "purchase",
    "folio-create-payment",
    "folio-cancel-payment",
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if not hasattr(args, "func"):
            parser.print_help()
            return 0
        return args.func(args)
    except FikenError as exc:
        print_json({"ok": False, "error": str(exc), "status": exc.status})
        return 2
    except FolioError as exc:
        print_json({"ok": False, "error": str(exc), "status": exc.status})
        return 2
    except ApiError as exc:
        print_json({"ok": False, "provider": exc.provider, "error": str(exc), "status": exc.status})
        return 2
    except Exception as exc:
        print_json({"ok": False, "error": str(exc)})
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="regnskap")
    sub = parser.add_subparsers(dest="command")

    setup = sub.add_parser("setup", help="Lagre Fiken-token og valgfri standardbedrift")
    setup.add_argument("--token")
    setup.add_argument(
        "--token-stdin",
        action="store_true",
        help="Les Fiken-token fra stdin. Brukes av agent/browser-onboarding for å unngå shell history.",
    )
    setup.add_argument("--company")
    setup.add_argument(
        "--auto-company",
        action="store_true",
        help="Hent selskaper fra Fiken og lagre default hvis tokenet bare har tilgang til ett selskap.",
    )
    setup.set_defaults(func=cmd_setup)

    doctor = sub.add_parser("doctor", help="Sjekk lokal konfigurasjon")
    doctor.set_defaults(func=cmd_doctor)

    fiken = sub.add_parser("fiken", help="Fiken API-kommandoer")
    fiken_sub = fiken.add_subparsers(dest="fiken_command")

    add_fiken_read_commands(fiken_sub)
    add_fiken_write_commands(fiken_sub)
    add_fiken_raw_commands(fiken_sub)

    folio = sub.add_parser("folio", help="Folio bank-provider")
    folio_sub = folio.add_subparsers(dest="folio_command")
    add_folio_commands(folio_sub)

    tripletex = sub.add_parser("tripletex", help="Tripletex provider")
    tripletex_sub = tripletex.add_subparsers(dest="tripletex_command")
    add_tripletex_commands(tripletex_sub)

    unimicro = sub.add_parser("unimicro", help="UniMicro provider")
    unimicro_sub = unimicro.add_subparsers(dest="unimicro_command")
    add_unimicro_commands(unimicro_sub)

    providers = sub.add_parser("providers", help="Sammenlign provider-kapabiliteter")
    providers_sub = providers.add_subparsers(dest="providers_command")
    add_provider_commands(providers_sub)

    reconcile = sub.add_parser("reconcile", help="Avstem og prioriter regnskapsarbeid på tvers av kilder")
    reconcile_sub = reconcile.add_subparsers(dest="reconcile_command")
    add_reconcile_commands(reconcile_sub)

    docs = sub.add_parser("docs", help="Søk i Fikens hjelpesider og kontohjelp")
    docs_sub = docs.add_subparsers(dest="docs_command")
    add_docs_commands(docs_sub)
    return parser


def add_common_company(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--company", help="Fiken company slug")


def add_common_pagination(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page", type=int, default=0)
    parser.add_argument("--page-size", type=int, default=25)
    parser.add_argument("--all", action="store_true", help="Hent alle sider")
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Query-filter. Kan brukes flere ganger.",
    )


def add_execute(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Utfør skriveoperasjonen. Uten denne kjører kommandoen dry-run.",
    )


def add_json_body(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--json", help="JSON-payload som streng")
    source.add_argument("--json-file", type=Path, help="Fil med JSON-payload")


def add_optional_json_body(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--json", help="JSON-payload som streng")
    source.add_argument("--json-file", type=Path, help="Fil med JSON-payload")


def add_fiken_read_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    user = sub.add_parser("user", help="Hent innlogget Fiken-bruker")
    user.set_defaults(func=cmd_fiken_user)

    companies = sub.add_parser("companies", help="List selskaper")
    add_common_pagination(companies)
    companies.set_defaults(func=cmd_fiken_companies)

    list_cmd = sub.add_parser("list", help="List en ressurs under et selskap")
    add_common_company(list_cmd)
    add_common_pagination(list_cmd)
    list_cmd.add_argument("resource", choices=sorted(RESOURCE_ALIASES))
    list_cmd.set_defaults(func=cmd_fiken_list)

    get_cmd = sub.add_parser("get", help="GET mot vilkårlig Fiken API-path")
    get_cmd.add_argument("path", help="For eksempel /companies/slug/accounts")
    get_cmd.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    get_cmd.set_defaults(func=cmd_fiken_get)

    ehf = sub.add_parser("ehf-capabilities", help="Sjekk Fiken API-støtte for EHF-relaterte kjøpsflyter")
    add_common_company(ehf)
    ehf.add_argument("--openapi-file", type=Path, help="Les OpenAPI fra lokal fil i stedet for Fiken docs")
    ehf.add_argument("--skip-probes", action="store_true", help="Ikke probe kjente EHF-read-paths mot Fiken")
    ehf.set_defaults(func=cmd_ehf_capabilities)


def add_fiken_write_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    upload = sub.add_parser("upload-inbox", help="Last opp bilag til Fiken inbox")
    add_common_company(upload)
    upload.add_argument("--file", required=True, type=Path)
    upload.add_argument("--name")
    upload.add_argument("--description")
    add_execute(upload)
    upload.set_defaults(func=cmd_upload_inbox)

    attach = sub.add_parser("attach-purchase", help="Legg ved fil på eksisterende kjøp")
    add_common_company(attach)
    attach.add_argument("--purchase-id", required=True, type=int)
    attach.add_argument("--file", required=True, type=Path)
    attach.add_argument("--attach-to-sale", action=argparse.BooleanOptionalAction, default=True)
    attach.add_argument("--attach-to-payment", action=argparse.BooleanOptionalAction, default=False)
    add_execute(attach)
    attach.set_defaults(func=cmd_attach_purchase)

    contact = sub.add_parser("create-contact", help="Opprett kontakt")
    add_common_company(contact)
    add_json_body(contact)
    add_execute(contact)
    contact.set_defaults(func=cmd_create_contact)

    invoice = sub.add_parser("invoice-draft", help="Opprett fakturautkast")
    add_common_company(invoice)
    add_json_body(invoice)
    add_execute(invoice)
    invoice.set_defaults(func=cmd_invoice_draft)

    prepare = sub.add_parser("prepare-purchase", help="Valider og normaliser kjøpspayload uten å skrive")
    add_common_company(prepare)
    add_json_body(prepare)
    prepare.add_argument("--skip-duplicates", action="store_true", help="Ikke hent eksisterende kjøp for duplikatsjekk")
    prepare.add_argument("--duplicate-days", type=int, default=10, help="Datotoleranse for duplikatsjekk")
    prepare.add_argument("--page-size", type=int, default=100, help="Fiken pageSize for duplikatsjekk")
    prepare.set_defaults(func=cmd_prepare_purchase)

    purchase = sub.add_parser("purchase", help="Opprett kjøp. Brukes bare etter eksplisitt godkjenning.")
    add_common_company(purchase)
    add_json_body(purchase)
    add_execute(purchase)
    purchase.set_defaults(func=cmd_purchase)


def add_fiken_raw_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    post = sub.add_parser("post", help="POST mot vilkårlig Fiken API-path")
    post.add_argument("path")
    add_json_body(post)
    add_execute(post)
    post.set_defaults(func=cmd_fiken_post)

    patch = sub.add_parser("patch", help="PATCH mot vilkårlig Fiken API-path")
    patch.add_argument("path")
    patch.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    add_execute(patch)
    patch.set_defaults(func=cmd_fiken_patch)


def add_folio_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    setup = sub.add_parser("setup", help="Lagre Folio-token og base URL")
    setup.add_argument("--token")
    setup.add_argument("--token-stdin", action="store_true", help="Les Folio-token fra stdin")
    setup.add_argument("--base-url", default=DEFAULT_FOLIO_BASE_URL, help="Folio API base URL")
    setup.set_defaults(func=cmd_folio_setup)

    doctor = sub.add_parser("doctor", help="Sjekk Folio-konfigurasjon")
    doctor.set_defaults(func=cmd_folio_doctor)

    get = sub.add_parser("get", help="GET mot Folio API-path")
    get.add_argument("path")
    get.add_argument("--base-url")
    get.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    get.set_defaults(func=cmd_folio_get)

    accounts = sub.add_parser("accounts", help="List Folio-kontoer")
    accounts.set_defaults(func=cmd_folio_accounts)

    transactions = sub.add_parser("transactions", help="List Folio-transaksjoner")
    add_folio_date_range(transactions)
    transactions.add_argument("--include-merchants", action="store_true")
    transactions.set_defaults(func=cmd_folio_transactions)

    transaction = sub.add_parser("transaction", help="Hent én Folio-transaksjon")
    transaction.add_argument("id")
    transaction.set_defaults(func=cmd_folio_transaction)

    account_transactions = sub.add_parser("account-transactions", help="List transaksjoner for Folio-konto")
    account_transactions.add_argument("account_number")
    add_folio_date_range(account_transactions)
    account_transactions.set_defaults(func=cmd_folio_account_transactions)

    balance = sub.add_parser("balance", help="Hent historisk saldo for Folio-konto")
    balance.add_argument("account_number")
    balance.add_argument("date", help="Dato YYYY-MM-DD")
    balance.set_defaults(func=cmd_folio_balance)

    events = sub.add_parser("events", help="List Folio-events")
    add_folio_date_range(events)
    events.add_argument("--include-merchants", action="store_true")
    events.add_argument("--include-agents", action="store_true")
    events.add_argument("--include-cards", action="store_true")
    events.set_defaults(func=cmd_folio_events)

    payments = sub.add_parser("payments", help="List Folio-betalinger")
    add_folio_date_range(payments)
    payments.add_argument("--include-agents", action="store_true")
    payments.set_defaults(func=cmd_folio_payments)

    payment = sub.add_parser("payment", help="Hent én Folio-betaling")
    payment.add_argument("id")
    payment.set_defaults(func=cmd_folio_payment)

    create_payment = sub.add_parser("create-payment", help="Opprett Folio-betaling som bankutkast")
    add_json_body(create_payment)
    add_execute(create_payment)
    create_payment.set_defaults(func=cmd_folio_create_payment)

    cancel_payment = sub.add_parser("cancel-payment", help="Kanseller Folio-betaling")
    cancel_payment.add_argument("id")
    add_execute(cancel_payment)
    cancel_payment.set_defaults(func=cmd_folio_cancel_payment)

    category = sub.add_parser("category", help="Hent Folio-regnskapskategori")
    category.add_argument("id")
    category.set_defaults(func=cmd_folio_category)

    attachment = sub.add_parser("attachment", help="Hent Folio-vedlegg")
    attachment.add_argument("id")
    attachment.add_argument("--type", default="original", choices=["original", "cropped", "128x128", "256x256", "512x512"])
    attachment.add_argument("--output", required=True, type=Path)
    attachment.set_defaults(func=cmd_folio_attachment)

    upload_attachment = sub.add_parser("upload-attachment", help="Legg ved fil på Folio-event")
    upload_attachment.add_argument("event_id")
    upload_attachment.add_argument("--file", required=True, type=Path)
    add_execute(upload_attachment)
    upload_attachment.set_defaults(func=cmd_folio_upload_attachment)

    docs = sub.add_parser("docs", help="Vis Folio API-dokumentasjon")
    docs.set_defaults(func=cmd_folio_docs)


def add_folio_date_range(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-date", required=True, help="Fra-dato YYYY-MM-DD")
    parser.add_argument("--end-date", help="Til-dato YYYY-MM-DD")


def add_tripletex_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    setup = sub.add_parser("setup", help="Lagre Tripletex tokens og standard company-id")
    setup.add_argument("--consumer-token")
    setup.add_argument("--consumer-token-stdin", action="store_true", help="Les consumer token fra stdin")
    setup.add_argument("--employee-token")
    setup.add_argument("--employee-token-stdin", action="store_true", help="Les employee token fra stdin")
    setup.add_argument("--company-id")
    setup.add_argument("--base-url", default=DEFAULT_TRIPLETEX_BASE_URL)
    setup.set_defaults(func=cmd_tripletex_setup)

    doctor = sub.add_parser("doctor", help="Sjekk Tripletex-konfigurasjon")
    doctor.set_defaults(func=cmd_tripletex_doctor)

    capabilities = sub.add_parser("capabilities", help="Rapporter Tripletex API-kapabiliteter")
    capabilities.add_argument("--openapi-file", type=Path)
    capabilities.add_argument("--base-url")
    capabilities.set_defaults(func=cmd_tripletex_capabilities)

    whoami = sub.add_parser("whoami", help="Hent Tripletex session/whoAmI")
    whoami.add_argument("--company-id")
    whoami.set_defaults(func=cmd_tripletex_whoami)

    list_cmd = sub.add_parser("list", help="List en kjent Tripletex-ressurs")
    list_cmd.add_argument("resource", choices=sorted(TRIPLETEX_RESOURCE_ALIASES))
    list_cmd.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    list_cmd.set_defaults(func=cmd_tripletex_list)

    get = sub.add_parser("get", help="GET mot Tripletex API-path")
    get.add_argument("path")
    get.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    get.set_defaults(func=cmd_tripletex_get)

    post = sub.add_parser("post", help="POST mot Tripletex API-path")
    post.add_argument("path")
    add_json_body(post)
    post.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    add_execute(post)
    post.set_defaults(func=cmd_tripletex_post)

    put = sub.add_parser("put", help="PUT mot Tripletex API-path")
    put.add_argument("path")
    add_optional_json_body(put)
    put.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    add_execute(put)
    put.set_defaults(func=cmd_tripletex_put)

    delete = sub.add_parser("delete", help="DELETE mot Tripletex API-path")
    delete.add_argument("path")
    delete.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    add_execute(delete)
    delete.set_defaults(func=cmd_tripletex_delete)

    pdf = sub.add_parser("pdf", help="Last ned Tripletex PDF for supplier-invoice, voucher eller payslip")
    pdf.add_argument("kind", choices=["supplier-invoice", "voucher", "payslip"])
    pdf.add_argument("id")
    pdf.add_argument("--output", required=True, type=Path)
    pdf.set_defaults(func=cmd_tripletex_pdf)

    voucher = sub.add_parser("voucher", help="Opprett Tripletex voucher")
    add_json_body(voucher)
    voucher.add_argument("--send-to-ledger", action=argparse.BooleanOptionalAction, default=None)
    add_execute(voucher)
    voucher.set_defaults(func=cmd_tripletex_voucher)

    attach_voucher = sub.add_parser("attach-voucher", help="Legg ved fil på Tripletex voucher")
    attach_voucher.add_argument("voucher_id")
    attach_voucher.add_argument("--file", required=True, type=Path)
    add_execute(attach_voucher)
    attach_voucher.set_defaults(func=cmd_tripletex_attach_voucher)

    supplier_action = sub.add_parser("supplier-invoice-action", help="Approve/reject/addPayment på Tripletex supplier invoice")
    supplier_action.add_argument("action", choices=["approve", "reject", "add-payment"])
    supplier_action.add_argument("--invoice-id")
    supplier_action.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    add_execute(supplier_action)
    supplier_action.set_defaults(func=cmd_tripletex_supplier_invoice_action)

    invoice_payment = sub.add_parser("invoice-payment", help="Marker betaling på Tripletex kundeinvoice")
    invoice_payment.add_argument("invoice_id")
    invoice_payment.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    add_execute(invoice_payment)
    invoice_payment.set_defaults(func=cmd_tripletex_invoice_payment)

    prepare_salary = sub.add_parser("prepare-salary-transaction", help="Valider Tripletex salary transaction uten å skrive")
    add_json_body(prepare_salary)
    prepare_salary.set_defaults(func=cmd_tripletex_prepare_salary_transaction)

    salary = sub.add_parser("salary-transaction", help="Opprett Tripletex salary/transaction")
    add_json_body(salary)
    salary.add_argument("--generate-tax-deduction", action=argparse.BooleanOptionalAction, default=None)
    add_execute(salary)
    salary.set_defaults(func=cmd_tripletex_salary_transaction)

    attach_salary = sub.add_parser("attach-salary-transaction", help="Legg ved fil på Tripletex salary transaction")
    attach_salary.add_argument("transaction_id")
    attach_salary.add_argument("--file", required=True, type=Path)
    add_execute(attach_salary)
    attach_salary.set_defaults(func=cmd_tripletex_attach_salary_transaction)


def add_unimicro_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    setup = sub.add_parser("setup", help="Lagre UniMicro token, company key og base URLs")
    setup.add_argument("--token")
    setup.add_argument("--token-stdin", action="store_true")
    setup.add_argument("--company-key")
    setup.add_argument("--api-base-url", default=DEFAULT_UNIMICRO_API_BASE_URL)
    setup.add_argument("--file-base-url", default=DEFAULT_UNIMICRO_FILE_BASE_URL)
    setup.set_defaults(func=cmd_unimicro_setup)

    doctor = sub.add_parser("doctor", help="Sjekk UniMicro-konfigurasjon")
    doctor.set_defaults(func=cmd_unimicro_doctor)

    capabilities = sub.add_parser("capabilities", help="Rapporter UniMicro-kapabiliteter")
    capabilities.set_defaults(func=cmd_unimicro_capabilities)

    list_cmd = sub.add_parser("list", help="List en kjent UniMicro-ressurs")
    list_cmd.add_argument("resource", choices=sorted(UNIMICRO_RESOURCE_ALIASES))
    list_cmd.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    list_cmd.set_defaults(func=cmd_unimicro_list)

    get = sub.add_parser("get", help="GET mot UniMicro API-path")
    get.add_argument("path")
    get.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    get.set_defaults(func=cmd_unimicro_get)

    post = sub.add_parser("post", help="POST mot UniMicro API-path")
    post.add_argument("path")
    add_json_body(post)
    post.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    add_execute(post)
    post.set_defaults(func=cmd_unimicro_post)

    put = sub.add_parser("put", help="PUT mot UniMicro API-path")
    put.add_argument("path")
    add_optional_json_body(put)
    put.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    add_execute(put)
    put.set_defaults(func=cmd_unimicro_put)

    delete = sub.add_parser("delete", help="DELETE mot UniMicro API-path")
    delete.add_argument("path")
    delete.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    add_execute(delete)
    delete.set_defaults(func=cmd_unimicro_delete)

    prepare_supplier = sub.add_parser("prepare-supplier-invoice", help="Valider UniMicro supplier invoice uten write")
    add_json_body(prepare_supplier)
    prepare_supplier.set_defaults(func=cmd_unimicro_prepare_supplier_invoice)

    supplier = sub.add_parser("supplier-invoice", help="Opprett UniMicro supplier invoice")
    add_json_body(supplier)
    add_execute(supplier)
    supplier.set_defaults(func=cmd_unimicro_supplier_invoice)

    assign = sub.add_parser("assign-supplier-invoice", help="Send UniMicro supplier invoice til approval")
    assign.add_argument("invoice_id")
    add_json_body(assign)
    add_execute(assign)
    assign.set_defaults(func=cmd_unimicro_assign_supplier_invoice)

    prepare_journal = sub.add_parser("prepare-journal-entry", help="Valider UniMicro journal entry uten write")
    add_json_body(prepare_journal)
    prepare_journal.add_argument("--accounts-json-file", type=Path)
    prepare_journal.add_argument("--vattypes-json-file", type=Path)
    prepare_journal.set_defaults(func=cmd_unimicro_prepare_journal_entry)

    journal = sub.add_parser("journal-entry", help="Book UniMicro journal entry")
    add_json_body(journal)
    add_execute(journal)
    journal.set_defaults(func=cmd_unimicro_journal_entry)

    upload = sub.add_parser("upload-file", help="Last opp fil til UniMicro file server")
    upload.add_argument("--file", required=True, type=Path)
    upload.add_argument("--entity-id")
    upload.add_argument("--entity-type")
    upload.add_argument("--caption")
    add_execute(upload)
    upload.set_defaults(func=cmd_unimicro_upload_file)

    link = sub.add_parser("link-file", help="Lenk eksisterende UniMicro-fil til entitet")
    link.add_argument("file_id")
    link.add_argument("--entity-type", required=True)
    link.add_argument("--entity-id", required=True)
    add_execute(link)
    link.set_defaults(func=cmd_unimicro_link_file)

    ocr = sub.add_parser("ocr-file", help="Kjør UniMicro OCR-analyse på fil")
    ocr.add_argument("file_id")
    ocr.set_defaults(func=cmd_unimicro_ocr_file)


def add_provider_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    capabilities = sub.add_parser("capabilities", help="Rapporter kapabiliteter for alle eller én provider")
    capabilities.add_argument("--provider", choices=["tripletex", "unimicro"])
    capabilities.add_argument("--tripletex-openapi-file", type=Path)
    capabilities.set_defaults(func=cmd_providers_capabilities)


def add_reconcile_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    card = sub.add_parser(
        "card-purchases",
        help="Match Folio-kortkjøp mot Fiken-kjøp, utkast og inbox",
    )
    add_common_company(card)
    card.add_argument("--start-date", default=default_start_date(), help="Fra-dato YYYY-MM-DD")
    card.add_argument("--end-date", default=today_iso(), help="Til-dato YYYY-MM-DD")
    card.add_argument("--max-days-diff", type=int, default=3, help="Toleranse for datomatch")
    card.add_argument("--page-size", type=int, default=100, help="Fiken pageSize")
    card.add_argument(
        "--only-needs-action",
        action="store_true",
        help="Vis bare kjøp som krever oppfølging",
    )
    card.set_defaults(func=cmd_reconcile_card_purchases)


def add_docs_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    search = sub.add_parser("search", help="Søk i Fikens hjelpesider")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--refresh", action="store_true", help="Hent fersk indeks fra Fiken")
    search.add_argument("--local-only", action="store_true", help="Søk bare i lokal manuell cache")
    search.set_defaults(func=cmd_docs_search)

    context = sub.add_parser("context", help="Hent relevante Fiken-hjelpeartikler som markdown-kontekst")
    context.add_argument("query")
    context.add_argument("--limit", type=int, default=2)
    context.add_argument("--chars", type=int, default=4000)
    context.add_argument("--refresh", action="store_true", help="Hent ferske artikler fra Fiken")
    context.set_defaults(func=cmd_docs_context)

    get = sub.add_parser("get", help="Hent en Fiken-hjelpeartikkel som markdown")
    get.add_argument("slug_or_id")
    get.add_argument("--refresh", action="store_true")
    get.set_defaults(func=cmd_docs_get)

    accounts = sub.add_parser("accounts", help="Søk i Fikens kontohjelp")
    accounts.add_argument("query")
    accounts.add_argument("--org-form", help="Filtrer på organisasjonsform, for eksempel AS eller ENK")
    accounts.add_argument("--limit", type=int, default=8)
    accounts.add_argument("--refresh", action="store_true")
    accounts.set_defaults(func=cmd_docs_accounts)

    add = sub.add_parser("add", help="Legg til dokumentasjonstekst i lokal cache")
    add.add_argument("--title", required=True)
    add.add_argument("--source-url", required=True)
    source = add.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--text-file", type=Path)
    source.add_argument("--text-stdin", action="store_true")
    add.set_defaults(func=cmd_docs_add)

    list_cmd = sub.add_parser("list", help="List cachede dokumentasjonssider")
    list_cmd.set_defaults(func=cmd_docs_list)

    url = sub.add_parser("url", help="Vis anbefalt offisiell Fiken docs-URL")
    url.set_defaults(func=cmd_docs_url)


def cmd_setup(args: argparse.Namespace) -> int:
    if args.token and args.token_stdin:
        raise ValueError("Bruk enten --token eller --token-stdin, ikke begge.")
    existing = load_config()
    if args.token_stdin:
        token = sys.stdin.read().strip()
    elif args.token:
        token = args.token
    else:
        token = existing.token
        if not token:
            token = getpass.getpass("Fiken API-token: ")
    if not token:
        raise ValueError("Tomt Fiken-token.")

    existing.token = token
    existing.default_company = args.company or existing.default_company
    config = existing
    auto_company_result: dict[str, Any] | None = None
    if args.auto_company and not args.company:
        companies = FikenClient(token).get_paginated("/companies", all_pages=True)["data"]
        if len(companies) == 1:
            config.default_company = str(companies[0]["slug"])
            auto_company_result = {"status": "set", "company": config.default_company}
        else:
            auto_company_result = {
                "status": "needs_choice",
                "companies": [
                    {"slug": company.get("slug"), "name": company.get("name")}
                    for company in companies
                ],
            }
    path = save_config(config)
    print_json(
        {
            "ok": True,
            "config": str(path),
            "default_company": config.default_company,
            "auto_company": auto_company_result,
        }
    )
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    config = load_config()
    token_source = "env" if "FIKEN_API_TOKEN" in os.environ else "config" if config.token else None
    folio_token_source = (
        "env" if "FOLIO_API_TOKEN" in os.environ else "config" if config.folio_token else None
    )
    folio_base_source = "env" if "FOLIO_API_BASE_URL" in os.environ else "config" if config.folio_base_url else "default"
    tripletex_token_source = (
        "env"
        if "TRIPLETEX_CONSUMER_TOKEN" in os.environ and "TRIPLETEX_EMPLOYEE_TOKEN" in os.environ
        else "config"
        if config.tripletex_consumer_token and config.tripletex_employee_token
        else None
    )
    unimicro_token_source = (
        "env" if "UNIMICRO_API_TOKEN" in os.environ else "config" if config.unimicro_api_token else None
    )
    print_json(
        {
            "ok": True,
            "has_token": bool(token_source),
            "token_source": token_source,
            "default_company": config.default_company,
            "folio": {
                "has_token": bool(folio_token_source),
                "token_source": folio_token_source,
                "has_base_url": True,
                "base_url_source": folio_base_source,
            },
            "tripletex": {
                "has_tokens": bool(tripletex_token_source),
                "token_source": tripletex_token_source,
                "company_id": resolve_tripletex_company_id(config),
                "base_url": resolve_tripletex_base_url(config),
                "session_cached": bool(config.tripletex_session_token),
                "session_valid": session_is_valid(config.tripletex_session_expires),
            },
            "unimicro": {
                "has_token": bool(unimicro_token_source),
                "token_source": unimicro_token_source,
                "has_company_key": bool(os.environ.get("UNIMICRO_COMPANY_KEY") or config.unimicro_company_key),
                "api_base_url": resolve_unimicro_api_base_url(config),
                "file_base_url": resolve_unimicro_file_base_url(config),
            },
        }
    )
    return 0


def cmd_folio_setup(args: argparse.Namespace) -> int:
    if args.token and args.token_stdin:
        raise ValueError("Bruk enten --token eller --token-stdin, ikke begge.")
    existing = load_config()
    if args.token_stdin:
        token = sys.stdin.read().strip()
    elif args.token:
        token = args.token
    else:
        token = existing.folio_token
    base_url = args.base_url or existing.folio_base_url or DEFAULT_FOLIO_BASE_URL
    if not token:
        raise ValueError("Tomt Folio-token. Bruk --token-stdin eller FOLIO_API_TOKEN.")
    if not base_url:
        raise ValueError("Mangler Folio base URL.")

    existing.folio_token = token
    existing.folio_base_url = base_url
    path = save_config(existing)
    print_json({"ok": True, "config": str(path), "folio_base_url": base_url})
    return 0


def cmd_folio_doctor(_: argparse.Namespace) -> int:
    config = load_config()
    token_source = "env" if "FOLIO_API_TOKEN" in os.environ else "config" if config.folio_token else None
    base_url_source = "env" if "FOLIO_API_BASE_URL" in os.environ else "config" if config.folio_base_url else "default"
    print_json(
        {
            "ok": True,
            "has_token": bool(token_source),
            "token_source": token_source,
            "has_base_url": bool(base_url_source),
            "base_url_source": base_url_source,
        }
    )
    return 0


def cmd_folio_get(args: argparse.Namespace) -> int:
    client = folio_client_from_config(base_url=args.base_url)
    print_response(client.get(args.path, params=parse_filters(args.filter)))
    return 0


def cmd_folio_accounts(_: argparse.Namespace) -> int:
    print_response(folio_client_from_config().get("/accounts"))
    return 0


def cmd_folio_transactions(args: argparse.Namespace) -> int:
    params = folio_date_params(args)
    params["includeMerchants"] = args.include_merchants
    print_response(folio_client_from_config().get("/transactions", params=params))
    return 0


def cmd_folio_transaction(args: argparse.Namespace) -> int:
    print_response(folio_client_from_config().get(f"/transactions/{args.id}"))
    return 0


def cmd_folio_account_transactions(args: argparse.Namespace) -> int:
    print_response(
        folio_client_from_config().get(
            f"/accounts/{args.account_number}/transactions",
            params=folio_date_params(args),
        )
    )
    return 0


def cmd_folio_balance(args: argparse.Namespace) -> int:
    print_response(folio_client_from_config().get(f"/accounts/{args.account_number}/balance/{args.date}"))
    return 0


def cmd_folio_events(args: argparse.Namespace) -> int:
    params = folio_date_params(args)
    params["includeMerchants"] = args.include_merchants
    params["includeAgents"] = args.include_agents
    params["includeCards"] = args.include_cards
    print_response(folio_client_from_config().get("/events", params=params))
    return 0


def cmd_folio_payments(args: argparse.Namespace) -> int:
    params = folio_date_params(args)
    params["includeAgents"] = args.include_agents
    print_response(folio_client_from_config().get("/payments", params=params))
    return 0


def cmd_folio_payment(args: argparse.Namespace) -> int:
    print_response(folio_client_from_config().get(f"/payments/{args.id}"))
    return 0


def cmd_folio_create_payment(args: argparse.Namespace) -> int:
    payload = read_json_arg(args)
    path = "/payments"
    if not args.execute:
        print_json(
            {
                "ok": True,
                "dry_run": True,
                "method": "POST",
                "path": path,
                "json": payload,
                "warning": "Oppretter Folio-betaling som bankutkast ved --execute. Krever eksplisitt bruker-godkjenning.",
            }
        )
        return 0
    print_response(folio_client_from_config().request("POST", path, body=payload))
    return 0


def cmd_folio_cancel_payment(args: argparse.Namespace) -> int:
    path = f"/payments/{args.id}"
    if not args.execute:
        print_json(
            {
                "ok": True,
                "dry_run": True,
                "method": "DELETE",
                "path": path,
                "warning": "Kansellerer Folio-betaling ved --execute. Krever eksplisitt bruker-godkjenning.",
            }
        )
        return 0
    print_response(folio_client_from_config().request("DELETE", path))
    return 0


def cmd_folio_category(args: argparse.Namespace) -> int:
    print_response(folio_client_from_config().get(f"/categories/{args.id}"))
    return 0


def cmd_folio_attachment(args: argparse.Namespace) -> int:
    response = folio_client_from_config().get_bytes(f"/attachments/{args.id}/{args.type}")
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(response.data)
    print_json({"ok": True, "status": response.status, "headers": response.headers, "output": str(output)})
    return 0


def cmd_folio_upload_attachment(args: argparse.Namespace) -> int:
    file_path = checked_file(args.file)
    path = f"/events/{args.event_id}/attachments"
    if not args.execute:
        print_json({"ok": True, "dry_run": True, "method": "POST binary", "path": path, "file": str(file_path)})
        return 0
    print_response(folio_client_from_config().upload_bytes(path, file_path))
    return 0


def cmd_folio_docs(_: argparse.Namespace) -> int:
    print_json({"ok": True, "docs_url": FOLIO_API_DOCS_URL, "openapi_url": FOLIO_OPENAPI_URL})
    return 0


def cmd_tripletex_setup(args: argparse.Namespace) -> int:
    if args.consumer_token and args.consumer_token_stdin:
        raise ValueError("Bruk enten --consumer-token eller --consumer-token-stdin.")
    if args.employee_token and args.employee_token_stdin:
        raise ValueError("Bruk enten --employee-token eller --employee-token-stdin.")
    existing = load_config()
    if args.consumer_token_stdin and args.employee_token_stdin:
        lines = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
        if len(lines) < 2:
            raise ValueError("Når begge Tripletex-token leses fra stdin, oppgi consumer token på linje 1 og employee token på linje 2.")
        consumer_token, employee_token = lines[0], lines[1]
    else:
        consumer_token = read_optional_stdin_or_arg(
            args.consumer_token,
            args.consumer_token_stdin,
            existing.tripletex_consumer_token,
            "Tripletex consumer token: ",
        )
        employee_token = read_optional_stdin_or_arg(
            args.employee_token,
            args.employee_token_stdin,
            existing.tripletex_employee_token,
            "Tripletex employee token: ",
        )
    if not consumer_token or not employee_token:
        raise ValueError("Mangler Tripletex consumer token eller employee token.")
    existing.tripletex_consumer_token = consumer_token
    existing.tripletex_employee_token = employee_token
    existing.tripletex_company_id = args.company_id or existing.tripletex_company_id
    existing.tripletex_base_url = args.base_url or existing.tripletex_base_url or DEFAULT_TRIPLETEX_BASE_URL
    path = save_config(existing)
    print_json(
        {
            "ok": True,
            "config": str(path),
            "tripletex_company_id": existing.tripletex_company_id or "0",
            "tripletex_base_url": existing.tripletex_base_url,
        }
    )
    return 0


def cmd_tripletex_doctor(_: argparse.Namespace) -> int:
    config = load_config()
    token_source = (
        "env"
        if "TRIPLETEX_CONSUMER_TOKEN" in os.environ and "TRIPLETEX_EMPLOYEE_TOKEN" in os.environ
        else "config"
        if config.tripletex_consumer_token and config.tripletex_employee_token
        else None
    )
    print_json(
        {
            "ok": True,
            "has_tokens": bool(token_source),
            "token_source": token_source,
            "company_id": resolve_tripletex_company_id(config),
            "base_url": resolve_tripletex_base_url(config),
            "base_url_source": "env" if "TRIPLETEX_BASE_URL" in os.environ else "config" if config.tripletex_base_url else "default",
            "session_cached": bool(config.tripletex_session_token),
            "session_expires": config.tripletex_session_expires,
            "session_valid": session_is_valid(config.tripletex_session_expires),
        }
    )
    return 0


def cmd_tripletex_capabilities(args: argparse.Namespace) -> int:
    text = args.openapi_file.read_text(encoding="utf-8") if args.openapi_file else fetch_text_url(openapi_url_for_tripletex(args.base_url))
    print_json(detect_tripletex_capabilities(text))
    return 0


def cmd_tripletex_whoami(args: argparse.Namespace) -> int:
    client, config = tripletex_client_from_config(company_id=args.company_id)
    print_response(client.get("/token/session/>whoAmI", config=config))
    return 0


def cmd_tripletex_list(args: argparse.Namespace) -> int:
    client, config = tripletex_client_from_config()
    print_response(client.get(TRIPLETEX_RESOURCE_ALIASES[args.resource], params=parse_filters(args.filter), config=config))
    return 0


def cmd_tripletex_get(args: argparse.Namespace) -> int:
    client, config = tripletex_client_from_config()
    print_response(client.get(args.path, params=parse_filters(args.filter), config=config))
    return 0


def cmd_tripletex_post(args: argparse.Namespace) -> int:
    return tripletex_write_request(args, "POST", args.path, read_json_arg(args), params=parse_filters(args.filter))


def cmd_tripletex_put(args: argparse.Namespace) -> int:
    payload = read_optional_json_arg(args)
    return tripletex_write_request(args, "PUT", args.path, payload, params=parse_filters(args.filter))


def cmd_tripletex_delete(args: argparse.Namespace) -> int:
    return tripletex_write_request(args, "DELETE", args.path, None, params=parse_filters(args.filter))


def cmd_tripletex_pdf(args: argparse.Namespace) -> int:
    paths = {
        "supplier-invoice": f"/supplierInvoice/{args.id}/pdf",
        "voucher": f"/ledger/voucher/{args.id}/pdf",
        "payslip": f"/salary/payslip/{args.id}/pdf",
    }
    client, config = tripletex_client_from_config()
    response = client.get_bytes(paths[args.kind], config=config)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(response.data)
    print_json({"ok": True, "status": response.status, "headers": response.headers, "output": str(output)})
    return 0


def cmd_tripletex_voucher(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    if args.send_to_ledger is not None:
        params["sendToLedger"] = args.send_to_ledger
    return tripletex_write_request(args, "POST", "/ledger/voucher", read_json_arg(args), params=params)


def cmd_tripletex_attach_voucher(args: argparse.Namespace) -> int:
    file_path = checked_file(args.file)
    path = f"/ledger/voucher/{args.voucher_id}/attachment"
    if not args.execute:
        print_json({"ok": True, "dry_run": True, "method": "POST multipart", "path": path, "file": str(file_path)})
        return 0
    client, config = tripletex_client_from_config()
    print_response(client.upload_file(path, file_path, config=config))
    return 0


def cmd_tripletex_supplier_invoice_action(args: argparse.Namespace) -> int:
    params = parse_filters(args.filter)
    if args.action == "add-payment":
        if not args.invoice_id:
            raise ValueError("--invoice-id kreves for add-payment.")
        path = f"/supplierInvoice/{args.invoice_id}/:addPayment"
        method = "POST"
    elif args.invoice_id:
        path = f"/supplierInvoice/{args.invoice_id}/:{args.action}"
        method = "PUT"
    else:
        path = f"/supplierInvoice/:{args.action}"
        method = "PUT"
    return tripletex_write_request(args, method, path, None, params=params)


def cmd_tripletex_invoice_payment(args: argparse.Namespace) -> int:
    return tripletex_write_request(args, "PUT", f"/invoice/{args.invoice_id}/:payment", None, params=parse_filters(args.filter))


def cmd_tripletex_prepare_salary_transaction(args: argparse.Namespace) -> int:
    print_json(prepare_salary_transaction(read_json_arg(args)))
    return 0


def cmd_tripletex_salary_transaction(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    if args.generate_tax_deduction is not None:
        params["generateTaxDeduction"] = args.generate_tax_deduction
    return tripletex_write_request(args, "POST", "/salary/transaction", read_json_arg(args), params=params)


def cmd_tripletex_attach_salary_transaction(args: argparse.Namespace) -> int:
    file_path = checked_file(args.file)
    path = f"/salary/transaction/{args.transaction_id}/attachment"
    if not args.execute:
        print_json({"ok": True, "dry_run": True, "method": "POST multipart", "path": path, "file": str(file_path)})
        return 0
    client, config = tripletex_client_from_config()
    print_response(client.upload_file(path, file_path, config=config))
    return 0


def cmd_unimicro_setup(args: argparse.Namespace) -> int:
    if args.token and args.token_stdin:
        raise ValueError("Bruk enten --token eller --token-stdin.")
    existing = load_config()
    token = read_optional_stdin_or_arg(args.token, args.token_stdin, existing.unimicro_api_token, "UniMicro API-token: ")
    if not token:
        raise ValueError("Mangler UniMicro API-token.")
    existing.unimicro_api_token = token
    existing.unimicro_company_key = args.company_key or existing.unimicro_company_key
    existing.unimicro_api_base_url = args.api_base_url or existing.unimicro_api_base_url or DEFAULT_UNIMICRO_API_BASE_URL
    existing.unimicro_file_base_url = args.file_base_url or existing.unimicro_file_base_url or DEFAULT_UNIMICRO_FILE_BASE_URL
    path = save_config(existing)
    print_json(
        {
            "ok": True,
            "config": str(path),
            "unimicro_company_key": existing.unimicro_company_key,
            "unimicro_api_base_url": existing.unimicro_api_base_url,
            "unimicro_file_base_url": existing.unimicro_file_base_url,
        }
    )
    return 0


def cmd_unimicro_doctor(_: argparse.Namespace) -> int:
    config = load_config()
    token_source = "env" if "UNIMICRO_API_TOKEN" in os.environ else "config" if config.unimicro_api_token else None
    print_json(
        {
            "ok": True,
            "has_token": bool(token_source),
            "token_source": token_source,
            "has_company_key": bool(os.environ.get("UNIMICRO_COMPANY_KEY") or config.unimicro_company_key),
            "api_base_url": resolve_unimicro_api_base_url(config),
            "file_base_url": resolve_unimicro_file_base_url(config),
        }
    )
    return 0


def cmd_unimicro_capabilities(_: argparse.Namespace) -> int:
    print_json(unimicro_capabilities())
    return 0


def cmd_unimicro_list(args: argparse.Namespace) -> int:
    client = unimicro_client_from_config()
    print_response(client.get(UNIMICRO_RESOURCE_ALIASES[args.resource], params=parse_filters(args.filter)))
    return 0


def cmd_unimicro_get(args: argparse.Namespace) -> int:
    print_response(unimicro_client_from_config().get(args.path, params=parse_filters(args.filter)))
    return 0


def cmd_unimicro_post(args: argparse.Namespace) -> int:
    return unimicro_write_request(args, "POST", args.path, read_json_arg(args), params=parse_filters(args.filter))


def cmd_unimicro_put(args: argparse.Namespace) -> int:
    return unimicro_write_request(args, "PUT", args.path, read_optional_json_arg(args), params=parse_filters(args.filter))


def cmd_unimicro_delete(args: argparse.Namespace) -> int:
    return unimicro_write_request(args, "DELETE", args.path, None, params=parse_filters(args.filter))


def cmd_unimicro_prepare_supplier_invoice(args: argparse.Namespace) -> int:
    print_json(prepare_unimicro_supplier_invoice(read_json_arg(args)))
    return 0


def cmd_unimicro_supplier_invoice(args: argparse.Namespace) -> int:
    return unimicro_write_request(args, "POST", "/api/biz/supplierinvoices", read_json_arg(args))


def cmd_unimicro_assign_supplier_invoice(args: argparse.Namespace) -> int:
    return unimicro_write_request(
        args,
        "POST",
        f"/api/biz/supplierinvoices/{args.invoice_id}",
        read_json_arg(args),
        params={"action": "assign-to"},
    )


def cmd_unimicro_prepare_journal_entry(args: argparse.Namespace) -> int:
    candidate = read_json_arg(args)
    accounts = read_json_file_or_empty(args.accounts_json_file)
    vat_types = read_json_file_or_empty(args.vattypes_json_file)
    print_json(prepare_unimicro_journal_entry(candidate, accounts=accounts, vat_types=vat_types))
    return 0


def cmd_unimicro_journal_entry(args: argparse.Namespace) -> int:
    return unimicro_write_request(
        args,
        "POST",
        "/api/biz/journalentries",
        read_json_arg(args),
        params={"action": "book-journal-entries"},
    )


def cmd_unimicro_upload_file(args: argparse.Namespace) -> int:
    file_path = checked_file(args.file)
    fields: dict[str, str | int | bool] = {"FileName": file_path.name}
    if args.caption:
        fields["Caption"] = args.caption
    if args.entity_id:
        fields["EntityID"] = args.entity_id
    if args.entity_type:
        fields["EntityType"] = args.entity_type
    if not args.execute:
        print_json({"ok": True, "dry_run": True, "method": "POST multipart", "path": "/api/file", "file": str(file_path), "fields": fields})
        return 0
    print_response(unimicro_client_from_config().upload_file(file_path, fields=fields))
    return 0


def cmd_unimicro_link_file(args: argparse.Namespace) -> int:
    path = f"/api/biz/files/{args.file_id}"
    params = {"action": "link", "entitytype": args.entity_type, "entityid": args.entity_id}
    return unimicro_write_request(args, "POST", path, None, params=params)


def cmd_unimicro_ocr_file(args: argparse.Namespace) -> int:
    print_response(unimicro_client_from_config().get(f"/api/biz/files/{args.file_id}", params={"action": "ocranalyse"}))
    return 0


def cmd_providers_capabilities(args: argparse.Namespace) -> int:
    result: dict[str, Any] = {"ok": True, "providers": {}}
    if args.provider in (None, "tripletex"):
        text = (
            args.tripletex_openapi_file.read_text(encoding="utf-8")
            if args.tripletex_openapi_file
            else fetch_text_url(TRIPLETEX_OPENAPI_URL)
        )
        result["providers"]["tripletex"] = detect_tripletex_capabilities(text)
    if args.provider in (None, "unimicro"):
        result["providers"]["unimicro"] = unimicro_capabilities()
    print_json(result)
    return 0


def cmd_docs_search(args: argparse.Namespace) -> int:
    results = search_docs(
        args.query,
        limit=args.limit,
        refresh=args.refresh,
        local_only=args.local_only,
    )
    print_json(
        {
            "ok": True,
            "query": args.query,
            "results": results,
            "cache_empty": len(results) == 0 and len(list_docs()) == 0,
            "docs_url": DOCS_URL,
            "help_index_url": HELP_INDEX_URL,
        }
    )
    return 0


def cmd_docs_context(args: argparse.Namespace) -> int:
    print_json(
        {
            "ok": True,
            "query": args.query,
            "contexts": context_for_query(
                args.query,
                limit=args.limit,
                chars=args.chars,
                refresh=args.refresh,
            ),
            "docs_url": DOCS_URL,
        }
    )
    return 0


def cmd_docs_get(args: argparse.Namespace) -> int:
    article = get_help_article(args.slug_or_id, refresh=args.refresh)
    print_json({"ok": True, "article": article})
    return 0


def cmd_docs_accounts(args: argparse.Namespace) -> int:
    print_json(
        {
            "ok": True,
            "query": args.query,
            "org_form": args.org_form,
            "results": search_accounts(
                args.query,
                org_form=args.org_form,
                limit=args.limit,
                refresh=args.refresh,
            ),
            "account_help_url": ACCOUNT_HELP_DATA_URL,
        }
    )
    return 0


def cmd_docs_add(args: argparse.Namespace) -> int:
    if args.text:
        text = args.text
    elif args.text_file:
        text = args.text_file.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    path = add_doc(args.title, args.source_url, text)
    print_json({"ok": True, "store": str(path), "title": args.title, "source_url": args.source_url})
    return 0


def cmd_docs_list(_: argparse.Namespace) -> int:
    print_json({"ok": True, "docs": list_docs(), "docs_url": DOCS_URL})
    return 0


def cmd_docs_url(_: argparse.Namespace) -> int:
    print_json(
        {
            "ok": True,
            "docs_url": DOCS_URL,
            "help_index_url": HELP_INDEX_URL,
            "account_help_url": ACCOUNT_HELP_DATA_URL,
            "api_docs_url": API_DOCS_URL,
        }
    )
    return 0


def cmd_fiken_user(_: argparse.Namespace) -> int:
    client = client_from_config()
    print_response(client.get("/user"))
    return 0


def cmd_fiken_companies(args: argparse.Namespace) -> int:
    client = client_from_config()
    result = client.get_paginated(
        "/companies",
        params=parse_filters(args.filter),
        page=args.page,
        page_size=args.page_size,
        all_pages=args.all,
    )
    print_json(result)
    return 0


def cmd_fiken_list(args: argparse.Namespace) -> int:
    config = load_config()
    company = resolve_company(config, args.company)
    client = client_from_config(config)
    resource = RESOURCE_ALIASES[args.resource]
    params, default_filters = list_params_for_resource(args.resource, args.filter)
    result = client.get_paginated(
        company_path(company, resource),
        params=params,
        page=args.page,
        page_size=args.page_size,
        all_pages=args.all,
    )
    if default_filters:
        result["default_filters"] = default_filters
    print_json(result)
    return 0


def cmd_fiken_get(args: argparse.Namespace) -> int:
    client = client_from_config()
    print_response(client.get(args.path, params=parse_filters(args.filter)))
    return 0


def cmd_ehf_capabilities(args: argparse.Namespace) -> int:
    config = load_config()
    company = resolve_company(config, args.company)
    openapi_text = (
        args.openapi_file.read_text(encoding="utf-8")
        if args.openapi_file
        else fetch_text_url(FIKEN_OPENAPI_URL)
    )
    probed_paths: dict[str, dict[str, Any]] = {}
    if not args.skip_probes:
        client = client_from_config(config)
        for template in KNOWN_EHF_READ_PATHS:
            path = template.replace("{companySlug}", company)
            try:
                response = client.get(path, params={"pageSize": 1})
                probed_paths[template] = {
                    "ok": True,
                    "status": response.status,
                    "data_type": type(response.data).__name__,
                }
            except FikenError as exc:
                probed_paths[template] = {
                    "ok": False,
                    "status": exc.status,
                    "error": str(exc),
                }
    result = detect_ehf_capabilities(openapi_text=openapi_text, probed_paths=probed_paths)
    result["ok"] = True
    result["company"] = company
    result["openapi_url"] = FIKEN_OPENAPI_URL
    print_json(result)
    return 0


def cmd_fiken_post(args: argparse.Namespace) -> int:
    return write_json_request(args, "POST", args.path, read_json_arg(args))


def cmd_fiken_patch(args: argparse.Namespace) -> int:
    params = parse_filters(args.filter)
    if not args.execute:
        print_json({"ok": True, "dry_run": True, "method": "PATCH", "path": args.path, "params": params})
        return 0
    client = client_from_config()
    print_response(client.patch(args.path, params=params))
    return 0


def cmd_upload_inbox(args: argparse.Namespace) -> int:
    config = load_config()
    company = resolve_company(config, args.company)
    file_path = checked_file(args.file)
    fields = {"filename": file_path.name, "name": args.name or file_path.name}
    if args.description:
        fields["description"] = args.description
    path = company_path(company, "inbox")
    if not args.execute:
        print_json({"ok": True, "dry_run": True, "method": "POST multipart", "path": path, "file": str(file_path), "fields": fields})
        return 0
    client = client_from_config(config)
    print_response(client.upload_file(path, file_path, fields=fields))
    return 0


def cmd_attach_purchase(args: argparse.Namespace) -> int:
    config = load_config()
    company = resolve_company(config, args.company)
    file_path = checked_file(args.file)
    fields = {
        "filename": file_path.name,
        "attachToSale": args.attach_to_sale,
        "attachToPayment": args.attach_to_payment,
    }
    path = company_path(company, f"purchases/{args.purchase_id}/attachments")
    if not args.execute:
        print_json({"ok": True, "dry_run": True, "method": "POST multipart", "path": path, "file": str(file_path), "fields": fields})
        return 0
    client = client_from_config(config)
    print_response(client.upload_file(path, file_path, fields=fields))
    return 0


def cmd_create_contact(args: argparse.Namespace) -> int:
    config = load_config()
    company = resolve_company(config, args.company)
    return write_json_request(args, "POST", company_path(company, "contacts"), read_json_arg(args), config=config)


def cmd_invoice_draft(args: argparse.Namespace) -> int:
    config = load_config()
    company = resolve_company(config, args.company)
    return write_json_request(args, "POST", company_path(company, "invoices/drafts"), read_json_arg(args), config=config)


def cmd_prepare_purchase(args: argparse.Namespace) -> int:
    config = load_config()
    company = resolve_company(config, args.company)
    candidate = read_json_arg(args)
    existing_purchases: list[dict[str, Any]] = []
    if not args.skip_duplicates:
        window = duplicate_date_window(candidate.get("date"), args.duplicate_days)
        if window:
            existing_purchases = client_from_config(config).get_paginated(
                company_path(company, "purchases"),
                params={"dateGe": window[0], "dateLe": window[1]},
                page_size=args.page_size,
                all_pages=True,
            )["data"]
    result = prepare_purchase(
        candidate,
        existing_purchases=existing_purchases,
        duplicate_days=args.duplicate_days,
    )
    result["company"] = company
    print_json(result)
    return 0


def cmd_purchase(args: argparse.Namespace) -> int:
    config = load_config()
    company = resolve_company(config, args.company)
    return write_json_request(args, "POST", company_path(company, "purchases"), read_json_arg(args), config=config)


def cmd_reconcile_card_purchases(args: argparse.Namespace) -> int:
    config = load_config()
    company = resolve_company(config, args.company)
    fiken = client_from_config(config)
    folio = folio_client_from_config(config)

    folio_params = {
        "startDate": args.start_date,
        "endDate": args.end_date,
        "includeMerchants": True,
        "includeAgents": True,
        "includeCards": True,
    }
    folio_data = folio.get("/events", params=folio_params).data
    purchases = fiken.get_paginated(
        company_path(company, "purchases"),
        params={"dateGe": args.start_date, "dateLe": args.end_date},
        page_size=args.page_size,
        all_pages=True,
    )["data"]
    purchase_drafts = fiken.get_paginated(
        company_path(company, "purchases/drafts"),
        page_size=args.page_size,
        all_pages=True,
    )["data"]
    inbox_documents = fiken.get_paginated(
        company_path(company, "inbox"),
        page_size=args.page_size,
        all_pages=True,
    )["data"]
    bank_accounts = fiken.get_paginated(
        company_path(company, "bankAccounts"),
        page_size=args.page_size,
        all_pages=True,
    )["data"]
    report = reconcile_card_purchases(
        folio_events=extract_collection(folio_data, "events"),
        purchases=purchases,
        purchase_drafts=purchase_drafts,
        inbox_documents=inbox_documents,
        bank_accounts=bank_accounts,
        start_date=args.start_date,
        end_date=args.end_date,
        max_days_diff=args.max_days_diff,
        only_needs_action=args.only_needs_action,
    )
    report["company"] = company
    print_json(report)
    return 0


def write_json_request(
    args: argparse.Namespace,
    method: str,
    path: str,
    payload: Any,
    *,
    config: Config | None = None,
) -> int:
    if not getattr(args, "execute", False):
        print_json({"ok": True, "dry_run": True, "method": method, "path": path, "json": payload})
        return 0
    client = client_from_config(config)
    if method == "POST":
        print_response(client.post(path, payload))
    else:
        raise ValueError(f"Ikke støttet skriveoperasjon: {method}")
    return 0


def tripletex_write_request(
    args: argparse.Namespace,
    method: str,
    path: str,
    payload: Any | None,
    *,
    params: dict[str, Any] | None = None,
) -> int:
    if not getattr(args, "execute", False):
        print_json(
            {
                "ok": True,
                "dry_run": True,
                "provider": "tripletex",
                "method": method,
                "path": path,
                "params": params or {},
                "json": payload,
                "warning": "Tripletex-write krever eksplisitt bruker-godkjenning før --execute.",
            }
        )
        return 0
    client, config = tripletex_client_from_config()
    if method == "POST":
        print_response(client.post(path, body=payload, params=params, config=config))
    elif method == "PUT":
        print_response(client.put(path, body=payload, params=params, config=config))
    elif method == "DELETE":
        print_response(client.delete(path, params=params, config=config))
    else:
        raise ValueError(f"Ikke støttet Tripletex-write: {method}")
    return 0


def unimicro_write_request(
    args: argparse.Namespace,
    method: str,
    path: str,
    payload: Any | None,
    *,
    params: dict[str, Any] | None = None,
) -> int:
    if not getattr(args, "execute", False):
        print_json(
            {
                "ok": True,
                "dry_run": True,
                "provider": "unimicro",
                "method": method,
                "path": path,
                "params": params or {},
                "json": payload,
                "warning": "UniMicro-write krever eksplisitt bruker-godkjenning før --execute.",
            }
        )
        return 0
    client = unimicro_client_from_config()
    if method == "POST":
        print_response(client.post(path, body=payload, params=params))
    elif method == "PUT":
        print_response(client.put(path, body=payload, params=params))
    elif method == "DELETE":
        print_response(client.delete(path, params=params))
    else:
        raise ValueError(f"Ikke støttet UniMicro-write: {method}")
    return 0


def client_from_config(config: Config | None = None) -> FikenClient:
    config = config or load_config()
    return FikenClient(resolve_token(config))


def folio_client_from_config(config: Config | None = None, *, base_url: str | None = None) -> FolioClient:
    config = config or load_config()
    return FolioClient(
        token=resolve_folio_token(config),
        base_url=resolve_folio_base_url(config, base_url),
    )


def tripletex_client_from_config(
    config: Config | None = None,
    *,
    company_id: str | None = None,
    base_url: str | None = None,
) -> tuple[TripletexClient, Config]:
    config = config or load_config()
    session_token = config.tripletex_session_token if session_is_valid(config.tripletex_session_expires) else None
    client = TripletexClient(
        consumer_token=resolve_tripletex_consumer_token(config),
        employee_token=resolve_tripletex_employee_token(config),
        company_id=resolve_tripletex_company_id(config, company_id),
        base_url=resolve_tripletex_base_url(config, base_url),
        session_token=session_token,
    )
    return client, config


def unimicro_client_from_config(
    config: Config | None = None,
    *,
    company_key: str | None = None,
    api_base_url: str | None = None,
    file_base_url: str | None = None,
) -> UniMicroClient:
    config = config or load_config()
    return UniMicroClient(
        token=resolve_unimicro_api_token(config),
        company_key=resolve_unimicro_company_key(config, company_key),
        api_base_url=resolve_unimicro_api_base_url(config, api_base_url),
        file_base_url=resolve_unimicro_file_base_url(config, file_base_url),
    )


def read_json_arg(args: argparse.Namespace) -> Any:
    if args.json_file:
        return json.loads(args.json_file.read_text(encoding="utf-8"))
    return json.loads(args.json)


def read_optional_json_arg(args: argparse.Namespace) -> Any | None:
    if getattr(args, "json_file", None):
        return json.loads(args.json_file.read_text(encoding="utf-8"))
    if getattr(args, "json", None):
        return json.loads(args.json)
    return None


def read_optional_stdin_or_arg(
    value: str | None,
    stdin_flag: bool,
    fallback: str | None,
    prompt: str,
) -> str | None:
    if stdin_flag:
        return sys.stdin.read().strip()
    if value:
        return value
    if fallback:
        return fallback
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    return None


def read_json_file_or_empty(path: Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("data") or value.get("values") or []
    if not isinstance(value, list):
        raise ValueError(f"Forventet JSON-liste i {path}")
    return [item for item in value if isinstance(item, dict)]


def openapi_url_for_tripletex(base_url: str | None = None) -> str:
    if not base_url:
        return TRIPLETEX_OPENAPI_URL
    return base_url.rstrip("/") + "/openapi.json"


def folio_date_params(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"startDate": args.start_date}
    if args.end_date:
        params["endDate"] = args.end_date
    return params


def extract_collection(data: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        value = data.get(key) or data.get("data") or []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def parse_filters(items: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Filter må være KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        params[key] = parse_value(value)
    return params


def list_params_for_resource(resource: str, filters: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    params = parse_filters(filters)
    default_filters: dict[str, Any] = {}
    if resource == "inbox" and "status" not in params:
        params["status"] = "unused"
        default_filters["status"] = "unused"
    return params, default_filters


def parse_value(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return int(value)
    except ValueError:
        return value


def checked_file(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    return resolved


def fetch_text_url(url: str) -> str:
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(url, timeout=60, context=context) as response:
        return response.read().decode("utf-8", errors="replace")


def print_response(response: Any) -> None:
    print_json({"ok": True, "status": response.status, "headers": response.headers, "data": response.data})


def print_json(data: Any) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
