---
name: fiken-regnskap
description: "Bruk Regnskap Agent CLI for trygge Fiken- og Folio-regnskapsworkflows: lese Fiken-data, lese bankdata fra Folio når API er konfigurert, laste opp bilag, lage fakturautkast, opprette kontakter, foreslå kjøpsføringer, sjekke duplikater og rapportere regnskapsstatus. Bruk når brukeren nevner Fiken, Folio, regnskap, bilag, kvitteringer, faktura, MVA, bankavstemming, superføring, kjøp, salg, leverandører eller ønsker en CLI-basert agentflyt for regnskap."
---

# Fiken Regnskap

Bruk `regnskap`-CLI-en som deterministisk lag mot Fiken API og, når konfigurert, Folio API. Agenten skal gjøre vurdering, avstemming og kontroll, mens CLI-en skal gjøre API-kallene.

## Oppstart

1. Sjekk at CLI-en finnes:
   ```bash
   regnskap doctor
   ```
2. Hvis kommandoen mangler, finn pakken i arbeidsmappen og kjør lokalt:
   ```bash
   cd ~/gdrive/tools/regnskap-agent && uv run regnskap doctor
   ```
3. Hvis Fiken-token mangler og browser er tilgjengelig, les `references/onboarding.md` og kjør browser-assistert oppsett. Hvis browser ikke er tilgjengelig, be brukeren lage personlig API-token i Fiken og kjøre:
   ```bash
   regnskap setup --token-stdin --auto-company
   ```
4. Hvis `auto_company.status` er `needs_choice`, velg riktig selskap og lagre standard:
   ```bash
   regnskap setup --company <slug>
   ```
5. Finn company slug før andre Fiken-kall hvis default ikke er satt:
   ```bash
   regnskap fiken companies
   ```
6. Hvis Folio skal brukes som bankkilde, sjekk at Folio-provider er konfigurert:
   ```bash
   regnskap folio doctor
   ```

## Sikkerhetsregler

- Kjør alltid skriveoperasjoner uten `--execute` først og vis dry-run til brukeren.
- Før du lager eller endrer payload for kjøp, faktura, MVA, vedlegg eller andre write-operasjoner, hent kontekst fra Fikens hjelpesider med `regnskap docs context "<tema>"`. For konto/MVA-forslag, bruk `regnskap docs accounts "<tema>" --org-form AS`. Les `references/docs-provider.md` ved behov.
- Bruk `--execute` kun etter eksplisitt godkjenning fra brukeren.
- Ikke bokfør automatisk når saken er uklar. Last heller bilag til Fiken inbox eller lag utkast der API-et støtter utkast.
- Sjekk duplikater før kjøp opprettes: søk i `purchases`, `purchase-drafts` og `inbox` på leverandør, dato, beløp og fakturanummer.
- Ved MVA-usikkerhet, forklar usikkerheten og stopp før write.
- For Altinn, MVA-melding, årsoppgjør, lønn, skatt og bankavstemming: hjelp med kontroll og dokumentasjon, men ikke send eller lever på vegne av brukeren.
- For kortkjøp fra Folio: start med `regnskap reconcile card-purchases`, særlig når brukeren ber om kjøp, korttransaksjoner, kvitteringer eller manglende bilag. Bruk rapporten som arbeidsliste før du søker i Gmail eller gjør Fiken-write.
- Ikke hardkod merchant-navn til konto/MVA-regler. Bruk bilaget, Fikens kontohjelp og relevant dokumentasjon for vurderingen.
- For Folio: bruk read-only kommandoer til avstemming og kontroll. Ikke initier betalinger eller andre bank-write-operasjoner.
- Folio v2-dokumentasjonen finnes i CLI-en med `regnskap folio docs`. Bruk eksplisitte Folio-kommandoer for kontoer, transaksjoner, events, betalinger som lesedata og vedlegg.

## Vanlige Kommandoer

Lesedata:
```bash
regnskap fiken list accounts
regnskap fiken list contacts --filter supplier=true
regnskap fiken list purchases --filter dateGe=2026-05-01
regnskap fiken list invoices --filter settled=false
regnskap fiken ehf-capabilities
```

Full API-dekning når en wrapper mangler:
```bash
regnskap fiken get /companies/<slug>/projects
regnskap fiken post /companies/<slug>/contacts --json-file payload.json
```

Bilag til inbox:
```bash
regnskap fiken upload-inbox --file /abs/path/bilag.pdf
regnskap fiken upload-inbox --file /abs/path/bilag.pdf --execute
```

Fakturautkast:
```bash
regnskap fiken invoice-draft --json-file invoice.json
regnskap fiken invoice-draft --json-file invoice.json --execute
```

Kjøp:
```bash
regnskap fiken prepare-purchase --json-file purchase-candidate.json
regnskap fiken purchase --json-file purchase.json
regnskap fiken attach-purchase --purchase-id 123 --file /abs/path/bilag.pdf
```

Folio bankdata:
```bash
regnskap folio doctor
regnskap folio accounts
regnskap folio transactions --start-date 2026-05-01 --end-date 2026-05-31
regnskap folio account-transactions <account-number> --start-date 2026-05-01
regnskap folio events --start-date 2026-05-01 --include-merchants --include-agents
regnskap reconcile card-purchases --start-date 2026-05-01 --end-date 2026-05-31 --only-needs-action
```

Kortkjøpsrapporten matcher Folio-events mot Fiken-kjøp, kjøpsutkast og inbox. Den kan gi status som `booked`, `booked_missing_attachment`, `purchase_draft`, `inbox_possible_match`, `ready_to_book` og `missing_receipt`, samt Gmail-søk for kvittering. Den foreslår ikke konto/MVA basert på merchants.

## Workflow

For kjøp, leverandørfaktura, EHF-varsel, kortkjøp og kvitteringsjakt:

1. Les `references/purchase-registration.md` for den konsoliderte kjøpspipelinen og sluttformatet.
2. Finn kandidaten fra riktig lesekilde: `reconcile card-purchases` for Folio-kort, `list inbox`/`list purchase-drafts` for Fiken, `ehf-capabilities` ved EHF-usikkerhet, og Gmail når faktura/kvittering bare er varslet eller sendt på e-post.
3. Les bilag eller varsel og klassifiser bilagsproveniens. EHF-varsel er metadata/proveniens, ikke originalbilag, med mindre original EHF/PDF faktisk er hentet. Hvis bare EHF-varsel finnes, skal du først prøve vedlagte/lokale filer, Gmail og eventuelt Fiken web/EHF-oversikten; hvis originalen fortsatt mangler, stopp og be brukeren laste opp/hente PDF-en.
4. Bruk Fiken-data, originalbilaget, Fikens kontohjelp og Vedtak-referansen for konto/MVA. Ikke lag konkret MVA-splitt fra EHF-varsel alene; skriv `må avklares` til originalbilaget er lest.
5. Kjør registrerbare kjøpskandidater gjennom `regnskap fiken prepare-purchase` før write-kommandoer. Bruk `--json` direkte eller en midlertidig fil under `/tmp`; ikke lagre interne kandidat- eller payload-filer i Drive/arbeidsmappen med mindre brukeren ber om det. Preflighten normaliserer Fiken-payload, MVA-beløp, KID/forfall, kontaktstatus, duplikatfunn og vedleggsstatus, men skriver ingenting.
6. Avslutt med et beslutningsgrunnlag, ikke bare en narrativ oppsummering. Tabellen skal bare inneholde linjer som fortsatt trenger brukerens beslutning/handling eller linjer som faktisk ble endret/opprettet.
7. Ikke ta med allerede bokførte kontrollsaker, historiske avvik eller kreditnota-/faktura-forvirring i føringstabellen når brukeren ber om å føre nye fakturaer. Nevn dem bare hvis de blokkerer den konkrete føringen eller brukeren eksplisitt spør.
8. Bruk presis bilagskilde i tabellen: `leverandør-PDF`, `e-postkvittering`, `e-postkvittering dokumentert som PDF`, `Fiken inbox`, `Fiken EHF`, `Fiken EHF-varsel` eller `mangler bilag`.
9. Tabellen skal ha disse kolonnene:

| Dato | Leverandør | Beløp | Fiken-status | Bilag funnet | Bilagskilde | Konto | MVA | Faktura/kvitteringsnr. | Anbefalt handling | Grunnlag/usikkerhet |
|---|---|---:|---|---|---|---|---|---|---|---|
| YYYY-MM-DD | Leverandørnavn | NOK 0,00 | må avklares | delvis | Fiken EHF-varsel | må avklares | må avklares | 12345 | Be bruker laste opp/hente original PDF | Varsel lest, men original EHF/PDF ikke hentet |

Etter tabellen skal neste steg beskrives i vanlig språk. Ikke vis interne CLI-kommandoer, JSON-payloads eller filnavn for payload-filer med mindre brukeren eksplisitt ber om tekniske detaljer.

For Vedtak AS, les `references/fiken-workflows.md` ved behov for konto- og MVA-konvensjoner.

## Referanser

- `references/fiken-workflows.md`: Vedtak-spesifikke kontoer, MVA-regler og arbeidsflyter.
- `references/purchase-registration.md`: Runbook for kortkjøp, kjøpsregistrering, bilagsproveniens og beslutningstabell.
- `references/docs-provider.md`: Søk i Fikens hjelpesider, kontohjelp og API-dokumentasjon.
- `references/onboarding.md`: Browser-assistert installasjon, Fiken API-token og trygg håndtering av tilvalg.
- `references/tool-coverage.md`: Hvilke Fiken-workflows som er dekket av CLI-en.
- `references/folio-provider.md`: Folio som bank-provider.
