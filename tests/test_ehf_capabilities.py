from __future__ import annotations

from regnskap_agent.ehf_capabilities import detect_ehf_capabilities


OPENAPI_WITHOUT_EHF = """
paths:
  /companies/{companySlug}/purchases:
    get: {}
    post: {}
  /companies/{companySlug}/purchases/drafts:
    get: {}
    post: {}
  /companies/{companySlug}/inbox:
    get: {}
    post: {}
"""


def test_ehf_capabilities_report_purchase_support_without_ehf_overview() -> None:
    result = detect_ehf_capabilities(openapi_text=OPENAPI_WITHOUT_EHF)

    assert result["purchase_api_supported"] is True
    assert result["purchase_drafts_supported"] is True
    assert result["inbox_supported"] is True
    assert result["ehf_overview_api_supported"] is False
    assert "Kjøp og kjøpsutkast kan føres via API" in result["notes"][0]


def test_ehf_capabilities_detect_documented_ehf_overview() -> None:
    result = detect_ehf_capabilities(
        openapi_text=OPENAPI_WITHOUT_EHF
        + """
  /companies/{companySlug}/ehf:
    get: {}
"""
    )

    assert result["ehf_overview_api_supported"] is True
    assert result["capabilities"]["ehf_overview"]["paths"] == ["/companies/{companySlug}/ehf"]


def test_ehf_capabilities_can_use_successful_probe() -> None:
    result = detect_ehf_capabilities(
        openapi_text=OPENAPI_WITHOUT_EHF,
        probed_paths={"/companies/{companySlug}/ehf": {"ok": True, "status": 200}},
    )

    assert result["ehf_overview_api_supported"] is True
    assert result["capabilities"]["ehf_overview"]["paths"] == ["/companies/{companySlug}/ehf"]
