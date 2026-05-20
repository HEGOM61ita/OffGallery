# Architettura dei Prompt LLM Vision — OffGallery

> **Scopo**: Documento di riferimento per l'ampliamento della pipeline di generazione testuale.
> Descrive la struttura esatta dei prompt, le variabili che li modificano, la logica di ordering
> delle sezioni e le ottimizzazioni che hanno portato alla configurazione attuale.
>
> **⚠️ ATTENZIONE — ZONA FRAGILE**: La struttura dei prompt è stata ottimizzata empiricamente
> su modelli piccoli (4B–8B parametri). Modifiche anche minori possono degradare significativamente
> la qualità dell'output. Prima di qualsiasi cambiamento, leggere il paragrafo "Razionale delle scelte".

---

## 1. Overview architettura

Il sistema genera testo descrittivo per immagini fotografiche in tre campi distinti:

| Campo | Tipo | Lunghezza tipica |
|-------|------|-----------------|
| `title` | Stringa breve, descrittiva | max 5 parole |
| `tags` | Lista di parole chiave | max 10 tag |
| `description` | Paragrafo narrativo | max 100 parole |

Ogni campo può essere generato singolarmente o in qualsiasi combinazione (es. solo tags, tags+descrizione,
tutti e tre). Il sistema usa un **nucleo unificato** per qualsiasi combinazione, anziché prompt separati.

### File principali coinvolti

| File | Ruolo nella pipeline prompt |
|------|-----------------------------|
| `embedding_generator.py` | Costruzione prompt, chiamata plugin, parsing output |
| `gui/processing_tab.py` | Orchestrazione: decide cosa generare, lancia thread LLM |
| `plugins/llm_ollama/plugin.py` | Invio HTTP a Ollama, pulizia output grezzo |
| `plugins/llm_lmstudio/plugin.py` | Invio HTTP a LM Studio (alternativa a Ollama) |
| `config_new.yaml` | Parametri generation (temperature, top_k, top_p, ecc.) |

---

## 2. Entrypoint pubblici

```
generate_llm_tags()        → generate_llm_combined(modes=['tags'])
generate_llm_description() → generate_llm_combined(modes=['description'])
generate_llm_title()       → generate_llm_combined(modes=['title'])
```

Il vero punto di ingresso è sempre `generate_llm_combined()` (embedding_generator.py).
I tre wrapper pubblici esistono solo per comodità esterna.

---

## 3. Struttura del prompt

### 3.1 Schema generale

```
/no_think
You are a professional photography cataloging system.

[LANGUAGE_RULES]

STEP 1 — ANALYSIS (internal reasoning, do not output this):
Carefully examine the image: main subject and its exact nature, secondary elements,
actions or motion, environment and setting, colors and light, composition and perspective,
atmosphere and mood. Build a complete mental description before generating any output.

STEP 2 — OUTPUT:
Write ONLY the lines below. Start each line with its label exactly as shown.
Stop immediately after the last required line. Do not repeat labels.

[FORMAT_SPEC]
```

### 3.2 Sezione LANGUAGE_RULES (dinamica)

```
LANGUAGE: ALL output MUST be in {lang_name}. NEVER mix languages.
[category_line]
[location_line]
[vernacular_line]
- If no species hint and you recognize an animal/plant, use a generic {lang_name} term.
- NEVER guess a species name. A generic term is ALWAYS better than a wrong name.
- NEVER use scientific/Latin names.
```

#### category_line (da BioCLIP taxonomy, campo `class` indice 2)

Caso con `category_hint` presente (es. "uccello" → tradotto EN in runtime → "bird"):

```
- The main subject is a {category_hint_en}. The species is already identified externally.
- DO NOT name the species. NEVER use species or scientific names.
- Focus ONLY on: visual attributes, behavior, environment, colors, composition.
```

Caso speciale `modes == ['title']` (solo titolo):

```
- The main subject is a {category_hint_en}. Use the correct {lang_name} translation of this term.
- DO NOT use species names or scientific Latin names.
```

Caso senza `category_hint`: la riga è omessa.

#### location_line (da GPS EXIF → geo_enricher.py)

Con GPS disponibile e lingua italiana/non-inglese:
```
- LOCATION: This photo was taken in: {location_hint}. Translate ALL place names to {lang_name}. Mention the location naturally if relevant.
```

Con GPS disponibile e lingua inglese:
```
- LOCATION: This photo was taken in: {location_hint}. Use standard English place names. Mention the location naturally if relevant.
```

Senza GPS:
```
- LOCATION: No GPS data available. Do NOT mention, guess or infer any specific location, city, country or place name.
```

#### vernacular_line (da BioCLIP, nome comune della specie)

Con `vernacular_name` presente:
```
- The common name of this species is: "{vernacular_name}". USE this name in your output (in {lang_name}). Do not translate it — it is already in the correct language.
```

Senza `vernacular_name`: la riga è omessa.

### 3.3 STEP 1 — Analysis kernel (Chain-of-Thought)

```
STEP 1 — ANALYSIS (internal reasoning, do not output this):
Carefully examine the image: main subject and its exact nature, secondary elements,
actions or motion, environment and setting, colors and light, composition and perspective,
atmosphere and mood. Build a complete mental description before generating any output.
```

**Razionale**: Su modelli piccoli (4B–8B), generare direttamente l'output porta a descrizioni
superficiali o incoerenti. Questo blocco forza il modello a compiere un'analisi interna completa
prima di scrivere. L'istruzione "(internal reasoning, do not output this)" evita che il testo
dell'analisi finisca nell'output finale. I risultati empirici mostrano un miglioramento
significativo nella coerenza semantica tra tags, descrizione e titolo.

### 3.4 STEP 2 — FORMAT_SPEC (dinamica per modo)

Le specifiche di formato per ogni campo:

```
TITLE: ...  (max {max_title_words} words, {lang_name}, factual/descriptive, no quotes, no ending punctuation)
TAGS: tag1,tag2,...  (max {max_tags}, {lang_name}, singular, comma-separated, only what you clearly see)
DESCRIPTION: ...  (max {max_description_words} words, {lang_name}, single paragraph, subject/environment/colors/composition/atmosphere)
```

Le righe compaiono **solo** per i modi effettivamente richiesti (vedi sezione 4 per l'ordine).

---

## 4. Ordine semantico delle sezioni di output

Indipendentemente da cosa l'utente vuole generare, l'ordine nel prompt è **sempre**:

```
TITLE → TAGS → DESCRIPTION
```

### Razionale (commento nel codice, embedding_generator.py ~2118)

**Ancora semantica 1 — TITLE sempre primo**: forza il modello a identificare il soggetto
principale in 5 parole prima di qualsiasi altro output. Il titolo funge da "ancora cognitiva":
impedisce che tags generici (forme, cielo) trascinino descrizione e titolo verso interpretazioni
sbagliate.

**Ancora semantica 2 — TAGS subito dopo TITLE**: l'enumerazione dei soggetti prima della
descrizione estesa migliora la coerenza. La descrizione finale risulta più focalizzata sui
soggetti già identificati.

### Meccanismo tecnico: campi "ancora" fantasma

Se l'utente vuole solo la descrizione (`modes=['description']`), il sistema aggiunge comunque
TITLE e TAGS al prompt (impostando max_tags=5 per non sprecare token). Poi **rimuove** i campi
extra dal risultato finale prima di restituirlo.

```python
# embedding_generator.py ~2116-2147
effective_modes = list(modes)

# Inietta title se mancante
title_added = False
if 'title' not in effective_modes:
    effective_modes = ['title'] + effective_modes
    title_added = True

# Inietta tags se mancante
anchor_added = False
if 'tags' not in effective_modes:
    effective_modes = [effective_modes[0]] + ['tags'] + effective_modes[1:]
    anchor_added = True

# ... (chiamata LLM) ...

# Rimuovi campi iniettati dal risultato
if anchor_added:
    result.pop('tags', None)
if title_added:
    result.pop('title', None)
```

---

## 5. Integrazione contesto BioCLIP

BioCLIP fornisce tre tipi di contesto che influenzano il prompt in modi diversi:

### 5.1 category_hint

- **Sorgente**: campo `class` (indice 2) della tassonomia BioCLIP
- **Pipeline**: classe tassonomica → dizionario `TAXONOMY_CLASS_HINTS` (IT) → traduzione EN via argostranslate
- **Uso nel prompt**: inserito in `category_line` dentro LANGUAGE_RULES
- **Soglia confidenza**: se `confidence < 0.15`, context BioCLIP ignorato completamente

Mappa tassonomica principale:
```
Aves          → uccello / bird
Mammalia      → mammifero / mammal
Reptilia      → rettile / reptile
Amphibia      → anfibio / amphibian
Actinopterygii → pesce / fish
Insecta       → insetto / insect
Arachnida     → aracnide / arachnid
Magnoliopsida → pianta / plant
Agaricomycetes → fungo / mushroom
```

### 5.2 vernacular_name

- **Sorgente**: campo "nome comune" da BioCLIP (lingua locale)
- **Uso nel prompt**: inserito in `vernacular_line` dentro LANGUAGE_RULES
- **Comportamento**: il modello DEVE usare questo nome, non traduzioni proprie

### 5.3 latin_name (post-processing, NON nel prompt)

Il nome latino (es. "Columba palumbus") **non viene mai passato al modello LLM**.
Viene invece inserito **programmaticamente** nell'output dopo il parsing:

```python
# embedding_generator.py ~2151-2163
if latin_name:
    result['tags'] = [latin_name] + normalize_tags(result['tags'])[:max_tags-1]
    result['description'] = f"{latin_name}: {result['description']}"
    result['title'] = f"{latin_name} - {result['title']}"
```

**Razionale**: I modelli 4B traducono male i nomi scientifici (es. "flamingo" → "fiammifero",
"Columba palumbus" → "colombo roccioso"). L'inserimento programmatico garantisce precisione assoluta.

---

## 6. Parametri di generazione

Configurazione attiva in `config_new.yaml`:

```yaml
generation:
  temperature: 0.1      # bassa → output deterministico e conservativo
  top_k: 40             # considera solo top 40 token per passo
  top_p: 0.8            # nucleus sampling: cumulativo 80%
  min_p: 0.0            # nessun filtro min_p
  num_ctx: 4096         # finestra di contesto (token)
  num_batch: 512        # batch size
  keep_alive: -1        # modello rimane caricato indefinitamente
```

**max_tokens** è calcolato dinamicamente in base ai modi richiesti:

```python
max_tokens = 15  # overhead label + newline
if 'tags' in modes:
    max_tokens += max_tags * 3 + 10
if 'description' in modes:
    max_tokens += int(max_description_words * 1.5) + 20
if 'title' in modes:
    max_tokens += int(max_title_words * 2) + 10
```

### Nota su /no_think

Il prompt inizia con `/no_think` (token speciale Qwen3) per disabilitare il blocco `<think>` nativo
di modelli come Qwen3-VL. Il plugin Ollama imposta anche `"think": false` nel payload.

**Attenzione**: il modello può comunque emettere `<think>...</think>` se il token non viene
riconosciuto. Il plugin gestisce questa eventualità con `_strip_think_blocks()`:

```python
# plugins/llm_ollama/plugin.py ~184-195
def _strip_think_blocks(text: str) -> str:
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    if cleaned:
        return cleaned
    # Blocco <think> non chiuso: token esauriti durante il thinking → stringa vuota
    if '</think>' not in text:
        return ''
    return text
```

---

## 7. Parsing dell'output

### 7.1 Algoritmo principale

Il parser (`_parse_combined_response`) legge l'output riga per riga cercando label note:

```
Label riconosciute: TAGS:, DESCRIPTION:, DESCRIZIONE:, TITLE:, TITOLO:
```

- Accumulazione multi-riga: tutto il testo dopo una label e prima della successiva viene accumulato
- Fallback senza label: se nessuna label trovata e la modalità è singola, l'intero testo è il valore
- Robustezza: le label vengono cercate case-insensitive (`upper.startswith(...)`)

### 7.2 Post-processing per tipo

**TAGS**:
- Split per `,` o `;`
- Filtro lunghezza: 2–50 caratteri
- Deduplicazione case-insensitive, preservando ordine
- Troncamento prima di label spurie (es. se il modello ripete il prompt)
- Limite: max `max_tags` elementi

**DESCRIPTION**:
- Join delle righe multiple
- Troncamento appena incontra una label successiva
- Preserva testo grezzo

**TITLE**:
- Solo prima riga
- Rimuove virgolette e punteggiatura finale

---

## 8. Esempi di prompt completi

### Caso A: Solo tags, con BioCLIP (uccello), con GPS

```
/no_think
You are a professional photography cataloging system.

LANGUAGE: ALL output MUST be in ITALIAN. NEVER mix languages.
- The main subject is a bird. The species is already identified externally.
- DO NOT name the species. NEVER use species or scientific names.
- Focus ONLY on: visual attributes, behavior, environment, colors, composition.
- LOCATION: This photo was taken in: Cagliari, Sardegna, Italy. Translate ALL place names to ITALIAN. Mention the location naturally if relevant.
- The common name of this species is: "Passero domestico". USE this name in your output (in ITALIAN). Do not translate it — it is already in the correct language.
- If no species hint and you recognize an animal/plant, use a generic ITALIAN term.
- NEVER guess a species name. A generic term is ALWAYS better than a wrong name.
- NEVER use scientific/Latin names.

STEP 1 — ANALYSIS (internal reasoning, do not output this):
Carefully examine the image: main subject and its exact nature, secondary elements,
actions or motion, environment and setting, colors and light, composition and perspective,
atmosphere and mood. Build a complete mental description before generating any output.

STEP 2 — OUTPUT:
Write ONLY the lines below. Start each line with its label exactly as shown.
Stop immediately after the last required line. Do not repeat labels.

TITLE: ...  (max 5 words, ITALIAN, factual/descriptive, no quotes, no ending punctuation)
TAGS: tag1,tag2,...  (max 5, ITALIAN, singular, comma-separated, only what you clearly see)
```

Output atteso dal modello:
```
TITLE: Passero domestico su ramo
TAGS: uccello, ramo, foglia, luce naturale, giardino
```

Output finale dopo post-processing (prepend nome latino, aggiunta city tag, limit a max_tags):
```python
tags = ['Passer domesticus', 'uccello', 'ramo', 'foglia', 'luce naturale', 'giardino', 'Cagliari']
```

---

### Caso B: Solo descrizione, senza BioCLIP, senza GPS

```
/no_think
You are a professional photography cataloging system.

LANGUAGE: ALL output MUST be in ITALIAN. NEVER mix languages.
- If no species hint and you recognize an animal/plant, use a generic ITALIAN term.
- NEVER guess a species name. A generic term is ALWAYS better than a wrong name.
- NEVER use scientific/Latin names.
- LOCATION: No GPS data available. Do NOT mention, guess or infer any specific location, city, country or place name.

STEP 1 — ANALYSIS (internal reasoning, do not output this):
Carefully examine the image: main subject and its exact nature, secondary elements,
actions or motion, environment and setting, colors and light, composition and perspective,
atmosphere and mood. Build a complete mental description before generating any output.

STEP 2 — OUTPUT:
Write ONLY the lines below. Start each line with its label exactly as shown.
Stop immediately after the last required line. Do not repeat labels.

TITLE: ...  (max 5 words, ITALIAN, factual/descriptive, no quotes, no ending punctuation)
TAGS: tag1,tag2,...  (max 5, ITALIAN, singular, comma-separated, only what you clearly see)
DESCRIPTION: ...  (max 100 words, ITALIAN, single paragraph, subject/environment/colors/composition/atmosphere)
```

Output atteso dal modello:
```
TITLE: Paesaggio montano al tramonto
TAGS: montagna, tramonto, cielo, nuvola, roccia
DESCRIPTION: Un paesaggio montano illuminato dalla luce dorata del tramonto. Le vette rocciose emergono da una coltre di nuvole basse, mentre il cielo si tinge di sfumature arancio e rosa. La composizione orizzontale esalta la vastità del panorama, con le rocce in primo piano che bilanciano visivamente le cime più lontane. L'atmosfera è silenziosa e maestosa.
```

Output finale (solo DESCRIPTION, perché TITLE e TAGS erano campi "ancora" rimossi):
```python
description = "Un paesaggio montano illuminato dalla luce dorata del tramonto. ..."
```

---

### Caso C: Tutti e tre i campi, soggetto non riconosciuto da BioCLIP

```
/no_think
You are a professional photography cataloging system.

LANGUAGE: ALL output MUST be in ITALIAN. NEVER mix languages.
- If no species hint and you recognize an animal/plant, use a generic ITALIAN term.
- NEVER guess a species name. A generic term is ALWAYS better than a wrong name.
- NEVER use scientific/Latin names.
- LOCATION: No GPS data available. Do NOT mention, guess or infer any specific location, city, country or place name.

STEP 1 — ANALYSIS (internal reasoning, do not output this):
Carefully examine the image: main subject and its exact nature, secondary elements,
actions or motion, environment and setting, colors and light, composition and perspective,
atmosphere and mood. Build a complete mental description before generating any output.

STEP 2 — OUTPUT:
Write ONLY the lines below. Start each line with its label exactly as shown.
Stop immediately after the last required line. Do not repeat labels.

TITLE: ...  (max 5 words, ITALIAN, factual/descriptive, no quotes, no ending punctuation)
TAGS: tag1,tag2,...  (max 10, ITALIAN, singular, comma-separated, only what you clearly see)
DESCRIPTION: ...  (max 100 words, ITALIAN, single paragraph, subject/environment/colors/composition/atmosphere)
```

---

## 9. Variabili che modificano il prompt

| Variabile | Sorgente | Impatto | Condizione di attivazione |
|-----------|----------|---------|--------------------------|
| `modes` | config utente | Sezioni output presenti | Sempre |
| `lang_code` | config UI | Lingua di tutto l'output | Sempre |
| `category_hint` | BioCLIP taxonomy\[2\] | Inserisce tipo soggetto in LANGUAGE_RULES | BioCLIP confidence ≥ 0.15 |
| `location_hint` | GPS EXIF → geo_enricher | Inserisce luogo in LANGUAGE_RULES | GPS disponibile nel file |
| `vernacular_name` | BioCLIP | Inserisce nome comune in LANGUAGE_RULES | BioCLIP confidence ≥ 0.15 |
| `max_tags` | config (default 10) | Limita numero tag richiesti | Campo tags abilitato |
| `max_description_words` | config (default 100) | Limita lunghezza descrizione | Campo description abilitato |
| `max_title_words` | config (default 5) | Limita lunghezza titolo | Campo title abilitato |
| `temperature` | config (default 0.1) | Variabilità output | Sempre |
| `top_k` / `top_p` | config | Strategia di sampling | Sempre |

---

## 10. Flusso dati completo

```
EXIF/RAW → thumbnail PIL
BioCLIP → taxonomy → category_hint, vernacular_name, latin_name, bioclip_context
GPS EXIF → geo_enricher → location_hint
config → lang_code, max_tags, max_desc_words, max_title_words, generation params

↓
generate_llm_combined(modes, bioclip_context, category_hint, location_hint, vernacular_name)
  ↓
  _prepare_llm_image(thumbnail)   → image_b64 (JPEG 512px, base64)
  _build_prompt(modes, ...)       → prompt string  [vedi sezioni 3-4]
  _call_llm_vision_unified(...)
    ↓
    llm_plugin.generate(image_b64, prompt, max_tokens, params)   [Ollama / LM Studio]
    ↓
    _strip_think_blocks(raw_response)
    ↓
    _parse_combined_response(text, modes, max_tags)
    ↓
    [rimozione campi "ancora" fantasma]
    ↓
    [prepend latin_name programmatico] ← da bioclip_context, NON dal LLM
    ↓
    normalize_tags(tags)
    ↓
    result: {'tags': [...], 'description': '...', 'title': '...'}

↓
processing_tab._thread_llm → merge/overwrite con DB → XMP export
```

---

## 11. Razionale delle scelte di ottimizzazione

### Perché il CoT esplicito (STEP 1 analysis)?

Su modelli piccoli, la generazione diretta dell'output porta a:
- Tags generici scollegati dall'immagine reale
- Descrizioni che ripetono solo il titolo
- Incoerenza tra i tre campi

L'istruzione di analisi interna forza un "pre-ragionamento" che:
1. Migliora la qualità semantica del titolo (più specifico)
2. Migliora la diversità dei tags (meno ridondanti)
3. Rende la descrizione più narrativa e coerente con gli altri campi

### Perché TITLE → TAGS → DESCRIPTION?

L'ordine è stato determinato empiricamente. Con l'ordine inverso (description prima):
- Il modello tende a "allargare" l'interpretazione nella descrizione
- Tags e titolo successivi diventano vaghi per coerenza con la descrizione ampia

Il titolo in 5 parole costringe a identificare il soggetto principale. I tag lo elencano
in dettaglio. La descrizione ha poi un "terreno semantico" già definito su cui costruire.

### Perché temperatura 0.1?

Alta temperatura (0.7+) sui modelli vision 4B porta a:
- Invenzione di dettagli non presenti nell'immagine
- Nomi di specie inventati (particolarmente problematico)
- Instabilità tra esecuzioni successive sulla stessa immagine

Temperatura bassa garantisce output conservativo ma coerente.

### Perché il nome latino NON viene dato al modello?

Testato empiricamente: i modelli 4B con nome scientifico nel prompt tendono a:
- "Tradurlo" letteralmente (Columba palumbus → "colomba pallida")
- Inventare caratteristiche basate solo sul nome, non sull'immagine
- Mescolare la specie reale con specie simili

L'inserimento programmatico post-parsing garantisce precisione assoluta.

### Perché /no_think?

Il blocco `<think>` nativo di Qwen3 occupa token preziosi (num_ctx limitato a 4096).
Con thinking abilitato, il modello può esaurire il budget di token nella fase di reasoning
e non generare alcun output strutturato. `/no_think` + `"think": false` previene questo problema.

**Paradosso**: il CoT è implementato come istruzione testuale (STEP 1), non come thinking nativo,
perché il CoT testuale è visibile al parser e consente di verificare/troncarlo, mentre il
thinking nativo di Qwen3 non è controllabile nel numero di token che consuma.

---

## 12. Plugin `prompt_context` — Architettura e implementazione

> **Stato**: ✅ IMPLEMENTATO — versione 1.0.0 (commit successivo all'aggiornamento di questo file).
> Questa sezione resta la fonte di verità: qualsiasi modifica futura al plugin o al punto
> di iniezione deve partire da qui.

### Obiettivo

Permettere all'utente di personalizzare il contesto descrittivo dei prompt senza toccare
la struttura portante (CoT, anchor semantici, label di output, parser). La personalizzazione
avviene tramite un **blocco CONTEXT** iniettato nel prompt in un punto preciso e sicuro,
prodotto da un plugin dedicato.

### Punto di iniezione

```
/no_think
You are a professional photography cataloging system.

[LANGUAGE_RULES]

[→ BLOCCO CONTEXT — iniettato qui dal plugin, se presente ←]

STEP 1 — ANALYSIS (internal reasoning, do not output this):
...

STEP 2 — OUTPUT:
...
```

Il punto è scelto perché:
- Viene dopo le regole di lingua (il modello ha già il contesto linguistico)
- Viene prima del CoT (il contesto è disponibile durante il ragionamento interno)
- Non interferisce con le label di output né con il parser

### Invarianti — cosa non tocca mai il plugin

Le seguenti parti del prompt sono **fuori portata** per qualsiasi plugin `prompt_context`:

- `/no_think` e la frase di apertura `You are a professional...`
- L'intero blocco STEP 1 (kernel CoT)
- La struttura STEP 2 e le label `TITLE:`, `TAGS:`, `DESCRIPTION:`
- L'ordine semantico degli anchor (TITLE → TAGS → DESCRIPTION)
- L'iniezione programmatica del nome latino da BioCLIP (post-parsing)

### Interfaccia da aggiungere in `plugins/base.py`

```python
class PromptContextPlugin(ABC):
    """Fornisce un blocco CONTEXT opzionale da iniettare nel prompt vision.

    Il blocco viene inserito dopo LANGUAGE_RULES e prima del kernel CoT (STEP 1).
    Il plugin non modifica nessun'altra parte del prompt.
    Coperto dalla Plugin Interface Exception dichiarata nell'intestazione di questo file.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """True se il plugin è pronto all'uso (preset caricato, configurazione valida)."""
        ...

    @abstractmethod
    def get_context(self, metadata: dict) -> Optional[str]:
        """Ritorna il blocco CONTEXT da iniettare nel prompt.

        Args:
            metadata: {
                'image_path':       str,
                'modes':            list[str],       # ['tags', 'description', 'title']
                'lang_code':        str,             # 'it', 'en', ...
                'bioclip_taxonomy': list | None,
                'geo_hierarchy':    str | None,
                'existing_tags':    list[str],
            }

        Returns:
            Testo libero da iniettare (max ~150 parole consigliato),
            oppure None se il plugin non ha contesto da aggiungere per questa immagine.
        """
        ...

    def get_preset_name(self) -> str:
        """Nome del preset attivo — usato nel log. Default: nome della classe."""
        return type(self).__name__
```

L'eccezione AGPLv3 in cima a `base.py` va aggiornata per nominare esplicitamente
`PromptContextPlugin` accanto a `LLMVisionPlugin` e `GeoEnricherPlugin`.

### Hook in `embedding_generator._call_llm_vision_unified()`

Circa 8 righe da aggiungere dopo la costruzione di `language_rules` e prima di
`analysis_kernel`:

```python
# Iniezione blocco CONTEXT da plugin prompt_context (se presente e attivo)
context_block = ''
if self.prompt_context_plugin is not None:
    try:
        _meta = {
            'image_path':       getattr(image_input, 'filename', None),
            'modes':            modes,
            'lang_code':        self.lang_code,
            'bioclip_taxonomy': None,   # passato come parametro se disponibile
            'geo_hierarchy':    None,
            'existing_tags':    [],
        }
        _ctx = self.prompt_context_plugin.get_context(_meta)
        if _ctx:
            context_block = _ctx.strip() + '\n\n'
    except Exception:
        logger.warning('PromptContextPlugin.get_context() fallita — ignorata', exc_info=True)
```

Il prompt diventa:

```python
prompt = (
    "/no_think\n"
    "You are a professional photography cataloging system.\n\n"
    f"{language_rules}\n"
    f"{context_block}"          # ← nuovo, vuoto se plugin assente
    f"{analysis_kernel}"
    "STEP 2 — OUTPUT:\n"
    ...
)
```

### Struttura del plugin concreto

```
plugins/prompt_context/
├── plugin.py              ← PromptContextPlugin implementation
├── __init__.py
├── manifest.json          ← type: "prompt_context"
├── LEGAL_NOTICE.txt
├── README.md
├── presets/               ← preset built-in distribuiti col plugin
│   ├── naturalistic.yaml
│   ├── reportage.yaml
│   ├── commercial.yaml
│   ├── landscape.yaml
│   ├── underwater.yaml
│   ├── macro_scientific.yaml
│   ├── street.yaml
│   └── astro.yaml
└── generator/
    └── meta_prompt.txt    ← prompt usato per l'auto-generazione (scritto dagli autori)
```

I preset utente vengono salvati fuori dal plugin (non tracciati da git):

```
APP_DIR/user_presets/*.yaml   oppure   ~/.config/offgallery/prompt_presets/*.yaml
```

### Struttura di un preset YAML

```yaml
id: naturalistic
name: Archivio Naturalistico
description: Fotografia scientifica di natura — specie, habitat, comportamento
icon: 🦋
author: OffGallery
version: 1.0

context_block: |
  CONTEXT: This is a scientific wildlife photography archive.
  - Priority: species behavior, ecological relationships, and natural habitat accuracy.
  - For birds: note posture, plumage phase, foraging or flight behavior if visible.
  - For plants: note growth stage, habitat, any visible ecological interaction.
  - Prefer precise observational language over aesthetic or poetic descriptions.
  - If the subject shows interaction with environment (feeding, nesting, camouflage), document it.
```

### Catalogo preset built-in pianificati

| ID | Nome | Focus |
|----|------|-------|
| `naturalistic` | Archivio Naturalistico | Specie, habitat, comportamento — linguaggio scientifico |
| `reportage` | Fotografia di Reportage | Soggetti umani, contesto sociale, momento decisivo |
| `commercial` | Catalogo Commerciale | Prodotti, dettagli tecnici — no nomi propri di persone |
| `landscape` | Paesaggio e Territorio | Luce, stagione, morfologia del territorio, senso del luogo |
| `underwater` | Fotografia Subacquea | Specie marine, visibilità, comportamento subacqueo |
| `macro_scientific` | Macro e Scientifico | Dettagli morfologici, strutture, scale di riferimento |
| `street` | Street Photography | Composizione urbana, anonimizzazione, atmosfera |
| `astro` | Astrofotografia | Corpi celesti, condizioni di ripresa, costellazioni |

### Auto-generazione preset da testo utente

Il plugin include un generatore che chiama il LLM locale (testo puro, nessuna immagine)
con un meta-prompt scritto dagli autori. L'utente descrive l'archivio in linguaggio libero;
il modello produce un `context_block` strutturato, pronto da salvare come preset.

Parametri ottimizzati per la generazione del preset (diversi dal vision):

```python
meta_params = {
    'temperature': 0.4,   # più alta rispetto a 0.1 del vision: serve creatività controllata
    'top_p':       0.9,
    'top_k':       50,
    'num_ctx':     2048,
    'num_predict': 200,   # stretto: il context_block deve essere conciso
}
```

Il meta-prompt (`generator/meta_prompt.txt`) è un file di testo fisso scritto dagli autori,
non modificabile dall'utente finale. Viene versionato e migliorato nei rilasci successivi.

### Integrazione UI (tab Processing)

- Dropdown **"Contesto prompt"** accanto alle opzioni LLM esistenti
- Voci: `(nessuno)` | preset built-in | preset utente | `✏️ Gestisci preset...`
- Dialog **"Gestisci preset"**: tab Catalogo / Personali / Genera nuovo
- Il campo "Genera nuovo" mostra una text area per la descrizione libera, il bottone
  "Genera con LLM", l'anteprima del `context_block` prodotto, e i bottoni Salva / Usa / Annulla

### Licenza

| Componente | File | Licenza |
|-----------|------|---------|
| Interfaccia `PromptContextPlugin` | `plugins/base.py` | AGPLv3 + eccezione (da aggiornare) |
| Rilevamento nel loader | `plugins/loader.py` | AGPLv3 + eccezione |
| Hook nel prompt builder | `embedding_generator.py` | AGPLv3 (core) |
| Plugin concreto, preset, generatore, UI | `plugins/prompt_context/` | OffGallery Plugins License v1.0 |
| Preset utente | `APP_DIR/user_presets/` | Utente — nessuna restrizione |

### Ordine di implementazione — completato

1. ✅ `plugins/base.py`: `PromptContextPlugin` aggiunto, intestazione eccezione AGPLv3 aggiornata
2. ✅ `plugins/loader.py`: `load_prompt_context_plugin()` — rilevamento e caricamento
3. ✅ `embedding_generator.py`: `self.prompt_context_plugin`, `_init_prompt_context_plugin()`, hook in `_call_llm_vision_unified()`
4. ✅ `plugins/prompt_context/plugin.py`: `PromptContextPluginImpl`, `load_all_presets()`, `save_user_preset()`, `delete_user_preset()`, `generate_preset_from_description()`
5. ✅ 8 preset YAML built-in in `plugins/prompt_context/presets/`
6. ✅ `plugins/prompt_context/generator/meta_prompt.txt`: meta-prompt fisso per auto-generazione
7. ✅ UI completa (vedi Sezione 13)

---

## 13. Componenti UI del plugin `prompt_context`

### 13.1 Plugin Tab — `PromptContextPluginCard` (slim)

La card appare nel tab Plugin con lo stesso layout delle altre card (`LLMPluginCard`):

```
[📋 Contesto Prompt  v1.0.0]  [descrizione breve…]  [▶ 🌿 Naturalistico]  [Configura ▸]
```

- La label a destra mostra il preset attivo (`▶ {icon} {nome}`) o "Nessun preset" in grigio
- Il bottone **"Configura ▸"** apre `PromptContextConfigDialog` in modale
- La label si aggiorna automaticamente quando la dialog attiva un preset
- Emette `preset_activated = pyqtSignal(str)` — propagato via `PluginsTab.prompt_context_preset_changed`
  alla `ProcessingTab` tramite connessione in `main_window.py`

### 13.2 Plugin Tab — `PromptContextConfigDialog`

Dialog modale (700×520 min) aperto da "Configura ▸". Contiene due sezioni:

**Sezione "Preset disponibili"**

```
[lista preset 200px]   [anteprima context_block — monospace, read-only]
[label attivo]                              [✅ Attiva]  [🗑 Elimina]
```

- Lista mostra `{icon} {nome}` + ` ★` per i preset utente
- Selezionando un preset si vede l'anteprima del `context_block`
- **"✅ Attiva"** è **disabilitato** se il preset selezionato è già quello attivo (evita l'ambiguità del verde permanente)
- Al click su "Attiva": salva `active_preset` in `config_new.yaml`, emette `preset_activated`, disabilita il tasto
- **"🗑 Elimina"** abilitato solo per preset utente (`source == 'user'`)

**Sezione "Genera nuovo preset con LLM"**

```
[textarea descrizione archivio — italiano]
[⚡ Genera con LLM]
[anteprima context_block generato — nascosta finché non si genera]
[campo nome preset]  [💾 Salva preset]
```

- Chiama `generate_preset_from_description()` con parametri ottimizzati (temp 0.4, top_p 0.9)
- Endpoint e modello letti da config (stessa configurazione di `llm_vision`)
- Il preset salvato ottiene `icon: 🔖`, `source: user`, viene aggiunto alla lista

### 13.3 Processing Tab — Dropdown preset

Riga sottile sotto le opzioni plugin (icona `📋`, QComboBox inline):

```
[📋]  [(nessun contesto)  ▼  🌿 Archivio Naturalistico]
```

- Popola all'avvio leggendo `load_all_presets()`
- Pre-seleziona `active_preset` da config
- Al cambio: salva su `config_new.yaml` + propaga a `embedding_gen.prompt_context_plugin.set_active_preset()`
- **Sincronizzazione automatica**: `on_activated()` chiama `_refresh_prompt_context_combo()` ogni volta
  che l'utente passa al tab Processing, allineando il dropdown al config aggiornato dalla Plugin Tab

### 13.4 Gallery Tab — Dialog generazione LLM

Il dialog `LLMTagDialog` (apertura da menù contestuale gallery) include:

**Sezione "Cosa generare"** (checkbox persistenti):
- `☑ Titolo` / `☑ Tag` / `☑ Descrizione` — stato salvato in `config_new.yaml → gallery_llm_dialog`

**Sezione "Parametri"** (spinbox persistenti, override per questo task):
- Parole titolo: 1–15 (default da config `auto_import.title.max_words`)
- Numero tag: 1–50 (default da config `auto_import.tags.max`)
- Parole descrizione: 10–500 (default da config `auto_import.description.max_words`)

**Sezione "Contesto prompt"** (combo rapida, solo se preset installati):
- `(nessuno)` + lista preset — pre-seleziona l'`active_preset` corrente
- Scelta rapida senza possibilità di generare nuovi preset (solo nella Plugin Tab)

Alla conferma (OK), tutti i valori vengono salvati in:

```yaml
gallery_llm_dialog:
  gen_title: true
  gen_tags: true
  gen_description: true
  max_tags: 10
  max_words_desc: 100
  max_title_words: 5
```

e il preset scelto in `prompt_context.active_preset`. Al prossimo utilizzo il dialog
si riapre con gli stessi valori.

### 13.5 Propagazione cross-tab del preset attivo

```
PromptContextConfigDialog._on_activate()
  → salva config_new.yaml
  → emette preset_activated(preset_id)
PromptContextPluginCard._on_dialog_preset_activated()
  → aggiorna _lbl_active
  → riemette preset_activated(preset_id)
PluginsTab.prompt_context_preset_changed (pyqtSignal)
  ← connesso in PluginsTab._populate_plugins()
main_window.py → processing_tab.refresh_prompt_context_preset(preset_id)
  → aggiorna QComboBox (blockSignals)
  → embedding_gen.prompt_context_plugin.set_active_preset(preset_id)
```

La `ProcessingTab.on_activated()` chiama anche `_refresh_prompt_context_combo()` come
sincronizzazione di rientro (lettura da disco), coprendo il caso in cui il segnale non
sia stato ricevuto (es. la plugin tab è stata usata prima che il tab Processing venisse
mai aperto).
