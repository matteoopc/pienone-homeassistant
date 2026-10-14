"""Prova dell'integrazione dentro Home Assistant vero (pytest-homeassistant-custom-component), senza rete.
Da ha/: python -m pytest prove_ha -q   (con homeassistant 2026.9.x e Python 3.14)"""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pienone.const import API  # noqa: E402  (l'indirizzo vero sta solo in const.py)
ESTRAZIONE = {"giorno": "2026-10-06", "estrazione": "2026-10-06"}


def vicini(prezzo):
    return {"estrazione": ESTRAZIONE, "totale": 3, "mediana_zona": prezzo + 0.05, "raggio_km": 5,
            "impianti": [{"id": 1002, "nome": "ROMA", "bandiera": "Q8", "prezzo": prezzo, "distanza_km": 2,
                          "piu_conveniente": True, "lat": 41.9, "lon": 12.5, "aggiornato": "2026-10-05T20:15:32"}]}


GARAGE = [
    {"id": "AAAA-1", "nome": "Golf", "carburante": "benzina", "livello": 0.31, "autonomiaKm": 150},
    {"id": "BBBB-2", "nome": "Ducato", "carburante": "gasolio", "livello": 0.77, "autonomiaKm": 612, "km": 50000},
    {"id": "CCCC-3", "nome": "Zoe", "carburante": "benzina", "elettrica": True, "livello": 0.61, "autonomiaKm": 140},
]
DOC = {"garage": GARAGE, "valori": {"autoAttiva": {"json": "\"CCCC-3\""}}, "preferiti": [{"id": 1002}], "diario": []}


@pytest.fixture(autouse=True)
def abilita(enable_custom_integrations):
    yield


@pytest.fixture
def api(aioclient_mock):
    prezzi = {"benzina": 1.979, "gasolio": 1.849, "gpl": 0.799, "metano": 1.399}
    for c, p in prezzi.items():
        aioclient_mock.get(f"{API}/v1/vicini", params={"lat": 41.903, "lon": 12.496, "carburante": c,
                                                        "self": 1 if c in ("benzina", "gasolio") else 0,
                                                        "raggio_km": 5.0, "limite": 20, "ordine": "prezzo"}, json=vicini(p))
        aioclient_mock.get(f"{API}/v1/tendenza", params={"lat": 41.903, "lon": 12.496, "carburante": c,
                                                          "self": 1 if c in ("benzina", "gasolio") else 0, "raggio_km": 5.0},
                           json={"sufficiente": True, "zona_diff_cent": 2.1})
    aioclient_mock.get(f"{API}/v1/colonnine", json={"totale": 2, "colonnine": [
        {"id": "pun-a", "operatore": "Operatore A", "distanza_km": 0.6, "libere": 1, "prezzo_kwh": None, "lat": 41.90, "lon": 12.50},
        {"id": "pun-b", "operatore": "BE CHARGE", "distanza_km": 1.0, "libere": 0, "prezzo_kwh": 0.49}]})
    aioclient_mock.get(f"{API}/v1/impianto/1002", json={"impianto": {"nome": "ROMA", "bandiera": "Q8", "comune": "ROMA"},
                                                         "prezzi": [{"famiglia": "gasolio", "self": 1, "prezzo": 1.849},
                                                                    {"famiglia": "benzina", "self": 1, "prezzo": 1.989}]})
    return aioclient_mock


async def avvia(hass, hass_storage, dati_voce, doc=DOC):
    hass.config.latitude, hass.config.longitude = 41.9028, 12.4964
    hass_storage["pienone"] = {"version": 1, "key": "pienone",
                               "data": {"dati": doc, "aggiornato": "2026-01-01T00:00:00Z", "webhook_id": "ab" * 24,
                                        "ultima_sincronia": "2026-10-07T18:22:00Z"}}
    voce = MockConfigEntry(domain="pienone", data=dati_voce, title="Pienone benzina", entry_id="voce1")
    voce.add_to_hass(hass)
    assert await hass.config_entries.async_setup(voce.entry_id)
    await hass.async_block_till_done()
    return voce


async def test_configurazione_vecchia_e_auto(hass: HomeAssistant, hass_storage, api, hass_client, hass_client_no_auth):
    # una configurazione della 0.2.0: un carburante solo
    voce = await avvia(hass, hass_storage, {"carburante": "benzina", "self_service": True, "raggio_km": 5.0,
                                            "latitudine": 41.9028, "longitudine": 12.4964})
    reg = er.async_get(hass)
    # gli id della 0.2.0 restano: le entità di chi l'aveva già non cambiano
    assert reg.async_get_entity_id("sensor", "pienone", "voce1_piu_conveniente")
    assert reg.async_get_entity_id("sensor", "pienone", "voce1_consiglio")
    # i principali seguono l'auto attiva (la Zoe): colonnine
    eid = reg.async_get_entity_id("sensor", "pienone", "voce1_piu_conveniente")
    s = hass.states.get(eid)
    assert s.attributes["carburante"] == "elettrico" and s.attributes["unit_of_measurement"] == "€/kWh"
    assert float(s.state) == 0.49
    # un dispositivo per auto
    devs = dr.async_get(hass)
    nomi = {d.name for d in dr.async_entries_for_config_entry(devs, voce.entry_id)}
    assert {"Pienone · Golf", "Pienone · Ducato", "Pienone · Zoe"} <= nomi, nomi
    ducato = hass.states.get(reg.async_get_entity_id("sensor", "pienone", "pienone_auto_BBBB-2_piu_conveniente"))
    assert float(ducato.state) == 1.849 and ducato.attributes["dati_mimit_del"] == "2026-10-06"
    cons = hass.states.get(reg.async_get_entity_id("sensor", "pienone", "pienone_auto_AAAA-1_consiglio"))
    assert cons.state.startswith("In zona sale"), cons.state
    batt = hass.states.get(reg.async_get_entity_id("sensor", "pienone", "pienone_auto_CCCC-3_livello"))
    assert batt.state == "61" and batt.attributes.get("device_class") == "battery"
    assert reg.async_get_entity_id("sensor", "pienone", "pienone_auto_CCCC-3_tendenza_7_giorni") is None
    quadro = hass.states.get(reg.async_get_entity_id("sensor", "pienone", "pienone_quadro"))
    assert quadro.state == "1 auto da rifornire presto", quadro.state
    assert len(quadro.attributes["auto"]) == 3
    # sicurezza: niente id del webhook negli attributi né nell'archivio
    sinc = hass.states.get("sensor.pienone_sincronizzazione")
    assert "pienone_webhook" not in sinc.attributes and sinc.attributes["versione"] == 2
    assert "webhook_id" not in hass_storage["pienone"]["data"]
    # l'indirizzo autenticato: col token di Home Assistant legge, senza risponde 401
    client = await hass_client()
    r = await client.post("/api/pienone/documento", json={"azione": "leggi"})
    assert r.status == 200 and (await r.json())["dati"]["garage"][1]["nome"] == "Ducato"
    anonimo = await hass_client_no_auth()
    r = await anonimo.post("/api/pienone/documento", json={"azione": "leggi"})
    assert r.status == 401
    # il vecchio webhook non risponde più
    r = await anonimo.post("/api/webhook/" + "ab" * 24, json={"azione": "leggi"})
    assert r.status in (200, 404) and "garage" not in (await r.text())

    # l'app toglie la Golf: via il suo dispositivo
    nuovo = {**DOC, "garage": GARAGE[1:]}
    r = await client.post("/api/pienone/documento", json={"azione": "scrivi", "dati": nuovo, "aggiornato": "2026-01-02T00:00:00Z"})
    assert r.status == 200, await r.text()
    risposta = await r.json()
    assert risposta["salvato"], risposta
    await hass.async_block_till_done()
    nomi = {d.name for d in dr.async_entries_for_config_entry(devs, voce.entry_id)}
    assert "Pienone · Golf" not in nomi and "Pienone · Ducato" in nomi, nomi


async def test_configurazione_nuova_tutti_i_carburanti(hass: HomeAssistant, hass_storage, api):
    await avvia(hass, hass_storage, {"carburanti": ["benzina", "gasolio", "gpl", "metano", "elettrico"], "self_service": True,
                                     "raggio_km": 5.0, "latitudine": 41.9028, "longitudine": 12.4964}, doc={})
    reg = er.async_get(hass)
    for c in ("benzina", "gasolio", "gpl", "metano"):
        assert hass.states.get(reg.async_get_entity_id("sensor", "pienone", f"voce1_{c}_piu_conveniente")).state != "unknown"
    assert hass.states.get(reg.async_get_entity_id("sensor", "pienone", "voce1_elettrico_colonnine_libere")).state == "1"
    # senza auto sincronizzate i principali seguono il primo carburante scelto
    s = hass.states.get(reg.async_get_entity_id("sensor", "pienone", "voce1_piu_conveniente"))
    assert float(s.state) == 1.979 and s.attributes["carburante"] == "benzina"


async def test_flusso_di_configurazione(hass: HomeAssistant):
    r = await hass.config_entries.flow.async_init("pienone", context={"source": "user"})
    assert r["type"] == "form"
    campi = {str(k): k for k in r["data_schema"].schema}
    assert campi["carburanti"].default() == ["benzina", "gasolio", "gpl", "metano", "elettrico"]
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"carburanti": [], "self_service": True, "raggio_km": 5,
                                                                      "latitudine": 41.9, "longitudine": 12.5})
    assert r["errors"] == {"base": "nessun_carburante"}


async def test_id_degli_esempi(hass: HomeAssistant, hass_storage, api):
    """Gli id usati in examples/ esistono davvero (Home Assistant in italiano, un'auto «Panda» nell'app)."""
    import re
    from pathlib import Path
    hass.config.language = "it"
    doc = {"garage": [{"id": "PPPP-1", "nome": "Panda", "carburante": "benzina", "livello": 0.4, "autonomiaKm": 300}],
           "valori": {"autoAttiva": {"json": "\"PPPP-1\""}}, "diario": []}
    await avvia(hass, hass_storage, {"carburanti": ["benzina", "elettrico"], "self_service": True, "raggio_km": 5.0,
                                     "latitudine": 41.9028, "longitudine": 12.4964}, doc=doc)
    presenti = set(hass.states.async_entity_ids("sensor"))
    usati = set()
    for f in (Path(__file__).parents[1] / "examples").glob("*.yaml"):
        usati |= set(re.findall(r"sensor\.pienone_[a-z0-9_]+", f.read_text()))
    assert usati - presenti == set(), (sorted(usati - presenti), sorted(presenti))


async def test_stato_dell_app(hass: HomeAssistant, hass_storage, api):
    """Lo «stato» mandato dall'app: sezioni mostrate, sensori per sezione e per auto, sezioni nuove senza codice nuovo."""
    doc = {**DOC, "stato": {"contratto": 1, "inviato": "2026-10-07T18:00:00Z", "sezioni": {
        "viaggio": {"in_corso": True, "meta": "Milano", "auto_id": "BBBB-2", "soste": [{"nome": "Q8", "prezzo": 1.849}]},
        "carplay": {"collegato": True, "auto_id": "BBBB-2"},
        "statistiche": {"BBBB-2": {"consumo_medio": 7.4, "spesa_mese": 180.5, "km_mese": 1200, "litri_mese": 96,
                                   "prezzo_medio": 1.88}},
        "obd": {"AAAA-1": {"livello": 0.31, "km": 50000, "adattatore": "OBDII"}},
        "notifiche": {"permesso": "consentite", "serbatoio": True, "viaggio": True, "salita": False},
        "attivita": {"attiva": False},
        "posizione": {"lat": 41.9, "lon": 12.5},
        "sezione_futura": {"qualcosa": 42}}}}
    await avvia(hass, hass_storage, {"carburanti": ["benzina", "gasolio"], "self_service": True, "raggio_km": 5.0,
                                     "latitudine": 41.9028, "longitudine": 12.4964}, doc=doc)
    reg = er.async_get(hass)
    stato = lambda uid: hass.states.get(reg.async_get_entity_id("sensor", "pienone", uid))
    assert stato("pienone_in_viaggio").state == "In viaggio verso Milano"
    assert stato("pienone_carplay").state == "Collegato · Ducato"
    assert stato("pienone_live_activity").state == "spenta"
    assert stato("pienone_notifiche_app").state == "2"
    dati = stato("pienone_dati_app")
    assert dati.attributes["contratto"] == 1 and dati.attributes["sezione_futura"] == {"qualcosa": 42}
    assert "posizione" not in dati.attributes   # spenta di partenza anche in HA
    assert float(stato("pienone_auto_BBBB-2_spesa_mese").state) == 180.5
    assert stato("pienone_auto_BBBB-2_consumo_medio").attributes["unit_of_measurement"] == "L/100km"
    assert stato("pienone_auto_AAAA-1_obd").state == "nessun codice"
    # codici guasto dall'app (contratto 1, sezione obd): spia accesa e un codice
    hass.data["pienone_archivio"].dati["stato"]["sezioni"]["obd"]["BBBB-2"] = {
        "spia_motore": True, "codici": [{"codice": "P0420", "spiegazione": "Catalizzatore poco efficiente (bancata 1)"}],
        "in_sospeso": []}
    hass.data["pienone_archivio"].avvisa()
    await hass.async_block_till_done()
    obd = stato("pienone_auto_BBBB-2_obd")
    assert obd.state == "spia accesa · 1 codice" and obd.attributes["codici"][0]["codice"] == "P0420"


async def test_senza_app_auto_definite_in_ha(hass: HomeAssistant, hass_storage, api, aioclient_mock):
    """Senza l'app: un'auto definita in HA con le sue entità; poi l'app sincronizza un'auto con lo stesso nome."""
    from homeassistant.config_entries import ConfigSubentryData
    hass.states.async_set("sensor.panda_carburante", "12", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.panda_autonomia", "60", {"unit_of_measurement": "km"})
    hass.config.latitude, hass.config.longitude = 41.9028, 12.4964
    hass_storage["pienone"] = {"version": 1, "key": "pienone", "data": {"dati": None, "aggiornato": None}}
    voce = MockConfigEntry(domain="pienone", entry_id="voce1", title="Pienone",
                           data={"carburanti": ["benzina", "gasolio"], "self_service": True, "raggio_km": 5.0,
                                 "latitudine": 41.9028, "longitudine": 12.4964},
                           subentries_data=[ConfigSubentryData(data={"nome": "Panda", "tipo": "benzina", "capienza": 40,
                                                                     "consumo": 5.5, "entita_livello": "sensor.panda_carburante",
                                                                     "entita_autonomia": "sensor.panda_autonomia"},
                                                               subentry_id="sub1", subentry_type="auto", title="Panda",
                                                               unique_id=None)])
    voce.add_to_hass(hass)
    assert await hass.config_entries.async_setup(voce.entry_id)
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    liv = reg.async_get_entity_id("sensor", "pienone", "pienone_auto_ha_sub1_livello")
    assert hass.states.get(liv).state == "12"
    cons = hass.states.get(reg.async_get_entity_id("sensor", "pienone", "pienone_auto_ha_sub1_consiglio"))
    assert cons.state.startswith("Riserva: fai il pieno presto."), cons.state
    assert reg.async_get(liv).config_subentry_id == "sub1"
    # l'entità dell'auto cambia: il sensore segue subito
    hass.states.async_set("sensor.panda_carburante", "80", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    assert hass.states.get(liv).state == "80"
    # il numero casuale dell'installazione va al server, nient'altro di personale
    intestazioni = [c[3] for c in aioclient_mock.mock_calls if c[3]]
    assert intestazioni and all(len(h.get("X-Pienone-Installazione", "")) == 32 for h in intestazioni)
    # l'app sincronizza una «Panda» col suo garage: niente doppioni, vale l'auto dell'app
    a = hass.data["pienone_archivio"]
    await a.cambia({"garage": [{"id": "PPPP-1", "nome": "Panda", "carburante": "benzina", "livello": None, "km": 30000}]},
                   "2026-01-02T00:00:00Z")
    await hass.async_block_till_done()
    nomi = [d.name for d in dr.async_entries_for_config_entry(dr.async_get(hass), "voce1")]
    assert nomi.count("Pienone · Panda") == 1, nomi
    liv_app = hass.states.get(reg.async_get_entity_id("sensor", "pienone", "pienone_auto_PPPP-1_livello"))
    assert liv_app.state == "80"   # dall'entità di HA, perché all'app manca


async def test_flusso_aggiungi_auto(hass: HomeAssistant, hass_storage, api):
    voce = await avvia(hass, hass_storage, {"carburanti": ["benzina"], "self_service": True, "raggio_km": 5.0,
                                            "latitudine": 41.9028, "longitudine": 12.4964}, doc={})
    r = await hass.config_entries.subentries.async_init((voce.entry_id, "auto"), context={"source": "user"})
    assert r["type"] == "form"
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"nome": "Zoe", "tipo": "elettrica", "consumo": 15})
    assert r["type"] == "create_entry"
    await hass.async_block_till_done()
    assert any(s.title == "Zoe" for s in voce.subentries.values())
    # le opzioni propongono i distributori vicini come preferiti
    r = await hass.config_entries.options.async_init(voce.entry_id)
    campi = {str(k): v for k, v in r["data_schema"].schema.items()}
    opzioni = campi["preferiti_scelti"].config["options"]
    assert any(o["value"] == "1002" for o in opzioni), opzioni
