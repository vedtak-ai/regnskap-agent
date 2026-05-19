from __future__ import annotations

from pathlib import Path


def test_skill_requires_decision_table_for_card_purchases() -> None:
    skill = Path("skills/fiken-regnskap/SKILL.md").read_text(encoding="utf-8")
    assert "beslutningsgrunnlag" in skill
    assert "ikke bare en narrativ oppsummering" in skill
    for column in [
        "Dato",
        "Leverandør",
        "Beløp",
        "Fiken-status",
        "Bilag funnet",
        "Bilagskilde",
        "Konto",
        "MVA",
        "Faktura/kvitteringsnr.",
        "Anbefalt handling",
        "Grunnlag/usikkerhet",
    ]:
        assert column in skill


def test_skill_hides_internal_commands_unless_requested() -> None:
    skill = Path("skills/fiken-regnskap/SKILL.md").read_text(encoding="utf-8")
    assert "Ikke vis interne CLI-kommandoer" in skill
    assert "med mindre brukeren eksplisitt ber om tekniske detaljer" in skill


def test_skill_points_to_purchase_registration_reference() -> None:
    skill = Path("skills/fiken-regnskap/SKILL.md").read_text(encoding="utf-8")
    reference = Path("skills/fiken-regnskap/references/purchase-registration.md").read_text(encoding="utf-8")
    assert "references/purchase-registration.md" in skill
    assert "regnskap fiken prepare-purchase" in skill
    for source in [
        "leverandør-PDF",
        "e-postkvittering",
        "e-postkvittering dokumentert som PDF",
        "Fiken inbox",
        "Fiken EHF",
        "Fiken EHF-varsel",
        "mangler bilag",
    ]:
        assert source in reference
    assert "bare vise åpne eller endrede linjer" in reference


def test_skill_has_single_purchase_pipeline_and_precise_ehf_notice_language() -> None:
    skill = Path("skills/fiken-regnskap/SKILL.md").read_text(encoding="utf-8")
    reference = Path("skills/fiken-regnskap/references/purchase-registration.md").read_text(encoding="utf-8")
    assert "For kjøp, leverandørfaktura, EHF-varsel, kortkjøp og kvitteringsjakt" in skill
    assert "regnskap fiken ehf-capabilities" in skill
    assert "EHF-varsel er metadata/proveniens, ikke originalbilag" in skill
    assert "Ikke lag konkret MVA-splitt fra EHF-varsel alene" in skill
    assert "stopp og be brukeren laste opp/hente PDF-en" in skill
    assert "midlertidig fil under `/tmp`" in skill
    assert "Ikke ta med allerede bokførte kontrollsaker" in skill
    assert "Dette er én konsolidert pipeline" in reference
    assert "skal ikke omtales som originalbilag" in reference
    assert "Ikke lag konkret konto-/MVA-splitt fra EHF-varsel alene" in reference
    assert "skal agenten først prøve vedlagte/lokale filer" in reference
