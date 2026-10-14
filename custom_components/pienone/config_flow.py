"""Configurazione dall'interfaccia: zona (di partenza la casa), carburanti, self, raggio; poi preferiti e soglia.

0.2.1 (7/10: «perché devo scegliere tra benzina e gasolio e non posso avere tutto?»): i carburanti sono una scelta
multipla con tutti già spuntati, e si cambiano dopo da «Configura». I sensori principali seguono comunque l'auto attiva
dell'app sincronizzata.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import logica
from .const import (CARBURANTI, CONF_CARBURANTE, CONF_CARBURANTI, CONF_LAT, CONF_MOSTRA, CONF_LON, CONF_PREFERITI,
                    CONF_PREFERITI_SCELTI, CONF_RAGGIO, CONF_SELF, CONF_SOGLIA, DOMINIO, RAGGIO_PREDEFINITO,
                    SOGLIA_PREDEFINITA)


def _in_italia(lat: float, lon: float) -> bool:
    return 35 <= lat <= 48 and 6 <= lon <= 19.5


def _scelta_carburanti(predefiniti: list[str]) -> vol.Required:
    return vol.Required(CONF_CARBURANTI, default=predefiniti)


SELETTORE_SEZIONI = selector.SelectSelector(
    selector.SelectSelectorConfig(options=list(logica.SEZIONI), multiple=True, mode=selector.SelectSelectorMode.LIST,
                                  translation_key="sezione"))

SELETTORE_CARBURANTI = selector.SelectSelector(
    selector.SelectSelectorConfig(options=CARBURANTI, multiple=True, mode=selector.SelectSelectorMode.LIST,
                                  translation_key="carburante"))


class FlussoPienone(config_entries.ConfigFlow, domain=DOMINIO):
    VERSION = 1

    async def async_step_user(self, dati=None):
        errori = {}
        if dati is not None:
            if not _in_italia(dati[CONF_LAT], dati[CONF_LON]):
                errori["base"] = "fuori_italia"
            elif not dati.get(CONF_CARBURANTI):
                errori["base"] = "nessun_carburante"
            else:
                await self.async_set_unique_id(f"zona_{round(dati[CONF_LAT], 3)}_{round(dati[CONF_LON], 3)}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Pienone", data=dati)
        schema = vol.Schema({
            _scelta_carburanti(list(CARBURANTI)): SELETTORE_CARBURANTI,
            vol.Required(CONF_SELF, default=True): bool,
            vol.Required(CONF_RAGGIO, default=RAGGIO_PREDEFINITO): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=15, step=1, unit_of_measurement="km")),
            vol.Required(CONF_LAT, default=self.hass.config.latitude): vol.Coerce(float),
            vol.Required(CONF_LON, default=self.hass.config.longitude): vol.Coerce(float),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errori)

    @staticmethod
    @callback
    def async_get_options_flow(voce):
        return OpzioniPienone()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, voce) -> dict[str, type[ConfigSubentryFlow]]:
        return {"auto": FlussoAuto}


def _schema_auto(d: dict) -> vol.Schema:
    sensore = selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "number", "input_number"]))
    def numero(mx: float, u: str | None) -> selector.NumberSelector:
        c = selector.NumberSelectorConfig(min=0, max=mx, step=0.1, mode=selector.NumberSelectorMode.BOX)
        if u:
            c["unit_of_measurement"] = u
        return selector.NumberSelector(c)
    return vol.Schema({
        vol.Required("nome", default=d.get("nome", "")): str,
        vol.Required("tipo", default=d.get("tipo", "benzina")): selector.SelectSelector(selector.SelectSelectorConfig(
            options=list(logica.TIPI_AUTO), translation_key="tipo_auto")),
        vol.Optional("capienza", description={"suggested_value": d.get("capienza")}): numero(200, "L"),
        vol.Optional("batteria_kwh", description={"suggested_value": d.get("batteria_kwh")}): numero(250, "kWh"),
        vol.Optional("consumo", description={"suggested_value": d.get("consumo")}): numero(50, None),
        vol.Optional("entita_livello", description={"suggested_value": d.get("entita_livello")}): sensore,
        vol.Optional("entita_autonomia", description={"suggested_value": d.get("entita_autonomia")}): sensore,
        vol.Optional("entita_km", description={"suggested_value": d.get("entita_km")}): sensore,
    })


class FlussoAuto(ConfigSubentryFlow):
    """Senza l'app (7/10): un'auto definita qui, con le entità che ha già (per esempio dell'integrazione dell'auto)."""

    async def async_step_user(self, dati=None) -> SubentryFlowResult:
        if dati is not None:
            return self.async_create_entry(title=dati["nome"], data=dati)
        return self.async_show_form(step_id="user", data_schema=_schema_auto({}))

    async def async_step_reconfigure(self, dati=None) -> SubentryFlowResult:
        sotto = self._get_reconfigure_subentry()
        if dati is not None:
            return self.async_update_and_abort(self._get_entry(), sotto, title=dati["nome"], data=dati)
        return self.async_show_form(step_id="reconfigure", data_schema=_schema_auto(dict(sotto.data)))


class OpzioniPienone(config_entries.OptionsFlow):
    async def async_step_init(self, dati=None):
        errori = {}
        if dati is not None:
            if not dati.get(CONF_CARBURANTI):
                errori["base"] = "nessun_carburante"
            else:
                return self.async_create_entry(data=dati)
        v = self.config_entry
        attuali = logica.carburanti_scelti(v.options.get(CONF_CARBURANTI, v.data.get(CONF_CARBURANTI)),
                                           v.data.get(CONF_CARBURANTE))
        # una configurazione della 0.2.0 (un carburante solo): di partenza qui li propone tutti
        if CONF_CARBURANTI not in v.options and CONF_CARBURANTI not in v.data:
            attuali = list(CARBURANTI)
        schema = vol.Schema({
            _scelta_carburanti(attuali): SELETTORE_CARBURANTI,
            vol.Required(CONF_SELF, default=v.options.get(CONF_SELF, v.data.get(CONF_SELF, True))): bool,
            vol.Optional(CONF_MOSTRA, default=v.options.get(CONF_MOSTRA, list(logica.SEZIONI_ACCESE))): SELETTORE_SEZIONI,
            vol.Optional(CONF_PREFERITI_SCELTI, default=v.options.get(CONF_PREFERITI_SCELTI, [])): self._vicini(),
            vol.Optional(CONF_PREFERITI, default=v.options.get(CONF_PREFERITI, "")): str,
            vol.Required(CONF_SOGLIA, default=v.options.get(CONF_SOGLIA, SOGLIA_PREDEFINITA)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.5, max=20, step=0.5, unit_of_measurement="c€")),
            vol.Required(CONF_RAGGIO, default=v.options.get(CONF_RAGGIO, v.data.get(CONF_RAGGIO, RAGGIO_PREDEFINITO))):
                selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=15, step=1, unit_of_measurement="km")),
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errori)

    def _vicini(self) -> selector.SelectSelector:
        """Senza l'app i preferiti si scelgono dall'elenco dei distributori vicini (quelli già letti), più quelli già
        scelti anche se oggi non sono fra i vicini."""
        c = self.hass.data.get(DOMINIO, {}).get(self.config_entry.entry_id)
        voci: dict[str, str] = {}
        for carb, z in ((c.data or {}).get("zona") or {}).items() if c else []:
            for i in (z.get("vicini") or {}).get("impianti") or []:
                km = i.get("distanza_km")
                dove = f" · {(i.get('comune') or '').title()}" + (f" · {str(round(km, 1)).replace('.', ',')} km" if km else "")
                voci.setdefault(str(i["id"]), f"{logica.titolo(i)}{dove}")
        for x in self.config_entry.options.get(CONF_PREFERITI_SCELTI, []) or []:
            voci.setdefault(str(x), f"Distributore {x}")
        return selector.SelectSelector(selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value=k, label=v) for k, v in voci.items()], multiple=True,
            mode=selector.SelectSelectorMode.DROPDOWN))
