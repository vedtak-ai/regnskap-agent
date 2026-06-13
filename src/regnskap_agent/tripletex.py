from __future__ import annotations

import base64
import json
import ssl
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import certifi

from .config import Config, save_config
from .http_client import ApiResponse, JsonApiClient, decode_body


BASE_URL = "https://tripletex.no/v2"
TEST_BASE_URL = "https://api-test.tripletex.tech/v2"
OPENAPI_URL = "https://tripletex.no/v2/openapi.json"


TRIPLETEX_RESOURCE_ALIASES = {
    "accounts": "/ledger/account",
    "vat-types": "/ledger/vatType",
    "suppliers": "/supplier",
    "customers": "/customer",
    "invoices": "/invoice",
    "supplier-invoices": "/supplierInvoice",
    "supplier-invoices-for-approval": "/supplierInvoice/forApproval",
    "vouchers": "/ledger/voucher",
    "non-posted-vouchers": "/ledger/voucher/>nonPosted",
    "voucher-reception": "/ledger/voucher/>voucherReception",
    "bank-accounts": "/bank",
    "bank-statements": "/bank/statement",
    "bank-statement-transactions": "/bank/statement/transaction",
    "bank-reconciliations": "/bank/reconciliation",
    "employees": "/employee",
    "employments": "/employee/employment",
    "salary-types": "/salary/type",
    "salary-transactions": "/salary/transaction",
    "payslips": "/salary/payslip",
    "salary-compilation": "/salary/compilation",
    "salary-settings": "/salary/settings",
    "travel-expenses": "/travelExpense",
}


class TripletexClient:
    def __init__(
        self,
        *,
        consumer_token: str,
        employee_token: str,
        company_id: str = "0",
        base_url: str = BASE_URL,
        session_token: str | None = None,
    ) -> None:
        self.consumer_token = consumer_token
        self.employee_token = employee_token
        self.company_id = company_id or "0"
        self.base_url = base_url.rstrip("/")
        self.session_token = session_token

    def ensure_session_token(self, *, config: Config | None = None) -> str:
        if self.session_token:
            return self.session_token
        expires = (date.today() + timedelta(days=30)).isoformat()
        token = self.create_session_token(expires)
        self.session_token = token
        if config is not None:
            config.tripletex_session_token = token
            config.tripletex_session_expires = expires
            save_config(config)
        return token

    def create_session_token(self, expiration_date: str) -> str:
        params = {
            "consumerToken": self.consumer_token,
            "employeeToken": self.employee_token,
            "expirationDate": expiration_date,
        }
        url = self.base_url + "/token/session/:create?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "regnskap-agent/0.1"},
            method="PUT",
        )
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(req, timeout=60, context=context) as response:
            data = decode_body(response.read())
        if not isinstance(data, dict):
            raise RuntimeError(f"Tripletex session token mangler i respons: {data}")
        token = data.get("token") or data.get("value", {}).get("token")
        if not token:
            raise RuntimeError(f"Tripletex session token mangler i respons: {data}")
        return str(token)

    def authed(self, *, config: Config | None = None) -> JsonApiClient:
        token = self.ensure_session_token(config=config)
        auth = base64.b64encode(f"{self.company_id}:{token}".encode("utf-8")).decode("ascii")
        return JsonApiClient(
            provider="Tripletex",
            base_url=self.base_url,
            default_headers={
                "Authorization": f"Basic {auth}",
                "Accept": "application/json",
                "User-Agent": "regnskap-agent/0.1",
            },
        )

    def get(self, path: str, *, params: dict[str, Any] | None = None, config: Config | None = None) -> ApiResponse:
        return self.authed(config=config).get(path, params=params)

    def post(
        self,
        path: str,
        *,
        body: Any | None = None,
        params: dict[str, Any] | None = None,
        config: Config | None = None,
    ) -> ApiResponse:
        return self.authed(config=config).post(path, body=body, params=params)

    def put(
        self,
        path: str,
        *,
        body: Any | None = None,
        params: dict[str, Any] | None = None,
        config: Config | None = None,
    ) -> ApiResponse:
        return self.authed(config=config).put(path, body=body, params=params)

    def delete(self, path: str, *, params: dict[str, Any] | None = None, config: Config | None = None) -> ApiResponse:
        return self.authed(config=config).delete(path, params=params)

    def get_bytes(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        config: Config | None = None,
    ) -> ApiResponse:
        return self.authed(config=config).get_bytes(path, params=params)

    def upload_file(
        self,
        path: str,
        file_path: Path,
        *,
        fields: dict[str, str | bool | int] | None = None,
        params: dict[str, Any] | None = None,
        config: Config | None = None,
    ) -> ApiResponse:
        return self.authed(config=config).upload_multipart(path, file_path, fields=fields, params=params)


def session_is_valid(expires: str | None) -> bool:
    if not expires:
        return False
    try:
        # Tripletex expires at midnight on the expiration date, so today's date is not safe.
        return date.fromisoformat(expires[:10]) > date.today()
    except ValueError:
        return False


def detect_tripletex_capabilities(openapi: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(openapi, str):
        openapi = json.loads(openapi)
    paths = set((openapi.get("paths") or {}).keys())

    def has(path: str, method: str | None = None) -> bool:
        if path not in openapi.get("paths", {}):
            return False
        if method is None:
            return True
        return method.lower() in openapi["paths"][path]

    def any_prefix(prefix: str) -> list[str]:
        return sorted(path for path in paths if path.startswith(prefix))

    modules: dict[str, Any] = {
        "supplier_invoices": {
            "read": has("/supplierInvoice", "get"),
            "write": (
                has("/supplierInvoice/{invoiceId}/:addPayment", "post")
                or has("/supplierInvoice/{invoiceId}/:approve", "put")
                or has("/supplierInvoice/{invoiceId}/:reject", "put")
                or has("/supplierInvoice/{invoiceId}/:changeDimension", "put")
            ),
            "approval": has("/supplierInvoice/:approve", "put") or has("/supplierInvoice/{invoiceId}/:approve", "put"),
            "attachments": has("/supplierInvoice/{invoiceId}/pdf", "get"),
            "danger_level": "medium",
            "endpoints": [p for p in sorted(paths) if p.startswith("/supplierInvoice")],
        },
        "vouchers": {
            "read": has("/ledger/voucher", "get"),
            "write": has("/ledger/voucher", "post"),
            "attachments": has("/ledger/voucher/{voucherId}/attachment", "post"),
            "danger_level": "high",
            "endpoints": [p for p in sorted(paths) if p.startswith("/ledger/voucher")],
        },
        "invoices": {
            "read": has("/invoice", "get"),
            "write": has("/invoice", "post"),
            "attachments": has("/invoice/{invoiceId}/pdf", "get"),
            "danger_level": "medium",
            "endpoints": [p for p in sorted(paths) if p.startswith("/invoice")][:20],
        },
        "bank_reconciliation": {
            "read": has("/bank/reconciliation", "get") or has("/bank/statement", "get"),
            "write": has("/bank/reconciliation", "post") or has("/bank/statement/import", "post"),
            "danger_level": "high",
            "endpoints": [p for p in sorted(paths) if p.startswith("/bank/")],
        },
        "travel_expense": {
            "read": bool(any_prefix("/travelExpense")),
            "write": has("/travelExpense", "post"),
            "attachments": has("/travelExpense/{travelExpenseId}/attachment", "post"),
            "danger_level": "high",
            "endpoints": any_prefix("/travelExpense")[:30],
        },
        "salary": {
            "read": has("/salary/payslip", "get") or has("/salary/compilation", "get"),
            "write": has("/salary/transaction", "post"),
            "attachments": has("/salary/transaction/{id}/attachment", "post"),
            "payroll_run": any("payrollrun" in path.lower() for path in paths),
            "danger_level": "critical",
            "endpoints": any_prefix("/salary") + [p for p in sorted(paths) if "salaryType" in p],
            "limitations": [
                "Dokumentert API viser salary transactions, payslips og avstemming.",
                "Ikke kall dette en full lønnskjøring uten eget dokumentert payroll-run-endepunkt.",
                "Ingen Altinn/A-melding/ID-porten submission støttes av CLI-en.",
            ],
        },
    }
    return {
        "ok": True,
        "provider": "tripletex",
        "openapi_version": (openapi.get("info") or {}).get("version"),
        "modules": modules,
    }
