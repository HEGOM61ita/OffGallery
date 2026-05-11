"""
Lettura e scrittura di config_new.yaml senza dipendenze esterne.
Usato dall'installer per leggere/aggiornare la scelta del backend LLM.
"""

import os
import re
from typing import Optional

_BACKENDS = {
    "ollama":   {"endpoint": "http://localhost:11434"},
    "lmstudio": {"endpoint": "http://localhost:1234"},
}


def _config_path(install_path: str) -> str:
    return os.path.join(install_path, "config_new.yaml")


def config_exists(install_path: str) -> bool:
    return os.path.isfile(_config_path(install_path))


def read_llm_backend(install_path: str) -> str:
    """Restituisce 'ollama' o 'lmstudio'. Default 'ollama' se non trovato."""
    path = _config_path(install_path)
    if not os.path.isfile(path):
        return "ollama"
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*backend:\s*(\S+)", line)
                if m:
                    val = m.group(1).strip()
                    return val if val in _BACKENDS else "ollama"
    except Exception:
        pass
    return "ollama"


def write_llm_backend(install_path: str, backend: str) -> bool:
    """
    Aggiorna backend: e endpoint: in config_new.yaml.
    Restituisce True se il file è stato modificato.
    """
    if backend not in _BACKENDS:
        return False
    path = _config_path(install_path)
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()

        new_content = re.sub(
            r"(\s*backend:\s*)\S+",
            lambda m: m.group(1) + backend,
            content, count=1,
        )
        new_content = re.sub(
            r"(\s*endpoint:\s*)http://localhost:\d+",
            lambda m: m.group(1) + _BACKENDS[backend]["endpoint"],
            new_content, count=1,
        )

        if new_content == content:
            return False

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except Exception:
        return False
