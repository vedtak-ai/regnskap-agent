# Workflow Coverage

Denne CLI-en dekker vanlige Fiken-workflows og gjør write-operasjoner som dry-run som standard.

## Dekket som eksplisitte kommandoer

| Workflow | Kommando |
|---|---|
| Hent bruker | `regnskap fiken user` |
| List selskaper | `regnskap fiken companies` |
| List kontoer | `regnskap fiken list accounts --company <slug>` |
| List bankkontoer | `regnskap fiken list bank-accounts --company <slug>` |
| List bankbalanser | `regnskap fiken list bank-balances --company <slug>` |
| List kontakter | `regnskap fiken list contacts --company <slug>` |
| Opprett kontakt | `regnskap fiken create-contact --company <slug> --json-file contact.json` |
| List fakturaer | `regnskap fiken list invoices --company <slug>` |
| Sjekk EHF/API-kapabilitet | `regnskap fiken ehf-capabilities --company <slug>` |
| Lag fakturautkast | `regnskap fiken invoice-draft --company <slug> --json-file invoice.json` |
| List kjøp | `regnskap fiken list purchases --company <slug>` |
| Preflight for kjøp | `regnskap fiken prepare-purchase --company <slug> --json-file purchase-candidate.json` |
| Opprett kjøp | `regnskap fiken purchase --company <slug> --json-file purchase.json` |
| Last opp inbox-bilag | `regnskap fiken upload-inbox --company <slug> --file bilag.pdf` |
| Legg ved kjøpsbilag | `regnskap fiken attach-purchase --company <slug> --purchase-id <id> --file bilag.pdf` |
| Avstem kortkjøp mot Fiken/Folio | `regnskap reconcile card-purchases --company <slug> --start-date <date> --end-date <date>` |

## Dekket via generisk list

`account-balances`, `credit-notes`, `credit-note-drafts`, `inbox`, `invoice-drafts`, `journal-entries`, `offers`, `offer-drafts`, `order-confirmations`, `products`, `projects`, `purchase-drafts`, `sales`, `sale-drafts`, `time-entries`, `activities`, `time-users`, `transactions`.

## Dekket via rå API-kall

Alt annet som Fiken v2 API-et tilbyr kan nås med:

```bash
regnskap fiken get /path
regnskap fiken post /path --json-file payload.json
regnskap fiken patch /path --filter key=value
```

Rå `post` og `patch` er også dry-run som standard.

## Folio

| Workflow | Kommando |
|---|---|
| Sjekk Folio-oppsett | `regnskap folio doctor` |
| Lagre Folio-token | `regnskap folio setup --token-stdin` |
| List kontoer | `regnskap folio accounts` |
| List transaksjoner | `regnskap folio transactions --start-date <date>` |
| List kontotransaksjoner | `regnskap folio account-transactions <account-number> --start-date <date>` |
| Hent saldo | `regnskap folio balance <account-number> <date>` |
| List events | `regnskap folio events --start-date <date>` |
| List betalinger | `regnskap folio payments --start-date <date>` |
| Opprett betaling som bankutkast | `regnskap folio create-payment --json-file payment.json` |
| Kanseller betaling | `regnskap folio cancel-payment <payment-id>` |
| Hent vedlegg | `regnskap folio attachment <id> --output <file>` |
| Last opp event-vedlegg | `regnskap folio upload-attachment <event-id> --file <file>` |
| Les fra Folio API | `regnskap folio get /path --filter key=value` |

Folio betaling-write og event-vedlegg er dry-run som standard.
Kortkjøpsavstemming er read-only og matcher Folio-events mot Fiken-kjøp, kjøpsutkast og inbox. Den bruker ikke hardkodede merchant-regler for konto eller MVA.

## Ikke løst ennå

- Hard teknisk approval-gate inne i CLI utover `--execute`.
- Automatisk parsing av alle PDF-varianter. Agenten gjør parsing, CLI-en gjør API-kall.
- Andre Folio-write-workflows for overføringer, kortendringer og event-oppdateringer er ikke lagt inn.
- ZP er ikke koblet fordi provider og API ikke er identifisert i arbeidsmappen. Arkitekturen bør utvides med en egen provider når ZP betyr konkret system og autentisering er avklart.
