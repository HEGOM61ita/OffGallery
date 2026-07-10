# Weather Context Plugin

Arricchisce le foto con i **dati meteo storici** al momento e nella posizione in cui la foto è stata scattata.

I dati meteo vengono recuperati dalla **Open-Meteo Historical API** (gratuita, nessuna chiave API richiesta) e salvati come campo JSON nel database OffGallery. Sono disponibili per ricerca, filtri e tooltip nella Gallery.

---

## Requisiti

- Le foto devono avere coordinate GPS **e** data/ora nei metadati EXIF (`DateTimeOriginal`)
- Connessione internet richiesta al primo utilizzo (ogni coppia posizione+data viene recuperata una volta)
- Le elaborazioni successive usano la cache locale — nessuna connessione richiesta

---

## Utilizzo

Cliccare **Esegui** nella scheda del plugin, oppure abilitare il checkbox in **Processing Tab** per l'esecuzione automatica dopo ogni importazione.

Le foto senza coordinate GPS o senza data vengono silenziosamente saltate.

---

## Cache

I risultati meteo vengono cachati in un database SQLite locale (`plugins/weather_context/data/weather_cache.db`).
La chiave di cache è `(lat arrotondata a 0.01°, lon arrotondata a 0.01°, data)` — risoluzione di circa 1 km.

---

## Opzioni di configurazione

| Opzione | Default | Descrizione |
|---------|---------|-------------|
| Database cache | `data/weather_cache.db` | Percorso al database SQLite locale |
| Timeout richiesta | 10 s | Timeout HTTP per le chiamate Open-Meteo |

---

## Campo di output

| Campo | Tipo | Esempio |
|-------|------|---------|
| `weather_context` | TEXT (JSON) | `{"temp_c": 8, "condition": "drizzle", "humidity": 72, "wind_kmh": 12, "precip_mm": 0.4}` |

---

## Codici condizione meteo

| Codice | Italiano | English |
|--------|----------|---------|
| `clear` | Sereno | Clear |
| `partly_cloudy` | Parzialmente nuvoloso | Partly cloudy |
| `cloudy` | Nuvoloso | Cloudy |
| `fog` | Nebbia | Fog |
| `drizzle` | Pioggerella | Drizzle |
| `rain` | Pioggia | Rain |
| `snow` | Neve | Snow |
| `thunderstorm` | Temporale | Thunderstorm |

---

## Ricerca

In **Search Tab**, la sezione *Plugin* mostra un selettore **Condizione meteo** con solo i codici effettivamente presenti nel database.

---

## Licenza

OffGallery Plugins License v1.0 — Proprietario, nessuna redistribuzione.
Dati meteo: Open-Meteo API (open-meteo.com), CC BY 4.0.

---

---

# Weather Context Plugin (EN)

Enriches photos with historical weather data at the time and location the photo was taken.

Weather data is retrieved from the **Open-Meteo Historical API** (free, no API key required) and stored as a JSON field in the OffGallery database. The data is available for search, filtering and hover tooltips in the Gallery tab.

---

## Requirements

- Photos must have GPS coordinates **and** a date/time in EXIF (`DateTimeOriginal`)
- Internet connection required at processing time (each unique location+date is fetched from the API)
- Subsequent runs use the local cache — no internet needed for already-processed location/date pairs

---

## Running the plugin

Click **Run** in the Plugin card, or enable the checkbox in the **Processing** tab to run automatically after each import.

Photos without GPS coordinates or without a date are silently skipped.

---

## Cache

Weather results are cached in a local SQLite database (`plugins/weather_context/data/weather_cache.db`).
The cache key is `(lat rounded to 0.01°, lon rounded to 0.01°, date)` — approximately 1 km resolution.

This means:
- Re-processing the same photos is instant (no API calls)
- Photos taken within ~1 km on the same day share a single cached result

The cache path is configurable via **Configure** in the Plugin card.

---

## Configuration options

| Option | Default | Description |
|--------|---------|-------------|
| Cache database | `data/weather_cache.db` | Path to the local SQLite cache |
| Request timeout | 10 s | HTTP timeout for Open-Meteo API calls |

---

## Output field

| Field | Type | Example |
|-------|------|---------|
| `weather_context` | TEXT (JSON) | `{"temp_c": 8, "condition": "drizzle", "humidity": 72, "wind_kmh": 12, "precip_mm": 0.4}` |

### JSON keys

| Key | Type | Description |
|-----|------|-------------|
| `temp_c` | float | Temperature in °C |
| `condition` | string | Condition code (see table below) |
| `humidity` | int | Relative humidity % |
| `wind_kmh` | float | Wind speed km/h |
| `precip_mm` | float | Precipitation mm |

### Condition codes

| Code | Italian | English |
|------|---------|---------|
| `clear` | Sereno | Clear |
| `partly_cloudy` | Parzialmente nuvoloso | Partly cloudy |
| `cloudy` | Nuvoloso | Cloudy |
| `fog` | Nebbia | Fog |
| `drizzle` | Pioggerella | Drizzle |
| `rain` | Pioggia | Rain |
| `snow` | Neve | Snow |
| `thunderstorm` | Temporale | Thunderstorm |

---

## Search

In the **Search** tab, the *Plugin* section shows a **Weather condition** dropdown populated with only the condition codes actually present in the database. Selecting one filters results to photos with that weather condition.

---

## License

OffGallery Plugins License v1.0 — Proprietary, no redistribution.
Weather data: Open-Meteo API (open-meteo.com), CC BY 4.0.
