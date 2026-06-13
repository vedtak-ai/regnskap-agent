# Regnskap Agent

CLI og Codex-skill for provider-baserte regnskapsworkflows.

Målet er å flytte skjøre regnskapsoperasjoner fra nettleserklikk til en enkel, installerbar CLI. Agenten bruker skillen til å analysere bilag, velge riktig workflow og kjøre CLI-en med `--dry-run` før alle skriveoperasjoner.

## Designvalg

Denne løsningen er en vanlig CLI som kan installeres hos hvem som helst, med eksplisitte kommandoer for de vanligste workflowene og rå `get/post/put/delete` der providerne støtter det. Skillen ligger oppå og gir agenten arbeidsregler, duplikatsjekk og menneske-i-løkken.

## Installer lokalt

Fra denne mappen:

```bash
uv tool install --from . regnskap-agent
```

Alternativt uten global installasjon:

```bash
uv run regnskap --help
```

## Sett opp Fiken

Lag en personlig API-nøkkel i Fiken og kjør:

```bash
regnskap setup --token-stdin --auto-company
regnskap fiken companies
```

Token kan også settes med miljøvariabel:

```bash
export FIKEN_API_TOKEN=...
```

For agentstyrt oppsett bør token sendes via stdin, ikke som shell-argument:

```bash
regnskap setup --token-stdin --auto-company
```

Når Codex-skillen brukes med en tilgjengelig nettleser, kan agenten åpne Fiken, vente mens brukeren logger inn og hjelper deretter med å lage token og lagre det.

Hvis tokenet har tilgang til flere selskaper, velg standard etterpå:

```bash
regnskap setup --company <company-slug>
```

Når standard company er lagret kan kommandoer kjøres uten `--company`.

## Fiken-hjelpesider

CLI-en søker direkte i Fikens hjelpesider uten nettleser. Agenten kan hente relevante artikler som markdown-kontekst før den lager payloads:

```bash
regnskap docs search "mva faktura utlandet"
regnskap docs context "mva faktura utlandet" --limit 2
```

For konto- og MVA-forslag bruker CLI-en Fikens kontohjelp:

```bash
regnskap docs accounts "kontorstol" --org-form AS
```

Det finnes fortsatt en manuell lokal cache med `regnskap docs add/list`, men den er bare et supplement. Hovedkildene er Fikens egne hjelpesider, kontohjelp og API-dokumentasjon.

## Folio

Folio kan settes opp som egen bank-provider. Folio v2-dokumentasjonen ligger på `https://api.folio.no/v2/api`, og standard base URL er `https://api.folio.no/v2`.

```bash
regnskap folio setup --token-stdin
regnskap folio doctor
regnskap folio accounts
regnskap folio transactions --start-date 2026-05-01 --end-date 2026-05-31
regnskap folio account-transactions <account-number> --start-date 2026-05-01
regnskap folio balance <account-number> 2026-05-31
regnskap folio events --start-date 2026-05-01 --include-merchants --include-agents
regnskap folio payments --start-date 2026-05-01 --include-agents
regnskap folio create-payment --json-file payment.json
regnskap folio cancel-payment <payment-id>
```

CLI-en har raw `regnskap folio get /path` for nye read-endepunkter. Betalingsoppretting, kansellering av betalinger og vedlegg på events støttes som dry-run først. Andre bank-write-operasjoner er ikke lagt inn som kommandoer:

```bash
regnskap folio upload-attachment <event-id> --file ./receipt.pdf
```

## Tripletex

Tripletex settes opp som egen provider. Den bruker consumer token og employee token til å hente session token, og session token caches lokalt til utløpsdato.

```bash
regnskap tripletex setup --consumer-token-stdin --employee-token-stdin --company-id 0
regnskap tripletex doctor
regnskap tripletex capabilities
regnskap tripletex list accounts
regnskap tripletex list supplier-invoices
regnskap tripletex list salary-types
regnskap tripletex list payslips
regnskap tripletex list bank-reconciliations
```

Rå API-dekning finnes for nye endepunkter:

```bash
regnskap tripletex get /supplierInvoice
regnskap tripletex post /ledger/voucher --json-file voucher.json
regnskap tripletex put /supplierInvoice/123/:approve --filter comment=ok
```

Alle Tripletex-write-kommandoer er dry-run uten `--execute`. Lønn støttes der Tripletex OpenAPI dokumenterer det, først som `salary/transaction` og vedlegg. CLI-en later ikke som den kan kjøre en komplett lønnskjøring hvis OpenAPI-en ikke har et dokumentert payroll-run-endepunkt.

```bash
regnskap tripletex prepare-salary-transaction --json-file salary.json
regnskap tripletex salary-transaction --json-file salary.json
regnskap tripletex attach-salary-transaction <id> --file ./grunnlag.pdf
```

## UniMicro

UniMicro settes opp med API-token, company key og base URL-er for API og filserver.

```bash
regnskap unimicro setup --token-stdin --company-key <company-key>
regnskap unimicro doctor
regnskap unimicro capabilities
regnskap unimicro list supplier-invoices
regnskap unimicro list journal-entries
regnskap unimicro list accounts
regnskap unimicro list vat-types
```

Før write kan agenten normalisere leverandørfaktura eller journal entry:

```bash
regnskap unimicro prepare-supplier-invoice --json-file supplier-invoice.json
regnskap unimicro prepare-journal-entry --json-file journal.json --accounts-json-file accounts.json --vattypes-json-file vattypes.json
```

Write-kommandoer er dry-run uten `--execute`, inkludert supplier invoice, journal entry, filopplasting, file-link og approval assignment.

```bash
regnskap unimicro supplier-invoice --json-file supplier-invoice.json
regnskap unimicro journal-entry --json-file journal.json
regnskap unimicro upload-file --file ./bilag.pdf --entity-type SupplierInvoice --entity-id 123
regnskap unimicro ocr-file <file-id>
```

## Provider-kapabiliteter

Før agenten bruker Tripletex eller UniMicro bør den hente kapabiliteter:

```bash
regnskap providers capabilities
regnskap providers capabilities --provider tripletex
regnskap providers capabilities --provider unimicro
```

Dette viser hvilke moduler som har read, write, attachments, approval, payroll/salary, bankavstemming og hvilke begrensninger som gjelder.

## Avstemming av kortkjøp

For å unngå at agenten må hente store rå JSON-lister og selv holde hele avstemmingen i kontekst, finnes en samlet read-only rapport for kortkjøp:

```bash
regnskap reconcile card-purchases --start-date 2026-05-01 --end-date 2026-05-31 --only-needs-action
```

Kommandoen henter Folio-events, Fiken-kjøp, kjøpsutkast, inbox og bankkontoer, og matcher på beløp, dato, betalingskonto og tekst. Rapporten markerer blant annet `booked`, `booked_missing_attachment`, `purchase_draft`, `inbox_possible_match`, `ready_to_book` og `missing_receipt`.

Den foreslår ikke konto eller MVA basert på hardkodede merchants. Agenten skal bruke bilaget, Fikens kontohjelp og relevant kontekst for den vurderingen.

## Kjøpsklargjøring

Før kjøp opprettes kan agenten validere og normalisere en strukturert kandidat:

```bash
regnskap fiken prepare-purchase --company <slug> --json-file purchase-candidate.json
```

Kommandoen skriver ikke til Fiken. Den returnerer `ready`, `needs_clarification` eller `blocked`, beregner eller validerer eksplisitt MVA-beløp der det er trygt, viser kontaktstatus, vedleggsstatus og duplikatfunn. Selve opprettelsen skjer fortsatt med separate `create-contact`, `purchase` og `attach-purchase`-kommandoer etter godkjenning.

For EHF-varsler kan agenten sjekke hva som er tilgjengelig i Fiken API:

```bash
regnskap fiken ehf-capabilities --company <slug>
```

Dette skiller mellom at kjøp/kjøpsutkast kan føres via API, og om selve EHF-oversikten er eksponert som dokumentert API-endepunkt.

`regnskap fiken list inbox` viser ubrukte bilag som standard for å unngå støy i agentflyten. Bruk `--filter status=all` for hele inbox-historikken eller `--filter status=used` for brukte bilag.

## Trygg skriveflyt

Alle skrivekommandoer er `dry-run` som standard. Bruk først:

```bash
regnskap fiken upload-inbox --file ./bilag.pdf
```

Når payloaden ser riktig ut:

```bash
regnskap fiken upload-inbox --file ./bilag.pdf --execute
```

## Installer skill

Skillen ligger i `skills/fiken-regnskap`. For lokal Codex:

```bash
mkdir -p ~/.codex/skills
cp -R skills/fiken-regnskap ~/.codex/skills/
```

Den kan også brukes direkte fra prosjektmappen dersom klienten støtter lokale skills.
