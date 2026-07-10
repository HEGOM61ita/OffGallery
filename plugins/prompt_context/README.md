# Contesto Prompt Plugin

Inietta un blocco **CONTEXT** personalizzato nel prompt Vision-Language di OffGallery per adattare tag, descrizioni e titoli al dominio specifico dell'archivio fotografico.

---

## Come funziona

Il plugin si inserisce nella pipeline LLM di OffGallery prima dell'analisi dell'immagine. Quando è attivo un preset, il suo `context_block` viene inserito nel prompt tra le regole di lingua e il kernel di analisi (STEP 1 Chain-of-Thought), orientando il modello verso il tipo di fotografia dell'archivio.

Senza un preset attivo il comportamento è identico al prompt standard di OffGallery.

---

## Preset built-in

| Icona | Nome | Dominio |
|-------|------|---------|
| 🦋 | Archivio Naturalistico | Specie, habitat, comportamento animale, fotografia scientifica |
| 🏔 | Paesaggio e Territorio | Geomorfologia, luce, stagione, contesto geografico |
| 🔭 | Astrofotografia | Oggetti celesti, costellazioni, condizioni atmosferiche |
| 🔬 | Macro Scientifico | Dettaglio estremo, strutture microscopiche, entomologia |
| 🐠 | Subacqueo | Specie marine, comportamento, condizioni di visibilità |
| 📰 | Reportage e Documentario | Contesto sociale, narrativa visiva, documentazione storica |
| 🛍 | Commerciale e Prodotto | Prodotto, brand, comunicazione visiva, composizione tecnica |
| 🌆 | Street e Urbano | Vita urbana, architettura, luce ambientale, interazione sociale |

---

## Preset utente

Oltre ai preset built-in è possibile generare preset personalizzati tramite LLM locale (tab Plugin → Configura → sezione "Genera nuovo preset"). I preset utente sono salvati in `APP_DIR/user_presets/` e possono essere eliminati dalla stessa interfaccia.

---

## Configurazione

In **Plugin Tab → Contesto Prompt → Configura**:

1. Selezionare un preset dalla lista (inclusa la voce **Standard** per disattivare il contesto)
2. Premere **Attiva** — il preset diventa attivo in Processing Tab e Gallery
3. Il preset attivo viene ricordato tra le sessioni

Il dropdown **Contesto prompt** in Processing Tab si aggiorna automaticamente alla selezione.

---

## Struttura preset

I preset sono file YAML nella directory `presets/` del plugin:

```yaml
id: nome_univoco
name: Nome leggibile
description: Breve descrizione del dominio
icon: "🦋"
author: OffGallery
version: "1.0"

context_block: |
  CONTEXT: ...
  - Istruzione 1
  - Istruzione 2
```

Il `context_block` deve essere scritto in inglese per massimizzare la compatibilità con i modelli VLM.

---

## Nessun requisito aggiuntivo

Il plugin non richiede download, database o connessione internet. Funziona con qualsiasi backend LLM configurato in OffGallery (Ollama, LM Studio).

---

## Licenza / License

OffGallery Plugins License v1.0 — Proprietario, nessuna redistribuzione.

---

---

# Prompt Context Plugin (EN)

Injects a custom **CONTEXT** block into OffGallery's Vision-Language prompt to tailor tags, descriptions and titles to the specific domain of the photo archive.

---

## How it works

The plugin hooks into the OffGallery LLM pipeline before image analysis. When a preset is active, its `context_block` is inserted into the prompt between the language rules and the analysis kernel (STEP 1 Chain-of-Thought), steering the model toward the archive's photographic genre.

With no active preset the behaviour is identical to OffGallery's standard prompt.

---

## Built-in presets

| Icon | Name | Domain |
|------|------|--------|
| 🦋 | Wildlife Archive | Species, habitat, animal behaviour, scientific photography |
| 🏔 | Landscape & Territory | Geomorphology, light, season, geographic context |
| 🔭 | Astrophotography | Celestial objects, constellations, atmospheric conditions |
| 🔬 | Scientific Macro | Extreme detail, microscopic structures, entomology |
| 🐠 | Underwater | Marine species, behaviour, visibility conditions |
| 📰 | Reportage & Documentary | Social context, visual narrative, historical documentation |
| 🛍 | Commercial & Product | Product, brand, visual communication, technical composition |
| 🌆 | Street & Urban | Urban life, architecture, ambient light, social interaction |

---

## User presets

In addition to built-in presets, custom presets can be generated via a local LLM (Plugin Tab → Configure → "Generate new preset" section). User presets are saved in `APP_DIR/user_presets/` and can be deleted from the same interface.

---

## Configuration

In **Plugin Tab → Prompt Context → Configure**:

1. Select a preset from the list (including **Standard** to disable any context)
2. Press **Activate** — the preset becomes active in Processing Tab and Gallery
3. The active preset is remembered across sessions

The **Prompt context** dropdown in Processing Tab updates automatically on selection.

---

## Preset structure

Presets are YAML files in the plugin's `presets/` directory:

```yaml
id: unique_id
name: Human-readable name
description: Short domain description
icon: "🦋"
author: OffGallery
version: "1.0"

context_block: |
  CONTEXT: ...
  - Instruction 1
  - Instruction 2
```

The `context_block` should be written in English for maximum VLM model compatibility.

---

## No additional requirements

The plugin requires no downloads, databases or internet connection. It works with any LLM backend configured in OffGallery (Ollama, LM Studio).

---

## License

OffGallery Plugins License v1.0 — Proprietary, no redistribution.
