from __future__ import annotations

import re
from typing import Any


KNOWN_EHF_READ_PATHS = [
    "/companies/{companySlug}/ehf",
    "/companies/{companySlug}/ehfs",
    "/companies/{companySlug}/incomingInvoices",
    "/companies/{companySlug}/supplierInvoices",
    "/companies/{companySlug}/purchaseInvoices",
]


def detect_ehf_capabilities(
    *,
    openapi_text: str | None = None,
    probed_paths: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    paths = extract_openapi_paths(openapi_text or "")
    ehf_paths = [
        path
        for path in paths
        if path.startswith("/companies/{companySlug}/") and "ehf" in path.lower()
    ]
    probed_paths = probed_paths or {}
    probed_ehf_paths = [
        path
        for path, result in probed_paths.items()
        if int(result.get("status") or 0) == 200
    ]
    ehf_overview_paths = ehf_paths or probed_ehf_paths

    return {
        "purchase_api_supported": "/companies/{companySlug}/purchases" in paths,
        "purchase_drafts_supported": "/companies/{companySlug}/purchases/drafts" in paths,
        "inbox_supported": "/companies/{companySlug}/inbox" in paths,
        "ehf_overview_api_supported": bool(ehf_overview_paths),
        "capabilities": {
            "purchases": {
                "supported": "/companies/{companySlug}/purchases" in paths,
                "path": "/companies/{companySlug}/purchases",
            },
            "purchase_drafts": {
                "supported": "/companies/{companySlug}/purchases/drafts" in paths,
                "path": "/companies/{companySlug}/purchases/drafts",
            },
            "inbox": {
                "supported": "/companies/{companySlug}/inbox" in paths,
                "path": "/companies/{companySlug}/inbox",
            },
            "ehf_overview": {
                "supported": bool(ehf_overview_paths),
                "paths": ehf_overview_paths,
            },
        },
        "probed_paths": probed_paths,
        "notes": notes_for_capabilities(bool(ehf_overview_paths)),
    }


def extract_openapi_paths(openapi_text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"^\s{1,4}(/[^:\n]+):\s*$", openapi_text, re.MULTILINE)
    }


def notes_for_capabilities(ehf_overview_supported: bool) -> list[str]:
    if ehf_overview_supported:
        return [
            "Fiken API ser ut til å eksponere en EHF-oversikt. Bruk dokumentert read-endepunkt før browser/UI.",
            "Kjøp kan fortsatt føres via purchases eller purchase drafts etter godkjenning.",
        ]
    return [
        "Kjøp og kjøpsutkast kan føres via API, men OpenAPI viser ikke et dokumentert EHF-oversikt-endepunkt.",
        "EHF-varsel kan brukes som metadata/proveniens, men er ikke original EHF/PDF med mindre originalen faktisk hentes.",
    ]
