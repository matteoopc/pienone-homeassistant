# Pienone per Home Assistant — per chi sviluppa

## Il contratto fra l'app e l'integrazione (stabile e versionato)

Regola: **una modifica all'integrazione non deve mai richiedere una nuova versione dell'app.**

L'app manda il suo **documento completo** e l'integrazione calcola tutto il resto: sensori, consigli, dispositivi,
quadro, card. Il documento è lo stesso dell'account di Pienone, con queste chiavi di primo livello:

| Chiave | Cosa c'è |
|---|---|
| `garage` | le auto: `id`, `nome`, `carburante` (benzina, gasolio, gpl, metano), `elettrica`, `ibridaPlugin`, `livello` (0…1), `livelloDel`, `fonte`, `autonomiaKm`, `km`, `capacitaLitri`, `consumoMedio`, `batteriaKwh`, `consumoKwh`, `caricaBatteria`, `autonomiaElettricaKm`, `self_`, `marca`, `modello`, `modificato` |
| `preferiti` | i distributori preferiti: `id` (MIMIT), `titolo`, `posizione`… |
| `diario` | i pieni: `id`, `data`, `litri`, `euro`, `km`, `autoID`, `distributore`, `daConfermare`, `automatico`… |
| `viaggi` | i viaggi pianificati: `titolo`, `luogo`, `data`, `km`, `andataRitorno`, `daCalendario`… |
| `avvisi` | gli avvisi di prezzo: `impianto`, `carburante`, `self`, `soglia` |
| `valori` | le impostazioni (`autoAttiva`, `carburante`, `self`, `raggio`…), ognuna `{json, modificato}` |
| `scelte`, `zona`, `auto`, `preferenze`, `cancellati` | come nell'account |

Le date sono secondi dal 1° gennaio 2001 (come le manda l'app); `aggiornato` del documento è ISO 8601.

### Le regole

1. **Si aggiungono campi, mai si tolgono o si rinominano.** Un campo che non serve più resta (anche vuoto).
2. **L'integrazione legge le versioni vecchie e quelle nuove**: ogni campo è facoltativo, con un ripiego sensato.
3. **Il trasporto è versionato**: il sensore `sensor.pienone_sincronizzazione` ha l'attributo `versione`.
   `2` = l'app scrive su `POST /api/pienone/documento` (col token dell'utente). L'app sceglie in base a quel numero e
   resta compatibile con le versioni precedenti.
4. **Una nuova build dell'app serve solo se l'app deve mandare un dato che oggi non manda.** In quel caso il campo si
   prevede in anticipo e va nella build già in programma: mai una build solo per Home Assistant.
5. Le unioni per elemento le fa l'app; qui vince il documento più recente e le chiavi che non arrivano restano.

## Prove

- `python3 prove_pienone.py`: le regole pure (`logica.py`), senza Home Assistant.
- `python -m pytest -q`: l'integrazione dentro Home Assistant vero (`pytest-homeassistant-custom-component`, Python 3.14),
  con il server finto: configurazione, dispositivi per auto, quadro, sicurezza dell'indirizzo, id degli esempi.
