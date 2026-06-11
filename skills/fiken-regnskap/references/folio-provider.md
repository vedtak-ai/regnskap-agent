# Folio Provider

Bruk denne når Folio er bankkilden for konto- og transaksjonsdata.

## Kilder

- API-dokumentasjon: `https://api.folio.no/v2/api`
- OpenAPI YAML: `https://api.folio.no/v2/api.yml`
- OAuth2 token exchange: `https://api.folio.no/v2/oauth2.html`
- Standard API base URL: `https://api.folio.no/v2`

Folio API v2 bruker bearer token. Personlig API-nøkkel kan opprettes i Folio på `https://app.folio.no/til/api-tilgang`.

## Oppsett

Lagre token:
```bash
regnskap folio setup --token-stdin
```

Alternativt kan miljøvariabler brukes:
```bash
export FOLIO_API_TOKEN=...
export FOLIO_API_BASE_URL=https://api.folio.no/v2
```

Sjekk konfigurasjon:
```bash
regnskap folio doctor
```

## Lesedata

Kontoer:
```bash
regnskap folio accounts
```

Transaksjoner:
```bash
regnskap folio transactions --start-date 2026-05-01 --end-date 2026-05-31 --include-merchants
regnskap folio transaction <transaction-id>
regnskap folio account-transactions <account-number> --start-date 2026-05-01 --end-date 2026-05-31
```

Saldo:
```bash
regnskap folio balance <account-number> 2026-05-31
```

Events og betalinger:
```bash
regnskap folio events --start-date 2026-05-01 --include-merchants --include-agents --include-cards
regnskap folio payments --start-date 2026-05-01 --include-agents
regnskap folio payment <payment-id>
regnskap folio create-payment --json-file payment.json
regnskap folio cancel-payment <payment-id>
```

Regnskapskategori:
```bash
regnskap folio category <category-id>
```

Vedlegg:
```bash
regnskap folio attachment <attachment-id> --type original --output /abs/path/receipt.pdf
regnskap folio upload-attachment <event-id> --file /abs/path/receipt.pdf
```

Raw read-only kall:
```bash
regnskap folio get /path --filter key=value
```

## Regler

- Betalingsoppretting og kansellering er dry-run som standard. Bruk `--execute` bare etter eksplisitt godkjenning fra brukeren i samme samtale. `create-payment` oppretter Folio-betaling som bankutkast, ikke en generell bankoverføring utenfor Folio sitt betalingsobjekt.
- Ikke initier overføringer, kortendringer eller andre bank-write-operasjoner.
- `upload-attachment` er dry-run som standard. Bruk `--execute` kun etter eksplisitt godkjenning.
- Bruk Folio-data til bankavstemming, transaksjonsoversikt og manglende bilag. Bruk Fiken som regnskapssystem og kilde for bokføringsstatus.
- Ved kortkjøp og kvitteringsjakt, start med `regnskap reconcile card-purchases --start-date <date> --end-date <date> --only-needs-action` for å få en kompakt arbeidsliste på tvers av Folio og Fiken.
- Hvis samme transaksjon finnes både i Folio og Fiken, rapporter differanser heller enn å prøve å rette automatisk.
