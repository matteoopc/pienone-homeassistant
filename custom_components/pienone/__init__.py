"""Pienone per Home Assistant: prezzi dei carburanti (dati MIMIT) vicino a casa, tendenza e consiglio.

I prezzi arrivano dall'API pubblica di Pienone; della zona scelta va solo la posizione arrotondata a 3 decimali
(circa 100 m). Sincronizzazione con l'app (5/10, facoltativa): l'app, se l'utente la accende, legge e scrive
il suo documento (preferiti, auto, pieni, preferenze, avvisi) in .storage/pienone tramite POST /api/pienone/documento,
col token dell'utente di Home Assistant (archivio.py). I dati restano in questa casa: niente passa dal server di Pienone.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from . import archivio, logica
from .const import DATI_ARCHIVIO, DOMINIO, SERVIZIO_AGGIORNA, SERVIZIO_REGISTRA_PIENO
from .coordinatore import CoordinatorePienone

PIATTAFORME = [Platform.SENSOR]

SCHEMA_PIENO = vol.Schema({
    vol.Required("litri"): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=500)),
    vol.Optional("euro"): vol.All(vol.Coerce(float), vol.Range(min=0, max=5000)),
    vol.Optional("prezzo"): vol.All(vol.Coerce(float), vol.Range(min=0, max=10)),
    vol.Optional("km"): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional("distributore"): cv.string,
    vol.Optional("impianto"): vol.Coerce(int),
    vol.Optional("auto"): cv.string,
    vol.Optional("quando"): cv.datetime,
    vol.Optional("pieno_completo", default=True): cv.boolean,
})


async def async_setup_entry(hass: HomeAssistant, voce: ConfigEntry) -> bool:
    arch = await archivio.apri(hass, voce.entry_id)
    coord = CoordinatorePienone(hass, voce, arch)
    await coord.async_config_entry_first_refresh()
    coord.segui_entita()
    hass.data.setdefault(DOMINIO, {})[voce.entry_id] = coord
    await hass.config_entries.async_forward_entry_setups(voce, PIATTAFORME)
    voce.async_on_unload(voce.add_update_listener(_ricarica))

    if not hass.services.has_service(DOMINIO, SERVIZIO_AGGIORNA):
        async def aggiorna(chiamata: ServiceCall) -> None:
            for c in hass.data.get(DOMINIO, {}).values():
                await c.async_request_refresh()

        hass.services.async_register(DOMINIO, SERVIZIO_AGGIORNA, aggiorna)

    if not hass.services.has_service(DOMINIO, SERVIZIO_REGISTRA_PIENO):
        async def registra_pieno(chiamata: ServiceCall) -> ServiceResponse:
            """Un pieno nel diario dell'app (da un'automazione, un tag NFC, il salto del livello): l'app lo trova alla
            prossima sincronizzazione, da confermare."""
            a: archivio.Archivio = hass.data[DATI_ARCHIVIO]
            adesso = dt_util.utcnow()
            q = chiamata.data.get("quando")
            quando = dt_util.as_utc(q if q.tzinfo else q.replace(tzinfo=dt_util.get_default_time_zone())) if q else None
            dati, aggiunto, idi = logica.registra_pieno(
                a.dati, chiamata.data["litri"], adesso, euro=chiamata.data.get("euro"), prezzo=chiamata.data.get("prezzo"),
                km=chiamata.data.get("km"), distributore=chiamata.data.get("distributore"),
                impianto=chiamata.data.get("impianto"), auto=chiamata.data.get("auto"), quando=quando,
                pieno_completo=chiamata.data["pieno_completo"])
            if aggiunto:
                await a.cambia(dati, logica.iso(adesso))
            return {"id": idi, "aggiunto": aggiunto}

        hass.services.async_register(DOMINIO, SERVIZIO_REGISTRA_PIENO, registra_pieno, schema=SCHEMA_PIENO,
                                     supports_response=SupportsResponse.OPTIONAL)
    return True


async def async_unload_entry(hass: HomeAssistant, voce: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(voce, PIATTAFORME)
    if ok:
        hass.data[DOMINIO].pop(voce.entry_id, None)
        archivio.chiudi(hass, voce.entry_id)
        if not hass.data[DOMINIO]:
            hass.services.async_remove(DOMINIO, SERVIZIO_AGGIORNA)
            hass.services.async_remove(DOMINIO, SERVIZIO_REGISTRA_PIENO)
    return ok


async def _ricarica(hass: HomeAssistant, voce: ConfigEntry) -> None:
    await hass.config_entries.async_reload(voce.entry_id)
