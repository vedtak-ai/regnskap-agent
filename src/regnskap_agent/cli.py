from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any

from .config import (
    Config,
    DEFAULT_FOLIO_BASE_URL,
    load_config,
    resolve_company,
    resolve_folio_base_url,
    resolve_folio_token,
    resolve_token,
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
from .fiken import FikenClient, FikenError, company_path
from .folio import API_DOCS_URL as FOLIO_API_DOCS_URL
from .folio import OPENAPI_URL as FOLIO_OPENAPI_URL
from .folio import FolioClient, FolioError


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

    config = Config(
        token=token,
        default_company=args.company or existing.default_company,
        folio_token=existing.folio_token,
        folio_base_url=existing.folio_base_url,
    )
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
    token_source = "env" if "FIKEN_API_TOKEN" in __import__("os").environ else "config" if config.token else None
    folio_token_source = (
        "env" if "FOLIO_API_TOKEN" in __import__("os").environ else "config" if config.folio_token else None
    )
    folio_base_source = "env" if "FOLIO_API_BASE_URL" in __import__("os").environ else "config" if config.folio_base_url else "default"
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

    config = Config(
        token=existing.token,
        default_company=existing.default_company,
        folio_token=token,
        folio_base_url=base_url,
    )
    path = save_config(config)
    print_json({"ok": True, "config": str(path), "folio_base_url": base_url})
    return 0


def cmd_folio_doctor(_: argparse.Namespace) -> int:
    config = load_config()
    token_source = "env" if "FOLIO_API_TOKEN" in __import__("os").environ else "config" if config.folio_token else None
    base_url_source = "env" if "FOLIO_API_BASE_URL" in __import__("os").environ else "config" if config.folio_base_url else "default"
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
    result = client.get_paginated(
        company_path(company, resource),
        params=parse_filters(args.filter),
        page=args.page,
        page_size=args.page_size,
        all_pages=args.all,
    )
    print_json(result)
    return 0


def cmd_fiken_get(args: argparse.Namespace) -> int:
    client = client_from_config()
    print_response(client.get(args.path, params=parse_filters(args.filter)))
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


def cmd_purchase(args: argparse.Namespace) -> int:
    config = load_config()
    company = resolve_company(config, args.company)
    return write_json_request(args, "POST", company_path(company, "purchases"), read_json_arg(args), config=config)


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


def client_from_config(config: Config | None = None) -> FikenClient:
    config = config or load_config()
    return FikenClient(resolve_token(config))


def folio_client_from_config(config: Config | None = None, *, base_url: str | None = None) -> FolioClient:
    config = config or load_config()
    return FolioClient(
        token=resolve_folio_token(config),
        base_url=resolve_folio_base_url(config, base_url),
    )


def read_json_arg(args: argparse.Namespace) -> Any:
    if args.json_file:
        return json.loads(args.json_file.read_text(encoding="utf-8"))
    return json.loads(args.json)


def folio_date_params(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"startDate": args.start_date}
    if args.end_date:
        params["endDate"] = args.end_date
    return params


def parse_filters(items: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Filter må være KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        params[key] = parse_value(value)
    return params


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


def print_response(response: Any) -> None:
    print_json({"ok": True, "status": response.status, "headers": response.headers, "data": response.data})


def print_json(data: Any) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
