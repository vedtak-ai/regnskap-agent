# Fiken Docs Provider

Bruk denne når agenten trenger veiledning fra Fikens faktiske hjelpesider eller kontohjelp.

## Struktur

Dette er en docs-provider i samme skill og CLI, ikke en subskill eller underagent. Agenten skal hente relevant kontekst deterministisk før den velger konto, MVA-kode eller lager payload.

## Kilder

- Fiken hjelpesenter: `https://hjelp.fiken.no/api/hjelpeartikler/fuse-index`
- Fiken artikkel-markdown: `https://hjelp.fiken.no/api/hjelpeartikler/markdown/<slug>`
- Fiken kontohjelp: `https://kontohjelp.fiken.no/data/kontoGruppeInfo`
- Fiken API-dokumentasjon: `https://fiken.no/api/v2/documentation`

## Kommandoer

Søk etter relevante hjelpesider:
```bash
regnskap docs search "faktura mva utlandet"
```

Hent toppartikler som markdown-kontekst:
```bash
regnskap docs context "faktura mva utlandet" --limit 2
```

Hent en spesifikk artikkel:
```bash
regnskap docs get faktura-paa-frakt-toll-og-mva-ved-import-fra-utlandet
```

Søk i Fikens kontohjelp:
```bash
regnskap docs accounts "kontorstol" --org-form AS
```

Vis kildene CLI-en bruker:
```bash
regnskap docs url
```

## Workflow

1. Når spørsmålet gjelder regnskapsføring, MVA, betaling, faktura, vedlegg eller feilretting, kjør:
   ```bash
   regnskap docs context "<tema>"
   ```
2. Når spørsmålet gjelder riktig konto eller MVA-koder for en konto, kjør:
   ```bash
   regnskap docs accounts "<vare/tjeneste/kontonummer>" --org-form AS
   ```
3. Bruk `source_url`, `valid_vat_codes`, `default_vat_code` og markdown-teksten som kontekst for vurderingen.
4. Hvis resultatene er svake, prøv 2-3 mer konkrete søk før du spør brukeren.
5. Bruk `--refresh` hvis svaret virker utdatert eller cachen er gammel.

## Regler

- Ikke bruk nettleser til å søke i Fikens hjelpesider. CLI-en gjør HTTP-oppslaget direkte.
- Ikke søk i kundens Fiken-data når målet er dokumentasjon. Kundedata brukes først etter at relevant veiledning er hentet.
- Ikke stol på intern hukommelse for `vatType`, MVA, konto, attachments, draft-endpoints eller feilretting når Fiken-hjelp kan sjekkes.
- Ikke kopier store deler av dokumentasjonen inn i skillen. Hent kontekst med `regnskap docs context`.
- Fikens hjelpesider, kontohjelp og API-dokumentasjon er fasit for regnskapsveiledning og payload-detaljer.
