# Fiken Workflows

## Prinsipp

Foretrekk API og utkast over nettleserautomatisering. Fiken web brukes fortsatt til endelig kontroll, bankavstemming, MVA-melding og alt som krever skjønn eller innlogging utenfor API-et.

## Standard kontoer

| Konto | Bruk |
|---|---|
| 6553 | Programvare og SaaS, for eksempel OpenAI, Anthropic, Google Workspace, Microsoft |
| 6705 | Regnskapsfører og regnskapstjenester |
| 6901 | Telefon og mobil |
| 7140 | Reise |
| 7321 | Markedsføring |
| 4300 | Varekjøp dersom relevant |

## MVA

| Scenario | Fiken MVA-type |
|---|---|
| Norsk leverandør med 25 prosent MVA | `HIGH` |
| Norsk leverandør uten MVA | `NONE` |
| Utenlandsk SaaS/tjeneste uten norsk MVA | `HIGH_FOREIGN_SERVICE_DEDUCTIBLE` |
| Utenlandsk leverandør som fakturerer norsk MVA | Bokfør i NOK med norsk MVA-fordeling hvis Fiken ikke støtter valutalinjer med `HIGH` |

Ikke gjett ved usikker MVA. Stopp og be om regnskapsfaglig avklaring.

## Kjøpsføring

Før kjøp opprettes:

1. Søk etter eksisterende kjøp:
   ```bash
   regnskap fiken list purchases --company <slug> --filter dateGe=YYYY-MM-DD --filter dateLe=YYYY-MM-DD
   ```
2. Søk etter utkast:
   ```bash
   regnskap fiken list purchase-drafts --company <slug>
   ```
3. Søk i inbox:
   ```bash
   regnskap fiken list inbox --company <slug>
   ```
4. Lag JSON-payload og kjør dry-run:
   ```bash
   regnskap fiken purchase --company <slug> --json-file purchase.json
   ```
5. Bare etter godkjenning:
   ```bash
   regnskap fiken purchase --company <slug> --json-file purchase.json --execute
   ```

Bruk `kind: supplier` når leverandør og fakturanummer er kjent. Bruk `cash_purchase` bare for anonyme kvitteringer.

## Fakturautkast

Lag alltid faktura som draft først:

```bash
regnskap fiken invoice-draft --company <slug> --json-file invoice.json
```

Etter execute skal fakturaen fortsatt kontrolleres i Fiken før sending.

## Superføring

Bruk denne CLI-baserte skillen som hovedflyt. Hvis en konkret Fiken UI-flyt ikke dekkes av API-et, skal agenten stoppe og forklare hva som må gjøres manuelt eller lage et trygt utkast der API-et støtter det. Ikke bokfør automatisk.
