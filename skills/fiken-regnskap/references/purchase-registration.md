# Purchase Registration Pipeline

Bruk denne referansen for kjøp, leverandørfaktura, EHF-varsel, kortkjøp og kvitteringsjakt. Dette er én konsolidert pipeline, ikke egne subskills per kilde.

## Rekkefølge

1. Finn kjøpskandidater fra riktig lesekilde: Folio-kort via `reconcile card-purchases`, Fiken via `list inbox` og `list purchase-drafts`, EHF-kapabilitet via `ehf-capabilities`, og Gmail når faktura/kvittering bare er varslet eller sendt der.
2. Les bilag eller varsel før konto, MVA, fakturanummer, KID og forfall vurderes.
3. Vurder konto og MVA fra bilaget/varselet, eksisterende Fiken-kjøp, Fikens kontohjelp og Vedtak-referansen. Ikke bruk merchant-navn alene som grunnlag.
4. Lag én strukturert kjøpskandidat per linje som kan registreres.
5. Kjør kandidaten gjennom `regnskap fiken prepare-purchase`. Bruk `--json` eller midlertidig fil under `/tmp`; ikke lagre interne kandidat- eller payload-filer i Drive/arbeidsmappen med mindre brukeren ber om det. Kommandoen skal gi `ready`, `needs_clarification` eller `blocked`, og returnere normalisert Fiken-payload, MVA-beløp, KID/forfall, kontaktstatus, duplikatfunn, kildeproveniens og vedleggsstatus.
6. Presenter beslutningsgrunnlaget for brukeren. Ikke opprett kontakt, kjøp eller vedlegg før brukeren har godkjent.
7. Etter godkjenning brukes eksisterende skrivekommandoer som egne steg: `create-contact` ved behov, `purchase` og deretter `attach-purchase` hvis det finnes vedlegg.
8. Kontroller etterpå med relevant read-only kommando, for eksempel `reconcile card-purchases` for kortkjøp eller `list purchases` for leverandørfaktura.

## Bilagsproveniens

Bruk presise kategorier i vurderingen og sluttmeldingen:

| Kategori | Bruk |
|---|---|
| `leverandør-PDF` | Original PDF eller faktura/kvittering fra leverandør |
| `e-postkvittering` | Kvitteringen finnes som tekst/HTML i e-post og dette er leverandørens bilag |
| `e-postkvittering dokumentert som PDF` | E-postkvitteringen er gjort om til PDF for vedlegg, uten å late som det er original leverandør-PDF |
| `Fiken inbox` | Bilaget ligger allerede i Fiken inbox |
| `Fiken EHF` | Original EHF eller PDF fra Fiken EHF-oversikten er faktisk hentet |
| `Fiken EHF-varsel` | Varsel fra Fiken med fakturametadata er lest, men original EHF/PDF er ikke hentet |
| `mangler bilag` | Ingen egnet dokumentasjon er funnet |

Airbnb og lignende leverandører kan gi kvittering bare som e-post/HTML. Da er det riktig å beskrive kilden som e-postkvittering eller e-postkvittering dokumentert som PDF, ikke som manglende original PDF.
EHF-varsler fra Fiken er nyttige metadata for leverandør, beløp, fakturanummer, KID og forfall, men skal ikke omtales som originalbilag med mindre original EHF/PDF faktisk er hentet. Ikke lag konkret konto-/MVA-splitt fra EHF-varsel alene.
Hvis Fiken API ikke eksponerer original EHF/PDF, skal agenten først prøve vedlagte/lokale filer, Gmail og eventuelt Fiken web/EHF-oversikten via tilgjengelig browser etter innlogging. Hvis originalen fortsatt mangler, stopp og be brukeren laste opp/hente PDF-en før endelig føring.

## Beslutningsgrunnlag

Når brukeren ber om registrering av kjøp eller kvitteringer, skal sluttmeldingen være tabellarisk og bare vise åpne eller endrede linjer. Ikke ta med allerede bokførte linjer som ikke trenger handling.
Ikke bland inn allerede bokførte kontrollsaker, historiske avvik eller kreditnota-/faktura-forvirring i føringstabellen. Nevn slike saker bare hvis de blokkerer den konkrete føringen eller brukeren eksplisitt spør.

Start med en kort statuslinje med antall `klar til registrering`, `mangler bilag`, `må avklares`, `allerede bokført`, `mulig duplikat` og `endret/opprettet`.

Bruk denne tabellen:

| Dato | Leverandør | Beløp | Fiken-status | Bilag funnet | Bilagskilde | Konto | MVA | Faktura/kvitteringsnr. | Anbefalt handling | Grunnlag/usikkerhet |
|---|---|---:|---|---|---|---|---|---|---|---|
| YYYY-MM-DD | Leverandørnavn | NOK 0,00 | må avklares | delvis | Fiken EHF-varsel | må avklares | må avklares | 12345 | Be bruker laste opp/hente original PDF | Varsel lest, men original EHF/PDF ikke hentet |

Etter tabellen skal neste steg beskrives i vanlig språk. Ikke vis interne CLI-kommandoer, JSON-payloads eller filnavn for payload-filer med mindre brukeren eksplisitt ber om tekniske detaljer.
