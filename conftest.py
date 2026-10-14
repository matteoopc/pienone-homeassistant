"""Le prove in Home Assistant vero (prove_ha): il pacchetto custom_components del kit di prova copre il nostro, quindi
si aggiunge la nostra cartella al suo percorso."""
from pathlib import Path

import custom_components

custom_components.__path__.append(str(Path(__file__).parent / "custom_components"))
