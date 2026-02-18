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
/aesthetic        - Modelli e logica per valutazione estetica
/assets           - Risorse grafiche, icone, file statici UI
/brisque_models   - Modelli per calcolo qualità immagine (BRISQUE)
/database         - Database per indicizzazione e retrieval
/exiftool_files   - Binari e utility per metadati EXIF
/gui              - Moduli interfaccia utente
/INPUT            - Cartella acquisizione nuovi file da processare
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
| `gui/processing_tab.py` | Elaborazione immagini, merge tag, orchestrazione modelli AI |
| `embedding_generator.py` | Generazione embedding (CLIP, DINOv2), BioCLIP taxonomy, LLM Vision, scores |
| `retrieval.py` | Ricerca semantica CLIP e ricerca tag con fuzzy matching |
| `gui/search_tab.py` | UI ricerca con filtri fotografici (EXIF, rating, color) |
| `gui/gallery_tab.py` | Visualizzazione risultati con badge (aesthetic, technical, rating, color) |
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
| Modello | Config Key | Output |
|---------|------------|--------|
| CLIP | `embedding.models.clip` | `clip_embedding` (512 floats) |
| DINOv2 | `embedding.models.dinov2` | `dinov2_embedding` (768 floats) |
| BioCLIP | `embedding.models.bioclip` | `bioclip_taxonomy` (7 livelli tassonomici, ~450k TreeOfLife) |
| Aesthetic | `embedding.models.aesthetic` | `aesthetic_score` (0-10) |
| Technical | `embedding.models.technical` | `technical_score` (MUSIQ) |
| LLM Vision | `embedding.models.llm_vision` | tags, description, title |

- BioCLIP accetta sia **filepath** che **PIL.Image**
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

### Bug Comuni da Evitare
1. **Embedding deserializzazione**: Usare `np.frombuffer()` per raw bytes, non `pickle.loads()`
2. **LIMIT in ricerca semantica**: Mai limitare candidati prima del confronto CLIP
3. **Tag ordering con set()**: `list(set(...))` perde l'ordine, usare list comprehension
4. **Campi mancanti in SELECT**: Sempre includere score, label e `bioclip_taxonomy` per badge/tooltip gallery
5. **BioCLIP separato dai tags**: MAI mischiare BioCLIP nel campo `tags`. Usare solo `bioclip_taxonomy`
6. **Import XMP e AI|Taxonomy**: Filtrare via i tag `AI|Taxonomy|*` durante import XMP
7. **Nome latino MAI dal LLM**: inserirlo solo programmaticamente da BioCLIP context, il modello 4B non è affidabile per nomi specie
8. **Gallery LLM profile**: sempre `profile_name='llm_vision'` per RAW, mai lasciare che CallerOptimizer scelga `gallery_display`
9. **Config key mismatch**: `processing_tab` salva max_tags con chiave `'max'`, leggere con `.get('max', 10)` non `'max_tags'`

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
