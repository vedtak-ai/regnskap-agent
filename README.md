# Regnskap Agent

CLI og Codex-skill for Fiken-baserte regnskapsworkflows.

Målet er å flytte skjøre regnskapsoperasjoner fra nettleserklikk til en enkel, installerbar CLI. Agenten bruker skillen til å analysere bilag, velge riktig workflow og kjøre CLI-en med `--dry-run` før alle skriveoperasjoner.

## Designvalg

Denne løsningen er en vanlig CLI som kan installeres hos hvem som helst, med eksplisitte kommandoer for de vanligste workflowene og rå `get/post/patch` for full Fiken API-dekning. Skillen ligger oppå og gir agenten arbeidsregler, duplikatsjekk og menneske-i-løkken.

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
```

CLI-en har raw `regnskap folio get /path` for nye read-endepunkter. Betalingsoppretting og andre bank-write-operasjoner er ikke lagt inn som kommandoer. Vedlegg på events støttes som dry-run først:

```bash
regnskap folio upload-attachment <event-id> --file ./receipt.pdf
```

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
