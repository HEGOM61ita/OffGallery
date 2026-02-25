# OffGallery - Istruzioni per lo Sviluppo

## Panoramica
Sistema di catalogazione automatica e retrieval di immagini fotografiche (RAW, JPG, ecc.) con analisi semantica e estetica tramite modelli LLM e Vision Models locali.

## Requisito Fondamentale: OFFLINE
**CRITICO**: Nessun dato o immagine deve essere inviato a servizi cloud esterni. Tutti i modelli e le elaborazioni devono risiedere localmente.

## Specifiche Tecniche
- **Linguaggio**: Python 3.11+
- **Ambiente**: Conda (`conda activate OffGallery`)
- **Lancio da Windows**: Dal terminale Anaconda: `python gui_launcher.py`
- **Punto di ingresso**: `gui_launcher.py` (nella root)
- **Lingua UI/Output**: Italiano
- **Lingua Codice/Docs**: Inglese

## Struttura Directory
```
/aesthetic           - Modelli e logica per valutazione estetica
/assets              - Risorse grafiche, icone, file statici UI
/brisque_models      - Modelli BRISQUE (file YAML bundled, NON scaricati — non vanno in /Models)
/catalog_readers     - Lettori cataloghi fotografici esterni
                       lightroom_reader.py: legge .lrcat (SQLite) → lista Path + stats
                       dxo_reader.py: futuro
/database            - Database per indicizzazione e retrieval
/exiftool_files      - Binari e utility per metadati EXIF
/gui                 - Moduli interfaccia utente
/INPUT               - Cartella acquisizione nuovi file da processare
/Models              - Modelli AI scaricati (CLIP, DINOv2, BioCLIP, aesthetic, treeoflife)
                       Percorso configurabile in config_new.yaml → models_repository.models_dir
                       Default: relativo alla root del progetto. Può essere assoluto (es. E:\MyModels)
```

## Regole di Sviluppo

### Privacy
- MAI suggerire integrazioni con chiavi API o connessioni internet
- Eccezione: primo download dei modelli

### Commenti
- Scrivere i commenti al codice in **Italiano**

### Stabilità
- Prima di modificare moduli in `/gui`, analizzare le dipendenze con gli script nella root

### Best Practices
- Testare le modifiche con `gui_launcher.py`
- Mantenere compatibilità con Python 3.12.9
- Non committare file di modelli, database o binari (vedi `.gitignore`)

### Workflow Modifiche
- **PRIMA DI CODIFICARE**: Spiegare sempre il piano e chiedere approvazione. Non fare modifiche a raffica senza consenso esplicito.
- **Commit frequenti**: Fare sempre commit dopo ogni modifica significativa
- **Verifica importazioni**: Prima di modificare un file, verificare che le modifiche non rompano le importazioni degli altri moduli nelle sottocartelle
- **Test sintassi**: Usare `python -m py_compile <file>` per verificare la sintassi prima del commit
- **Thread safety**: Il progetto usa molti thread - prestare attenzione ai conflitti di esecuzione e usare guard/flag per prevenire chiamate multiple

### Architettura Thread
- Le operazioni DB vengono eseguite nel thread principale
- I worker thread sono usati per operazioni lunghe (LLM, BioCLIP, embedding)
- Usare flag come `_importing_xmp`, `_exporting_xmp` per prevenire chiamate concorrenti

## Architettura Tecnica Dettagliata

### File Principali e Ruoli
| File | Ruolo |
|------|-------|
| `gui/processing_tab.py` | Elaborazione immagini, merge tag, orchestrazione modelli AI, sorgente catalogo |
| `catalog_readers/lightroom_reader.py` | Legge catalogo Lightroom `.lrcat` (SQLite) → lista file + stats |
| `embedding_generator.py` | Generazione embedding (CLIP, DINOv2), BioCLIP taxonomy, LLM Vision, scores |
| `retrieval.py` | Ricerca semantica CLIP e ricerca tag con fuzzy matching |
| `gui/search_tab.py` | UI ricerca con filtri fotografici (EXIF, rating, color) |
| `gui/gallery_tab.py` | Visualizzazione risultati con badge (aesthetic, technical, rating, color) |
| `geo_enricher.py` | Geolocalizzazione offline GPS→gerarchia `GeOFF|Continent|Country|Region|City` |
| `config_new.yaml` | Configurazione modelli, profili estrazione, path |

### Storage Embedding (CRITICO)
- **Formato**: CLIP embeddings salvati come **raw float32 bytes** (2048 bytes = 512 floats)
- **Deserializzazione corretta**:
```python
if isinstance(raw_data, bytes):
    if len(raw_data) == 2048:
        img_emb = np.frombuffer(raw_data, dtype=np.float32)
    else:
        # Fallback pickle per vecchi formati
        img_emb = pickle.loads(raw_data)
```
- **NON usare** `pickle.loads()` direttamente su embedding recenti

### Ricerca Semantica CLIP
- Query tradotte IT→EN via **argostranslate** prima dell'encoding CLIP
- La ricerca deve confrontare con **TUTTE** le immagini (no LIMIT nella query SQL)
- Applicare threshold e limit solo sui risultati finali
- Query SQL deve includere: `aesthetic_score, technical_score, lr_rating, color_label` per badge gallery

### Separazione BioCLIP / Tags (CRITICO)
- **BioCLIP tassonomia** vive nel campo DB dedicato `bioclip_taxonomy` (JSON array 7 livelli)
- Il campo `tags` contiene **solo** tag LLM + user (mai BioCLIP)
- BioCLIP nel tooltip hover: sezione separata con gerarchia compatta
- BioCLIP in XMP: scritto come `HierarchicalSubject` con prefisso `AI|Taxonomy|...`
- **NO import BioCLIP da XMP**: i dati BioCLIP si gestiscono solo dentro OffGallery
- In import XMP: i tag `AI|Taxonomy|*` vengono filtrati e ignorati
- Deduplicazione tag LLM case-insensitive mantenendo ordine

### Modelli AI e Configurazione
| Modello | Config Key | Output | Directory in /Models |
|---------|------------|--------|----------------------|
| CLIP | `embedding.models.clip` | `clip_embedding` (512 floats) | `Models/clip/` |
| DINOv2 | `embedding.models.dinov2` | `dinov2_embedding` (768 floats) | `Models/dinov2/` |
| BioCLIP v2 | `embedding.models.bioclip` | `bioclip_taxonomy` (7 livelli, ~450k TreeOfLife) | `Models/bioclip/` |
| TreeOfLife | (scaricato con BioCLIP) | — | `Models/treeoflife/` |
| Aesthetic | `embedding.models.aesthetic` | `aesthetic_score` (0-10) | `Models/aesthetic/` |
| Technical/MUSIQ | `embedding.models.technical` | `technical_score` | — (usa torch hub) |
| LLM Vision | `embedding.models.llm_vision` | tags, description, title | — (Ollama, gestito separatamente) |
| BRISQUE | — | qualità tecnica non-RAW | `brisque_models/` (bundled YAML, NON in /Models) |

- **BioCLIP**: versione 2 (`pybioclip>=1.0`, architettura ViT-L-14). Accetta filepath o PIL.Image
- **CLIP/DINOv2**: al primo avvio scaricano da HuggingFace repo e vengono salvati in `Models/` via `save_pretrained()`. Avvii successivi: caricamento locale offline
- **models_dir**: configurabile in `config_new.yaml` → `models_repository.models_dir`. Relativo = `APP_DIR/Models`, assoluto = percorso diretto
- LLM Vision config: `auto_import.tags.max_tags` (non `max`)
- Tutti i modelli devono essere chiamati esplicitamente in `generate_embeddings()`

### Pipeline LLM Vision (CRITICO)
- **Generazione sempre in IT diretto**: il prompt genera in italiano con termini generici
- **NO pipeline EN+traduzione**: rimossa perché il modello 4B traduceva male i nomi specie (flamingo→fiammifero, Columba palumbus→colombo roccioso)
- **Nome latino da BioCLIP inserito programmaticamente** (mai dal LLM):
  - Titolo: `"Columba palumbus - Uccello su ramo"` (prepend con ` - `)
  - Descrizione: `"Columba palumbus: Uccello appollaiato..."` (prepend con `: `)
  - Tag: nome latino come primo tag `["Columba palumbus", "uccello", "ramo", ...]`
- **`_call_ollama_vision_api`** non riceve più `bioclip_context` — ha un solo path IT
- **`_translate_to_italian` e `_call_ollama_text_api` sono stati rimossi**
- **Contesto BioCLIP in gallery**: leggere da campo DB `bioclip_taxonomy`, NON da `tags`
- **Profilo immagine gallery→LLM**: usare `profile_name='llm_vision'`, mai `gallery_display`

### Config `image_processing` (Semplificato)
- Contiene **solo** `supported_formats` — usato da `processing_tab.py` per trovare le immagini
- Parametri rimossi (erano morti): `convert_raw`, `jpeg_quality`, `max_dimension`, `max_workers`, `resize_images`, intero blocco `raw_processing`

### Gerarchia Geografica Offline (GeOFF)
- **Libreria**: `reverse_geocoder` — dati GeoNames bundled in `rg_cities1000.csv`, no internet dopo install
- **File dati**: `<conda_env>/Lib/site-packages/reverse_geocoder/rg_cities1000.csv` (~130k città)
- **Formato gerarchia**: `GeOFF|Continent|Country|Region|City` (es. `GeOFF|Europe|Italy|Sardegna|Trinità d'Agultu`)
- **Campo DB**: `geo_hierarchy` (TEXT) — aggiunto alla tabella `images`
- **In XMP**: scritto come `HierarchicalSubject` con prefisso `GeOFF|` (analogo a `AI|Taxonomy|` per BioCLIP)
- **In import XMP**: i tag `GeOFF|*` vengono filtrati e ignorati (come `AI|Taxonomy|*`)
- **In retrieval.py**: entrambe le SELECT (filter-only e CLIP search) devono includere `geo_hierarchy`
- **Modulo**: `geo_enricher.py` — funzioni: `enrich_with_geo()`, `get_location_hint()`, `get_geo_leaf()`

### GPS Parsing (raw_processor.py)
- ExifTool con `-G -a -s -e` restituisce DMS string: `"41 deg 3' 14.70""`
- **`_parse_gps_coordinate(value, ref=None)`**: usa regex per DMS→decimal, applica segno da Ref (S/W → negativo)
- Chiamare sempre con Ref: `self._parse_gps_coordinate(get_val(['GPSLatitude']), get_val(['GPSLatitudeRef']))`

### Estrazione RAW (raw_processor.py)
- **Catena fallback** in `_extract_original_method()`:
  1. `_extract_jpeg_from_raw()` — ExifTool stdout con `-JpgFromRaw`, `-OtherImage`
  2. `_extract_preview_image()` — ExifTool `-PreviewImage`
  3. rawpy decode completo
  4. `_extract_exiftool_any_preview()` — last resort: `-LargePreview`, `-SubIFD:PreviewImage`, `-OriginalRawImage`, `-PreviewTIFF`, `-RawThumbnailImage`
- Se tutto fallisce → `cached_thumbnail = None` → in `processing_tab.py` embedding e LLM vengono **saltati**, metadati EXIF salvati comunque
- **Warning nel log**: `"⚠️ nome.NEF: nessuna immagine estraibile dal RAW — embedding e LLM saltati"`
- **Guard in ProcessingWorker**: `if embedding_enabled and embedding_generator and cached_thumbnail is not None:`

### Processing Tab — Sorgente Immagini
- **Radio "Directory"**: comportamento originale, scansiona filesystem
- **Radio "Catalogo .lrcat"**: usa `LightroomCatalogReader.read_catalog()` → lista `Path` passata come `image_list` al `ProcessingWorker`
- `ProcessingWorker.__init__` accetta `image_list=None` — se non None bypassa scansione directory
- Checkbox Tags/Descrizione/Titolo + Sovrascrivi + Max **sono in processing_tab** (spostati da config_tab)
- I valori LLM vengono salvati nel YAML al click su **Avvia** tramite `_save_llm_config_to_yaml()`
- **config_tab** non ha più la sezione "Generazione durante Import Batch" — legge/scrive solo connessione LLM

### Comportamento Genera+Sovrascrivi (processing_tab)
- **Tags**: Sovrascrivi=OFF → merge (aggiunge solo tag non presenti, case-insensitive); Sovrascrivi=ON → replace totale
- **Descrizione/Titolo**: Sovrascrivi=OFF → LLM non viene chiamato se campo già presente (skip, non merge); Sovrascrivi=ON → genera sempre

### Bug Comuni da Evitare
1. **Embedding deserializzazione**: Usare `np.frombuffer()` per raw bytes, non `pickle.loads()`
2. **LIMIT in ricerca semantica**: Mai limitare candidati prima del confronto CLIP
3. **Tag ordering con set()**: `list(set(...))` perde l'ordine, usare list comprehension
4. **Campi mancanti in SELECT**: Sempre includere score, label, `bioclip_taxonomy` e `geo_hierarchy` per badge/tooltip gallery
5. **BioCLIP separato dai tags**: MAI mischiare BioCLIP nel campo `tags`. Usare solo `bioclip_taxonomy`
6. **Import XMP e AI|Taxonomy / GeOFF**: Filtrare via i tag `AI|Taxonomy|*` e `GeOFF|*` durante import XMP
7. **Nome latino MAI dal LLM**: inserirlo solo programmaticamente da BioCLIP context, il modello 4B non è affidabile per nomi specie
8. **Gallery LLM profile**: sempre `profile_name='llm_vision'` per RAW, mai lasciare che CallerOptimizer scelga `gallery_display`
9. **Config key mismatch**: `processing_tab` salva max_tags con chiave `'max'`, leggere con `.get('max', 10)` non `'max_tags'`
10. **print() vs logger**: Mai usare `print()` nei moduli GUI. Usare sempre `logger = logging.getLogger(__name__)` e `logger.debug/info/warning/error()`
11. **Import locale Qt in init_ui()**: MAI fare `from PyQt6.QtCore import Qt` dentro una funzione che usa `Qt` prima di quella riga — Python tratta il nome come locale in tutta la funzione e dà UnboundLocalError. Importare Qt a livello di modulo.
12. **geo_hierarchy mancante in DB esistente**: il campo è stato aggiunto dopo — DB creati prima non lo hanno. Non fare migrazioni automatiche: l'utente ricrea il DB.

## Roadmap: Sistema Plugin

### Obiettivo
Progettare un sistema di plugin modulare per OffGallery. I plugin sono moduli Python che, una volta collocati in una directory dedicata del progetto (es. `/plugins`), vengono riconosciuti automaticamente all'avvio e le loro funzionalità rese disponibili sia in Config Tab che in Gallery.

### Caso d'uso principale
Un plugin "LLM Vision 7B" che fornisce un motore alternativo per tag, descrizioni e titoli usando un modello quantizzato più grande (es. 7B-8B VL). Questo plugin:
- Si usa **in alternativa** al motore 4B integrato, non in parallelo
- Serve per riscansione o scansione mirata di foto con output di qualità superiore
- Richiede **scaricamento dei modelli concorrenti** dalla VRAM: i modelli embedding (CLIP, DINOv2, BioCLIP, Aesthetic, MUSIQ) non possono stare in memoria contemporaneamente a un 7B
- L'utente attiva/disattiva il plugin da Config Tab, che automaticamente disabilita i modelli incompatibili e libera VRAM

### Requisiti architetturali
- **Auto-discovery**: scan della directory plugin all'avvio, caricamento dinamico dei moduli conformi
- **Interfaccia standard**: ogni plugin espone un manifest (nome, versione, descrizione, requisiti VRAM, modelli incompatibili) e metodi standard (init, process, cleanup)
- **Gestione VRAM**: il sistema deve gestire il mutua esclusione dei modelli in base alla VRAM disponibile e ai requisiti dichiarati dal plugin
- **UI dinamica**: Config Tab genera automaticamente le sezioni di configurazione dai parametri esposti dal plugin
- **Gallery integration**: i plugin che generano tag/descrizioni/titoli appaiono nel menu contestuale come opzioni alternative
