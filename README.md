<p align="center">
  <img src="images/icona.png" width="128" alt="Pienone">
</p>

<h1 align="center">Pienone per Home Assistant</h1>

<p align="center">
  I prezzi dei carburanti e le colonnine in Italia, per ognuna delle tue auto, dentro Home Assistant.<br>
  <em>Fuel prices and EV chargers in Italy, for each of your cars, inside Home Assistant.</em>
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS"></a>
  <a href="../../actions/workflows/validate.yml"><img src="../../actions/workflows/validate.yml/badge.svg" alt="Validazione"></a>
</p>

<p align="center">
  <a href="#italiano">Italiano</a> · <a href="#english">English</a>
</p>

---

<a id="italiano"></a>

## Italiano

### Cos'è Pienone

**Pienone** è un'app per iPhone con i prezzi dei carburanti di tutti i distributori italiani, presi ogni giorno dai dati
ufficiali del Ministero delle Imprese e del Made in Italy (MIMIT, open data), e le colonnine di ricarica della
Piattaforma Unica Nazionale (PUN). Ti dice dove conviene fare il pieno vicino a te e lungo il viaggio, tiene il diario
dei rifornimenti e funziona anche in CarPlay.

Questa integrazione porta gli stessi dati in **Home Assistant**: sensori per le tue automazioni, le tue plance e i tuoi
avvisi. Funziona da sola; con l'app sincronizzata (facoltativo) conosce anche le tue auto, i preferiti e i viaggi.

L'app è in prova su TestFlight, non ancora sull'App Store; l'integrazione funziona anche senza l'app.

### Cosa trovi in Home Assistant

**Dispositivo «Pienone»** (il principale)

| Entità | Cosa dice |
|---|---|
| `sensor.pienone_piu_conveniente` | Il più conveniente vicino per il carburante della tua **auto attiva** nell'app (per un'auto elettrica: la ricarica, in €/kWh). Senza app: il primo carburante scelto. Attributi: distributore, indirizzo, distanza, coordinate, `portami_li` (Apple Mappe), `dati_mimit_del`, `prezzo_comunicato_il` |
| `sensor.pienone_prezzo_tipico_della_zona` | La mediana dei prezzi nel raggio: il prezzo «normale» della zona |
| `sensor.pienone_tendenza_7_giorni` | Di quanti centesimi è cambiata la media della zona in una settimana |
| `sensor.pienone_consiglio` | Una frase pronta da leggere o da far dire |
| `sensor.pienone_quadro` | Il quadro generale: «2 auto da rifornire presto». Negli attributi, per ogni auto: livello, autonomia, consiglio, dove conviene e prezzo |
| `sensor.pienone_prossimo_viaggio` | Il prossimo viaggio pianificato nell'app (anche dal calendario), con luogo e km |
| `sensor.pienone_auto_attiva`, `sensor.pienone_ultimo_pieno`, `sensor.pienone_sincronizzazione` | Dall'app sincronizzata |
| un sensore per ogni distributore preferito | Il prezzo di oggi; negli attributi i prezzi di tutti i carburanti |

**Un dispositivo per ogni carburante scelto** («Pienone · benzina», «· gasolio», «· GPL», «· metano»): più conveniente,
prezzo tipico, tendenza e consiglio. **«Pienone · elettrico»**: colonnine libere vicine e ricarica più conveniente.

**Un dispositivo per ogni auto** del garage dell'app sincronizzata («Pienone · Panda»…), che compare e sparisce da solo
quando aggiungi o togli un'auto nell'app: livello (batteria per le elettriche), autonomia, km, carburante, il più
conveniente per il *suo* carburante (le colonnine per le elettriche, tutti e due per le ibride plug-in), prezzo tipico,
tendenza, consiglio («Ce la fai fino a Milano e ritorno», «Riserva: fai il pieno presto», «In zona sale…») e il suo
ultimo pieno.

**Eventi**: `pienone_prezzo_sceso` (il più conveniente della zona o un preferito sono scesi almeno della soglia,
per ogni carburante) e `pienone_sotto_soglia` (un avviso di prezzo dell'app è arrivato alla sua soglia).

**Azioni**: `pienone.aggiorna` (rilegge subito) e `pienone.registra_pieno` (un pieno nel diario dell'app, da
confermare: da un'automazione, un tag NFC, il salto del livello del serbatoio).

### Installazione

#### Con HACS (consigliato)

1. HACS › ⋮ › **Repository personalizzati** › incolla l'indirizzo di questo repository, tipo **Integrazione**.
2. Cerca **Pienone**, installa, riavvia Home Assistant.
3. Impostazioni › Dispositivi e servizi › **Aggiungi integrazione** › Pienone.

#### A mano

Copia `custom_components/pienone` nella cartella `custom_components` della configurazione di Home Assistant e riavvia.

### Configurazione

Tutto dall'interfaccia, niente YAML:

- **Carburanti**: benzina, gasolio, GPL, metano ed elettrico, tutti già scelti; togli quelli che non ti servono.
- **Self service** (per benzina e gasolio), **raggio** (1-15 km), **zona** (di partenza la posizione di casa).

Dopo, da **Configura**: carburanti, self, preferiti (se non usi l'app), soglia del calo e raggio.

### Sincronizzazione con l'app (facoltativa)

Nell'app: Le mie auto › un'auto › Home Assistant › **Sincronizza con Home Assistant**. Preferiti, auto, pieni,
preferenze, avvisi di prezzo e viaggi restano uguali nell'app e qui; vince l'ultima modifica.
L'app scrive solo nell'integrazione Pienone, con il tuo utente di Home Assistant (`POST /api/pienone/documento`, che
vuole il token): non comanda mai l'auto né il resto della casa. I dati restano nel tuo Home Assistant
(`.storage/pienone`): niente passa dal server di Pienone.

### Plance, card e automazioni pronte

Nella cartella [`examples/`](examples/), solo card native di Home Assistant (niente card da installare):

- [`plancia-pienone.yaml`](examples/plancia-pienone.yaml): la plancia completa (quadro, zona, una scheda per auto, pieni);
- [`card-singole.yaml`](examples/card-singole.yaml): scheda auto con «Portami lì», zona, ultimo pieno, mappa, elenco;
- [`automazioni.yaml`](examples/automazioni.yaml): «fai il pieno» quando il consiglio lo dice, avviso sotto il 20%,
  promemoria la sera prima di un viaggio.

Negli esempi l'auto si chiama «Panda»: metti il nome della tua (`sensor.pienone_<auto>_livello`).

### Privacy

Al server di Pienone va solo la zona arrotondata a circa 100 metri, per chiedere i prezzi vicini. Nient'altro: le auto,
i pieni e i viaggi restano in Home Assistant e nell'app.

### Supporta Pienone

Pienone è gratuito e senza pubblicità. Se ti è utile, puoi offrire un caffè con [GitHub Sponsors](https://github.com/sponsors/matteoopc).

### Licenza

Codice con licenza MIT (vedi [LICENSE](LICENSE)). Il nome Pienone e l'icona non sono coperti dalla licenza (vedi
[NOTICE](NOTICE)). Dati dei prezzi: MIMIT, open data (IODL 2.0); colonnine: PUN.

---

<a id="english"></a>

## English

### What Pienone is

**Pienone** is an iPhone app with the fuel prices of every Italian station, taken daily from the official open data of
the Italian Ministry of Enterprises (MIMIT), and the EV chargers of the national platform (PUN). This integration brings
the same data into **Home Assistant**. It works on its own; with the app synced (optional) it also knows your cars,
favourites and trips.

The app is in testing on TestFlight, not yet on the App Store; the integration also works without the app.

### What you get

- **«Pienone» device**: cheapest nearby for the fuel of your **active car** in the app (charging in €/kWh for an
  electric car), typical area price, 7-day trend, advice, an **overview** («2 cars to refuel soon») with every car in the
  attributes, next trip, active car, last refuel, a sensor per favourite station.
- **One device per chosen fuel** (petrol, diesel, LPG, CNG) and **«Pienone · electric»** (free chargers nearby,
  cheapest charging).
- **One device per car** of the synced app garage, added and removed automatically: level (battery for EVs), range,
  odometer, fuel, cheapest for *its* fuel, typical price, trend, advice («You'll make it to Milan and back»), last refuel.
- Events `pienone_prezzo_sceso` and `pienone_sotto_soglia`; actions `pienone.aggiorna` and `pienone.registra_pieno`.

### Installation

HACS › ⋮ › **Custom repositories** › this repository's address, type **Integration** › install **Pienone** › restart ›
Settings › Devices & services › **Add integration** › Pienone. Or copy `custom_components/pienone` by hand.

### Configuration

All from the UI: fuels (all pre-selected, including electric), self service, radius, area (defaults to home).
Change them later from **Configure**.

### Sync with the app (optional)

In the app: My cars › a car › Home Assistant › **Sync with Home Assistant**. The app writes only to this integration,
as your Home Assistant user (`POST /api/pienone/documento`, token required); it never controls the car or anything else.
Data stays in your Home Assistant.

### Ready-made dashboards, cards and automations

See [`examples/`](examples/) (native cards only). The example car is called «Panda»: use your car's name.

### Privacy

Only the area, rounded to about 100 m, goes to the Pienone server to ask for nearby prices.

### Support Pienone

Pienone is free and ad-free. If you find it useful, you can buy us a coffee through [GitHub Sponsors](https://github.com/sponsors/matteoopc).

### License

MIT for the code (see [LICENSE](LICENSE)). The Pienone name and icon are not covered (see [NOTICE](NOTICE)).
Price data: MIMIT open data (IODL 2.0); chargers: PUN.
