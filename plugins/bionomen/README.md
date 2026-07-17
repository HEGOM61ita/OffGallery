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
| Lingua nomi comuni | `auto` | Lingua dei nomi comuni, indipendente da quella dei testi LLM |
| Taxa abilitati | `aves` | Gruppi tassonomici da cercare |
| Copertura geografica | vuoto (mondiale) | Paesi ISO per Insecta e Plantae (es. `IT, FR`) |

---

## Copertura geografica (solo Insecta e Plantae)

Insetti e piante contano milioni di specie: scaricarle tutte richiede giorni, e quasi nessuna ha un nome comune. La sezione **Copertura geografica** del pannello Configura permette di limitare questi due taxa ad alcuni paesi, scaricando solo le specie effettivamente osservate lì.

| Taxon | Mondiale | Solo Italia |
|-------|----------|-------------|
| Insecta | 1.105.104 specie (~2 giorni) | **24.698** (~1 ora) |
| Plantae | 446.842 specie (~21 ore) | **16.020** |

I paesi si possono **aggiungere in seguito**: i nuovi nomi si sommano a quelli già scaricati, nello stesso database, senza ripetere il lavoro già fatto. Campo vuoto = mondiale (con avviso prima di procedere).

Per gli altri taxa il campo non compare: sono fra 9.800 e 21.100 specie e si scaricano in pochi minuti.

---

## Campi di output

| Campo | Tipo | Esempio |
|-------|------|---------|
| `vernacular_name` | TEXT | `Colombaccio` |

---

## Taxa supportati

Aves, Mammalia, Reptilia, Amphibia, Insecta, Plantae

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
| Common name language | `auto` | Language for common names, independent from the LLM text language |
| Enabled taxa | `aves` | Taxonomic groups to look up |
| Geographic coverage | empty (worldwide) | ISO countries for Insecta and Plantae (e.g. `IT, FR`) |

---

## Geographic coverage (Insecta and Plantae only)

Insects and plants comprise millions of species: downloading them all takes days, and almost none have a common name. The **Geographic coverage** section of the Configure panel limits these two taxa to selected countries, downloading only the species actually recorded there.

| Taxon | Worldwide | Italy only |
|-------|-----------|------------|
| Insecta | 1,105,104 species (~2 days) | **24,698** (~1 hour) |
| Plantae | 446,842 species (~21 hours) | **16,020** |

Countries can be **added later**: new names are appended to those already downloaded, in the same database, without repeating work already done. Empty field = worldwide (with a warning before proceeding).

The field does not appear for the other taxa: they range from 9,800 to 21,100 species and download in a few minutes.

---

## Output field

| Field | Type | Example |
|-------|------|---------|
| `vernacular_name` | TEXT | `Common Wood Pigeon` |

---

## Supported taxa

Aves, Mammalia, Reptilia, Amphibia, Insecta, Plantae

---

## License

OffGallery Plugins License v1.0 — Proprietary, no redistribution.
Biological data: GBIF (gbif.org), CC BY 4.0.
