"""Prove delle regole dell'integrazione (logica.py), senza Home Assistant. Da questa cartella: python3 prove_pienone.py"""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("logica", "custom_components/pienone/logica.py")
logica = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logica)

fatte = fallite = 0


def uguale(a, b, nome):
    global fatte, fallite
    fatte += 1
    if a != b:
        fallite += 1
        print(f"FALLITA — {nome}: {a!r} ≠ {b!r}")


auchan = {"id": 1001, "nome": "Centro", "bandiera": "Auchan", "prezzo": 1.979, "distanza_km": 4.99,
          "piu_conveniente": True, "da_verificare": False}
bianca = {"id": 1, "nome": "STAZIONE ROSSI", "bandiera": "Pompe Bianche", "prezzo": 1.9, "da_verificare": True}
q8 = {"id": 1002, "nome": "ROMA", "bandiera": "Q8", "prezzo": 1.989, "distanza_km": 2, "da_verificare": False}

uguale(logica.euro_litro(1.979), "1,979 €/L", "euro al litro")
uguale(logica.titolo(auchan), "Auchan", "titolo: la bandiera")
uguale(logica.titolo(bianca), "Stazione Rossi", "titolo: pompa bianca col nome")
uguale(logica.migliore({"impianti": [q8, auchan]}), auchan, "migliore: quello segnato dal server")
uguale(logica.migliore({"impianti": [bianca, q8]}), q8, "migliore: salta i prezzi da verificare")
uguale(logica.migliore({"impianti": []}), None, "migliore: zona vuota")

scheda = {"prezzi": [{"famiglia": "benzina", "self": 1, "prezzo": 1.99}, {"famiglia": "benzina", "self": 0, "prezzo": 2.19},
                     {"famiglia": "gpl", "self": 0, "prezzo": 0.799}]}
uguale(logica.prezzo_scheda(scheda, "benzina", True), 1.99, "scheda: self")
uguale(logica.prezzo_scheda(scheda, "benzina", False), 2.19, "scheda: servito")
uguale(logica.prezzo_scheda(scheda, "gpl", True), 0.799, "scheda: il GPL è sempre servito")
uguale(logica.prezzo_scheda(scheda, "metano", True), None, "scheda: carburante che non ha")

t_su = {"sufficiente": True, "zona_diff_cent": 2.14}
t_giu = {"sufficiente": True, "zona_diff_cent": -1.5}
t_fermo = {"sufficiente": True, "zona_diff_cent": 0.3}
uguale(logica.consiglio(auchan, t_su, "benzina"),
       "In zona la benzina sale (+2,1 cent in 7 giorni): conviene fare il pieno presto. Il più conveniente: Auchan a 1,979 €/L.",
       "consiglio: sale")
uguale(logica.consiglio(auchan, t_giu, "gasolio").startswith("In zona il gasolio scende (−1,5 cent"), True, "consiglio: scende")
uguale(logica.consiglio(None, t_fermo, "gpl"), "Prezzi fermi in zona negli ultimi 7 giorni.", "consiglio: fermo, nessun distributore")
uguale(logica.consiglio(auchan, {"sufficiente": False}, "benzina"), "Il più conveniente qui vicino: Auchan a 1,979 €/L.", "consiglio: senza tendenza")
uguale(logica.consiglio(None, None, "metano"), "Nessun prezzo di metano qui vicino.", "consiglio: niente")
uguale(logica.consiglio(None, t_su, "gpl").startswith("In zona il GPL sale"), True, "consiglio: GPL maiuscolo")

uguale(logica.calo(1.999, 1.979, 2), 2.0, "calo: 2 cent")
uguale(logica.calo(1.999, 1.989, 2), None, "calo: sotto la soglia")
uguale(logica.calo(1.979, 1.999, 2), None, "calo: è salito")
uguale(logica.calo(None, 1.9, 2), None, "calo: niente prima")

# --- sincronizzazione con l'app (5/10): stesse regole del server dell'account ---
from datetime import datetime, timezone, timedelta
adesso = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
d1 = {"preferiti": [{"id": 1, "titolo": "Q8"}], "scelte": {"carburante": "gasolio"}}
ok, doc, agg = logica.scrivi_dati(None, None, d1, "2026-10-05T10:00:00Z", adesso)
uguale((ok, doc, agg), (True, d1, "2026-10-05T10:00:00Z"), "dati: prima scrittura salvata")
ok, doc2, agg2 = logica.scrivi_dati(doc, agg, {"preferiti": []}, "2026-10-05T09:00:00Z", adesso)
uguale((ok, doc2, agg2), (False, d1, agg), "dati: scrittura più vecchia rifiutata, torna quella salvata")
ok, _, _ = logica.scrivi_dati(doc, agg, {"preferiti": []}, "2026-10-05T12:00:00+02:00", adesso)
uguale(ok, False, "dati: stessa ora con fuso diverso non vince")
ok, doc3, _ = logica.scrivi_dati(doc, agg, {"preferiti": [{"id": 2}], "garage": None}, "2026-10-05T10:00:01Z", adesso)
uguale((ok, doc3), (True, {"preferiti": [{"id": 2}], "scelte": {"carburante": "gasolio"}}),
       "dati: la più nuova vince, le chiavi non mandate (o null) restano")
_, _, agg4 = logica.scrivi_dati(doc, agg, d1, "2099-01-01T00:00:00Z", adesso)
uguale(agg4, "2026-10-05T12:00:00Z", "dati: data nel futuro riportata ad adesso")
try:
    logica.scrivi_dati(None, None, {"password": "x"}, "2026-10-05T10:00:00Z", adesso); errore = None
except logica.DatiNonValidi as e:
    errore = e.codice
uguale(errore, 422, "dati: chiave estranea → 422")
try:
    logica.scrivi_dati(None, None, {"zona": "x" * (1024 * 1024 + 10)}, "2026-10-05T10:00:00Z", adesso); errore = None
except logica.DatiNonValidi as e:
    errore = e.codice
uguale(errore, 413, "dati: oltre 1 MB → 413")

uguale(logica.da_swift(780000000.0), datetime(2025, 9, 19, 18, 40, tzinfo=timezone.utc), "date dell'app: secondi dal 2001")
uguale(logica.a_swift(logica.da_swift(780000000.0)), 780000000.0, "date dell'app: andata e ritorno")

golf = {"id": "AAAA-1", "nome": "Golf", "carburante": "benzina", "capacitaLitri": 50, "consumoMedio": 6.5, "livello": 0.38}
ducato = {"id": "BBBB-2", "nome": "Ducato", "carburante": "gasolio", "autonomiaKm": 412.4}
doc_auto = {"garage": [golf, ducato], "valori": {"autoAttiva": {"json": '"BBBB-2"', "modificato": 1.0}}}
uguale(logica.auto_attiva(doc_auto)["nome"], "Ducato", "auto attiva: quella scelta nell'app")
uguale(logica.auto_attiva({"garage": [golf]})["nome"], "Golf", "auto attiva: senza scelta la prima")
uguale(logica.autonomia_km(ducato), 412, "autonomia: quella letta")
uguale(logica.autonomia_km(golf), 292, "autonomia: livello × capienza ÷ consumo")
uguale(logica.preferiti_ids({"preferiti": [{"id": 3, "posizione": 2}, {"id": 1}, {"id": 2, "posizione": 0}]}), [2, 3, 1],
       "preferiti: nell'ordine scelto, senza posto in fondo")

d, aggiunto, idi = logica.registra_pieno(doc_auto, 40.5, adesso, prezzo=1.799, km=120000, distributore="Q8 Roma",
                                         impianto=1002, nuovo_id="abc")
voce = d["diario"][0]
uguale((aggiunto, idi, voce["autoID"], voce["carburante"], voce["euro"], voce["automatico"], voce["daConfermare"]),
       (True, "ABC", "BBBB-2", "gasolio", 72.86, "Home Assistant", True), "pieno: sull'auto attiva, euro dal prezzo, da confermare")
d2, aggiunto2, idi2 = logica.registra_pieno(d, 41, adesso + timedelta(minutes=90))
uguale((aggiunto2, idi2, len(d2["diario"])), (False, "ABC", 1), "pieno: la stessa auto entro 2 ore è lo stesso pieno")
d3, aggiunto3, _ = logica.registra_pieno(d, 30, adesso + timedelta(minutes=30), auto="golf")
uguale((aggiunto3, d3["diario"][0]["autoID"], len(d3["diario"])), (True, "AAAA-1", 2), "pieno: un'altra auto (per nome) si aggiunge")
uguale(logica.ultimo_pieno(d3)["autoID"], "AAAA-1", "ultimo pieno: il più recente")
uguale(doc_auto.get("diario"), None, "pieno: il documento di partenza non cambia")

uguale(logica.sotto_soglia(1.85, 1.79, 1.80), True, "avviso: arrivato alla soglia")
uguale(logica.sotto_soglia(1.79, 1.78, 1.80), False, "avviso: era già sotto, niente di nuovo")
uguale(logica.sotto_soglia(None, 1.80, 1.80), True, "avviso: alla prima lettura già alla soglia")
uguale(logica.sotto_soglia(1.75, 1.85, 1.80), False, "avviso: è salito")

# --- 0.2.1: tutti i carburanti, sensori che seguono l'auto, un dispositivo per auto, quadro (7/10)
uguale(logica.carburanti_scelti(None, "benzina"), ["benzina"], "0.2.0: il carburante che c'era")
uguale(logica.carburanti_scelti(["elettrico", "gasolio"]), ["gasolio", "elettrico"], "carburanti nell'ordine fisso")
uguale(logica.carburanti_scelti([]), list(logica.TUTTI), "niente di valido: tutti")
uguale(logica.carburanti_scelti("gpl"), ["gpl"], "un testo solo")

zoe = {"id": "CCCC-3", "nome": "Zoe", "carburante": "benzina", "elettrica": True, "livello": 0.61,
               "autonomiaKm": 140, "self_": True}
phev = {"id": "DDDD-4", "nome": "Ibrida", "carburante": "benzina", "elettrica": True, "ibridaPlugin": True,
        "livello": 0.5, "capacitaLitri": 40, "consumoMedio": 5}
uguale(logica.per_auto(zoe, "benzina", True)["carburante"], "elettrico", "auto: elettrica → colonnine")
uguale(logica.per_auto(ducato, "benzina", True)["carburante"], "gasolio", "auto: diesel → gasolio")
uguale((logica.per_auto(phev, "gasolio", True)["carburante"], logica.per_auto(phev, "gasolio", True)["colonnine"]),
       ("benzina", True), "auto: plug-in → il suo carburante più le colonnine")
uguale(logica.per_auto(None, "metano", True)["carburante"], "metano", "nessuna auto: la configurazione")
uguale(logica.per_auto({"carburante": "benzina", "self_": False}, "benzina", True)["self"], False, "self dall'auto")
uguale(logica.self_per("gpl", True), False, "il GPL non ha il self")

col = {"totale": 4, "colonnine": [
    {"id": "a", "operatore": "OPERATORE A", "distanza_km": 0.6, "libere": 1, "prezzo_kwh": None, "lat": 41.9, "lon": 12.5},
    {"id": "b", "operatore": "ENEL X", "distanza_km": 2.0, "libere": 0, "prezzo_kwh": 0.59},
    {"id": "c", "operatore": "IONITY", "distanza_km": 3.1, "libere": 2, "prezzo_kwh": 0.49},
    {"id": "d", "operatore": "BE CHARGE", "distanza_km": 1.0, "libere": 0, "prezzo_kwh": 0.49}]}
uguale(logica.ricarica_conveniente(col)["id"], "d", "ricarica: la più economica, a parità la più vicina")
uguale(logica.colonnina_libera(col)["id"], "a", "colonnina: la più vicina libera")
uguale(logica.libere(col), 2, "colonnine libere")
uguale(logica.mediana_kwh(col), 0.49, "mediana €/kWh")
uguale(logica.ricarica_conveniente({"colonnine": [{"prezzo_kwh": None}]}), None, "ricarica: nessun prezzo dichiarato")
uguale(logica.consiglio_ricarica(col), "La ricarica più conveniente qui vicino: Be Charge a 0,49\u00a0€/kWh. Libera più vicina: Operatore A a 0,6 km.",
       "consiglio della ricarica")
uguale(logica.consiglio_ricarica(None), "Nessuna colonnina qui vicino.", "consiglio senza colonnine")
uguale(logica.data_estrazione({"estrazione": {"giorno": "2026-10-06", "estrazione": "2026-10-06"}}), "2026-10-06",
       "data dei dati MIMIT")

uguale(logica.autonomia_auto(zoe), 140, "autonomia elettrica letta")
uguale(logica.autonomia_auto({"elettrica": True, "livello": 0.5, "batteriaKwh": 42, "consumoKwh": 15}), 140,
       "autonomia elettrica stimata dai kWh")
uguale(logica.autonomia_auto(phev), 400, "plug-in: autonomia del carburante")

viaggi = {"viaggi": [
    {"titolo": "Riunione", "luogo": "Milano", "data": logica.a_swift(adesso + timedelta(days=1)), "km": 100, "andataRitorno": True},
    {"titolo": "Vecchio", "luogo": "Roma", "data": logica.a_swift(adesso - timedelta(days=1)), "km": 500},
    {"titolo": "Lontano", "luogo": "Bari", "data": logica.a_swift(adesso + timedelta(days=20)), "km": 900}]}
v = logica.prossimo_viaggio(viaggi, adesso)
uguale((v["luogo"], v["km"], v["andata_ritorno"]), ("Milano", 200, True), "prossimo viaggio: il primo nei 7 giorni, A/R")
uguale(logica.prossimo_viaggio({"viaggi": []}, adesso), None, "nessun viaggio")

q8m = {**q8, "prezzo": 1.849}
c1 = logica.consiglio_auto({**ducato, "autonomiaKm": 612, "livello": 0.77}, q8m, None, v)
uguale((c1["testo"], c1["presto"]), ("Ce la fai fino a Milano e ritorno (200 km, autonomia 612 km).", False), "auto: ce la fai")
c2 = logica.consiglio_auto({**golf, "livello": 0.31, "autonomiaKm": 150}, auchan, None, v)
uguale((c2["testo"], c2["presto"]), ("Per Milano e ritorno (200 km) non basta: fai il pieno prima di partire. Il più conveniente: Auchan a 1,979\u00a0€/L.", True),
       "auto: non basta per il viaggio")
c3 = logica.consiglio_auto({**golf, "livello": 0.12, "autonomiaKm": None}, auchan, None, None)
uguale((c3["presto"], c3["testo"].startswith("Riserva: fai il pieno presto.")), (True, True), "auto: riserva")
c4 = logica.consiglio_auto({**golf, "livello": 0.5}, auchan, t_su, None)
uguale((c4["presto"], c4["testo"].startswith("In zona sale (+2,1 cent")), (True, True), "auto: la zona sale, mezzo serbatoio")
c5 = logica.consiglio_auto({**golf, "livello": 0.8}, auchan, t_giu, None)
uguale((c5["presto"], c5["testo"].startswith("In zona scende")), (False, True), "auto: la zona scende")
c6 = logica.consiglio_auto({**zoe, "livello": 0.1, "autonomiaKm": 30}, col["colonnine"][3], None, None)
uguale(c6["testo"], "Riserva: fai la ricarica presto. Il più conveniente: Be Charge a 0,49\u00a0€/kWh.", "elettrica in riserva")
c7 = logica.consiglio_auto({**golf, "livello": 0.8, "autonomiaKm": 520}, None, None, None)
uguale(c7, {"testo": "Tutto a posto (80%, 520 km).", "presto": False}, "auto: tutto a posto")

uguale(logica.quadro([{"presto": True}, {"presto": False}, {"presto": True}]), "2 auto da rifornire presto", "quadro: 2")
uguale(logica.quadro([{"presto": True}]), "1 auto da rifornire presto", "quadro: 1")
uguale(logica.quadro([{"presto": False}]), "Tutte a posto", "quadro: nessuna")
uguale(logica.quadro([]), "Nessuna auto", "quadro: senza auto")
diario = {"diario": [{"autoID": "aaaa-1", "data": 10.0, "litri": 30}, {"autoID": "BBBB-2", "data": 20.0},
                     {"autoID": "AAAA-1", "data": 15.0}]}
uguale(logica.ultimo_pieno_auto(diario, "AAAA-1")["data"], 15.0, "ultimo pieno di quell'auto (id senza maiuscole)")

# --- «stato» dell'app e modalità senza app (7/10)
stato_doc = {"stato": {"contratto": 1, "inviato": "2026-10-07T18:00:00Z", "sezioni": {
    "viaggio": {"in_corso": True, "meta": "Milano"}, "posizione": {"lat": 41.9, "lon": 12.5},
    "statistiche": {"aaaa-1": {"consumo_medio": 6.2}}, "nuova_sezione": {"x": 1}}}}
uguale(logica.testo_viaggio(logica.sezione(stato_doc, "viaggio")), "In viaggio verso Milano", "stato: in viaggio")
uguale(logica.testo_viaggio({"in_corso": False}), "Fermo", "stato: fermo")
mostrate = logica.sezioni_mostrate(None, stato_doc)
uguale(sorted(mostrate), ["nuova_sezione", "statistiche", "viaggio"], "stato: la posizione no di partenza, le sezioni nuove sì")
uguale(sorted(logica.sezioni_mostrate(["viaggio"], stato_doc)), ["viaggio"], "stato: solo quelle scelte")
uguale(logica.per_auto_in(stato_doc, "statistiche", "AAAA-1"), {"consumo_medio": 6.2}, "stato: per auto, id senza maiuscole")
uguale(logica.sezione({}, "viaggio"), None, "stato: senza app")

h = logica.auto_da_ha("s1", {"nome": "Panda", "tipo": "benzina", "capienza": 40, "consumo": 5},
                      {"livello": (50.0, "%"), "autonomia": (100.0, "mi"), "km": (12000.0, "km")})
uguale((h["id"], h["livello"], round(h["autonomiaKm"]), h["km"], h["capacitaLitri"]), ("ha_s1", 0.5, 161, 12000.0, 40.0),
       "auto in HA: livello in %, autonomia in miglia")
uguale(logica.auto_da_ha("s2", {"nome": "P", "capienza": 40}, {"livello": (20.0, "L")})["livello"], 0.5, "auto in HA: livello in litri")
uguale(logica.auto_da_ha("s3", {"nome": "P"}, {"livello": (1.0, "%")})["livello"], 0.01, "auto in HA: 1% non è pieno")
ev = logica.auto_da_ha("s4", {"nome": "Zoe", "tipo": "elettrica", "consumo": 15}, {})
uguale((logica.per_auto(ev, "benzina", True)["carburante"], ev.get("consumoKwh")), ("elettrico", 15.0), "auto in HA: elettrica")
uguale(logica.per_auto(logica.auto_da_ha("s5", {"nome": "I", "tipo": "ibrida_plugin"}, {}), "benzina", True)["colonnine"], True,
       "auto in HA: plug-in con le colonnine")
app = [{"id": "AAAA-1", "nome": "Golf", "livello": None, "km": 50000}]
uniti = logica.unisci_garage(app, [{"id": "ha_x", "nome": "golf", "livello": 0.3, "km": 1}, {"id": "ha_y", "nome": "Panda"}])
uguale([(a["id"], a.get("livello"), a.get("km")) for a in uniti], [("AAAA-1", 0.3, 50000), ("ha_y", None, None)],
       "unione: la gemella dell'app vince, dall'HA solo quello che manca; le altre si aggiungono")
uguale(app[0]["livello"], None, "unione: il garage dell'app non cambia")

print(f"{fatte - fallite}/{fatte} prove passate")
sys.exit(1 if fallite else 0)
