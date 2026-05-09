"""
Gestione dello stato persistente dell'installazione.
Legge e scrive installer_state.json nella cartella di installazione.
Nessuna dipendenza esterna — solo stdlib.
"""

import json
import os
import time
from copy import deepcopy
from typing import Any, Optional


# Stato iniziale di un'installazione pulita
_DEFAULT_STATE = {
    "version": "1.0",
    "install_path": "",
    "profile": "",                # "leggero" | "completo" | "personalizzato"
    "created_at": "",
    "updated_at": "",
    "miniconda": {
        "status": "pending",      # pending | in_progress | done | error | skipped
        "path": "",
        "conda_version": "",
        "error": "",
    },
    "conda_env": {
        "status": "pending",
        "python_version": "",
        "error": "",
    },
    "core": {
        "status": "pending",
        "version": "",
        "error": "",
    },
    "packages": {
        "status": "pending",
        "torch_variant": "",      # "cuda118" | "cuda121" | "cpu"
        "error": "",
    },
    "models": {
        "clip":      {"status": "pending", "size_mb": 580,  "error": ""},
        "dinov2":    {"status": "pending", "size_mb": 330,  "error": ""},
        "aesthetic": {"status": "pending", "size_mb": 1600, "error": ""},
        "bioclip":   {"status": "pending", "size_mb": 4200, "error": ""},
        "argos":     {"status": "pending", "size_mb": 92,   "error": ""},
    },
    "ollama": {
        "status": "pending",      # pending | done | skipped | error
        "version": "",
        "model_pulled": False,
        "error": "",
    },
    "lmstudio": {
        "status": "pending",
        "version": "",
        "error": "",
    },
    "shortcut": {
        "status": "pending",
        "error": "",
    },
}

# Valori di stato validi
VALID_STATUSES = {"pending", "in_progress", "done", "error", "skipped", "not_installed"}


class StateManager:
    """
    Interfaccia per leggere e scrivere installer_state.json.

    Uso tipico:
        sm = StateManager("/path/to/OffGallery")
        sm.load_or_create()

        if sm.is_done("miniconda"):
            ...
        sm.set_status("miniconda", "done", conda_version="24.1")
        sm.set_model_status("clip", "done")
    """

    def __init__(self, install_path: str):
        self.install_path = install_path
        self._path = os.path.join(install_path, "installer_state.json")
        self._state: dict = {}

    # ------------------------------------------------------------------
    # Caricamento e salvataggio
    # ------------------------------------------------------------------

    def load_or_create(self) -> bool:
        """
        Carica lo stato da file se esiste, altrimenti crea uno stato nuovo.
        Restituisce True se ha caricato un file esistente (installazione parziale).
        """
        if os.path.isfile(self._path):
            try:
                with open(self._path, encoding="utf-8") as f:
                    loaded = json.load(f)
                self._state = _merge_with_defaults(loaded, deepcopy(_DEFAULT_STATE))
                return True
            except (json.JSONDecodeError, OSError):
                # File corrotto — ricomincia da zero ma tieni un backup
                _backup_corrupted(self._path)

        self._state = deepcopy(_DEFAULT_STATE)
        self._state["install_path"] = self.install_path
        self._state["created_at"] = _now()
        self._save()
        return False

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True) if os.path.dirname(self._path) else None
        self._state["updated_at"] = _now()
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)   # scrittura atomica

    # ------------------------------------------------------------------
    # Lettura
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """
        Legge un valore con chiave dot-notation.
        Esempi: get("miniconda.status"), get("models.clip.size_mb")
        """
        return _dot_get(self._state, key, default)

    def status(self, component: str) -> str:
        """Restituisce lo status di un componente (es. 'miniconda', 'conda_env')."""
        return self.get(f"{component}.status", "pending")

    def model_status(self, model: str) -> str:
        """Restituisce lo status di un modello (es. 'clip', 'dinov2')."""
        return self.get(f"models.{model}.status", "pending")

    def is_done(self, component: str) -> bool:
        return self.status(component) == "done"

    def is_model_done(self, model: str) -> bool:
        return self.model_status(model) == "done"

    def is_skipped(self, component: str) -> bool:
        return self.status(component) == "skipped"

    def needs_install(self, component: str) -> bool:
        """True se il componente deve ancora essere installato."""
        return self.status(component) in ("pending", "in_progress", "error")

    def all_models_done(self) -> bool:
        return all(
            self.is_model_done(m)
            for m in self._state.get("models", {})
        )

    def has_partial_install(self) -> bool:
        """True se almeno un componente è già done (installazione ripresa)."""
        components = ["miniconda", "conda_env", "core", "packages", "shortcut"]
        models     = list(self._state.get("models", {}).keys())
        return any(self.is_done(c) for c in components + models)

    @property
    def profile(self) -> str:
        return self._state.get("profile", "")

    @property
    def install_path_saved(self) -> str:
        return self._state.get("install_path", "")

    # ------------------------------------------------------------------
    # Scrittura
    # ------------------------------------------------------------------

    def set_profile(self, profile: str):
        self._state["profile"] = profile
        self._save()

    def set_install_path(self, path: str):
        self._state["install_path"] = path
        self.install_path = path
        self._path = os.path.join(path, "installer_state.json")
        self._save()

    def set_status(self, component: str, status: str, **extra_fields):
        """
        Aggiorna lo status di un componente e opzionalmente altri campi.

        Esempio:
            sm.set_status("miniconda", "done", conda_version="24.1", path="C:/miniconda3")
            sm.set_status("packages", "error", error="pip timeout dopo 120s")
        """
        _assert_valid_status(status)
        if component not in self._state:
            self._state[component] = {}
        self._state[component]["status"] = status
        for k, v in extra_fields.items():
            self._state[component][k] = v
        self._save()

    def set_model_status(self, model: str, status: str, **extra_fields):
        """
        Aggiorna lo status di un singolo modello.

        Esempio:
            sm.set_model_status("clip", "done")
            sm.set_model_status("bioclip", "error", error="hash mismatch")
        """
        _assert_valid_status(status)
        if "models" not in self._state:
            self._state["models"] = {}
        if model not in self._state["models"]:
            self._state["models"][model] = {}
        self._state["models"][model]["status"] = status
        for k, v in extra_fields.items():
            self._state["models"][model][k] = v
        self._save()

    def mark_in_progress(self, component: str):
        self.set_status(component, "in_progress")

    def mark_done(self, component: str, **extra_fields):
        self.set_status(component, "done", error="", **extra_fields)

    def mark_error(self, component: str, error: str):
        self.set_status(component, "error", error=error)

    def mark_skipped(self, component: str):
        self.set_status(component, "skipped", error="")

    def reset_component(self, component: str):
        """Riporta un componente a 'pending' per forzare la reinstallazione."""
        self.set_status(component, "pending", error="")

    def reset_model(self, model: str):
        self.set_model_status(model, "pending", error="")

    # ------------------------------------------------------------------
    # Dump leggibile (per il log)
    # ------------------------------------------------------------------

    def summary(self) -> str:
        lines = [f"Profilo: {self.profile}", f"Cartella: {self.install_path}"]
        components = ["miniconda", "conda_env", "core", "packages"]
        for c in components:
            lines.append(f"  {c}: {self.status(c)}")
        lines.append("  modelli:")
        for m, data in self._state.get("models", {}).items():
            lines.append(f"    {m}: {data.get('status', '?')}")
        for c in ["ollama", "lmstudio", "shortcut"]:
            lines.append(f"  {c}: {self.status(c)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _dot_get(d: dict, key: str, default: Any = None) -> Any:
    """Naviga un dizionario con notazione dot (es. 'models.clip.status')."""
    parts = key.split(".")
    cur = d
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _merge_with_defaults(loaded: dict, defaults: dict) -> dict:
    """
    Unisce lo stato caricato con i default, aggiungendo chiavi mancanti
    senza sovrascrivere quelle già presenti nel file.
    """
    for key, val in defaults.items():
        if key not in loaded:
            loaded[key] = val
        elif isinstance(val, dict) and isinstance(loaded.get(key), dict):
            loaded[key] = _merge_with_defaults(loaded[key], val)
    return loaded


def _assert_valid_status(status: str):
    if status not in VALID_STATUSES:
        raise ValueError(f"Status non valido: '{status}'. Validi: {VALID_STATUSES}")


def _backup_corrupted(path: str):
    backup = path + f".corrupted_{int(time.time())}"
    try:
        os.rename(path, backup)
    except OSError:
        pass


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
