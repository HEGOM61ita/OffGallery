# BioNomen Plugin

Arricchisce i tag delle foto con i **nomi comuni biologici** nella lingua selezionata, a partire dalla classificazione tassonomica prodotta da BioCLIP.

---

## Come funziona

BioNomen legge il campo `bioclip_taxonomy` già presente nel database OffGallery e cerca il nome comune corrispondente nei database locali. I database sono compilati a partire da dati GBIF e vengono scaricati dall'utente tramite il pannello di configurazione.

Il nome comune viene salvato nel campo `vernacular_name` e appare nei tooltip della Gallery.

---

## Requisiti

- BioCLIP deve essere abilitato e aver già classificato le foto
- I database delle specie devono essere scaricati dal pannello BioNomen in Config Tab
- Nessuna connessione internet richiesta durante l'elaborazione

---

## Utilizzo

1. Aprire **Config Tab → Plugin → BioNomen**
2. Scaricare i database dei taxa desiderati (Aves, Mammalia, Plantae, ecc.)
3. Cliccare **Esegui** nella scheda del plugin, oppure abilitare il checkbox in **Processing Tab** per l'esecuzione automatica dopo ogni importazione

Le foto senza classificazione BioCLIP vengono silenziosamente saltate.

---

## Opzioni di configurazione

| Opzione | Default | Descrizione |
|---------|---------|-------------|
| Lingua nomi comuni | `it` | Lingua dei nomi comuni (italiano, inglese, ecc.) |
| Taxa abilitati | tutti | Gruppi tassonomici da cercare |

---

## Campi di output

| Campo | Tipo | Esempio |
|-------|------|---------|
| `vernacular_name` | TEXT | `Colombaccio` |

---

## Taxa supportati

Aves, Mammalia, Reptilia, Amphibia, Insecta, Arachnida, Plantae, Fungi

---

## Licenza / License

OffGallery Plugins License v1.0 — Proprietario, nessuna redistribuzione.
Dati biologici: GBIF (gbif.org), CC BY 4.0.

---

---

# BioNomen Plugin (EN)

Enriches photo tags with **biological common names** in the selected language, based on the taxonomic classification produced by BioCLIP.

---

## How it works

BioNomen reads the `bioclip_taxonomy` field already present in the OffGallery database and looks up the corresponding common name in local databases. Databases are compiled from GBIF data and are downloaded by the user via the configuration panel.

The common name is stored in the `vernacular_name` field and appears in Gallery tooltips.

---

## Requirements

- BioCLIP must be enabled and must have already classified the photos
- Species databases must be downloaded from the BioNomen panel in Config Tab
- No internet connection required during processing

---

## Usage

1. Open **Config Tab → Plugin → BioNomen**
2. Download the databases for the desired taxa (Aves, Mammalia, Plantae, etc.)
3. Click **Run** in the plugin card, or enable the checkbox in **Processing Tab** to run automatically after each import

Photos without BioCLIP classification are silently skipped.

---

## Configuration options

| Option | Default | Description |
|--------|---------|-------------|
| Common name language | `it` | Language for common names (Italian, English, etc.) |
| Enabled taxa | all | Taxonomic groups to look up |

---

## Output field

| Field | Type | Example |
|-------|------|---------|
| `vernacular_name` | TEXT | `Common Wood Pigeon` |

---

## Supported taxa

Aves, Mammalia, Reptilia, Amphibia, Insecta, Arachnida, Plantae, Fungi

---

## License

OffGallery Plugins License v1.0 — Proprietary, no redistribution.
Biological data: GBIF (gbif.org), CC BY 4.0.
