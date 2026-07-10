# GeoNames Plugin — Struttura file

## File previsti

```
plugins/geonames/
│
├── manifest.json          ← già scritto
│
├── geonames.py            ← CORE LOGIC (chiamato come subprocess da processing_tab)
│                             - Funzioni: load_config(), save_config(),
│                               is_database_present(), get_database_date(),
│                               download_and_build_database()
│                             - Logica principale: search_location(), get_hierarchy(),
│                               process_no_gps(), process_overwrite()
│                             - Nessun import da OffGallery (autonomo AGPLv3-free)
│                             - Costruisce gerarchia GeOFF internamente
│                               (dizionari CC→continent/country replicati)
│
├── geonames_ui.py         ← UI CONFIG (aperta da PluginCard → Configura)
│                             - Sezione coordinate dirette (lat/lon/alt)
│                             - Sezione ricerca per nome (live search sul DB locale)
│                             - Sezione nazioni: lista nazioni disponibili,
│                               stato download (✓/✗), pulsante Scarica
│                             - Sezione directory dati: path selector + default plugin dir
│                             - Salva tutto in config.json del plugin
│
├── geonames_gallery.py    ← GALLERY ACTIONS
│                             - assign_location(image_ids, db_path, location)
│                               → scrive lat/lon/geo_hierarchy nel DB
│                             - recalc_hierarchy(image_ids, db_path)
│                               → ricalcola geo_hierarchy da lat/lon esistenti
│                             - clear_gps(image_ids, db_path)
│                               → azzera gps_latitude, gps_longitude,
│                                 gps_altitude, gps_direction, geo_hierarchy
│
├── config.json            ← generato al primo salvataggio dalla UI
│                             Contiene:
│                             {
│                               "data_dir": "<path o __plugin_dir__>",
│                               "downloaded_nations": ["IT", "FR", ...],
│                               "last_location": {
│                                 "name": "Barumini",
│                                 "latitude": 39.7058,
│                                 "longitude": 9.0003,
│                                 "altitude": null
│                               }
│                             }
│
└── data/                  ← creata automaticamente (o path custom da config)
    ├── IT.db              ← SQLite indicizzato da IT.txt GeoNames
    ├── FR.db              ← idem per Francia
    └── ...                ← una per nazione scaricata
```

## Note architetturali

- `geonames.py` viene **importato direttamente** da ProcessingWorker (fase 0, sincrono),
  NON come subprocess. Espone la classe `GeoNamesEnricher(config)` che implementa
  l'interfaccia `GeoEnricherPlugin` definita in `plugins/base.py`.
- ProcessingWorker carica il plugin una volta sola all'avvio del run(), controlla
  `plugin_type == 'geo_enricher'` nel manifest e `enabled_in_processing` nel config.json.
  Se il plugin non è pronto (DB mancante), fallback automatico sul builtin `geo_enricher.py`.
- `geonames_gallery.py` viene importato direttamente da `gallery_tab.py`
  (stesso pattern di NaturArea/BioNomen per le gallery actions)
- I file GeoNames per nazione vengono convertiti da TXT a SQLite con indice su nome, admin1,
  admin2 e country_code al momento del download, per ricerche veloci offline
- `plugin_type: geo_enricher` + `replaces_builtin: geo_enricher` nel manifest →
  il plugin non ha pipeline_stage né priority: gira esattamente dove girava il builtin
- Licenza: coperta dalla Plugin Interface Exception (GeoEnricherPlugin in base.py)
