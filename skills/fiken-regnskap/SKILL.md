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
- For Folio: bruk bare read-only `regnskap folio get` til API-kontrakten er dokumentert. Ikke initier betalinger eller andre bank-write-operasjoner.
- Folio v2-dokumentasjonen finnes i CLI-en med `regnskap folio docs`. Bruk eksplisitte Folio-kommandoer for kontoer, transaksjoner, events, betalinger som lesedata og vedlegg.

## Vanlige Kommandoer

Lesedata:
```bash
regnskap fiken list accounts
regnskap fiken list contacts --filter supplier=true
regnskap fiken list purchases --filter dateGe=2026-05-01
regnskap fiken list invoices --filter settled=false
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
```

## Workflow

For kvittering eller leverandørfaktura:

1. Les bilaget med egnet verktøy. Hvis `pdftotext` ikke finnes, bruk annen PDF-tekstuttrekking eller be brukeren gi tekst/CSV.
2. Identifiser leverandør, org.nr, fakturanummer, dato, valuta, totalbeløp, MVA og betalingsstatus.
3. Sjekk duplikater i Fiken.
4. Velg tryggeste handling:
   - uklar føring: upload til inbox
   - kundeinntekt: lag fakturautkast
   - klart betalt kjøp: foreslå purchase payload, dry-run, bekreft, execute, attach bilag
5. Rapporter hva som ble gjort og hva som fortsatt krever manuell behandling.

For Vedtak AS, les `references/fiken-workflows.md` ved behov for konto- og MVA-konvensjoner.

## Referanser

- `references/fiken-workflows.md`: Vedtak-spesifikke kontoer, MVA-regler og arbeidsflyter.
- `references/docs-provider.md`: Søk i Fikens hjelpesider, kontohjelp og API-dokumentasjon.
- `references/onboarding.md`: Browser-assistert installasjon, Fiken API-token og trygg håndtering av tilvalg.
- `references/tool-coverage.md`: Hvilke Fiken-workflows som er dekket av CLI-en.
- `references/folio-provider.md`: Folio som bank-provider.
