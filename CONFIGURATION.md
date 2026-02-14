# Configurazione OffGallery

OffGallery offre ampie possibilità di personalizzazione tramite il file `config_new.yaml` o direttamente dall'interfaccia grafica (tab **Configurazione**).

---

## File di Configurazione

Il file principale di configurazione è `config_new.yaml` nella root del progetto.

### Struttura Generale

```yaml
embedding:
  models:
    clip:
      enabled: true
      model_name: "ViT-B-32"
    dinov2:
      enabled: true
      model_name: "dinov2_vitb14"
    bioclip:
      enabled: true
      threshold: 0.15
      max_results: 5
    aesthetic:
      enabled: true
    technical:
      enabled: true
    llm_vision:
      enabled: true
      model: "qwen3-vl:4b-instruct"
      endpoint: "http://localhost:11434"
      timeout: 240
      generation:
        temperature: 0.2
        top_k: 20
        top_p: 0.8
      auto_import:
        tags:
          enabled: true
          max_tags: 10
        description:
          enabled: true
          max_words: 50
        title:
          enabled: false
          max_words: 5

search:
  semantic_threshold: 0.25
  fuzzy_matching: true
  fuzzy_threshold: 0.8

external_editors:
  lightroom:
    path: "C:/Program Files/Adobe/Adobe Lightroom Classic/Lightroom.exe"
  dxo:
    path: "C:/Program Files/DxO/DxO PhotoLab 7/DxOPhotoLab7.exe"
```

---

## Sezioni Principali

### Embedding Models

Configura i modelli AI per l'analisi delle immagini.

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `clip.enabled` | bool | Abilita embedding CLIP per ricerca semantica |
| `clip.model_name` | string | Modello CLIP da usare (ViT-B-32, ViT-L-14, etc.) |
| `dinov2.enabled` | bool | Abilita embedding DINOv2 per similarità visiva |
| `bioclip.enabled` | bool | Abilita classificazione flora/fauna |
| `bioclip.threshold` | float | Soglia minima confidenza BioCLIP (0.0-1.0) |
| `bioclip.max_results` | int | Numero massimo di tag specie |
| `aesthetic.enabled` | bool | Abilita valutazione estetica |
| `technical.enabled` | bool | Abilita valutazione qualità tecnica |
| `llm_vision.enabled` | bool | Abilita generazione tag/descrizioni via LLM |
| `llm_vision.model` | string | Modello Ollama da usare |
| `llm_vision.endpoint` | string | Indirizzo endpoint Ollama |
| `llm_vision.timeout` | int | Timeout in secondi per risposta LLM |
| `llm_vision.generation.temperature` | float | Creativita' LLM (0.0-2.0). Bassi (0.1-0.3): preciso. Alti (0.7+): creativo |
| `llm_vision.generation.top_k` | int | Numero token candidati per step (1-100) |
| `llm_vision.generation.top_p` | float | Nucleus sampling (0.0-1.0) |

### Auto Import

Configura il comportamento durante l'importazione automatica.

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `tags.max_tags` | int | Numero massimo di tag generati da LLM |
| `description.enabled` | bool | Genera descrizioni automatiche |
| `description.max_length` | int | Lunghezza massima descrizione |

### Search

Configura i parametri di ricerca.

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `semantic_threshold` | float | Soglia minima similarità CLIP (0.0-1.0) |
| `fuzzy_matching` | bool | Abilita ricerca fuzzy per tag |
| `fuzzy_threshold` | float | Precisione matching fuzzy (0.0-1.0) |

### External Editors

Configura i percorsi degli editor esterni per l'integrazione.

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `lightroom.path` | string | Percorso eseguibile Adobe Lightroom Classic |
| `dxo.path` | string | Percorso eseguibile DxO PhotoLab |

---

## Configurazione via GUI

La maggior parte delle impostazioni è accessibile dal tab **Configurazione** dell'interfaccia grafica:

1. **Modelli AI**: Abilita/disabilita singoli modelli
2. **Soglie**: Regola threshold per ricerca e classificazione
3. **Editor esterni**: Configura percorsi applicazioni
4. **Parametri LLM**: Modello, endpoint, temperature, top_k, top_p (sezione avanzata collassabile)

Le modifiche dalla GUI vengono salvate automaticamente in `config_new.yaml`.

---

## Profili di Ottimizzazione

OffGallery include profili di ottimizzazione per diverse situazioni:

| Profilo | Uso | Trade-off |
|---------|-----|-----------|
| `clip_embedding` | Generazione embedding | Qualità vs velocità |
| `aesthetic_score` | Valutazione estetica | Precisione vs risorse |
| `bioclip_classification` | Identificazione specie | Dettaglio vs memoria |
| `thumbnail_preview` | Anteprima gallery | Velocità vs qualità |

I profili vengono selezionati automaticamente in base al contesto di utilizzo.

---

## Note

- Le modifiche al file YAML richiedono il riavvio dell'applicazione
- Le modifiche dalla GUI sono applicate immediatamente
- Il backup della configurazione è automatico cliccando su 'save'
