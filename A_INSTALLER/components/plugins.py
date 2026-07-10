"""
Download e installazione dei plugin OffGallery.

I plugin sono distribuiti come zip (uno per plugin) tra gli asset di una
GitHub Release del repo pubblico. Ogni zip contiene SOLO il codice del plugin
(nessun dato pesante): i dati (mappe .tif, database .db, cache) vengono
scaricati a runtime dal plugin stesso tramite download_and_build_database().

Struttura zip attesa: <plugin_id>/... (la cartella del plugin come radice).
Estrazione in <app_dir>/plugins/<plugin_id>/.
"""

import os
import shutil
import zipfile
import tempfile
from dataclasses import dataclass
from typing import Optional, Callable

from utils.download import download_file, DownloadProgress, DownloadError


# ---------------------------------------------------------------------------
# Sorgente release
# ---------------------------------------------------------------------------

# Release del repo pubblico che ospita gli zip dei plugin.
# Aggiornare il tag qui se si pubblica una nuova release di plugin.
GH_REPO    = "HEGOM61ita/OffGallery"
GH_TAG     = "plugins-latest"
GH_BASE    = f"https://github.com/{GH_REPO}/releases/download/{GH_TAG}"

# Sottocartella locale dove vivono i plugin
PLUGINS_SUBDIR = "plugins"


# ---------------------------------------------------------------------------
# Manifest dei plugin
# ---------------------------------------------------------------------------

@dataclass
class PluginSpec:
    """Specifica di un plugin scaricabile."""
    key:         str           # id del plugin (== nome cartella in plugins/)
    label:       str           # nome leggibile per la UI
    icon:        str           # emoji per la UI
    description: str           # descrizione breve
    size_mb:     int           # dimensione approssimativa dello zip (per stima)
    sha256:      Optional[str] = None  # hash atteso dello zip (None = skip verifica)


# Manifest principale — allineato agli asset della release GH_TAG.
# I size_mb sono stime del solo codice (gli zip NON contengono dati).
PLUGINS: list[PluginSpec] = [
    PluginSpec(
        key="bionomen", label="BioNomen", icon="🔤",
        description="Nomi comuni biologici (GBIF, iNaturalist, Wikidata).",
        size_mb=1,
    ),
    PluginSpec(
        key="geonames", label="GeoNames", icon="📍",
        description="Geolocalizzazione precisa: coordinate GPS e gerarchia luoghi.",
        size_mb=1,
    ),
    PluginSpec(
        key="geospecies", label="GeoSpecies", icon="🌍",
        description="Affina BioCLIP con le specie attese nell'area geografica.",
        size_mb=1,
    ),
    PluginSpec(
        key="naturarea", label="NaturArea", icon="🏞",
        description="Area protetta (WDPA) e habitat (ESA WorldCover) da GPS.",
        size_mb=1,
    ),
    PluginSpec(
        key="weather_context", label="Meteo", icon="🌤",
        description="Contesto meteo storico delle foto (Open-Meteo).",
        size_mb=1,
    ),
    PluginSpec(
        key="llm_ollama", label="Ollama LLM Vision", icon="🧠",
        description="Backend LLM Vision via Ollama (qwen3-vl, LLaVA, Gemma3).",
        size_mb=1,
    ),
    PluginSpec(
        key="llm_lmstudio", label="LM Studio LLM Server", icon="🧩",
        description="Backend LLM Vision via LM Studio.",
        size_mb=1,
    ),
    PluginSpec(
        key="prompt_context", label="Contesto Prompt", icon="📋",
        description="Inietta un blocco CONTEXT personalizzato nel prompt vision.",
        size_mb=1,
    ),
]


# ---------------------------------------------------------------------------
# Callback di progresso
# ---------------------------------------------------------------------------

@dataclass
class PluginProgress:
    """Stato di avanzamento passato alla UI durante il download dei plugin."""
    plugin_key:    str
    plugin_label:  str
    plugin_index:  int          # plugin corrente (0-based)
    plugin_count:  int          # totale plugin da scaricare
    bytes_done:    int
    bytes_total:   int
    speed_bps:     float
    eta_sec:       float


PluginProgressCallback = Callable[[PluginProgress], None]


# ---------------------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------------------

def download_plugins(
    app_dir:     str,
    keys:        Optional[list[str]] = None,
    progress_cb: Optional[PluginProgressCallback] = None,
    log_cb:      Optional[Callable] = None,
    force:       bool = False,
) -> dict[str, bool]:
    """
    Scarica ed estrae i plugin specificati in `keys` (default: tutti).
    Salta i plugin già installati, a meno che `force=True`.

    Restituisce un dict {key: success} per ogni plugin.
    """
    specs = _filter_plugins(keys)
    plugins_root = os.path.join(app_dir, PLUGINS_SUBDIR)
    os.makedirs(plugins_root, exist_ok=True)
    results: dict[str, bool] = {}

    for idx, spec in enumerate(specs):
        dest_dir = os.path.join(plugins_root, spec.key)

        # Se già presente e non forzato, skip
        if not force and _plugin_complete(dest_dir):
            _log(log_cb, f"[{spec.label}] già presente, skip.")
            results[spec.key] = True
            continue

        _log(log_cb, f"[{spec.label}] Download...")

        # Scarica lo zip in una directory temporanea
        tmp_dir = tempfile.mkdtemp(prefix=f"offgallery_plugin_{spec.key}_")
        zip_path = os.path.join(tmp_dir, f"{spec.key}.zip")
        url = f"{GH_BASE}/{spec.key}.zip"

        def _cb(p: DownloadProgress, i=idx, spec=spec):
            if progress_cb:
                progress_cb(PluginProgress(
                    plugin_key=spec.key,
                    plugin_label=spec.label,
                    plugin_index=i,
                    plugin_count=len(specs),
                    bytes_done=p.bytes_done,
                    bytes_total=p.bytes_total,
                    speed_bps=p.speed_bps,
                    eta_sec=p.eta_sec,
                ))

        try:
            download_file(
                url=url,
                dest_path=zip_path,
                expected_sha256=spec.sha256,
                progress_cb=_cb,
            )
            _extract_plugin(zip_path, plugins_root, spec.key, force=force)
            _log(log_cb, f"[{spec.label}] installato.")
            results[spec.key] = True
        except DownloadError as exc:
            _log(log_cb, f"[{spec.label}] download fallito: {exc}")
            results[spec.key] = False
        except (zipfile.BadZipFile, OSError) as exc:
            _log(log_cb, f"[{spec.label}] estrazione fallita: {exc}")
            results[spec.key] = False
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return results


def plugin_exists(app_dir: str, key: str) -> bool:
    """True se il plugin `key` è installato (cartella con manifest.json)."""
    dest_dir = os.path.join(app_dir, PLUGINS_SUBDIR, key)
    return _plugin_complete(dest_dir)


def all_plugins_exist(app_dir: str, keys: Optional[list[str]] = None) -> bool:
    """True se tutti i plugin richiesti sono già installati."""
    specs = _filter_plugins(keys)
    return all(plugin_exists(app_dir, s.key) for s in specs)


def total_download_mb(keys: Optional[list[str]] = None) -> int:
    """Stima la dimensione totale in MB dei plugin da scaricare."""
    return sum(s.size_mb for s in _filter_plugins(keys))


def plugin_keys() -> list[str]:
    """Restituisce le chiavi di tutti i plugin nel manifest."""
    return [p.key for p in PLUGINS]


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _filter_plugins(keys: Optional[list[str]]) -> list[PluginSpec]:
    if keys is None:
        return PLUGINS
    key_set = set(keys)
    found = [p for p in PLUGINS if p.key in key_set]
    missing = key_set - {p.key for p in found}
    if missing:
        raise ValueError(f"Plugin sconosciuti: {missing}. Disponibili: {plugin_keys()}")
    return found


def _spec_by_key(key: str) -> Optional[PluginSpec]:
    return next((p for p in PLUGINS if p.key == key), None)


def _plugin_complete(dest_dir: str) -> bool:
    """True se la cartella del plugin esiste e contiene il manifest."""
    return os.path.isfile(os.path.join(dest_dir, "manifest.json"))


def _extract_plugin(zip_path: str, plugins_root: str, key: str, force: bool):
    """
    Estrae lo zip del plugin in plugins_root/<key>/.

    Lo zip può avere il plugin alla radice (file/... direttamente) oppure
    dentro una cartella <key>/. Gestiamo entrambi normalizzando su
    plugins_root/<key>/. Se force=True, la cartella esistente viene rimossa
    prima dell'estrazione (i dati runtime sono in sottocartelle escluse dallo
    zip, quindi vengono comunque preservati solo se non sovrascritti — per
    sicurezza il reinstall NON tocca data/ e cache/).
    """
    dest_dir = os.path.join(plugins_root, key)

    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if not names:
            raise zipfile.BadZipFile("archivio vuoto")

        # Rileva se tutti i file sono sotto una cartella radice "<key>/"
        prefix = f"{key}/"
        has_prefix = all(n.startswith(prefix) for n in names)

        # In reinstall (force) rimuovi solo il codice, preserva data/ e cache/
        if force and os.path.isdir(dest_dir):
            for entry in os.listdir(dest_dir):
                if entry in ("data", "cache"):
                    continue
                path = os.path.join(dest_dir, entry)
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

        os.makedirs(dest_dir, exist_ok=True)

        for name in names:
            rel = name[len(prefix):] if has_prefix else name
            if not rel:
                continue
            target = os.path.join(dest_dir, rel)
            # Protezione path traversal
            if not os.path.abspath(target).startswith(os.path.abspath(dest_dir)):
                raise zipfile.BadZipFile(f"percorso non sicuro nello zip: {name}")
            os.makedirs(os.path.dirname(target) or dest_dir, exist_ok=True)
            with zf.open(name) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _log(cb: Optional[Callable], msg: str):
    if cb:
        cb(msg)
