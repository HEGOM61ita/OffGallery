# GeoNames Plugin

Assegna coordinate GPS e gerarchia geografica a immagini sprovviste di dati di posizione, oppure ricalcola la gerarchia con precisione su milioni di luoghi tramite il database GeoNames.

Sostituisce il motore builtin di geolocalizzazione.

---

## Come funziona

GeoNames scarica e indicizza i dati geografici ufficiali da [geonames.org](https://www.geonames.org) per le nazioni selezionate. Il database viene costruito localmente in SQLite e permette di ricercare per nome o ricavare la gerarchia da coordinate GPS.

La gerarchia prodotta ha il formato `GeOFF|Continente|Paese|Regione|Città` e viene salvata nel campo `geo_hierarchy` del database OffGallery. Il foglio finale (Città) viene aggiunto automaticamente come tag dell'immagine.

Il plugin opera in due modalità selezionabili dalla configurazione:

| Modalità | Comportamento |
|----------|---------------|
| Geotag: tutte le foto | Ricalcola la gerarchia su tutte le immagini con GPS presente |
| Geotag: solo foto senza GPS | Assegna la posizione configurata alle immagini prive di coordinate |

---

## Requisiti

- Database GeoNames scaricato per almeno una nazione (da Config Tab → Plugin → GeoNames)
- Connessione internet solo per il download iniziale del database
- Nessuna connessione internet richiesta durante l'elaborazione

---

## Utilizzo

1. Aprire **Config Tab → Plugin → GeoNames**
2. Selezionare la nazione e fare clic su **Scarica dati** (operazione una tantum)
3. Opzionalmente cercare e impostare una posizione di default per le foto senza GPS
4. In **Processing Tab** il plugin è sempre attivo — la modalità corrente è mostrata nella riga del plugin
5. Per agire su foto già catalogate: selezionare in Gallery → menu **Plugin → GeoNames** → azione desiderata

### Azioni in Gallery

| Azione | Descrizione |
|--------|-------------|
| Assegna posizione... | Apre dialog per impostare GPS e gerarchia su immagini selezionate |
| Ricalcola gerarchia GPS | Ricalcola `geo_hierarchy` da coordinate esistenti usando il DB GeoNames |
| Cancella dati GPS | Rimuove GPS, altitudine, direzione e gerarchia dalle immagini selezionate |

---

## Opzioni di configurazione

| Opzione | Default | Descrizione |
|---------|---------|-------------|
| Geotag: solo foto senza GPS | No | Se attivo, elabora solo immagini senza GPS e assegna la posizione configurata |
| Posizione default | — | Coordinate e gerarchia assegnate alle foto senza GPS in modalità "solo no-GPS" |
| Directory dati | `plugins/geonames/data/` | Cartella dove vengono salvati i database GeoNames scaricati |

---

## Campi di output

| Campo | Tipo | Esempio |
|-------|------|---------|
| `gps_latitude` | REAL | `41.05183` |
| `gps_longitude` | REAL | `8.94759` |
| `gps_altitude` | REAL | `12.0` |
| `geo_hierarchy` | TEXT | `GeOFF\|Europe\|Italy\|Sardegna\|Costa Paradiso` |
| `tags` | JSON | aggiunge `"Costa Paradiso"` come primo tag |

---

## Dati geografici

I dati provengono da [GeoNames](https://www.geonames.org), licenza Creative Commons Attribution 4.0 (CC BY 4.0).
Attribuzione: GeoNames geographic database — https://www.geonames.org

---

## Licenza / License

OffGallery Plugins License v1.0 — Proprietario, nessuna redistribuzione.
Dati geografici: GeoNames (geonames.org), CC BY 4.0.

---

---

# GeoNames Plugin (EN)

Assigns GPS coordinates and geographic hierarchy to images lacking location data, or recalculates the hierarchy with precision across millions of places using the GeoNames database.

Replaces the built-in geolocation engine.

---

## How it works

GeoNames downloads and indexes official geographic data from [geonames.org](https://www.geonames.org) for selected countries. The database is built locally in SQLite and allows searching by name or deriving a hierarchy from GPS coordinates.

The produced hierarchy has the format `GeOFF|Continent|Country|Region|City` and is stored in the `geo_hierarchy` field of the OffGallery database. The leaf node (City) is automatically added as an image tag.

The plugin operates in two modes selectable from the configuration:

| Mode | Behaviour |
|------|-----------|
| Geotag: all photos | Recalculates the hierarchy for all images with existing GPS |
| Geotag: no-GPS photos only | Assigns the configured location to images without coordinates |

---

## Requirements

- GeoNames database downloaded for at least one country (from Config Tab → Plugin → GeoNames)
- Internet connection only for the initial database download
- No internet connection required during processing

---

## Usage

1. Open **Config Tab → Plugin → GeoNames**
2. Select a country and click **Download data** (one-time operation)
3. Optionally search and set a default location for photos without GPS
4. In **Processing Tab** the plugin is always active — the current mode is shown in the plugin row
5. To act on already-catalogued photos: select in Gallery → **Plugin → GeoNames** menu → desired action

### Gallery actions

| Action | Description |
|--------|-------------|
| Assign location... | Opens a dialog to set GPS and hierarchy on selected images |
| Recalculate GPS hierarchy | Recalculates `geo_hierarchy` from existing coordinates using the GeoNames DB |
| Clear GPS data | Removes GPS, altitude, direction and hierarchy from selected images |

---

## Configuration options

| Option | Default | Description |
|--------|---------|-------------|
| Geotag: no-GPS photos only | No | If enabled, processes only images without GPS and assigns the configured location |
| Default location | — | Coordinates and hierarchy assigned to GPS-less photos in "no-GPS only" mode |
| Data directory | `plugins/geonames/data/` | Folder where downloaded GeoNames databases are stored |

---

## Output fields

| Field | Type | Example |
|-------|------|---------|
| `gps_latitude` | REAL | `41.05183` |
| `gps_longitude` | REAL | `8.94759` |
| `gps_altitude` | REAL | `12.0` |
| `geo_hierarchy` | TEXT | `GeOFF\|Europe\|Italy\|Sardegna\|Costa Paradiso` |
| `tags` | JSON | adds `"Costa Paradiso"` as first tag |

---

## Geographic data

Data sourced from [GeoNames](https://www.geonames.org), Creative Commons Attribution 4.0 License (CC BY 4.0).
Attribution: GeoNames geographic database — https://www.geonames.org

---

## License

OffGallery Plugins License v1.0 — Proprietary, no redistribution.
Geographic data: GeoNames (geonames.org), CC BY 4.0.
