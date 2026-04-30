# OffGallery - Istruzioni per lo Sviluppo

## Panoramica
Sistema di catalogazione automatica e retrieval di immagini fotografiche (RAW, JPG, ecc.) con analisi semantica e estetica tramite modelli LLM e Vision Models locali.

## ⚠️ REGOLA ASSOLUTA — DIRECTORY DI LAVORO
**LAVORARE SEMPRE E SOLO NELLA ROOT REALE DEL PROGETTO: `D:\AI\Scripts\Descrittore`**

MAI usare worktree, directory temporanee, copie o ambienti isolati.
Ogni modifica, ogni file, ogni commit deve avvenire direttamente nella root reale su disco locale.
Se Claude Code propone di lavorare in un worktree — RIFIUTARE.

## Requisito Fondamentale: OFFLINE
**CRITICO**: Nessun dato o immagine deve essere inviato a servizi cloud esterni. Tutti i modelli e le elaborazioni devono risiedere localmente.

## Specifiche Tecniche
- **Linguaggio**: Python 3.11+
- **Ambiente**: Conda (`conda activate OffGallery`)
- **Lancio da Windows**: Dal terminale Anaconda: `python gui_launcher.py`
- **Punto di ingresso**: `gui_launcher.py` (nella root)
- **Lingua UI/Output**: Italiano
- **Lingua Codice/Docs**: Inglese

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
- **Prima di modifiche significative** (nuove feature, refactoring, modifiche a più file): spiegare il piano e attendere approvazione. Per fix singoli e ovvi si può procedere direttamente.
- **Commit frequenti**: Fare sempre commit dopo ogni modifica significativa
- **Verifica importazioni**: Prima di modificare un file, verificare che le modifiche non rompano le importazioni degli altri moduli nelle sottocartelle
- **Test sintassi**: Usare `python -m py_compile <file>` per verificare la sintassi prima del commit

### Diario di Sviluppo — OBBLIGATORIO
- La cartella `/DIARY` è **solo locale**, mai tracciata da git (né `origin/main` né `beta`)
- Dopo ogni commit che chiude un task (non fix banali di una riga), scrivere un'entry in `/DIARY/YYYY-MM.md`
- Formato entry:
  ```
  ## YYYY-MM-DD — <titolo breve>
  **Obiettivo**: cosa si voleva ottenere
  **Perché**: motivazione / problema che ha scatenato il lavoro
  **File principali toccati**: elenco
  **Decisioni notevoli**: scelte di design, alternative scartate (se presenti)
  **Commit**: <hash corto>
  ```
- Se il file del mese non esiste, crearlo

### Preservazione Root di Progetto — CRITICA
La directory `D:\AI\Scripts\Descrittore` e il suo contenuto NON devono mai essere sovrascritti, cancellati o alterati da operazioni git. Questo è accaduto in passato causando perdita di file.

**Comandi VIETATI — non usarli mai, nemmeno per "risolvere" disallineamenti git:**
- `git reset --hard` — sovrascrive file locali modificati senza avviso
- `git checkout -- .` / `git restore .` — stessa cosa
- `git clean -fd` — cancella file non tracciati, inclusi i plugin
- Per riallineare HEAD con GitHub usare sempre `git pull origin main`

**Regola plugin — ASSOLUTA:**
- La directory `/plugins` e tutto il suo contenuto esistono SOLO in locale e su `beta`. **Non devono mai essere toccati, spostati, cancellati o modificati** nel normale workflow di sviluppo.
- I file plugin non sono mai staged su `origin/main` (il `.gitignore` li esclude).
- Per il workflow di push beta vedere `WORKFLOW_BETA.md`.

### Regole Push GitHub
- **`origin/main`** (repo pubblica): codice sorgente senza plugin. Verifica prima del push: `git status` deve mostrare zero file da `/plugins`.
- **`beta`** (repo privata): contiene tutto + `/plugins` completi. Procedura in `WORKFLOW_BETA.md`.
- **Verifica pre-push pubblico**: `git diff --cached --name-only | grep plugins` deve restituire vuoto.

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
- **Formato**: CLIP embeddings salvati come **raw float32 bytes** (3072 bytes = 768 floats, modello ViT-L/14)
- **Deserializzazione corretta** (flessibile per qualsiasi dimensione):
```python
if isinstance(raw_data, bytes):
    if raw_data[0] == 0x80 and raw_data[1] in (2, 3, 4, 5):
        img_emb = pickle.loads(raw_data)  # vecchi formati pickle
    elif len(raw_data) % 4 == 0:
        img_emb = np.frombuffer(raw_data, dtype=np.float32).copy()  # raw float32
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
| CLIP | `embedding.models.clip` | `clip_embedding` (768 floats, ViT-L/14) | `Models/clip/` |
| DINOv2 | `embedding.models.dinov2` | `dinov2_embedding` (768 floats) | `Models/dinov2/` |
| BioCLIP v2 | `embedding.models.bioclip` | `bioclip_taxonomy` (7 livelli, ~450k TreeOfLife) | `Models/bioclip/` |
| Aesthetic | `embedding.models.aesthetic` | `aesthetic_score` (0-10) | `Models/aesthetic/` |
| MUSIQ | `embedding.models.technical` | `technical_score` (~0-100) | — (pyiqa) |
| LLM Vision | `embedding.models.llm_vision` | tags, description, title | — (Ollama) |

- **BioCLIP**: versione 2 (`pybioclip>=1.0`, architettura ViT-L-14). Accetta filepath o PIL.Image
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

### Gerarchia Geografica Offline (GeOFF)
- **Libreria**: `reverse_geocoder` — dati GeoNames bundled, no internet dopo install
- **Formato**: `GeOFF|Continent|Country|Region|City` (es. `GeOFF|Europe|Italy|Sardegna|Trinità d'Agultu`)
- **Campo DB**: `geo_hierarchy` (TEXT)
- **In XMP**: `HierarchicalSubject` con prefisso `GeOFF|`
- **In import XMP**: tag `GeOFF|*` e `AI|Taxonomy|*` filtrati e ignorati
- **In retrieval.py**: SELECT devono includere `geo_hierarchy`
- **Modulo**: `geo_enricher.py` — funzioni: `enrich_with_geo()`, `get_location_hint()`, `get_geo_leaf()`

### Estrazione RAW (raw_processor.py)
- Se nessun metodo estrae immagine → `cached_thumbnail = None` → embedding e LLM **saltati**, EXIF salvati comunque
- **Guard in ProcessingWorker**: `if embedding_enabled and embedding_generator and cached_thumbnail is not None:`

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
13. **Eccezioni silenziate**: mai usare `except: pass` o `except Exception: pass` senza almeno un `logger.warning("...", exc_info=True)`. In codice multi-thread i crash silenziosi spariscono senza traccia.
