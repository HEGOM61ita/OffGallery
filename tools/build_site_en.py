#!/usr/bin/env python
"""Genera le pagine inglesi del sito (HTML/en/) e allinea i meta SEO di quelle italiane.

Sorgente di verità: le pagine italiane in HTML/ (index, features, credits) e il
loro dizionario JS di traduzioni (T / i18n). Lo script:

  1. riscrive il blocco <head> SEO delle pagine italiane (titolo, description,
     Open Graph, Twitter Card, canonical, hreflang, favicon, JSON-LD);
  2. fa puntare il pulsante lingua delle pagine italiane all'URL inglese reale
     (prima sostituiva i testi via JavaScript sullo stesso URL, invisibile ai
     motori di ricerca);
  3. genera HTML/en/<pagina>.html con i testi inglesi già scritti nell'HTML,
     così sono indicizzabili anche senza eseguire JavaScript;
  4. rigenera HTML/sitemap.xml con le coppie IT/EN e gli hreflang.

Uso (dalla root del progetto):
    python tools/build_site_en.py [--lastmod AAAA-MM-GG]

Lo script è idempotente: rilanciarlo dopo aver modificato una pagina italiana
o il suo dizionario aggiorna le versioni inglesi.
"""
import argparse
import json
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "HTML"
SITE = "https://offgallery.app"
GITHUB = "https://github.com/HEGOM61ita/OffGallery"
REPO_ISOLATI = ("USER_MANUAL_IT.html", "USER_MANUAL_EN.html")
LASTMOD_MANUALI = "2026-09-03"

# ── Meta per pagina e lingua ────────────────────────────────────────────────
PAGINE = {
    "index.html": {
        "it_path": "/", "en_path": "/en/",
        "it_toggle": "'en/'", "en_toggle": "'../'",
        "priority": "1.0", "changefreq": "monthly",
        "it": {
            "title": "OffGallery — Il tuo archivio. La tua AI. Zero cloud.",
            "desc": ("OffGallery — Sei modelli AI locali per la catalogazione fotografica. "
                     "Ricerca semantica + tag + EXIF combinati, riconoscimento automatico di flora e fauna, "
                     "valutazione estetica, sync Lightroom/darktable via XMP, statistiche complete. "
                     "Scalabile, configurabile, multilingua. Zero cloud, privacy totale."),
            "og_desc": "Catalogazione intelligente per fotografi professionisti. AI locale, nessun dato inviato online.",
            "keywords": "OffGallery, fotografia, AI locale, offline, catalogazione foto, ricerca semantica, Lightroom, privacy",
        },
        "en": {
            "title": "OffGallery — Your archive. Your AI. Zero cloud.",
            "desc": ("OffGallery — Six local AI models for photo cataloging. "
                     "Combined semantic search + tags + EXIF, automatic flora and fauna recognition, "
                     "aesthetic scoring, Lightroom/darktable sync via XMP, full statistics. "
                     "Scalable, configurable, multilingual. Zero cloud, total privacy."),
            "og_desc": "Intelligent photo cataloging for professional photographers. Local AI, no data sent online.",
            "keywords": "OffGallery, photography, local AI, offline, photo cataloging, semantic search, Lightroom, privacy, RAW, XMP, BioCLIP",
        },
    },
    "features.html": {
        "it_path": "/features.html", "en_path": "/en/features.html",
        "it_toggle": "'en/features.html'", "en_toggle": "'../features.html'",
        "priority": "0.8", "changefreq": "monthly",
        "it": {
            "title": "OffGallery — Tutte le funzionalità",
            "desc": ("OffGallery — Tutte le funzionalità: sei modelli AI locali, ricerca semantica, "
                     "riconoscimento specie con BioCLIP, valutazione estetica e tecnica, plugin, "
                     "sync XMP con Lightroom e darktable. Tutto offline."),
        },
        "en": {
            "title": "OffGallery — All features",
            "desc": ("OffGallery — All features: six local AI models, semantic search, "
                     "species recognition with BioCLIP, aesthetic and technical scoring, plugins, "
                     "XMP sync with Lightroom and darktable. Fully offline."),
        },
    },
    "credits.html": {
        "it_path": "/credits.html", "en_path": "/en/credits.html",
        "it_toggle": "'en/credits.html'", "en_toggle": "'../credits.html'",
        "priority": "0.4", "changefreq": "yearly",
        "it": {
            "title": "OffGallery — Crediti e Ringraziamenti",
            "desc": "OffGallery — Crediti, ringraziamenti e licenze dei componenti open source e dei modelli AI utilizzati.",
        },
        "en": {
            "title": "OffGallery — Credits and Acknowledgements",
            "desc": "OffGallery — Credits, acknowledgements and licenses of the open source components and AI models used.",
        },
    },
}

# Funzionalità per il JSON-LD della home (solo cose presenti nel progetto)
FEATURE_LIST = {
    "it": [
        "Ricerca semantica multilingua con SigLIP",
        "Ricerca combinata semantica + tag + EXIF",
        "Riconoscimento di specie animali e vegetali con BioCLIP 2 (~450.000 specie, tassonomia a 7 livelli)",
        "Valutazione estetica e tecnica delle immagini",
        "Tag, titoli e descrizioni con LLM Vision locale (Ollama, LM Studio)",
        "Geolocalizzazione offline da GPS",
        "Sincronizzazione XMP con Lightroom, darktable, Capture One, digiKam",
        "Import da catalogo Lightroom (.lrcat)",
        "Supporto a oltre 25 formati RAW",
        "Interfaccia e contenuti generati in 6 lingue",
        "100% offline: nessuna immagine lascia il computer",
    ],
    "en": [
        "Multilingual semantic search with SigLIP",
        "Combined semantic + tag + EXIF search",
        "Animal and plant species recognition with BioCLIP 2 (~450,000 species, 7-level taxonomy)",
        "Aesthetic and technical image scoring",
        "Tags, titles and descriptions with a local Vision LLM (Ollama, LM Studio)",
        "Offline geolocation from GPS",
        "XMP sync with Lightroom, darktable, Capture One, digiKam",
        "Import from Lightroom catalogs (.lrcat)",
        "Support for 25+ RAW formats",
        "Interface and generated content in 6 languages",
        "100% offline: no image ever leaves the computer",
    ],
}

OG_ALT = {
    "it": "OffGallery — Il tuo archivio. La tua AI. Zero cloud.",
    "en": "OffGallery — Your archive. Your AI. Zero cloud.",
}

# Attributi (non coperti dal dizionario T) da tradurre nelle pagine inglesi
ATTR_EN = {
    'aria-label="Navigazione laterale"': 'aria-label="Side navigation"',
    'aria-label="Cambia lingua"': 'aria-label="Change language"',
    'alt="Logo OffGallery"': 'alt="OffGallery logo"',
    'alt="OffGallery — Ricerca semantica"': 'alt="OffGallery — Semantic search"',
    'alt="OffGallery — Elaborazione"': 'alt="OffGallery — Processing"',
    'alt="OffGallery — Statistiche"': 'alt="OffGallery — Statistics"',
    'alt="OffGallery — Configurazione"': 'alt="OffGallery — Settings"',
}

# Testi scritti direttamente nell'HTML italiano (fuori dal dizionario T): sezione
# di confronto con i competitor della home. Coppie (italiano, inglese) applicate
# in ordine; se un testo italiano cambia, lo script avvisa che la coppia è orfana.
EXTRA_EN = [
    ("<h2>OffGallery vs. i competitor</h2>", "<h2>OffGallery vs. the competition</h2>"),
    ("Un confronto onesto, basato su codice sorgente e documentazione ufficiale.",
     "An honest comparison, based on source code and official documentation."),
    ("Aggiornato al 13 maggio 2026 — Immich", "Updated May 13, 2026 — Immich"),
    ("★ Feature esclusive disponibili tramite plugin", "★ Exclusive features available through plugins"),
    ("Alcune delle capacità più uniche di OffGallery sono disponibili attraverso il sistema plugin. "
     "Tra queste, il <strong>generatore AI di prompt specializzati per la generazione di tag, titoli e descrizioni</strong>, "
     "adattati a specifiche esigenze: basterà descrivere in linguaggio naturale le proprietà richieste e l'AI svilupperà "
     "un prompt ottimizzato, sostitutivo di quello standard, col quale guiderà l'LLM Vision nella produzione di tag, "
     "titoli e descrizioni delle immagini sottoposte — una funzione che non esiste in nessun altro software di "
     "catalogazione fotografica.",
     "Some of OffGallery's most unique capabilities are available through the plugin system. Among them, the "
     "<strong>AI generator of specialized prompts for producing tags, titles and descriptions</strong>, tailored to "
     "specific needs: just describe the required properties in natural language and the AI will build an optimized "
     "prompt, replacing the standard one, to guide the Vision LLM in producing tags, titles and descriptions for the "
     "submitted images — a feature that does not exist in any other photo cataloging software."),
    ("Generatore AI di prompt specializzati per LLM Vision", "AI generator of specialized prompts for Vision LLMs"),
    ("Nomi comuni biologici multilingua (BioNomen)", "Multilingual biological common names (BioNomen)"),
    ("Dati geografici da databank pubblici", "Geographic data from public databanks"),
    ("Backend LLM intercambiabile (Ollama · LM Studio)", "Swappable LLM backend (Ollama · LM Studio)"),
    ("Scopri tutti i plugin →", "Discover all plugins →"),
    ("Ricerca e Retrieval", "Search and Retrieval"),
    ("AI e Analisi Automatica", "AI and Automatic Analysis"),
    ("Privacy e Architettura", "Privacy and Architecture"),
    ("Metadati ed Export", "Metadata and Export"),
    ('<th colspan="5">Configurazione</th>', '<th colspan="5">Configuration</th>'),
    ('Ricerca semantica in linguaggio naturale<small>("tramonto sul mare con barca")</small>',
     'Natural-language semantic search<small>("sunset over the sea with a boat")</small>'),
    ("(Google, 400M param, multilingua)", "(Google, 400M params, multilingual)"),
    ("(ViT-B/32, 151M param — solo EN)", "(ViT-B/32, 151M params — EN only)"),
    ("solo keyword/tag", "keyword/tag only"),
    ("SmartTags proprietari, no query libera", "Proprietary SmartTags, no free-text query"),
    ('Slider bilanciamento semantica / testo<small>(peso SigLIP vs tag/descrizione/titolo — "Deep Search")</small>',
     'Semantic / text balance slider<small>(SigLIP weight vs tag/description/title — "Deep Search")</small>'),
    ("★ ESCLUSIVA", "★ EXCLUSIVE"),
    ("Ricerca semantica multilingua nativa<small>(SigLIP comprende italiano, inglese e altre lingue — nessuna traduzione necessaria)</small>",
     "Native multilingual semantic search<small>(SigLIP understands Italian, English and other languages — no translation needed)</small>"),
    ('Ricerca per similarità visiva deep learning<small>("trova foto simili a questa")</small>',
     'Deep-learning visual similarity search<small>("find photos similar to this one")</small>'),
    ("Haar/Wavelets (non deep learning)", "Haar/Wavelets (not deep learning)"),
    ("Filtro per qualità AI<small>", "AI quality filter<small>"),
    ("Ricerca per gerarchia geografica strutturata<small>(Continente › Paese › Regione › Città)</small>",
     "Structured geographic hierarchy search<small>(Continent › Country › Region › City)</small>"),
    ("GeOFF gerarchico", "hierarchical GeOFF"),
    ("per luogo, non strutturato", "by place, unstructured"),
    ("GPS/mappa, no gerarchia", "GPS/map, no hierarchy"),
    ("mappa drag-and-drop", "drag-and-drop map"),
    ("Tassonomia biologica automatica<small>(7 livelli, ~450.000 specie flora/fauna — BioCLIP v2)</small>",
     "Automatic biological taxonomy<small>(7 levels, ~450,000 flora/fauna species — BioCLIP v2)</small>"),
    ("Descrizione e titolo automatici in linguaggio naturale<small>(LLM Vision locale via Ollama/LMStudio)</small>",
     "Automatic natural-language description and title<small>(local Vision LLM via Ollama/LMStudio)</small>"),
    ("Lingua di output LLM configurabile<small>(tag/descrizioni/titoli nella lingua scelta dall'utente)</small>",
     "Configurable LLM output language<small>(tags/descriptions/titles in the user's chosen language)</small>"),
    ('Culling guidato da AI<small>(filtra per score AI + stelle + colore; "trova simili" DINOv2 con soglia e finestra sessione; preset salvabili per workflow ripetibili)</small>',
     'AI-guided culling<small>(filter by AI score + stars + color; DINOv2 "find similar" with threshold and session window; savable presets for repeatable workflows)</small>'),
    ("</span> guidato da AI", "</span> AI-guided"),
    ("Geolocalizzazione inversa offline<small>(GPS → Continente/Paese/Città senza API esterne)</small>",
     "Offline reverse geocoding<small>(GPS → Continent/Country/City without external APIs)</small>"),
    ("richiede connessione iniziale", "requires initial connection"),
    ("usa servizio online", "uses an online service"),
    ("Le immagini non lasciano mai il dispositivo<small>(nessuna foto trasmessa a servizi esterni — alcuni plugin possono fare richieste spot a databank pubblici per arricchire i metadati)</small>",
     "Images never leave the device<small>(no photo is sent to external services — some plugins may make one-off requests to public databanks to enrich metadata)</small>"),
    ("Nessun abbonamento obbligatorio", "No mandatory subscription"),
    ("abbonamento mensile", "monthly subscription"),
    ("Architettura plugin estensibile", "Extensible plugin architecture"),
    ("sistema plugin nativo", "native plugin system"),
    ("</span> limitato</td>", "</span> limited</td>"),
    ("(round-trip con Lightroom/Capture One/darktable)", "(round-trip with Lightroom/Capture One/darktable)"),
    ("con preservazione selettiva campi", "with selective field preservation"),
    ("Export con selezione sorgente indipendente dalla gallery<small>(gallery oppure directory/intero DB — senza cercare prima)</small>",
     "Export with source selection independent of the gallery<small>(gallery, or directory/entire DB — no need to search first)</small>"),
    ("export automatico su tutti i file, no selezione arbitraria", "automatic export on all files, no arbitrary selection"),
    ("solo selezione destinazione", "destination selection only"),
    ("selezione manuale foto per foto", "manual photo-by-photo selection"),
    ("Export CSV dei metadati<small>(con esclusione GPS/EXIF per privacy)</small>",
     "Metadata CSV export<small>(with GPS/EXIF exclusion for privacy)</small>"),
    ("solo gerarchia tag", "tag hierarchy only"),
    ("Import catalogo Lightroom Classic<small>(.lrcat — rating, color label, percorsi file)</small>",
     "Lightroom Classic catalog import<small>(.lrcat — rating, color label, file paths)</small>"),
    ("solo file, no catalogo", "files only, no catalog"),
    ("Allocazione modelli AI su CPU/GPU con budget VRAM<small>(per modello, slider VRAM, rilevamento GPU automatico)</small>",
     "AI model allocation on CPU/GPU with VRAM budget<small>(per model, VRAM slider, automatic GPU detection)</small>"),
    ("granulare per modello", "granular per model"),
    ("selezione GPU, worker — no budget VRAM", "GPU selection, workers — no VRAM budget"),
    ("Selezione modelli AI individuali<small>(qualsiasi modello compatibile scaricato localmente, abilitabile da Config Tab)</small>",
     "Individual AI model selection<small>(any compatible model downloaded locally, enabled from the Config tab)</small>"),
    ("nessun vincolo", "no constraints"),
    ("CLIP e face recognition — no LLM", "CLIP and face recognition — no LLM"),
    ("modelli non selezionabili", "models not selectable"),
    ("Backend LLM configurabile<small>(Ollama o LMStudio, endpoint, modello, parametri avanzati, lingua output)</small>",
     "Configurable LLM backend<small>(Ollama or LMStudio, endpoint, model, advanced parameters, output language)</small>"),
    ("Soglie ricerca e similarità configurabili numericamente<small>(threshold SigLIP, soglia DINOv2, max risultati, fuzzy matching on/off)</small>",
     "Numerically configurable search and similarity thresholds<small>(SigLIP threshold, DINOv2 threshold, max results, fuzzy matching on/off)</small>"),
    ("solo soglia duplicati", "duplicate threshold only"),
    ("slider qualitativo", "qualitative slider"),
    ("Presente e verificato", "Present and verified"),
    ("Parziale o con limitazioni", "Partial or limited"),
    ("</span> Assente</span>", "</span> Absent</span>"),
    ("Non presente in nessun competitor", "Not present in any competitor"),
    ("Mylio: AI locale confermata, ma alcune funzioni di sync richiedono account Mylio.",
     "Mylio: local AI confirmed, but some sync features require a Mylio account."),
    ("Immich: scrittura XMP sidecar confermata, ma in librerie read-only non può scrivere.",
     "Immich: XMP sidecar writing confirmed, but it cannot write in read-only libraries."),
    ("<strong>Nota privacy plugin:</strong> le immagini non lasciano mai il dispositivo. Alcuni plugin possono effettuare richieste spot a databank pubblici (es. GBIF, GeoNames) per arricchire i metadati — mai per trasmettere foto.",
     "<strong>Plugin privacy note:</strong> images never leave the device. Some plugins may make one-off requests to public databanks (e.g. GBIF, GeoNames) to enrich metadata — never to transmit photos."),
    ("<strong>Fonti verificate:</strong>", "<strong>Verified sources:</strong>"),
    ("codice sorgente OffGallery", "OffGallery source code"),
]

# Parole italiane frequenti: servono solo a segnalare testo rimasto non tradotto
_SPIA_IT = re.compile(r"\b(della|degli|delle|nella|nelle|sono|che|il tuo|la tua|non|tutti|più|è|dei|dal|alla|alle)\b")


# ── Utilità ─────────────────────────────────────────────────────────────────
def leggi(p: Path) -> str:
    """Legge normalizzando i fine riga a \\n (le pagine nel repo sono CRLF)."""
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def scrivi(p: Path, testo: str, crlf: bool = True) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if crlf:
        testo = testo.replace("\n", "\r\n")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(testo)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def estrai_dizionario(html: str, lingua: str) -> dict:
    """Estrae le coppie chiave -> testo della lingua dal dizionario JS della pagina."""
    m = re.search(r"const (?:T|i18n) = \{", html)
    if not m:
        raise RuntimeError("dizionario di traduzioni non trovato")
    corpo = html[m.end():]
    chiusura = re.search(r"\n\s*\};", corpo)
    corpo = corpo[:chiusura.start()]
    inizi = {mm.group(1): mm.start() for mm in re.finditer(r"\n\s*(it|en):\s*\{", corpo)}
    ordine = sorted(inizi.items(), key=lambda kv: kv[1])
    for i, (lg, ini) in enumerate(ordine):
        if lg == lingua:
            fine = ordine[i + 1][1] if i + 1 < len(ordine) else len(corpo)
            blocco = corpo[ini:fine]
            break
    else:
        raise RuntimeError(f"lingua {lingua} assente nel dizionario")
    out = {}
    for k, v in re.findall(r'(\w+)\s*:\s*"((?:[^"\\]|\\.)*)"', blocco, flags=re.S):
        try:
            out[k] = json.loads('"' + v.replace("\\'", "'") + '"')
        except json.JSONDecodeError:
            out[k] = v.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    return out


class _Cercatore(HTMLParser):
    """Trova gli intervalli interni degli elementi con data-i18n."""
    VOID = {"br", "img", "meta", "link", "input", "hr", "source", "area", "base",
            "col", "embed", "param", "track", "wbr"}

    def __init__(self, testo: str):
        super().__init__(convert_charrefs=False)
        self.testo = testo
        self.righe = [0]
        for riga in testo.split("\n")[:-1]:
            self.righe.append(self.righe[-1] + len(riga) + 1)
        self.stack = []     # (tag, chiave|None, inizio_interno)
        self.intervalli = []  # (inizio, fine, chiave)

    def _pos(self):
        riga, col = self.getpos()
        return self.righe[riga - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        fine_tag = self._pos() + len(self.get_starttag_text())
        chiave = dict(attrs).get("data-i18n")
        self.stack.append((tag, chiave, fine_tag))

    def handle_startendtag(self, tag, attrs):
        return  # auto-chiuso: nessun contenuto interno

    def handle_endtag(self, tag):
        pos = self._pos()
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                _, chiave, ini = self.stack[i]
                del self.stack[i:]
                if chiave:
                    self.intervalli.append((ini, pos, chiave))
                return


def applica_dizionario(html: str, dizionario: dict) -> tuple[str, list]:
    """Sostituisce il contenuto degli elementi data-i18n con le stringhe date."""
    c = _Cercatore(html)
    c.feed(html)
    c.close()
    mancanti = []
    out, cur = [], 0
    for ini, fine, chiave in sorted(c.intervalli):
        if ini < cur:
            continue  # annidato in un intervallo già sostituito
        if chiave not in dizionario:
            mancanti.append(chiave)
            continue
        out.append(html[cur:ini])
        out.append(dizionario[chiave])
        cur = fine
    out.append(html[cur:])
    return "".join(out), mancanti


# ── Blocco <head> SEO ───────────────────────────────────────────────────────
def json_ld(lingua: str, pagina: str) -> str:
    """Dati strutturati della home (WebSite + SoftwareApplication)."""
    meta = PAGINE[pagina][lingua]
    url = SITE + PAGINE[pagina][f"{lingua}_path"]
    manuale = f"{SITE}/USER_MANUAL_{'IT' if lingua == 'it' else 'EN'}.html"
    grafo = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite", "@id": SITE + "/#website", "url": SITE + "/",
                "name": "OffGallery", "inLanguage": ["it", "en"],
            },
            {
                "@type": "SoftwareApplication", "@id": SITE + "/#app",
                "name": "OffGallery", "url": url, "description": meta["desc"],
                "applicationCategory": "MultimediaApplication",
                "operatingSystem": "Windows 10, Windows 11, macOS 12+, Linux",
                "isAccessibleForFree": True,
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
                "license": "https://www.gnu.org/licenses/agpl-3.0.html",
                "downloadUrl": GITHUB + "/releases/latest",
                "softwareHelp": {"@type": "WebPage", "url": manuale},
                "image": f"{SITE}/assets/og-{lingua}.png",
                "screenshot": [f"{SITE}/assets/Gallery.png", f"{SITE}/assets/Search.png"],
                "featureList": FEATURE_LIST[lingua],
                "inLanguage": lingua,
                "sameAs": [GITHUB],
                "isPartOf": {"@id": SITE + "/#website"},
            },
        ],
    }
    return ('<script type="application/ld+json">\n'
            + json.dumps(grafo, ensure_ascii=False, indent=2)
            + "\n  </script>")


def blocco_head(pagina: str, lingua: str) -> str:
    p = PAGINE[pagina]
    m = p[lingua]
    url = SITE + p[f"{lingua}_path"]
    it_url, en_url = SITE + p["it_path"], SITE + p["en_path"]
    og_desc = m.get("og_desc", m["desc"])
    img = f"{SITE}/assets/og-{lingua}.png"
    altro = "en_US" if lingua == "it" else "it_IT"
    righe = [
        f'<title>{esc(m["title"])}</title>',
        f'<meta name="description" content="{esc(m["desc"])}" />',
    ]
    if "keywords" in m:
        righe.append(f'<meta name="keywords" content="{esc(m["keywords"])}" />')
    righe += [
        '<meta property="og:site_name" content="OffGallery" />',
        f'<meta property="og:title" content="{esc(m["title"])}" />',
        f'<meta property="og:description" content="{esc(og_desc)}" />',
        '<meta property="og:type" content="website" />',
        f'<meta property="og:url" content="{url}" />',
        f'<meta property="og:locale" content="{"it_IT" if lingua == "it" else "en_US"}" />',
        f'<meta property="og:locale:alternate" content="{altro}" />',
        f'<meta property="og:image" content="{img}" />',
        '<meta property="og:image:width" content="1200" />',
        '<meta property="og:image:height" content="630" />',
        f'<meta property="og:image:alt" content="{esc(OG_ALT[lingua])}" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{esc(m["title"])}" />',
        f'<meta name="twitter:description" content="{esc(og_desc)}" />',
        f'<meta name="twitter:image" content="{img}" />',
        f'<link rel="canonical" href="{url}" />',
        f'<link rel="alternate" hreflang="it" href="{it_url}" />',
        f'<link rel="alternate" hreflang="en" href="{en_url}" />',
        f'<link rel="alternate" hreflang="x-default" href="{en_url}" />',
        '<link rel="icon" href="/favicon.ico" sizes="any" />',
        '<link rel="icon" type="image/png" sizes="192x192" href="/assets/favicon-192.png" />',
        '<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png" />',
    ]
    if pagina == "index.html":
        righe.append(json_ld(lingua, pagina))
    return "\n".join("  " + r if i else r for i, r in enumerate(righe)) + "\n"


def sostituisci_head(html: str, pagina: str, lingua: str) -> str:
    """Rimpiazza tutto ciò che sta fra <title> e il primo preconnect."""
    ini = html.index("<title>")
    fine = html.index('  <link rel="preconnect"')
    return html[:ini] + blocco_head(pagina, lingua) + html[fine:]


# ── Toggle lingua ───────────────────────────────────────────────────────────
TOGGLE_ORIGINALI = [
    # index.html
    ("document.getElementById('langToggle').addEventListener('click', () => {\n"
     "    lang = lang === 'it' ? 'en' : 'it';\n"
     "    applyLang(lang);\n"
     "  });"),
    # features.html
    ("document.getElementById('langToggle').addEventListener('click', () => "
     "{ lang = lang === 'it' ? 'en' : 'it'; applyLang(lang); });"),
    # credits.html
    ("document.getElementById('langToggle').addEventListener('click', () => {\n"
     "  const cur = localStorage.getItem('og_lang') || 'it';\n"
     "  applyLang(cur === 'it' ? 'en' : 'it');\n"
     "});\n\n"
     "applyLang(localStorage.getItem('og_lang') || 'it');"),
]


def toggle_js(destinazione: str) -> str:
    return ("// il cambio lingua porta alla pagina equivalente (URL reale, indicizzabile)\n"
            "document.getElementById('langToggle').addEventListener('click', () => "
            "{ window.location.href = " + destinazione + "; });")


def patch_toggle(html: str, destinazione: str, extra: str = "") -> str:
    nuovo = toggle_js(destinazione) + extra
    for orig in TOGGLE_ORIGINALI:
        if orig in html:
            html = html.replace(orig, nuovo)
            break
    else:
        # già patchato: aggiorna solo la destinazione
        html, n = re.subn(
            r"(?://[^\n]*\n)?document\.getElementById\('langToggle'\)\.addEventListener\('click', \(\) => "
            r"\{ window\.location\.href = [^;]+; \}\);(\napplyLang\('en'\);)?",
            lambda _m: nuovo, html)
        if n != 1:
            raise RuntimeError("toggle lingua non riconosciuto")
    # lo stato lingua non va più in localStorage (la lingua è l'URL)
    html = html.replace("  localStorage.setItem('og_lang', l);\n", "")
    return html


# ── Costruzione ─────────────────────────────────────────────────────────────
def costruisci_it(pagina: str) -> str:
    html = leggi(HTML / pagina)
    html = sostituisci_head(html, pagina, "it")
    html = patch_toggle(html, PAGINE[pagina]["it_toggle"])
    scrivi(HTML / pagina, html)
    return html


def sovrascritture_en(pagina: str, html_it: str) -> dict:
    """Testi EN che nel dizionario T hanno perso il markup presente nell'HTML italiano
    (link, <code>, <span>, icona): così la pagina inglese non perde nulla."""
    c = _Cercatore(html_it)
    c.feed(html_it)
    statico = {k: html_it[i:f] for i, f, k in c.intervalli}
    link = ('<a href="https://github.com/HEGOM61ita/OffGallery/releases/latest/download/{f}" '
            'style="color:#5b6ef5;font-weight:600">{f}</a>')
    ovr = {}
    if pagina == "index.html":
        ovr["f0_body"] = (link.format(f="OffGallerySetup.exe") + " (Windows) and "
                          + link.format(f="OffGallerySetup") + " (Linux) install everything automatically: "
                          "Miniconda, Python, libraries and AI models (~8 GB). No terminal. No manual setup.")
    if pagina == "features.html":
        ovr["pd_geo_2"] = ("Produced hierarchy: <code>GeOFF|Continent|Country|Region|City</code>. "
                           "The leaf node is automatically added as a tag. "
                           "Data is searchable and filterable from the Search Tab.")
        icona = re.match(r"<svg.*?</svg>", statico.get("cta_btn_other", ""), flags=re.S)
        if icona:
            dz = estrai_dizionario(html_it, "en")
            ovr["cta_btn_other"] = icona.group(0) + dz["cta_btn_other"]
    if pagina == "credits.html":
        ovr["page_title"] = 'Credits &amp; <span class="accent">Acknowledgements</span>'
    return ovr


def patch_dizionario_script(html: str, ovr: dict) -> str:
    """Allinea al dizionario inglese dello <script> i testi sovrascritti, altrimenti
    applyLang('en') al caricamento rimetterebbe la versione senza markup."""
    for chiave, valore in ovr.items():
        trovati = list(re.finditer(r'(\b' + re.escape(chiave) + r':\s*)"((?:[^"\\]|\\.)*)"', html))
        if not trovati:
            raise RuntimeError(f"chiave {chiave} non trovata nello script")
        m = trovati[-1]  # il blocco 'en' viene dopo quello 'it'
        html = html[:m.start()] + m.group(1) + json.dumps(valore, ensure_ascii=False) + html[m.end():]
    return html


def _segnala_italiano(pagina: str, html: str) -> None:
    """Avvisa se nel testo visibile della pagina inglese resta italiano."""
    corpo = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", html, flags=re.S)
    testo = re.sub(r"<[^>]+>", "\n", corpo)
    sospette = [" ".join(r.split()) for r in testo.split("\n") if _SPIA_IT.search(r.lower())]
    for r in sospette[:10]:
        print(f"  [{pagina}] possibile testo italiano: {r[:100]}")


def costruisci_en(pagina: str, html_it: str) -> list:
    dz_en = estrai_dizionario(html_it, "en")
    ovr = sovrascritture_en(pagina, html_it)
    dz_en.update(ovr)
    html, mancanti = applica_dizionario(html_it, dz_en)
    html = patch_dizionario_script(html, ovr)
    html = sostituisci_head(html, pagina, "en")
    html = html.replace('<html lang="it">', '<html lang="en">', 1)
    # percorsi: la pagina sta in /en/
    html = html.replace('src="assets/', 'src="../assets/')
    html = html.replace('href="USER_MANUAL_IT.html"', 'href="../USER_MANUAL_EN.html"')
    html = html.replace("'USER_MANUAL_IT.html'", "'../USER_MANUAL_IT.html'")
    html = html.replace("'USER_MANUAL_EN.html'", "'../USER_MANUAL_EN.html'")
    for it, en in ATTR_EN.items():
        html = html.replace(it, en)
    orfane = []
    for it, en in EXTRA_EN:
        if it not in html:
            orfane.append(it[:60])
        html = html.replace(it, en)
    if orfane and pagina == "index.html":
        print(f"  ATTENZIONE: {len(orfane)} traduzioni EXTRA_EN non più applicabili: {orfane}")
    # script: la pagina nasce già inglese; il toggle porta all'equivalente italiano
    html = html.replace("let lang = 'it';", "let lang = 'en';", 1)
    html = patch_toggle(html, PAGINE[pagina]["en_toggle"], extra="\napplyLang('en');")
    scrivi(HTML / "en" / pagina, html)
    _segnala_italiano(pagina, html)
    return mancanti


def costruisci_sitemap(lastmod: str) -> None:
    righe = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
             '        xmlns:xhtml="http://www.w3.org/1999/xhtml">', ""]

    def voce(url, lm, freq, prio, alt):
        r = ["  <url>", f"    <loc>{url}</loc>", f"    <lastmod>{lm}</lastmod>",
             f"    <changefreq>{freq}</changefreq>", f"    <priority>{prio}</priority>"]
        r += [f'    <xhtml:link rel="alternate" hreflang="{h}" href="{u}"/>' for h, u in alt]
        r += ["  </url>", ""]
        return r

    for nome, p in PAGINE.items():
        it_url, en_url = SITE + p["it_path"], SITE + p["en_path"]
        alt = [("it", it_url), ("en", en_url), ("x-default", en_url)]
        righe += voce(it_url, lastmod, p["changefreq"], p["priority"], alt)
        righe += voce(en_url, lastmod, p["changefreq"], p["priority"], alt)
    man_it, man_en = f"{SITE}/USER_MANUAL_IT.html", f"{SITE}/USER_MANUAL_EN.html"
    alt = [("it", man_it), ("en", man_en), ("x-default", man_en)]
    righe += voce(man_it, LASTMOD_MANUALI, "monthly", "0.5", alt)
    righe += voce(man_en, LASTMOD_MANUALI, "monthly", "0.5", alt)
    righe.append("</urlset>")
    scrivi(HTML / "sitemap.xml", "\n".join(righe) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lastmod", default=date.today().isoformat())
    args = ap.parse_args()
    esito = 0
    for pagina in PAGINE:
        html_it = costruisci_it(pagina)
        mancanti = costruisci_en(pagina, html_it)
        print(f"{pagina}: ok" + (f" (chiavi senza traduzione EN: {sorted(set(mancanti))})" if mancanti else ""))
        esito |= bool(mancanti)
    costruisci_sitemap(args.lastmod)
    print("sitemap.xml: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
