from __future__ import annotations

from pathlib import Path
from typing import Any

from .http_client import ApiResponse, JsonApiClient


API_BASE_URL = "https://api.unimicro.no"
FILE_BASE_URL = "https://files.unimicro.no"


UNIMICRO_RESOURCE_ALIASES = {
    "accounts": "/api/biz/accounts",
    "vat-types": "/api/biz/vattypes",
    "suppliers": "/api/biz/suppliers",
    "customers": "/api/biz/customers",
    "contacts": "/api/biz/contacts",
    "products": "/api/biz/products",
    "orders": "/api/biz/orders",
    "invoices": "/api/biz/invoices",
    "supplier-invoices": "/api/biz/supplierinvoices",
    "journal-entries": "/api/biz/journalentries",
    "journal-entry-lines": "/api/biz/journalentrylines",
    "files": "/api/biz/files",
    "users": "/api/biz/users",
    "teams": "/api/biz/teams",
}


class UniMicroClient:
    def __init__(
        self,
        *,
        token: str,
        company_key: str,
        api_base_url: str = API_BASE_URL,
        file_base_url: str = FILE_BASE_URL,
    ) -> None:
        self.token = token
        self.company_key = company_key
        self.api_base_url = api_base_url.rstrip("/")
        self.file_base_url = file_base_url.rstrip("/")

    def api(self) -> JsonApiClient:
        return JsonApiClient(
            provider="UniMicro",
            base_url=self.api_base_url,
            default_headers=self.headers(),
        )

    def file_api(self) -> JsonApiClient:
        return JsonApiClient(
            provider="UniMicro file server",
            base_url=self.file_base_url,
            default_headers=self.headers(),
        )

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "CompanyKey": self.company_key,
            "Accept": "application/json",
            "User-Agent": "regnskap-agent/0.1",
        }

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> ApiResponse:
        return self.api().get(path, params=params)

    def post(self, path: str, *, body: Any | None = None, params: dict[str, Any] | None = None) -> ApiResponse:
        return self.api().post(path, body=body, params=params)

    def put(self, path: str, *, body: Any | None = None, params: dict[str, Any] | None = None) -> ApiResponse:
        return self.api().put(path, body=body, params=params)

    def delete(self, path: str, *, params: dict[str, Any] | None = None) -> ApiResponse:
        return self.api().delete(path, params=params)

    def upload_file(
        self,
        file_path: Path,
        *,
        fields: dict[str, str | bool | int] | None = None,
    ) -> ApiResponse:
        return self.file_api().upload_multipart("/api/file", file_path, fields=fields, file_field="File")


def unimicro_capabilities() -> dict[str, Any]:
    return {
        "ok": True,
        "provider": "unimicro",
        "modules": {
            "supplier_invoices": {
                "read": True,
                "write": True,
                "attachments": True,
                "ocr": True,
                "approval": True,
                "danger_level": "high",
                "endpoints": [
                    "/api/biz/supplierinvoices",
                    "/api/biz/files/SupplierInvoice/{invoiceId}",
                    "/api/biz/files/{fileId}?action=ocranalyse",
                    "/api/biz/supplierinvoices/{invoiceId}?action=assign-to",
                ],
            },
            "journal_entries": {
                "read": True,
                "write": True,
                "attachments": True,
                "danger_level": "high",
                "endpoints": [
                    "/api/biz/journalentries?action=book-journal-entries",
                    "/api/biz/accounts",
                    "/api/biz/vattypes",
                ],
            },
            "sales": {
                "read": True,
                "write": True,
                "attachments": False,
                "danger_level": "medium",
                "endpoints": ["/api/biz/invoices", "/api/biz/orders", "/api/biz/customers", "/api/biz/products"],
            },
            "payroll": {
                "read": "unknown",
                "write": "unknown",
                "attachments": "unknown",
                "danger_level": "critical",
                "endpoints": [],
                "limitations": [
                    "UniMicro developer-portalen viser payroll-modul, men denne CLI-en har ikke verifisert "
                    "native payroll-run-endepunkter uten app-/swagger-kontekst.",
                    "Ikke kjør lønn/payroll i UniMicro før capabilities kan bekreftes mot tilgjengelig API-doc eller token.",
                ],
            },
        },
    }
