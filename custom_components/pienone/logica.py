"""Le regole dell'integrazione, senza Home Assistant: si provano con ha/prove_pienone.py."""
from __future__ import annotations


def euro_litro(v: float | None) -> str:
    """1.979 → «1,979 €/L»."""
    return "—" if v is None else f"{v:.3f}".replace(".", ",") + " €/L"


def titolo(imp: dict) -> str:
    """Il nome da mostrare: la bandiera, se c'è, altrimenti il nome del distributore."""
    b = (imp.get("bandiera") or "").strip()
    n = (imp.get("nome") or "").strip()
    if b and b.lower() not in ("pompe bianche", "altri"):
        return b
    return n.title() if n else "Distributore"


def migliore(risposta: dict) -> dict | None:
    """Il più conveniente della zona (il server lo segna), saltando i prezzi da verificare."""
    impianti = risposta.get("impianti") or []
    for i in impianti:
        if i.get("piu_conveniente"):
            return i
    validi = [i for i in impianti if not i.get("da_verificare")]
    return min(validi, key=lambda i: (i["prezzo"], i.get("distanza_km", 0)), default=None)


def prezzo_scheda(scheda: dict, carburante: str, self_: bool) -> float | None:
    """Il prezzo di oggi di un distributore (scheda /v1/impianto) per carburante e self/servito."""
    voluto = 1 if (self_ and carburante in ("benzina", "gasolio")) else 0
    prezzi = [p["prezzo"] for p in scheda.get("prezzi") or [] if p.get("famiglia") == carburante and p.get("self") == voluto]
    return min(prezzi) if prezzi else None


ARTICOLO = {"benzina": "la benzina", "gasolio": "il gasolio", "gpl": "il GPL", "metano": "il metano"}
NOME = {"benzina": "benzina", "gasolio": "gasolio", "gpl": "GPL", "metano": "metano"}


def consiglio(migliore_imp: dict | None, tendenza: dict | None, carburante: str) -> str:
    """Una frase, con le regole dell'app (niente modelli): la tendenza della zona sui 7 giorni e dove conviene."""
    dove = f" {titolo(migliore_imp)} a {euro_litro(migliore_imp['prezzo'])}" if migliore_imp else ""
    if not tendenza or not tendenza.get("sufficiente") or tendenza.get("zona_diff_cent") is None:
        return f"Il più conveniente qui vicino:{dove}." if dove else f"Nessun prezzo di {NOME.get(carburante, carburante)} qui vicino."
    d = tendenza["zona_diff_cent"]
    cent = f"{abs(d):.1f}".replace(".", ",")
    chi = ARTICOLO.get(carburante, carburante)
    if d >= 1:
        return f"In zona {chi} sale (+{cent} cent in 7 giorni): conviene fare il pieno presto.{(' Il più conveniente:' + dove + '.') if dove else ''}"
    if d <= -1:
        return f"In zona {chi} scende (−{cent} cent in 7 giorni): se puoi, aspetta qualche giorno.{(' Oggi il più conveniente:' + dove + '.') if dove else ''}"
    return f"Prezzi fermi in zona negli ultimi 7 giorni.{(' Il più conveniente:' + dove + '.') if dove else ''}"


def calo(prima: float | None, adesso: float | None, soglia_cent: float) -> float | None:
    """Di quanti centesimi è sceso il prezzo, se almeno della soglia; altrimenti None."""
    if prima is None or adesso is None:
        return None
    d = round((prima - adesso) * 100, 1)
    return d if d >= soglia_cent else None


# ---------------------------------------------------------------------------------------------------------------
# Sincronizzazione con l'app (5/10): l'integrazione tiene una copia del documento dell'app, con le stesse
# regole del server dell'account (/v1/account/dati): vince la data più recente; le chiavi che l'app non manda restano.
# L'unione PER ELEMENTO la fa l'app (UnioneAccount), qui si conserva e si legge. Le date dell'app sono secondi dal
# 1/1/2001 (JSONEncoder di Swift), gli id delle auto e dei pieni UUID in maiuscolo.

from datetime import datetime, timedelta, timezone
import uuid

CHIAVI_DATI = ("preferiti", "scelte", "zona", "auto", "garage", "preferenze", "diario", "viaggi", "avvisi",
               "valori", "cancellati",
               "stato")   # 0.2.1: quello che l'app sa adesso (contratto versionato, solo verso Home Assistant)
MAX_DATI = 1024 * 1024
RIF_2001 = datetime(2001, 1, 1, tzinfo=timezone.utc)
VICINI_ORE = 2   # due pieni della stessa auto a meno di 2 ore sono lo stesso pieno (come PieniAutomatici dell'app)


class DatiNonValidi(ValueError):
    """Il documento mandato dall'app non va bene: `codice` è lo stato HTTP da rispondere (422 o 413)."""

    def __init__(self, codice: int, messaggio: str) -> None:
        super().__init__(messaggio)
        self.codice = codice


def data_utc(testo: str) -> datetime:
    """«2026-10-05T10:00:00Z» (o con fuso) → data in UTC."""
    d = datetime.fromisoformat(testo.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def da_swift(secondi: float | None) -> datetime | None:
    return None if secondi is None else RIF_2001 + timedelta(seconds=float(secondi))


def a_swift(d: datetime) -> float:
    return round((d - RIF_2001).total_seconds(), 3)


def dimensione(dati: dict) -> int:
    import json
    return len(json.dumps(dati, ensure_ascii=False, separators=(",", ":")).encode())


def scrivi_dati(salvati: dict | None, aggiornato_salvati: str | None, nuovi: dict, aggiornato: str,
                adesso: datetime) -> tuple[bool, dict, str]:
    """Come PUT /v1/account/dati. Ritorna (salvato, documento, aggiornato). Una data nel futuro vale adesso."""
    estranee = set(nuovi) - set(CHIAVI_DATI)
    if estranee:
        raise DatiNonValidi(422, f"chiavi non ammesse: {sorted(estranee)}")
    nuovi = {k: v for k, v in nuovi.items() if v is not None}
    if dimensione(nuovi) > MAX_DATI:
        raise DatiNonValidi(413, "dati troppo grandi")
    nuova = min(data_utc(aggiornato), adesso)
    if salvati is not None and aggiornato_salvati and data_utc(aggiornato_salvati) >= nuova:
        return False, salvati, aggiornato_salvati   # vince quello che c'è già: l'app lo adotta
    unito = {**(salvati or {}), **nuovi}
    if dimensione(unito) > MAX_DATI:
        raise DatiNonValidi(413, "dati troppo grandi")
    return True, unito, iso(nuova)


def valore(dati: dict, chiave: str):
    """Un valore singolo dell'app («autoAttiva», «carburante»…): è JSON dentro il campo «json»."""
    import json
    v = ((dati or {}).get("valori") or {}).get(chiave)
    if not v or "json" not in v:
        return None
    try:
        return json.loads(v["json"])
    except ValueError:
        return None


def auto_attiva(dati: dict) -> dict | None:
    """L'auto scelta nell'app, o la prima del garage."""
    garage = (dati or {}).get("garage") or []
    idi = valore(dati, "autoAttiva")
    return next((a for a in garage if str(a.get("id", "")).upper() == str(idi or "").upper()), None) or (garage[0] if garage else None)


def autonomia_km(auto: dict | None) -> float | None:
    """Quella letta (Home Assistant dell'auto) o livello × capienza ÷ consumo."""
    if not auto:
        return None
    if auto.get("autonomiaKm") is not None:
        return round(float(auto["autonomiaKm"]))
    liv, cap, cons = auto.get("livello"), auto.get("capacitaLitri"), auto.get("consumoMedio")
    if liv is None or not cap or not cons:
        return None
    return round(float(liv) * float(cap) / float(cons) * 100)


def preferiti_ids(dati: dict) -> list[int]:
    """Gli id MIMIT dei preferiti dell'app, nell'ordine scelto (posizione), al massimo 10 come nelle opzioni."""
    p = list(enumerate((dati or {}).get("preferiti") or []))
    p.sort(key=lambda x: (x[1].get("posizione") is None, x[1].get("posizione") or 0, x[0]))
    return [int(v["id"]) for _, v in p if isinstance(v.get("id"), int)][:10]


def ultimo_pieno(dati: dict) -> dict | None:
    d = [r for r in (dati or {}).get("diario") or [] if r.get("data") is not None]
    return max(d, key=lambda r: r["data"], default=None)


def registra_pieno(dati: dict | None, litri: float, adesso: datetime, *, euro: float | None = None,
                   prezzo: float | None = None, km: float | None = None, distributore: str | None = None,
                   impianto: int | None = None, auto: str | None = None, quando: datetime | None = None,
                   pieno_completo: bool = True, nuovo_id: str | None = None) -> tuple[dict, bool, str]:
    """Un pieno nel diario, come lo scrive l'app (Rifornimento). `auto`: nome o id; senza, l'auto attiva.
    Se la stessa auto ha già un pieno a meno di 2 ore non se ne aggiunge un altro. Ritorna (documento, aggiunto, id)."""
    dati = dict(dati or {})
    quando = quando or adesso
    garage = dati.get("garage") or []
    scelta = None
    if auto:
        a = auto.strip().lower()
        scelta = next((x for x in garage if str(x.get("id", "")).lower() == a or str(x.get("nome", "")).strip().lower() == a), None)
    scelta = scelta or auto_attiva(dati)
    auto_id = scelta.get("id") if scelta else None
    t = a_swift(quando)
    for r in dati.get("diario") or []:
        stessa = r.get("autoID") is None or auto_id is None or str(r.get("autoID")).upper() == str(auto_id).upper()
        if stessa and r.get("data") is not None and abs(float(r["data"]) - t) <= VICINI_ORE * 3600:
            return dati, False, r.get("id")
    if euro is None and prezzo is not None:
        euro = round(prezzo * litri, 2)
    idi = (nuovo_id or str(uuid.uuid4())).upper()
    voce = {"id": idi, "data": t, "litri": round(float(litri), 2), "euro": round(float(euro or 0), 2),
            "distributore": (distributore or "").strip(), "pienoCompleto": bool(pieno_completo),
            "automatico": "Home Assistant", "daConfermare": True, "modificato": a_swift(adesso)}
    if km is not None:
        voce["km"] = float(km)
    if impianto is not None:
        voce["impianto"] = int(impianto)
    if auto_id:
        voce["autoID"] = str(auto_id).upper()
        if scelta.get("carburante"):
            voce["carburante"] = scelta["carburante"]
    dati["diario"] = [voce] + list(dati.get("diario") or [])
    return dati, True, idi


def sotto_soglia(prima: float | None, adesso: float | None, soglia: float | None) -> bool:
    """Un avviso di prezzo dell'app: il prezzo è arrivato alla soglia (€/L) adesso, prima no (o non si sapeva)."""
    if adesso is None or soglia is None:
        return False
    return adesso <= soglia and (prima is None or prima > soglia)


# --- 0.2.1 (7/10): tutti i carburanti, e i sensori principali seguono l'auto attiva sincronizzata

MIMIT = ("benzina", "gasolio", "gpl", "metano")
TUTTI = MIMIT + ("elettrico",)
NOME["elettrico"] = "elettrico"
CON_SELF = ("benzina", "gasolio")


def carburanti_scelti(scelti, vecchio: str | None = None) -> list[str]:
    """I carburanti della configurazione nell'ordine fisso; la 0.2.0 ne aveva uno solo («carburante»).
    Senza niente di valido: tutti."""
    if isinstance(scelti, str):
        scelti = [scelti]
    v = [c for c in TUTTI if c in (scelti or [])]
    if not v and vecchio in TUTTI:
        v = [vecchio]
    return v or list(TUTTI)


def per_auto(auto: dict | None, ripiego: str, self_ripiego: bool) -> dict:
    """Cosa seguono i sensori principali: il carburante dell'auto attiva (elettrica → colonnine; ibrida plug-in →
    il suo carburante più le colonnine), altrimenti quello della configurazione. «self» dall'auto, se lo dice."""
    if not auto:
        return {"carburante": ripiego, "colonnine": ripiego == "elettrico", "self": self_ripiego, "auto": None}
    s = auto.get("self_")
    self_ = bool(s) if isinstance(s, bool) else self_ripiego
    if auto.get("elettrica") and not auto.get("ibridaPlugin"):
        return {"carburante": "elettrico", "colonnine": True, "self": self_, "auto": auto.get("nome")}
    c = auto.get("carburante")
    if c not in MIMIT:
        c = ripiego if ripiego in MIMIT else "benzina"
    return {"carburante": c, "colonnine": bool(auto.get("ibridaPlugin")), "self": self_, "auto": auto.get("nome")}


def self_per(carburante: str, self_: bool) -> bool:
    """GPL e metano non hanno il self nei dati MIMIT."""
    return bool(self_) and carburante in CON_SELF


def euro_kwh(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}".replace(".", ",") + "\u00a0€/kWh"


def _colonnine(risposta: dict | None) -> list[dict]:
    return sorted((risposta or {}).get("colonnine") or [], key=lambda c: c.get("distanza_km") or 0)


def ricarica_conveniente(risposta: dict | None) -> dict | None:
    """La colonnina col prezzo €/kWh più basso (a parità, la più vicina); None se nessuna dichiara il prezzo."""
    con = [c for c in _colonnine(risposta) if isinstance(c.get("prezzo_kwh"), (int, float))]
    return min(con, key=lambda c: (c["prezzo_kwh"], c.get("distanza_km") or 0), default=None)


def colonnina_libera(risposta: dict | None) -> dict | None:
    """La più vicina con almeno una presa libera."""
    return next((c for c in _colonnine(risposta) if (c.get("libere") or 0) > 0), None)


def libere(risposta: dict | None) -> int:
    return sum(1 for c in _colonnine(risposta) if (c.get("libere") or 0) > 0)


def mediana_kwh(risposta: dict | None) -> float | None:
    p = sorted(c["prezzo_kwh"] for c in _colonnine(risposta) if isinstance(c.get("prezzo_kwh"), (int, float)))
    if not p:
        return None
    m = len(p) // 2
    return round(p[m] if len(p) % 2 else (p[m - 1] + p[m]) / 2, 3)


def nome_colonnina(c: dict) -> str:
    return (c.get("operatore") or c.get("nome") or "Colonnina").strip().title()


def consiglio_ricarica(risposta: dict | None) -> str:
    """Una frase per l'auto elettrica: dove costa meno, se lo si sa, e la più vicina libera."""
    r, lib = ricarica_conveniente(risposta), colonnina_libera(risposta)
    parti = []
    if r:
        parti.append(f"La ricarica più conveniente qui vicino: {nome_colonnina(r)} a {euro_kwh(r['prezzo_kwh'])}.")
    if lib:
        km = lib.get("distanza_km")
        dove = f" a {str(round(km, 1)).replace('.', ',')} km" if isinstance(km, (int, float)) else ""
        parti.append(f"Libera più vicina: {nome_colonnina(lib)}{dove}.")
    return " ".join(parti) or "Nessuna colonnina qui vicino."


def data_estrazione(vicini: dict | None) -> str | None:
    """Il giorno dei dati MIMIT («2026-10-06»): il MIMIT pubblica ogni mattina i prezzi del giorno prima."""
    e = (vicini or {}).get("estrazione") or {}
    return e.get("estrazione") or e.get("giorno") if isinstance(e, dict) else None


# --- un dispositivo per ogni auto e il quadro generale (7/10)

RISERVA = 0.2          # sotto il 20% si fa il pieno presto
AUTONOMIA_BASSA = 80   # km


def livello_auto(auto: dict) -> float | None:
    """0…1: per l'elettrica è la batteria (il livello), per la plug-in il livello del carburante."""
    v = auto.get("livello")
    return max(0.0, min(1.0, float(v))) if isinstance(v, (int, float)) else None


def autonomia_auto(auto: dict) -> float | None:
    """La letta, o la stima: carburante col consumo, elettrica coi kWh."""
    if auto.get("elettrica") and not auto.get("ibridaPlugin"):
        if auto.get("autonomiaKm") is not None:
            return round(float(auto["autonomiaKm"]))
        liv, kwh, cons = auto.get("livello"), auto.get("batteriaKwh"), auto.get("consumoKwh")
        if liv is None or not kwh or not cons:
            return None
        return round(float(liv) * float(kwh) / float(cons) * 100)
    return autonomia_km(auto)


def prossimo_viaggio(dati: dict | None, adesso: datetime, giorni: int = 7) -> dict | None:
    """Il primo viaggio pianificato (anche dal calendario) da adesso ai prossimi `giorni`, con la data vera e i km
    da fare (andata e ritorno, se lo è)."""
    futuri = []
    for v in (dati or {}).get("viaggi") or []:
        d = da_swift(v.get("data")) if isinstance(v.get("data"), (int, float)) else None
        if d is None or d < adesso or (d - adesso).days >= giorni:
            continue
        km = v.get("km")
        totale = round(float(km) * (2 if v.get("andataRitorno", True) else 1)) if isinstance(km, (int, float)) else None
        futuri.append({"luogo": v.get("luogo") or v.get("titolo") or "", "titolo": v.get("titolo"), "data": d,
                       "km": totale, "andata_ritorno": bool(v.get("andataRitorno", True))})
    return min(futuri, key=lambda x: x["data"], default=None)


def _dove(vicino: dict | None, elettrico: bool) -> str:
    if not vicino:
        return ""
    if elettrico:
        p = vicino.get("prezzo_kwh")
        return f"{nome_colonnina(vicino)}" + (f" a {euro_kwh(p)}" if isinstance(p, (int, float)) else "")
    return f"{titolo(vicino)} a {euro_litro(vicino.get('prezzo'))}"


def consiglio_auto(auto: dict, vicino: dict | None, tendenza: dict | None, viaggio: dict | None) -> dict:
    """Il consiglio di UN'auto: ce la fa per il prossimo viaggio? è in riserva? la zona sale o scende?
    `vicino`: il distributore (o la colonnina, per l'elettrica) più conveniente per il suo carburante.
    Restituisce la frase e «presto» (da rifornire presto: va nel conto del quadro)."""
    el = bool(auto.get("elettrica")) and not auto.get("ibridaPlugin")
    pieno = "la ricarica" if el else "il pieno"
    liv, aut = livello_auto(auto), autonomia_auto(auto)
    dove = _dove(vicino, el)
    coda = f" Il più conveniente: {dove}." if dove else ""
    if viaggio and viaggio.get("km") and aut is not None:
        meta = viaggio["luogo"] + (" e ritorno" if viaggio.get("andata_ritorno") else "")
        if aut >= viaggio["km"] * 1.1:
            return {"testo": f"Ce la fai fino a {meta} ({viaggio['km']} km, autonomia {aut} km).", "presto": False}
        return {"testo": f"Per {meta} ({viaggio['km']} km) non basta: fai {pieno} prima di partire.{coda}", "presto": True}
    if (liv is not None and liv < RISERVA) or (aut is not None and aut < AUTONOMIA_BASSA):
        return {"testo": f"Riserva: fai {pieno} presto.{coda}", "presto": True}
    d = (tendenza or {}).get("zona_diff_cent") if (tendenza or {}).get("sufficiente") else None
    if not el and d is not None and d >= 1 and liv is not None and liv < 0.6:
        cent = f"{abs(d):.1f}".replace(".", ",")
        return {"testo": f"In zona sale (+{cent} cent in 7 giorni): conviene fare il pieno.{coda}", "presto": True}
    if not el and d is not None and d <= -1:
        return {"testo": f"In zona scende: se puoi, aspetta qualche giorno.{coda}", "presto": False}
    stato = f"{round(liv * 100)}%" if liv is not None else "livello sconosciuto"
    return {"testo": f"Tutto a posto ({stato}" + (f", {aut} km" if aut is not None else "") + f").{coda}", "presto": False}


def ultimo_pieno_auto(dati: dict | None, auto_id) -> dict | None:
    d = [r for r in (dati or {}).get("diario") or []
         if r.get("data") is not None and str(r.get("autoID", "")).upper() == str(auto_id or "").upper()]
    return max(d, key=lambda r: r["data"], default=None)


def quadro(righe: list[dict]) -> str:
    """Lo stato del sensore «quadro»: quante auto sono da rifornire presto."""
    n = sum(1 for r in righe if r.get("presto"))
    if not righe:
        return "Nessuna auto"
    if n == 0:
        return "Tutte a posto"
    return "1 auto da rifornire presto" if n == 1 else f"{n} auto da rifornire presto"


# --- «stato»: tutto quello che l'app sa adesso (7/10, contratto versionato). L'app manda solo le sezioni che ha acceso
# (la posizione precisa è spenta di partenza); qui si mostrano solo quelle scelte in «Configura».

SEZIONI = ("viaggio", "carplay", "statistiche", "obd", "notifiche", "attivita", "preferenze", "posizione", "extra")
SEZIONI_ACCESE = ("viaggio", "carplay", "statistiche", "obd", "notifiche", "attivita", "preferenze", "extra")


def stato_app(dati: dict | None) -> dict:
    s = (dati or {}).get("stato")
    return s if isinstance(s, dict) else {}


def sezione(dati: dict | None, nome: str) -> dict | None:
    v = (stato_app(dati).get("sezioni") or {}).get(nome)
    return v if isinstance(v, dict) else None


def sezioni_mostrate(scelte, dati: dict | None) -> dict:
    """Le sezioni arrivate dall'app e scelte in «Configura» (anche quelle che questa versione non conosce: un campo
    nuovo dell'app compare senza aggiornare l'integrazione)."""
    scelte = SEZIONI_ACCESE if scelte is None else scelte
    arrivate = stato_app(dati).get("sezioni") or {}
    return {k: v for k, v in arrivate.items() if k in scelte or (k not in SEZIONI and "extra" in scelte)}


def per_auto_in(dati: dict | None, nome: str, auto_id) -> dict:
    """Una sezione divisa per auto («statistiche», «obd»): quella di un'auto (id senza badare alle maiuscole)."""
    s = sezione(dati, nome) or {}
    return next((v for k, v in s.items() if str(k).upper() == str(auto_id or "").upper() and isinstance(v, dict)), {})


def testo_viaggio(v: dict | None) -> str:
    if not v or not v.get("in_corso"):
        return "Fermo"
    meta = v.get("meta")
    return f"In viaggio verso {meta}" if meta else "In viaggio"


# --- senza l'app (7/10): auto definite in Home Assistant, unite al garage dell'app senza doppioni

TIPI_AUTO = ("benzina", "gasolio", "gpl", "metano", "elettrica", "ibrida_plugin")


def numero_stato(stato: str | None) -> float | None:
    try:
        v = float(str(stato).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return v if v == v else None   # NaN


def auto_da_ha(idi: str, d: dict, letture: dict) -> dict:
    """Un'auto definita in Home Assistant (sotto-voce «auto») nello stesso formato del garage dell'app.
    `letture`: {"livello": (valore, unità), "autonomia": …, "km": …} dalle entità scelte (facoltative)."""
    tipo = d.get("tipo") or "benzina"
    el, plug = tipo == "elettrica", tipo == "ibrida_plugin"
    a = {"id": f"ha_{idi}", "nome": d.get("nome") or "Auto", "carburante": "benzina" if el or plug else tipo,
         "elettrica": el or plug, "ibridaPlugin": plug, "fonte": "Home Assistant", "definita_in": "home_assistant"}
    if d.get("capienza"):
        a["capacitaLitri"] = float(d["capienza"])
    if d.get("consumo"):
        a["consumoMedio" if not el else "consumoKwh"] = float(d["consumo"])
    if d.get("batteria_kwh"):
        a["batteriaKwh"] = float(d["batteria_kwh"])
    liv, unita = letture.get("livello") or (None, None)
    if liv is not None:
        u = (unita or "").strip().lower()
        if u in ("l", "litri") and a.get("capacitaLitri"):
            a["livello"] = max(0.0, min(1.0, liv / a["capacitaLitri"]))
        elif u == "%" or liv > 1:
            a["livello"] = max(0.0, min(1.0, liv / 100))
        else:
            a["livello"] = max(0.0, min(1.0, liv))
    aut, unita = letture.get("autonomia") or (None, None)
    if aut is not None:
        a["autonomiaKm"] = aut * 1.609344 if (unita or "").lower() in ("mi", "miles") else aut
    km, unita = letture.get("km") or (None, None)
    if km is not None:
        a["km"] = km * 1.609344 if (unita or "").lower() in ("mi", "miles") else km
    return a


def unisci_garage(app: list[dict], ha: list[dict]) -> list[dict]:
    """Con l'app sincronizzata il suo garage è la fonte. Un'auto definita in Home Assistant con lo stesso nome di
    un'auto dell'app si fonde in quella (valgono i dati dell'app; dalle entità di HA solo quello che all'app manca);
    le altre si aggiungono. Niente doppioni."""
    out = [dict(a) for a in app]
    per_nome = {str(a.get("nome", "")).strip().lower(): a for a in out}
    for h in ha:
        gemella = per_nome.get(str(h.get("nome", "")).strip().lower())
        if gemella is None:
            out.append(h)
            continue
        for k in ("livello", "autonomiaKm", "km"):
            if gemella.get(k) is None and h.get(k) is not None:
                gemella[k] = h[k]
    return out
