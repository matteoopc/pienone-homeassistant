"""La copia del documento dell'app in Home Assistant (.storage/pienone) e l'indirizzo con cui l'app la legge e la scrive.

Regole uguali a quelle del server dell'account (logica.scrivi_dati): l'app manda il suo documento con una data, vince la
più recente, le chiavi che non manda restano. L'unione per elemento la fa l'app prima di scrivere.
0.2.1 (7/10): POST /api/pienone/documento, che vuole il token dell'utente di Home Assistant (lo controlla Home
Assistant stesso, requires_auth). Fino alla 0.2.0 era un webhook con l'id in un attributo del sensore della
sincronizzazione, quindi nello storico: il webhook non c'è più e il suo id si cancella dall'archivio al primo avvio.
L'indirizzo fa solo questo: leggere e scrivere il documento.
"""
from __future__ import annotations

import logging
import uuid

from aiohttp import web
from homeassistant.helpers.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import logica
from .const import ARCHIVIO_CHIAVE, ARCHIVIO_VERSIONE, DATI_ARCHIVIO, DOMINIO, SEGNALE_ARCHIVIO, URL_DOCUMENTO

_LOG = logging.getLogger(__name__)


class Archivio:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict] = Store(hass, ARCHIVIO_VERSIONE, ARCHIVIO_CHIAVE)
        self.dati: dict | None = None
        self.aggiornato: str | None = None
        self.ultima_sincronia: str | None = None
        self.installazione: str = ""   # numero casuale per installazione (X-Pienone-Installazione), nessun dato personale
        self.voci: set[str] = set()   # le configurazioni accese che lo usano
        self.proprietario: str | None = None   # la configurazione che ha i sensori della sincronizzazione (una sola)

    async def carica(self) -> None:
        s = await self._store.async_load() or {}
        self.dati = s.get("dati")
        self.aggiornato = s.get("aggiornato")
        self.ultima_sincronia = s.get("ultima_sincronia")
        self.installazione = s.get("installazione") or uuid.uuid4().hex
        if "webhook_id" in s or "installazione" not in s:
            await self.salva()   # 0.2.0: l'id del vecchio webhook (finito nello storico) si cancella

    async def salva(self) -> None:
        await self._store.async_save({"dati": self.dati, "aggiornato": self.aggiornato,
                                      "ultima_sincronia": self.ultima_sincronia, "installazione": self.installazione})

    def avvisa(self) -> None:
        async_dispatcher_send(self.hass, SEGNALE_ARCHIVIO)

    async def cambia(self, dati: dict, aggiornato: str) -> None:
        """Un documento nuovo (dall'app o da registra_pieno). Se cambiano i preferiti o le auto (aggiunte, tolte, diventate
        elettriche) le configurazioni si ricaricano: un sensore per preferito, un dispositivo per auto."""
        prima = self._forma(self.dati)
        self.dati, self.aggiornato = dati, aggiornato
        await self.salva()
        self.avvisa()
        if self._forma(dati) != prima:
            for idi in list(self.voci):
                self.hass.async_create_task(self.hass.config_entries.async_reload(idi))

    @staticmethod
    def _forma(dati: dict | None) -> tuple:
        """Quello che decide quali sensori ci sono: i preferiti e le auto col loro tipo."""
        d = dati or {}
        pref = tuple(logica.preferiti_ids(d)) if "preferiti" in d else None
        auto = tuple(sorted((str(a.get("id")), a.get("nome"), bool(a.get("elettrica")), bool(a.get("ibridaPlugin")))
                            for a in d.get("garage") or [] if a.get("id")))
        return pref, auto


class VistaDocumento(HomeAssistantView):
    """POST /api/pienone/documento: {"azione": "leggi"} o {"azione": "scrivi", "dati": …, "aggiornato": …}.
    Home Assistant vuole il token dell'utente prima di arrivare qui (requires_auth)."""
    url = URL_DOCUMENTO
    name = "api:pienone:documento"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        return await _gestisci(request.app[KEY_HASS], request)


async def _gestisci(hass: HomeAssistant, request: web.Request) -> web.Response:
    arch: Archivio | None = hass.data.get(DATI_ARCHIVIO)
    if arch is None:
        return web.json_response({"errore": "integrazione non pronta"}, status=503)
    try:
        corpo = await request.json()
    except ValueError:
        return web.json_response({"errore": "JSON non valido"}, status=400)
    if not isinstance(corpo, dict):
        return web.json_response({"errore": "JSON non valido"}, status=400)
    adesso = dt_util.utcnow()
    azione = corpo.get("azione")
    if azione == "leggi":
        return web.json_response({"dati": arch.dati, "aggiornato": arch.aggiornato})
    if azione != "scrivi":
        return web.json_response({"errore": "azione sconosciuta"}, status=400)
    dati, aggiornato = corpo.get("dati"), corpo.get("aggiornato")
    if not isinstance(dati, dict) or not isinstance(aggiornato, str):
        return web.json_response({"errore": "servono dati e aggiornato"}, status=422)
    try:
        salvato, doc, agg = logica.scrivi_dati(arch.dati, arch.aggiornato, dati, aggiornato, adesso)
    except logica.DatiNonValidi as e:
        return web.json_response({"errore": str(e)}, status=e.codice)
    except ValueError:
        return web.json_response({"errore": "data non valida"}, status=422)
    arch.ultima_sincronia = logica.iso(adesso)
    if salvato:
        await arch.cambia(doc, agg)
    else:
        await arch.salva()
        arch.avvisa()
    return web.json_response({"salvato": salvato, "dati": doc, "aggiornato": agg})


async def apri(hass: HomeAssistant, voce_id: str) -> Archivio:
    """L'archivio è uno per Home Assistant (anche con più configurazioni, una per carburante)."""
    arch: Archivio | None = hass.data.get(DATI_ARCHIVIO)
    if arch is None:
        arch = Archivio(hass)
        await arch.carica()
        hass.data[DATI_ARCHIVIO] = arch
        # un indirizzo non si toglie: si registra una volta per avvio di Home Assistant
        if not hass.data.get(f"{DOMINIO}_vista"):
            hass.http.register_view(VistaDocumento())
            hass.data[f"{DOMINIO}_vista"] = True
    arch.voci.add(voce_id)
    return arch


def chiudi(hass: HomeAssistant, voce_id: str) -> None:
    arch: Archivio | None = hass.data.get(DATI_ARCHIVIO)
    if arch is None:
        return
    arch.voci.discard(voce_id)
    if arch.proprietario == voce_id:
        arch.proprietario = None
    if not arch.voci:
        hass.data.pop(DATI_ARCHIVIO, None)   # l'indirizzo resta ma risponde 503 (integrazione non pronta)
