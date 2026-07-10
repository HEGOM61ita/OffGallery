# GeoSpecies Plugin

Affina la classificazione **BioCLIP** usando solo le specie attese nella posizione geografica della foto. Riduce il campo di ricerca da ~450.000 specie globali (TreeOfLife) a un sottoinsieme pertinente per paese.

---

## Come funziona

GeoSpecies estrae il paese dalle coordinate GPS della foto (tramite il campo `geo_hierarchy` già presente nel database OffGallery) e carica la checklist locale delle specie osservate in quel paese. La checklist viene passata a BioCLIP come sottoinsieme geografico, aumentando la precisione della classificazione tassonomica.

Il fetch da GBIF avviene **solo** durante il download esplicito dal pannello di configurazione. Durante l'elaborazione viene usata esclusivamente la cache locale.

---

## Requisiti

- Le foto devono avere coordinate GPS nei metadati EXIF
- Le checklist per i paesi desiderati devono essere scaricate dal pannello GeoSpecies in Config Tab
- Connessione internet richiesta solo per il download iniziale delle checklist

---

## Utilizzo

1. Aprire **Config Tab → Plugin → GeoSpecies**
2. Scaricare le checklist per i paesi di interesse
3. Il plugin si attiva automaticamente durante l'elaborazione per le foto con GPS

Le foto senza coordinate GPS vengono silenziosamente saltate.
Se non è disponibile una checklist per il paese della foto, BioCLIP usa il TreeOfLife completo e nel log appare un avviso.

---

## Opzioni di configurazione

| Opzione | Default | Descrizione |
|---------|---------|-------------|
| Directory cache | `cache/` | Cartella per le checklist scaricate |
| Scadenza cache | 90 giorni | Dopo quanti giorni una checklist viene considerata obsoleta |
| Max specie per taxon | 5000 | Limite specie per gruppo tassonomico per paese |
| Taxa abilitati | tutti | Gruppi tassonomici da includere |

---

## Campi di output

| Campo | Tipo | Esempio |
|-------|------|---------|
| `geospecies_subset_used` | TEXT (JSON) | `{"source": "gbif", "strategy": "A", "key": "IT", "species_count": 3241}` |

---

## Fonte dati

Dati di occorrenza specie: **GBIF** (Global Biodiversity Information Facility, gbif.org) — CC BY 4.0.

---

## Licenza / License

OffGallery Plugins License v1.0 — Proprietario, nessuna redistribuzione.

---

---

# GeoSpecies Plugin (EN)

Refines **BioCLIP** classification by using only the species expected at the photo's geographic location. Reduces the search space from ~450,000 global species (TreeOfLife) to a country-relevant subset.

---

## How it works

GeoSpecies extracts the country from the photo's GPS coordinates (via the `geo_hierarchy` field already in the OffGallery database) and loads the local checklist of species recorded in that country. The checklist is passed to BioCLIP as a geographic subset, increasing taxonomic classification accuracy.

GBIF fetching happens **only** during explicit download from the configuration panel. Processing uses exclusively the local cache.

---

## Requirements

- Photos must have GPS coordinates in EXIF metadata
- Checklists for the desired countries must be downloaded from the GeoSpecies panel in Config Tab
- Internet connection required only for the initial checklist download

---

## Usage

1. Open **Config Tab → Plugin → GeoSpecies**
2. Download checklists for the countries of interest
3. The plugin activates automatically during processing for photos with GPS

Photos without GPS coordinates are silently skipped.
If no checklist is available for the photo's country, BioCLIP uses the full TreeOfLife and a warning appears in the log.

---

## Configuration options

| Option | Default | Description |
|--------|---------|-------------|
| Cache directory | `cache/` | Folder for downloaded checklists |
| Cache expiry | 90 days | Days before a checklist is considered outdated |
| Max species per taxon | 5000 | Species limit per taxonomic group per country |
| Enabled taxa | all | Taxonomic groups to include |

---

## Output field

| Field | Type | Example |
|-------|------|---------|
| `geospecies_subset_used` | TEXT (JSON) | `{"source": "gbif", "strategy": "A", "key": "IT", "species_count": 3241}` |

---

## Data source

Species occurrence data: **GBIF** (Global Biodiversity Information Facility, gbif.org) — CC BY 4.0.

---

## License

OffGallery Plugins License v1.0 — Proprietary, no redistribution.
