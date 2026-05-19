# Browser-assistert Onboarding

Bruk denne referansen når brukeren vil sette opp Fiken uten å lage API-token manuelt.

## Arkitektur

Dette skal være en skill-workflow, ikke en underagent. Oppsettet involverer innlogging, 2FA, kontovalg og en hemmelig API-nøkkel. Hovedagenten skal holde brukeren i loopen og ikke delegere live token-håndtering til en bakgrunnsagent.

CLI-en gjør lagring og API-test. Browseren brukes bare til Fiken UI der token må opprettes.

## Sikkerhetsregler

- Be brukeren logge inn selv hvis Fiken krever passord, passkey, BankID, 2FA eller passordhåndterer.
- Ikke åpne eller lese passordhåndterer.
- Ikke opprett betalte abonnementer, API-tilbud, partnerintegrasjoner eller ekstra tjenester.
- Hvis Fiken viser betalte tilvalg, trials, API-avtaler eller samtykker som ikke er nødvendig for et personlig API-token, velg avbryt/nei/hopp over. Hvis valget er uklart, stopp og spør.
- Ikke vis API-token i sluttmeldingen. Lagre det med `regnskap setup --token-stdin`.
- Hvis token vises bare én gang, lagre det før siden lukkes.
- Etter oppsett, test med `regnskap fiken user` og `regnskap fiken companies`.

## Browser-flow

1. Bruk `browser-use:browser` hvis tilgjengelig.
2. Åpne Fiken API-siden:
   ```text
   https://fiken.no/innstillinger/api
   ```
   Hvis den ikke finnes eller redirecter, gå til Fiken innstillinger og søk/naviger til API.
3. Hvis brukeren ikke er logget inn, stopp og si at brukeren må logge inn i nettleservinduet. Fortsett etterpå.
4. Finn personlig API-token eller tilsvarende. Målet er et personlig token for API v2, ikke et betalt partnerprodukt.
5. Opprett token med navn:
   ```text
   regnskap-agent
   ```
6. Hvis siden ber om rettigheter/scopes, velg minimum som kreves for regnskapsworkflowen. Hvis bare full API-tilgang finnes, forklar risikoen og be om bekreftelse før token opprettes.
7. Når token vises, hent token-teksten fra siden eller be brukeren markere/kopiere hvis browseren ikke kan lese feltet.
8. Lagre token via stdin:
   ```bash
   regnskap setup --token-stdin --auto-company
   ```
   Bruk ikke `--token <token>` fordi det kan havne i shell history.
9. Kjør:
   ```bash
   regnskap fiken user
   regnskap fiken companies
   ```
10. Hvis flere selskaper finnes, sett valgt standardbedrift med:
   ```bash
   regnskap setup --company <slug>
   ```
   Ikke be om token på nytt. CLI-en gjenbruker lagret token.

Når default company er satt, dropp `--company` i senere kommandoer. Det sparer tokens og gjør agentflyten mindre skjør.

## Hva som kan automatiseres

Agenten kan åpne nettleseren, navigere, klikke gjennom ikke-sensitive sider, navngi token, avvise tilvalg, kopiere token hvis synlig og lagre det.

Brukeren må fortsatt selv godkjenne innlogging/2FA og bør eksplisitt godkjenne token-opprettelse. Det er riktig sikkerhetsgrense.
