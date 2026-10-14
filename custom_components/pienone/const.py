"""Costanti dell'integrazione Pienone."""

DOMINIO = "pienone"
API = "https://api.matteoopc.com"

CARBURANTI = ["benzina", "gasolio", "gpl", "metano", "elettrico"]   # 0.2.1: scelta multipla, tutti di partenza
# GPL e metano non hanno il self nei dati MIMIT
CON_SELF = {"benzina", "gasolio"}

CONF_CARBURANTE = "carburante"     # 0.2.0: uno solo (resta il ripiego delle configurazioni vecchie)
CONF_CARBURANTI = "carburanti"
CONF_MOSTRA = "mostra"   # 0.2.1: le sezioni dello «stato» dell'app da mostrare (Configura)
CONF_SELF = "self_service"
CONF_RAGGIO = "raggio_km"
CONF_LAT = "latitudine"
CONF_LON = "longitudine"
CONF_PREFERITI = "preferiti"
CONF_PREFERITI_SCELTI = "preferiti_scelti"   # 0.2.1, senza l'app: scelti dall'elenco dei vicini (Configura)
CONF_SOGLIA = "soglia_cent"

RAGGIO_PREDEFINITO = 5.0
SOGLIA_PREDEFINITA = 2.0   # centesimi: sotto questo calo niente evento
INTERVALLO_MINUTI = 30
RAGGIO_COLONNINE = 5.0

EVENTO_PREZZO_SCESO = "pienone_prezzo_sceso"
SERVIZIO_AGGIORNA = "aggiorna"

# sincronizzazione con l'app (5/10): il documento dell'app in .storage/pienone
ARCHIVIO_CHIAVE = "pienone"
ARCHIVIO_VERSIONE = 1
DATI_ARCHIVIO = "pienone_archivio"           # in hass.data
SEGNALE_ARCHIVIO = "pienone_archivio_cambiato"
# 0.2.1 (7/10): niente più webhook (il suo id finiva negli attributi, nello storico e nelle copie): l'app legge e
# scrive il documento su questo indirizzo, che vuole il token dell'utente di Home Assistant
URL_DOCUMENTO = "/api/pienone/documento"
VERSIONE_SINCRONIA = 2   # attributo «versione» del sensore della sincronizzazione: 2 = indirizzo autenticato
SERVIZIO_REGISTRA_PIENO = "registra_pieno"
EVENTO_SOTTO_SOGLIA = "pienone_sotto_soglia"
