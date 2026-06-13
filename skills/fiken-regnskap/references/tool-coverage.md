# Workflow Coverage

Denne CLI-en dekker vanlige Fiken-, Folio-, Tripletex- og UniMicro-workflows og gjør write-operasjoner som dry-run som standard.

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

## Tripletex

Start alltid med kapabiliteter når Tripletex er aktuell:

```bash
regnskap tripletex capabilities
```

| Workflow | Kommando |
|---|---|
| Sjekk Tripletex-oppsett | `regnskap tripletex doctor` |
| Lagre Tripletex tokens | `regnskap tripletex setup --consumer-token-stdin --employee-token-stdin` |
| Hent session-info | `regnskap tripletex whoami` |
| List kjent ressurs | `regnskap tripletex list <resource>` |
| Les native API-path | `regnskap tripletex get /path --filter key=value` |
| Rå Tripletex write | `regnskap tripletex post/put/delete /path ...` |
| Last ned PDF | `regnskap tripletex pdf supplier-invoice|voucher|payslip <id> --output <file>` |
| Opprett voucher | `regnskap tripletex voucher --json-file voucher.json` |
| Legg ved voucher-fil | `regnskap tripletex attach-voucher <id> --file <file>` |
| Supplier invoice action | `regnskap tripletex supplier-invoice-action approve|reject|add-payment ...` |
| Forbered salary transaction | `regnskap tripletex prepare-salary-transaction --json-file salary.json` |
| Opprett salary transaction | `regnskap tripletex salary-transaction --json-file salary.json` |
| Legg ved salary-fil | `regnskap tripletex attach-salary-transaction <id> --file <file>` |

Tripletex salary-støtte betyr dokumenterte `salary/transaction`-operasjoner og tilhørende lesedata/vedlegg. Ikke kall dette en komplett lønnskjøring hvis `capabilities` ikke viser et konkret payroll-run-endepunkt.

## UniMicro

Start alltid med kapabiliteter når UniMicro er aktuell:

```bash
regnskap unimicro capabilities
```

| Workflow | Kommando |
|---|---|
| Sjekk UniMicro-oppsett | `regnskap unimicro doctor` |
| Lagre UniMicro token | `regnskap unimicro setup --token-stdin --company-key <key>` |
| List kjent ressurs | `regnskap unimicro list <resource>` |
| Les native API-path | `regnskap unimicro get /path --filter key=value` |
| Rå UniMicro write | `regnskap unimicro post/put/delete /path ...` |
| Forbered supplier invoice | `regnskap unimicro prepare-supplier-invoice --json-file supplier-invoice.json` |
| Opprett supplier invoice | `regnskap unimicro supplier-invoice --json-file supplier-invoice.json` |
| Send supplier invoice til approval | `regnskap unimicro assign-supplier-invoice <id> --json-file approval.json` |
| Forbered journal entry | `regnskap unimicro prepare-journal-entry --json-file journal.json` |
| Book journal entry | `regnskap unimicro journal-entry --json-file journal.json` |
| Last opp fil | `regnskap unimicro upload-file --file <file> --entity-type SupplierInvoice --entity-id <id>` |
| Link fil | `regnskap unimicro link-file <file-id> --entity-type SupplierInvoice --entity-id <id>` |
| OCR-analyser fil | `regnskap unimicro ocr-file <file-id>` |

UniMicro payroll er ikke verifisert som write-støttet i CLI-en. Bruk `capabilities` og faktisk provider-doc før payroll antas.

## Provider-kapabiliteter

| Workflow | Kommando |
|---|---|
| Samlet kapabilitetsrapport | `regnskap providers capabilities` |
| Én provider | `regnskap providers capabilities --provider tripletex|unimicro` |

## Ikke løst ennå

- Hard teknisk approval-gate inne i CLI utover `--execute`.
- Automatisk parsing av alle PDF-varianter. Agenten gjør parsing, CLI-en gjør API-kall.
- Andre Folio-write-workflows for overføringer, kortendringer og event-oppdateringer er ikke lagt inn.
- UniMicro payroll-write er ikke verifisert uten app-/swagger-kontekst.
