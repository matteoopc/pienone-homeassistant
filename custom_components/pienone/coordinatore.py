"""Il giro di lettura ogni 30 minuti: per ogni carburante che serve (quelli scelti e quelli delle auto sincronizzate)
i vicini e la tendenza della zona, le colonnine se servono, le schede dei distributori preferiti e degli avvisi."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import logica
from .const import (API, CONF_CARBURANTE, CONF_CARBURANTI, CONF_LAT, CONF_MOSTRA, CONF_LON, CONF_PREFERITI,
                    CONF_PREFERITI_SCELTI, CONF_RAGGIO, CONF_SELF,
                    CONF_SOGLIA, DOMINIO, EVENTO_PREZZO_SCESO, EVENTO_SOTTO_SOGLIA, INTERVALLO_MINUTI,
                    RAGGIO_COLONNINE, RAGGIO_PREDEFINITO, SOGLIA_PREDEFINITA)

_LOG = logging.getLogger(__name__)


def opzione(voce: ConfigEntry, chiave: str, predefinito=None):
    """Le opzioni (modificabili dopo) vincono sui dati della configurazione iniziale."""
    return voce.options.get(chiave, voce.data.get(chiave, predefinito))


def preferiti(voce: ConfigEntry) -> list[int]:
    """Senza l'app: quelli scelti dall'elenco dei vicini, più quelli scritti per numero."""
    scelti = [int(x) for x in opzione(voce, CONF_PREFERITI_SCELTI, []) or [] if str(x).isdigit()]
    testo = str(opzione(voce, CONF_PREFERITI, "") or "")
    scritti = [int(x) for x in testo.replace(";", ",").replace(" ", ",").split(",") if x.strip().isdigit()]
    return list(dict.fromkeys(scelti + scritti))[:10]


class CoordinatorePienone(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, voce: ConfigEntry, archivio=None) -> None:
        super().__init__(hass, _LOG, name=DOMINIO, update_interval=timedelta(minutes=INTERVALLO_MINUTI))
        self.voce = voce
        # 0.2.0 aveva un carburante solo: resta il ripiego dei sensori principali e tiene i loro id
        self.vecchio = voce.data.get(CONF_CARBURANTE)
        self.scelti = logica.carburanti_scelti(opzione(voce, CONF_CARBURANTI), self.vecchio)
        self.ripiego = self.vecchio or next((c for c in self.scelti if c in logica.MIMIT), "benzina")
        self.self_ = bool(opzione(voce, CONF_SELF, True))
        self.raggio = float(opzione(voce, CONF_RAGGIO, RAGGIO_PREDEFINITO))
        # la zona arrotondata a 3 decimali (circa 100 m): basta per i distributori vicini
        self.lat = round(float(opzione(voce, CONF_LAT, hass.config.latitude)), 3)
        self.lon = round(float(opzione(voce, CONF_LON, hass.config.longitude)), 3)
        self.soglia = float(opzione(voce, CONF_SOGLIA, SOGLIA_PREDEFINITA))
        m = opzione(voce, CONF_MOSTRA)
        self.mostra = list(m) if isinstance(m, list) else list(logica.SEZIONI_ACCESE)
        self.archivio = archivio
        # con l'app sincronizzata valgono i suoi preferiti (5/10: niente più numeri scritti a mano)
        dati = archivio.dati if archivio else None
        self.preferiti = logica.preferiti_ids(dati) if dati and "preferiti" in dati else preferiti(voce)
        self._sessione = async_get_clientsession(hass)
        # senza l'app (7/10): le auto definite qui (sotto-voci «auto»), con le loro entità di livello, autonomia e km
        self.auto_ha = {sid: dict(s.data) for sid, s in voce.subentries.items() if s.subentry_type == "auto"}

    def segui_entita(self) -> None:
        """Quando cambia un'entità di un'auto definita qui, i sensori si aggiornano subito (non ogni 30 minuti)."""
        ids = sorted({e for d in self.auto_ha.values() for k in ("entita_livello", "entita_autonomia", "entita_km")
                      if (e := d.get(k))})
        if not ids:
            return

        @callback
        def cambiata(_evento: Event[EventStateChangedData]) -> None:
            self.async_update_listeners()

        self.voce.async_on_unload(async_track_state_change_event(self.hass, ids, cambiata))

    # --- quello che serve, dalle auto sincronizzate

    @property
    def dati_app(self) -> dict:
        return (self.archivio.dati if self.archivio else None) or {}

    def _lettura(self, entita: str | None):
        s = self.hass.states.get(entita) if entita else None
        v = logica.numero_stato(s.state) if s else None
        return (v, s.attributes.get("unit_of_measurement")) if v is not None else None

    def garage_ha(self) -> list[dict]:
        return [logica.auto_da_ha(sid, d, {"livello": self._lettura(d.get("entita_livello")),
                                           "autonomia": self._lettura(d.get("entita_autonomia")),
                                           "km": self._lettura(d.get("entita_km"))})
                for sid, d in self.auto_ha.items()]

    @property
    def garage(self) -> list[dict]:
        """Le auto dell'app sincronizzata più quelle definite qui (senza doppioni: logica.unisci_garage)."""
        app = [a for a in self.dati_app.get("garage") or [] if a.get("id")]
        return logica.unisci_garage(app, self.garage_ha())

    def principale(self) -> dict:
        """Cosa seguono i sensori principali: l'auto attiva sincronizzata, altrimenti la configurazione (senza l'app le
        auto definite qui non cambiano i principali: per quelle ci sono i loro dispositivi)."""
        return logica.per_auto(logica.auto_attiva(self.dati_app), self.ripiego, self.self_)

    def per(self, auto: dict) -> dict:
        return logica.per_auto(auto, self.ripiego, self.self_)

    def _da_leggere(self) -> tuple[list[str], bool]:
        carb = [c for c in self.scelti if c in logica.MIMIT]
        colonnine = "elettrico" in self.scelti
        for info in [self.principale()] + [self.per(a) for a in self.garage]:
            if info["carburante"] in logica.MIMIT and info["carburante"] not in carb:
                carb.append(info["carburante"])
            colonnine = colonnine or info["colonnine"]
        return carb, colonnine

    async def _leggi(self, percorso: str, parametri: dict | None = None) -> dict:
        # un numero casuale per installazione (nessun dato personale): serve al server per i limiti contro gli abusi
        intestazioni = {"User-Agent": "Pienone-HomeAssistant/0.2.3"}
        if self.archivio is not None and self.archivio.installazione:
            intestazioni["X-Pienone-Installazione"] = self.archivio.installazione
        async with asyncio.timeout(20):
            async with self._sessione.get(API + percorso, params=parametri, headers=intestazioni) as r:
                r.raise_for_status()
                return await r.json()

    async def _zona(self, carburante: str) -> dict:
        comuni = {"lat": self.lat, "lon": self.lon, "carburante": carburante,
                  "self": 1 if logica.self_per(carburante, self.self_) else 0, "raggio_km": self.raggio}
        vicini = await self._leggi("/v1/vicini", {**comuni, "limite": 20, "ordine": "prezzo"})
        try:
            tendenza = await self._leggi("/v1/tendenza", comuni)
        except (aiohttp.ClientError, TimeoutError):
            tendenza = None   # la tendenza è un di più
        m = logica.migliore(vicini)
        return {"vicini": vicini, "migliore": m, "tendenza": tendenza, "consiglio": logica.consiglio(m, tendenza, carburante)}

    async def _async_update_data(self) -> dict:
        carb, con_colonnine = self._da_leggere()
        zona: dict[str, dict] = {}
        errore = None
        for c in carb:
            try:
                zona[c] = await self._zona(c)
            except (aiohttp.ClientError, TimeoutError) as e:
                errore = e
        if carb and not zona:
            raise UpdateFailed(f"Pienone non risponde: {errore}") from errore
        colonnine = None
        if con_colonnine:
            try:
                colonnine = await self._leggi("/v1/colonnine", {"lat": self.lat, "lon": self.lon,
                                                                "raggio_km": min(self.raggio, RAGGIO_COLONNINE), "limite": 30})
            except (aiohttp.ClientError, TimeoutError):
                colonnine = None
        schede = {}
        # anche i distributori degli avvisi di prezzo dell'app (al massimo 20 schede per giro)
        da_leggere = list(dict.fromkeys(self.preferiti + [a["impianto"] for a in self._avvisi()]))[:20]
        for idi in da_leggere:
            try:
                schede[idi] = await self._leggi(f"/v1/impianto/{idi}", {"giorni": 1})
            except (aiohttp.ClientError, TimeoutError):
                continue
        estrazione = next((logica.data_estrazione(z["vicini"]) for z in zona.values() if z.get("vicini")), None)
        dati = {"zona": zona, "colonnine": colonnine, "schede": schede, "estrazione": estrazione}
        self._eventi(dati)
        return dati

    # --- le letture pronte per i sensori

    def zona(self, carburante: str) -> dict:
        return ((self.data or {}).get("zona") or {}).get(carburante) or {}

    def vicino_per(self, info: dict) -> dict | None:
        """Il più conveniente per quel carburante; per l'elettrica la ricarica più conveniente o la più vicina libera."""
        if info["carburante"] == "elettrico":
            c = (self.data or {}).get("colonnine")
            return logica.ricarica_conveniente(c) or logica.colonnina_libera(c)
        return self.zona(info["carburante"]).get("migliore")

    def consiglio_auto(self, auto: dict) -> dict:
        info = self.per(auto)
        tendenza = self.zona(info["carburante"]).get("tendenza") if info["carburante"] in logica.MIMIT else None
        viaggio = logica.prossimo_viaggio(self.dati_app, dt_util.utcnow())
        return logica.consiglio_auto(auto, self.vicino_per(info), tendenza, viaggio)

    # --- eventi

    def _avvisi(self) -> list[dict]:
        """Gli avvisi di prezzo impostati nell'app (impianto, carburante, self, soglia in €/L)."""
        return [a for a in self.dati_app.get("avvisi") or []
                if isinstance(a.get("impianto"), int) and isinstance(a.get("soglia"), (int, float))]

    def _eventi(self, nuovi: dict) -> None:
        """«pienone_prezzo_sceso»: il più conveniente della zona (per ogni carburante) o un preferito sono scesi
        almeno della soglia."""
        vecchi = self.data or {}
        for c, z in (nuovi.get("zona") or {}).items():
            prima = (((vecchi.get("zona") or {}).get(c) or {}).get("migliore") or {}).get("prezzo")
            adesso = (z.get("migliore") or {}).get("prezzo")
            if (d := logica.calo(prima, adesso, self.soglia)) is not None:
                m = z["migliore"]
                self.hass.bus.async_fire(EVENTO_PREZZO_SCESO, {
                    "dove": "zona", "carburante": c, "prezzo": adesso, "prima": prima, "calo_cent": d,
                    "distributore": logica.titolo(m), "id": m.get("id")})
        for idi, s in (nuovi.get("schede") or {}).items():
            v = (vecchi.get("schede") or {}).get(idi)
            for c in [x for x in self.scelti if x in logica.MIMIT]:
                p0 = logica.prezzo_scheda(v, c, logica.self_per(c, self.self_)) if v else None
                p1 = logica.prezzo_scheda(s, c, logica.self_per(c, self.self_))
                if (d := logica.calo(p0, p1, self.soglia)) is not None:
                    self.hass.bus.async_fire(EVENTO_PREZZO_SCESO, {
                        "dove": "preferito", "carburante": c, "prezzo": p1, "prima": p0, "calo_cent": d,
                        "distributore": logica.titolo(s.get("impianto") or {}), "id": idi})
        # «pienone_sotto_soglia»: un avviso di prezzo dell'app è arrivato alla sua soglia (una volta, finché non risale)
        # al primo giro dopo l'avvio di Home Assistant niente: non si sa se è appena scesa o lo era già
        for a in (self._avvisi() if self.data is not None else []):
            s, v = (nuovi.get("schede") or {}).get(a["impianto"]), (vecchi.get("schede") or {}).get(a["impianto"])
            if not s:
                continue
            p0 = logica.prezzo_scheda(v, a.get("carburante", ""), a.get("self") == 1) if v else None
            p1 = logica.prezzo_scheda(s, a.get("carburante", ""), a.get("self") == 1)
            if logica.sotto_soglia(p0, p1, float(a["soglia"])):
                self.hass.bus.async_fire(EVENTO_SOTTO_SOGLIA, {
                    "carburante": a.get("carburante"), "self": a.get("self") == 1, "prezzo": p1, "soglia": a["soglia"],
                    "distributore": logica.titolo(s.get("impianto") or {}), "id": a["impianto"]})
