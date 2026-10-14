"""I sensori.

- Principali (dispositivo «Pienone»): più conveniente, prezzo tipico, tendenza e consiglio per il carburante dell'auto
  attiva sincronizzata (7/10: con la Zoe attiva, le colonnine), altrimenti quello della configurazione; un
  sensore per ogni preferito; sincronizzazione, auto attiva, ultimo pieno, prossimo viaggio e il quadro generale.
- Per carburante (dispositivi «Pienone · benzina», «· gasolio»…, 0.2.1): gli stessi quattro per ogni carburante scelto;
  per l'elettrico le colonnine libere e la ricarica più conveniente.
- Per auto (un dispositivo per ogni auto del garage dell'app, 7/10): livello, autonomia, km, carburante, il più
  conveniente per il suo carburante, prezzo tipico, tendenza, consiglio, ultimo pieno.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import logica
from .const import DOMINIO, SEGNALE_ARCHIVIO, VERSIONE_SINCRONIA
from .coordinatore import CoordinatorePienone

EURO_LITRO = "€/L"
EURO_KWH = "€/kWh"
FONTE = "Prezzi MIMIT (open data) e colonnine PUN tramite Pienone"


async def async_setup_entry(hass: HomeAssistant, voce: ConfigEntry, aggiungi: AddEntitiesCallback) -> None:
    c: CoordinatorePienone = hass.data[DOMINIO][voce.entry_id]
    entita: list[SensorEntity] = [Migliore(c), Mediana(c), Tendenza(c), Consiglio(c)]
    entita += [Preferito(c, idi) for idi in c.preferiti]
    for carb in c.scelti:
        if carb == "elettrico":
            entita += [ColonnineLibere(c), RicaricaConveniente(c)]
        else:
            entita += [Migliore(c, carb), Mediana(c, carb), Tendenza(c, carb), Consiglio(c, carb)]
    # la sincronizzazione con l'app e le auto: una volta sola anche con più configurazioni
    a = c.archivio
    if a is not None and a.proprietario in (None, voce.entry_id):
        a.proprietario = voce.entry_id
        entita += [Sincronizzazione(c), AutoAttiva(c), UltimoPieno(c), ProssimoViaggio(c), Quadro(c), DatiApp(c)]
        if "viaggio" in c.mostra:
            entita.append(InViaggio(c))
        if "carplay" in c.mostra:
            entita.append(CarPlayApp(c))
        if "attivita" in c.mostra:
            entita.append(LiveActivity(c))
        if "notifiche" in c.mostra:
            entita.append(NotificheApp(c))
        for auto in c.garage:
            if not str(auto["id"]).startswith("ha_"):
                entita += sensori_auto(c, auto)
        _togli_auto_vecchie(hass, voce, {str(x["id"]) for x in c.garage})
    aggiungi(entita)
    # le auto definite qui (senza l'app): sotto la loro sotto-voce, così si tolgono insieme a lei
    for auto in c.garage:
        if str(auto["id"]).startswith("ha_"):
            aggiungi(sensori_auto(c, auto), config_subentry_id=str(auto["id"])[3:])


def sensori_auto(c: CoordinatorePienone, auto: dict) -> list[SensorEntity]:
    info = c.per(auto)
    s: list[SensorEntity] = [AutoLivello(c, auto), AutoAutonomia(c, auto), AutoKm(c, auto), AutoCarburante(c, auto),
                             AutoMigliore(c, auto), AutoConsiglio(c, auto), AutoUltimoPieno(c, auto)]
    if info["carburante"] != "elettrico":
        s += [AutoMediana(c, auto), AutoTendenza(c, auto)]
    if info["colonnine"] and info["carburante"] != "elettrico":
        s += [AutoRicarica(c, auto)]   # ibrida plug-in: anche la ricarica
    if "statistiche" in c.mostra:
        s += [AutoStatistica(c, auto, k) for k in STATISTICHE]
    if "obd" in c.mostra:
        s.append(AutoOBD(c, auto))
    return s


def _togli_auto_vecchie(hass: HomeAssistant, voce: ConfigEntry, presenti: set[str]) -> None:
    """Un'auto tolta nell'app: via il suo dispositivo (e i suoi sensori) anche da Home Assistant."""
    reg = dr.async_get(hass)
    for d in dr.async_entries_for_config_entry(reg, voce.entry_id):
        auto = [i[1][5:] for i in d.identifiers if i[0] == DOMINIO and str(i[1]).startswith("auto_")]
        if auto and auto[0] not in presenti:
            reg.async_update_device(d.id, remove_config_entry_id=voce.entry_id)


# --- basi

class Base(CoordinatorEntity[CoordinatorePienone], SensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = FONTE

    def __init__(self, c: CoordinatorePienone, chiave: str, carburante: str | None = None) -> None:
        super().__init__(c)
        self.carburante = carburante
        self._attr_translation_key = chiave
        if carburante is None:
            # i principali: gli stessi id della 0.2.0, così le entità di chi l'aveva già restano
            self._attr_unique_id = f"{c.voce.entry_id}_{chiave}"
            self._attr_device_info = DeviceInfo(identifiers={(DOMINIO, c.voce.entry_id)}, name="Pienone",
                                                manufacturer="Pienone", entry_type=DeviceEntryType.SERVICE)
        else:
            self._attr_unique_id = f"{c.voce.entry_id}_{carburante}_{chiave}"
            self._attr_device_info = DeviceInfo(identifiers={(DOMINIO, f"{c.voce.entry_id}_{carburante}")},
                                                name=f"Pienone · {logica.NOME.get(carburante, carburante)}",
                                                manufacturer="Pienone", entry_type=DeviceEntryType.SERVICE)

    @property
    def info(self) -> dict:
        """Il carburante che segue: quello del dispositivo, o (principali) quello dell'auto attiva."""
        if self.carburante is not None:
            return {"carburante": self.carburante, "colonnine": self.carburante == "elettrico",
                    "self": logica.self_per(self.carburante, self.coordinator.self_), "auto": None}
        return self.coordinator.principale()

    @property
    def elettrico(self) -> bool:
        return self.info["carburante"] == "elettrico"

    def _comuni(self) -> dict:
        i = self.info
        d = {"carburante": i["carburante"], "dati_mimit_del": (self.coordinator.data or {}).get("estrazione")}
        if self.carburante is None:
            d["segue_auto"] = i["auto"]
        return d


class Migliore(Base):
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:gas-station"

    def __init__(self, c, carburante=None):
        super().__init__(c, "piu_conveniente", carburante)
        if carburante is not None:
            # per carburante l'unità non cambia mai: si possono tenere le statistiche
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = EURO_LITRO

    @property
    def native_unit_of_measurement(self):
        return EURO_KWH if self.elettrico else EURO_LITRO

    @property
    def native_value(self):
        m = self.coordinator.vicino_per(self.info)
        if not m:
            return None
        return m.get("prezzo_kwh") if self.elettrico else m.get("prezzo")

    @property
    def extra_state_attributes(self):
        m = self.coordinator.vicino_per(self.info) or {}
        d = self._comuni()
        if not m:
            return d
        if self.elettrico:
            return {**d, **_colonnina(m)}
        return {**d, "distributore": logica.titolo(m), "indirizzo": m.get("indirizzo"), "comune": m.get("comune"),
                "distanza_km": m.get("distanza_km"), "prezzo_comunicato_il": m.get("aggiornato"), "id_mimit": m.get("id"),
                "latitude": m.get("lat"), "longitude": m.get("lon"),
                "apri_in_pienone": f"pienone://impianto/{m.get('id')}", "portami_li": _mappe(m)}


class Mediana(Base):
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:chart-bell-curve"

    def __init__(self, c, carburante=None):
        super().__init__(c, "mediana_zona", carburante)
        if carburante is not None:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = EURO_LITRO

    @property
    def native_unit_of_measurement(self):
        return EURO_KWH if self.elettrico else EURO_LITRO

    @property
    def native_value(self):
        if self.elettrico:
            return logica.mediana_kwh((self.coordinator.data or {}).get("colonnine"))
        return (self.coordinator.zona(self.info["carburante"]).get("vicini") or {}).get("mediana_zona")

    @property
    def extra_state_attributes(self):
        if self.elettrico:
            col = (self.coordinator.data or {}).get("colonnine") or {}
            return {**self._comuni(), "colonnine": col.get("totale"), "libere": logica.libere(col)}
        v = self.coordinator.zona(self.info["carburante"]).get("vicini") or {}
        return {**self._comuni(), "distributori": v.get("totale"), "raggio_km": v.get("raggio_km"),
                "minimo_zona": v.get("minimo_zona")}


class Tendenza(Base):
    _attr_native_unit_of_measurement = "c€/L"
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:trending-up"

    def __init__(self, c, carburante=None):
        super().__init__(c, "tendenza_7_giorni", carburante)
        if carburante is not None:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        if self.elettrico:
            return None   # per la ricarica non c'è uno storico dei prezzi
        t = self.coordinator.zona(self.info["carburante"]).get("tendenza") or {}
        return t.get("zona_diff_cent") if t.get("sufficiente") else None

    @property
    def extra_state_attributes(self):
        t = self.coordinator.zona(self.info["carburante"]).get("tendenza") or {}
        return {**self._comuni(), "oggi": t.get("oggi"), "confronto_con": t.get("prima"),
                "media_zona_oggi": t.get("zona_oggi"), "italia_cent": t.get("italia_diff_cent"), "motivo": t.get("motivo")}


class Consiglio(Base):
    _attr_icon = "mdi:lightbulb-on-outline"

    def __init__(self, c, carburante=None):
        super().__init__(c, "consiglio", carburante)

    @property
    def native_value(self):
        if self.elettrico:
            testo = logica.consiglio_ricarica((self.coordinator.data or {}).get("colonnine"))
        else:
            testo = self.coordinator.zona(self.info["carburante"]).get("consiglio")
        return testo[:255] if testo else None

    @property
    def extra_state_attributes(self):
        return self._comuni()


class ColonnineLibere(Base):
    _attr_icon = "mdi:ev-station"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c):
        super().__init__(c, "colonnine_libere", "elettrico")

    @property
    def native_value(self):
        col = (self.coordinator.data or {}).get("colonnine")
        return logica.libere(col) if col is not None else None

    @property
    def extra_state_attributes(self):
        col = (self.coordinator.data or {}).get("colonnine") or {}
        lib = logica.colonnina_libera(col)
        return {"colonnine_in_zona": col.get("totale"), "aggiornato": col.get("aggiornato"),
                **({"piu_vicina_libera": logica.nome_colonnina(lib), **_colonnina(lib)} if lib else {})}


class RicaricaConveniente(Base):
    _attr_icon = "mdi:ev-plug-type2"
    _attr_native_unit_of_measurement = EURO_KWH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, c):
        super().__init__(c, "ricarica_piu_conveniente", "elettrico")

    @property
    def native_value(self):
        r = logica.ricarica_conveniente((self.coordinator.data or {}).get("colonnine"))
        return r["prezzo_kwh"] if r else None

    @property
    def extra_state_attributes(self):
        r = logica.ricarica_conveniente((self.coordinator.data or {}).get("colonnine"))
        return _colonnina(r) if r else {}


def _colonnina(c: dict | None) -> dict:
    if not c:
        return {}
    return {"colonnina": logica.nome_colonnina(c), "indirizzo": c.get("indirizzo"), "comune": c.get("comune"),
            "distanza_km": c.get("distanza_km"), "potenza_max_kw": c.get("potenza_max_kw"), "prese_libere": c.get("libere"),
            "prese": c.get("n_prese"), "stato": c.get("stato"), "latitude": c.get("lat"), "longitude": c.get("lon"),
            "portami_li": _mappe(c)}


def _mappe(p: dict) -> str | None:
    if p.get("lat") is None or p.get("lon") is None:
        return None
    return f"https://maps.apple.com/?daddr={p['lat']},{p['lon']}"


class Preferito(Base):
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:star"
    _attr_native_unit_of_measurement = EURO_LITRO

    def __init__(self, c, idi: int):
        super().__init__(c, "preferito")
        self.idi = idi
        self._attr_unique_id = f"{c.voce.entry_id}_preferito_{idi}"
        self._attr_translation_placeholders = {"id": str(idi)}

    @property
    def _scheda(self) -> dict:
        return ((self.coordinator.data or {}).get("schede") or {}).get(self.idi) or {}

    @property
    def _carburante(self) -> str:
        """Il carburante dell'auto attiva; per un'elettrica quello della configurazione (il preferito è un distributore)."""
        c = self.coordinator.principale()["carburante"]
        return c if c in logica.MIMIT else (self.coordinator.ripiego if self.coordinator.ripiego in logica.MIMIT else "benzina")

    @property
    def name(self):
        imp = self._scheda.get("impianto") or {}
        return f"{logica.titolo(imp)} {(imp.get('comune') or '').title()}".strip() if imp else f"Preferito {self.idi}"

    @property
    def native_value(self):
        s = self._scheda
        c = self._carburante
        return logica.prezzo_scheda(s, c, logica.self_per(c, self.coordinator.self_)) if s else None

    @property
    def extra_state_attributes(self):
        imp = self._scheda.get("impianto") or {}
        prezzi = {c: logica.prezzo_scheda(self._scheda, c, logica.self_per(c, self.coordinator.self_))
                  for c in logica.MIMIT} if self._scheda else {}
        return {"id_mimit": self.idi, "carburante": self._carburante, "prezzi": {k: v for k, v in prezzi.items() if v},
                "indirizzo": imp.get("indirizzo"), "comune": imp.get("comune"), "latitude": imp.get("lat"),
                "longitude": imp.get("lon"), "apri_in_pienone": f"pienone://impianto/{self.idi}", "portami_li": _mappe(imp)}


# --- dall'app (una volta per Home Assistant)

class DallApp(Base):
    """Un sensore che legge la copia del documento dell'app (archivio) e si aggiorna quando cambia."""

    def __init__(self, c, chiave: str):
        super().__init__(c, chiave)
        self._attr_unique_id = f"{DOMINIO}_{chiave}"   # uno per Home Assistant, non per configurazione

    @property
    def _dati(self) -> dict:
        return self.coordinator.dati_app

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, SEGNALE_ARCHIVIO, self.async_write_ha_state))


class Sincronizzazione(DallApp):
    """Quando l'app ha sincronizzato l'ultima volta. «versione» 2: l'app scrive su /api/pienone/documento col token
    dell'utente (0.2.1: il webhook e il suo id negli attributi non ci sono più)."""
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:sync"

    def __init__(self, c):
        super().__init__(c, "sincronizzazione")
        # un nome fisso, in qualsiasi lingua: l'app lo legge per primo (GET /api/states/sensor.pienone_sincronizzazione)
        self.entity_id = "sensor.pienone_sincronizzazione"

    @property
    def native_value(self):
        a = self.coordinator.archivio
        return logica.data_utc(a.ultima_sincronia) if a and a.ultima_sincronia else None

    @property
    def extra_state_attributes(self):
        d = self._dati
        return {"versione": VERSIONE_SINCRONIA, "preferiti": len(d.get("preferiti") or []),
                "auto": len(d.get("garage") or []), "pieni": len(d.get("diario") or [])}


class AutoAttiva(DallApp):
    _attr_icon = "mdi:car"

    def __init__(self, c):
        super().__init__(c, "auto_attiva")

    @property
    def native_value(self):
        a = logica.auto_attiva(self._dati)
        return a.get("nome") if a else None

    @property
    def extra_state_attributes(self):
        a = logica.auto_attiva(self._dati) or {}
        if not a:
            return {}
        liv = a.get("livello")
        return {"carburante": self.coordinator.per(a)["carburante"], "capienza_l": a.get("capacitaLitri"),
                "consumo_l_100km": a.get("consumoMedio"),
                "livello_percento": round(liv * 100) if isinstance(liv, (int, float)) else None,
                "autonomia_km": logica.autonomia_auto(a), "km": a.get("km"), "marca": a.get("marca"),
                "modello": a.get("modello"), "dispositivo": f"Pienone · {a.get('nome')}", "id_auto": a.get("id")}


class UltimoPieno(DallApp):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:gas-station-outline"

    def __init__(self, c):
        super().__init__(c, "ultimo_pieno")

    @property
    def native_value(self):
        p = logica.ultimo_pieno(self._dati)
        return logica.da_swift(p["data"]) if p else None

    @property
    def extra_state_attributes(self):
        return _pieno(self._dati, logica.ultimo_pieno(self._dati))


def _pieno(dati: dict, p: dict | None) -> dict:
    if not p:
        return {}
    litri, euro = p.get("litri") or 0, p.get("euro") or 0
    auto = next((a.get("nome") for a in dati.get("garage") or [] if a.get("id") == p.get("autoID")), None)
    return {"litri": litri, "euro": euro, "prezzo": round(euro / litri, 3) if litri else None, "km": p.get("km"),
            "distributore": p.get("distributore"), "auto": auto, "da_confermare": bool(p.get("daConfermare")),
            "registrato_da": p.get("automatico") or "app"}


class ProssimoViaggio(DallApp):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:map-marker-path"

    def __init__(self, c):
        super().__init__(c, "prossimo_viaggio")

    @property
    def _viaggio(self) -> dict | None:
        return logica.prossimo_viaggio(self._dati, dt_util.utcnow())

    @property
    def native_value(self):
        v = self._viaggio
        return v["data"] if v else None

    @property
    def extra_state_attributes(self):
        v = self._viaggio
        return {"luogo": v["luogo"], "titolo": v["titolo"], "km": v["km"], "andata_ritorno": v["andata_ritorno"]} if v else {}


class Quadro(DallApp):
    """Il quadro generale (7/10): quante auto sono da rifornire presto e, per ognuna, livello, autonomia,
    consiglio e il più conveniente; più la tendenza della zona e il prossimo viaggio."""
    _attr_icon = "mdi:view-dashboard-outline"

    def __init__(self, c):
        super().__init__(c, "quadro")

    def _righe(self) -> list[dict]:
        righe = []
        for a in self.coordinator.garage:
            info = self.coordinator.per(a)
            cons = self.coordinator.consiglio_auto(a)
            v = self.coordinator.vicino_per(info) or {}
            liv = logica.livello_auto(a)
            el = info["carburante"] == "elettrico"
            righe.append({"auto": a.get("nome"), "carburante": info["carburante"],
                          "livello_percento": round(liv * 100) if liv is not None else None,
                          "autonomia_km": logica.autonomia_auto(a), "consiglio": cons["testo"], "presto": cons["presto"],
                          "dove": (logica.nome_colonnina(v) if el else logica.titolo(v)) if v else None,
                          "prezzo": (v.get("prezzo_kwh") if el else v.get("prezzo")) if v else None,
                          "unita": EURO_KWH if el else EURO_LITRO, "portami_li": _mappe(v) if v else None})
        return righe

    @property
    def native_value(self):
        return logica.quadro(self._righe())

    @property
    def extra_state_attributes(self):
        p = self.coordinator.principale()
        t = self.coordinator.zona(p["carburante"]).get("tendenza") or {} if p["carburante"] in logica.MIMIT else {}
        v = logica.prossimo_viaggio(self._dati, dt_util.utcnow())
        return {"auto": self._righe(), "carburante_zona": p["carburante"],
                "tendenza_zona_cent": t.get("zona_diff_cent") if t.get("sufficiente") else None,
                "prezzo_tipico_zona": (self.coordinator.zona(p["carburante"]).get("vicini") or {}).get("mediana_zona"),
                "prossimo_viaggio": {"luogo": v["luogo"], "data": v["data"].isoformat(), "km": v["km"]} if v else None,
                "dati_mimit_del": (self.coordinator.data or {}).get("estrazione")}


# --- per auto

class SuAuto(CoordinatorEntity[CoordinatorePienone], SensorEntity):
    """Un sensore del dispositivo di UN'auto del garage sincronizzato. L'auto si rilegge dall'archivio a ogni stato."""
    _attr_has_entity_name = True
    _attr_attribution = FONTE

    def __init__(self, c: CoordinatorePienone, auto: dict, chiave: str) -> None:
        super().__init__(c)
        self.id_auto = str(auto["id"])
        self._attr_translation_key = f"auto_{chiave}"
        self._attr_unique_id = f"{DOMINIO}_auto_{self.id_auto}_{chiave}"
        nome = auto.get("nome") or "Auto"
        self._attr_device_info = DeviceInfo(identifiers={(DOMINIO, f"auto_{self.id_auto}")}, name=f"Pienone · {nome}",
                                            manufacturer=auto.get("marca") or "Pienone", model=auto.get("modello"),
                                            entry_type=DeviceEntryType.SERVICE)

    @property
    def auto(self) -> dict:
        return next((a for a in self.coordinator.garage if str(a.get("id")) == self.id_auto), {})

    @property
    def available(self) -> bool:
        return bool(self.auto)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, SEGNALE_ARCHIVIO, self.async_write_ha_state))


class AutoLivello(SuAuto):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c, auto):
        super().__init__(c, auto, "livello")
        if c.per(auto)["carburante"] == "elettrico":
            self._attr_device_class = SensorDeviceClass.BATTERY
        else:
            self._attr_icon = "mdi:gauge"

    @property
    def native_value(self):
        v = logica.livello_auto(self.auto)
        return round(v * 100) if v is not None else None

    @property
    def extra_state_attributes(self):
        a = self.auto
        d = logica.da_swift(a.get("livelloDel")) if isinstance(a.get("livelloDel"), (int, float)) else None
        return {"letto_il": d.isoformat() if d else None, "fonte": a.get("fonte"),
                "batteria_percento": round(a["caricaBatteria"] * 100) if isinstance(a.get("caricaBatteria"), (int, float)) else None}


class AutoAutonomia(SuAuto):
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-distance"

    def __init__(self, c, auto):
        super().__init__(c, auto, "autonomia")

    @property
    def native_value(self):
        return logica.autonomia_auto(self.auto)

    @property
    def extra_state_attributes(self):
        a = self.auto
        return {"autonomia_elettrica_km": a.get("autonomiaElettricaKm")} if a.get("ibridaPlugin") else {}


class AutoKm(SuAuto):
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(self, c, auto):
        super().__init__(c, auto, "km")

    @property
    def native_value(self):
        k = self.auto.get("km")
        return round(k) if isinstance(k, (int, float)) else None


class AutoCarburante(SuAuto):
    _attr_icon = "mdi:fuel"

    def __init__(self, c, auto):
        super().__init__(c, auto, "carburante")

    @property
    def native_value(self):
        a = self.auto
        if not a:
            return None
        info = self.coordinator.per(a)
        if info["carburante"] == "elettrico":
            return "elettrico"
        return f"{info['carburante']} + elettrico" if a.get("ibridaPlugin") else info["carburante"]


class AutoMigliore(SuAuto):
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:gas-station"

    def __init__(self, c, auto):
        super().__init__(c, auto, "piu_conveniente")
        self._el = c.per(auto)["carburante"] == "elettrico"
        self._attr_native_unit_of_measurement = EURO_KWH if self._el else EURO_LITRO
        self._attr_state_class = SensorStateClass.MEASUREMENT
        if self._el:
            self._attr_icon = "mdi:ev-station"

    @property
    def native_value(self):
        v = self.coordinator.vicino_per(self.coordinator.per(self.auto)) if self.auto else None
        if not v:
            return None
        return v.get("prezzo_kwh") if self._el else v.get("prezzo")

    @property
    def extra_state_attributes(self):
        v = self.coordinator.vicino_per(self.coordinator.per(self.auto)) if self.auto else None
        if not v:
            return {}
        if self._el:
            return _colonnina(v)
        return {"distributore": logica.titolo(v), "indirizzo": v.get("indirizzo"), "comune": v.get("comune"),
                "distanza_km": v.get("distanza_km"), "prezzo_comunicato_il": v.get("aggiornato"), "id_mimit": v.get("id"),
                "latitude": v.get("lat"), "longitude": v.get("lon"), "apri_in_pienone": f"pienone://impianto/{v.get('id')}",
                "portami_li": _mappe(v), "dati_mimit_del": (self.coordinator.data or {}).get("estrazione")}


class AutoRicarica(SuAuto):
    """Ibrida plug-in: anche la ricarica più conveniente (o la più vicina libera)."""
    _attr_native_unit_of_measurement = EURO_KWH
    _attr_suggested_display_precision = 2
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:ev-station"

    def __init__(self, c, auto):
        super().__init__(c, auto, "ricarica")

    def _colonnina(self) -> dict | None:
        col = (self.coordinator.data or {}).get("colonnine")
        return logica.ricarica_conveniente(col) or logica.colonnina_libera(col)

    @property
    def native_value(self):
        c = self._colonnina()
        return c.get("prezzo_kwh") if c else None

    @property
    def extra_state_attributes(self):
        return _colonnina(self._colonnina())


class AutoMediana(SuAuto):
    _attr_native_unit_of_measurement = EURO_LITRO
    _attr_suggested_display_precision = 3
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-bell-curve"

    def __init__(self, c, auto):
        super().__init__(c, auto, "mediana_zona")

    @property
    def native_value(self):
        info = self.coordinator.per(self.auto) if self.auto else None
        return (self.coordinator.zona(info["carburante"]).get("vicini") or {}).get("mediana_zona") if info else None


class AutoTendenza(SuAuto):
    _attr_native_unit_of_measurement = "c€/L"
    _attr_suggested_display_precision = 1
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:trending-up"

    def __init__(self, c, auto):
        super().__init__(c, auto, "tendenza_7_giorni")

    @property
    def native_value(self):
        info = self.coordinator.per(self.auto) if self.auto else None
        t = self.coordinator.zona(info["carburante"]).get("tendenza") or {} if info else {}
        return t.get("zona_diff_cent") if t.get("sufficiente") else None


class AutoConsiglio(SuAuto):
    _attr_icon = "mdi:lightbulb-on-outline"

    def __init__(self, c, auto):
        super().__init__(c, auto, "consiglio")

    @property
    def native_value(self):
        return self.coordinator.consiglio_auto(self.auto)["testo"][:255] if self.auto else None

    @property
    def extra_state_attributes(self):
        if not self.auto:
            return {}
        v = logica.prossimo_viaggio(self.coordinator.dati_app, dt_util.utcnow())
        return {"da_rifornire_presto": self.coordinator.consiglio_auto(self.auto)["presto"],
                "prossimo_viaggio": v["luogo"] if v else None, "km_viaggio": v["km"] if v else None}


class AutoUltimoPieno(SuAuto):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:gas-station-outline"

    def __init__(self, c, auto):
        super().__init__(c, auto, "ultimo_pieno")

    @property
    def native_value(self):
        p = logica.ultimo_pieno_auto(self.coordinator.dati_app, self.id_auto)
        return logica.da_swift(p["data"]) if p else None

    @property
    def extra_state_attributes(self):
        return _pieno(self.coordinator.dati_app, logica.ultimo_pieno_auto(self.coordinator.dati_app, self.id_auto))


# --- dallo «stato» dell'app (contratto versionato): si mostrano le sezioni scelte in «Configura»

class DatiApp(DallApp):
    """Tutte le sezioni dello stato dell'app scelte in «Configura», negli attributi: anche i campi che questa versione
    dell'integrazione non conosce compaiono qui senza aggiornarla."""
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:cellphone-information"

    def __init__(self, c):
        super().__init__(c, "dati_app")

    @property
    def native_value(self):
        t = logica.stato_app(self._dati).get("inviato")
        try:
            return logica.data_utc(t) if t else None
        except ValueError:
            return None

    @property
    def extra_state_attributes(self):
        return {"contratto": logica.stato_app(self._dati).get("contratto"),
                **logica.sezioni_mostrate(self.coordinator.mostra, self._dati)}


class SezioneApp(DallApp):
    sezione = ""

    @property
    def _s(self) -> dict:
        return logica.sezione(self._dati, self.sezione) or {}

    @property
    def available(self) -> bool:
        return logica.sezione(self._dati, self.sezione) is not None

    @property
    def extra_state_attributes(self):
        return self._s


class InViaggio(SezioneApp):
    _attr_icon = "mdi:car-arrow-right"
    sezione = "viaggio"

    def __init__(self, c):
        super().__init__(c, "in_viaggio")

    @property
    def native_value(self):
        return logica.testo_viaggio(self._s)


class CarPlayApp(SezioneApp):
    _attr_icon = "mdi:car-connected"
    sezione = "carplay"

    def __init__(self, c):
        super().__init__(c, "carplay")

    @property
    def native_value(self):
        s = self._s
        if not s.get("collegato"):
            return "Scollegato"
        auto = next((a.get("nome") for a in self.coordinator.garage
                     if str(a.get("id")).upper() == str(s.get("auto_id") or "").upper()), None)
        return f"Collegato · {auto}" if auto else "Collegato"


class LiveActivity(SezioneApp):
    _attr_icon = "mdi:cellphone-text"
    sezione = "attivita"

    def __init__(self, c):
        super().__init__(c, "live_activity")

    @property
    def native_value(self):
        s = self._s
        return (s.get("tipo") or "attiva") if s.get("attiva") else "spenta"


class NotificheApp(SezioneApp):
    _attr_icon = "mdi:bell-outline"
    sezione = "notifiche"

    def __init__(self, c):
        super().__init__(c, "notifiche_app")

    @property
    def native_value(self):
        s = self._s
        if s.get("permesso") in ("negate", "non chiesto"):
            return s["permesso"]
        return sum(1 for v in s.values() if v is True)


# statistiche del diario per auto: chiave nello stato, unità, icona
STATISTICHE = {
    "consumo_medio": ("L/100km", "mdi:gauge"),
    "spesa_mese": ("€", "mdi:cash"),
    "km_mese": (UnitOfLength.KILOMETERS, "mdi:map-marker-distance"),
    "litri_mese": ("L", "mdi:water"),
    "prezzo_medio": (EURO_LITRO, "mdi:tag-outline"),
}


class AutoStatistica(SuAuto):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c, auto, chiave: str):
        super().__init__(c, auto, chiave)
        self.chiave = chiave
        unita, icona = STATISTICHE[chiave]
        el = c.per(auto)["carburante"] == "elettrico"
        if el and chiave == "consumo_medio":
            unita = "kWh/100km"
        elif el and chiave == "litri_mese":
            unita = "kWh"
        elif el and chiave == "prezzo_medio":
            unita = EURO_KWH
        self._attr_native_unit_of_measurement = unita
        self._attr_icon = icona

    @property
    def native_value(self):
        v = logica.per_auto_in(self.coordinator.dati_app, "statistiche", self.id_auto).get(self.chiave)
        return round(v, 3) if isinstance(v, (int, float)) else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()


class AutoOBD(SuAuto):
    _attr_icon = "mdi:car-wrench"

    def __init__(self, c, auto):
        super().__init__(c, auto, "obd")

    @property
    def _o(self) -> dict:
        return logica.per_auto_in(self.coordinator.dati_app, "obd", self.id_auto)

    @property
    def native_value(self):
        o = self._o
        if not o:
            return None
        codici, sospesi = o.get("codici") or [], o.get("in_sospeso") or []
        testo = f"{len(codici)} codici" if len(codici) != 1 else "1 codice"
        if not codici:
            testo = "nessun codice" + (f" ({len(sospesi)} in sospeso)" if sospesi else "")
        return ("spia accesa · " + testo) if o.get("spia_motore") else testo

    @property
    def extra_state_attributes(self):
        return self._o
