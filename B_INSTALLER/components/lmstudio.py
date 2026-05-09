"""
Installazione e rilevamento di LM Studio.
Supporta Windows, macOS (arm64 e x86_64) e Linux.

Differenza chiave rispetto a Ollama:
- LM Studio non ha CLI per scaricare modelli.
- Il download dei modelli e l'avvio del server locale avvengono
  dall'interfaccia grafica di LM Studio, non da questo installer.
- Questo modulo installa LM Studio e verifica che l'API risponda,
  ma il modello va caricato manualmente dall'utente la prima volta.
"""

import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
from typing import Optional, Callable

from utils.download import download_file, ProgressCallback

_CNW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

LM_PORT  = 1234
LM_API   = f"http://localhost:{LM_PORT}"
LM_DOWNLOAD_PAGE = "https://lmstudio.ai/download"

# URL di download per piattaforma/architettura.
# Usano il redirect ufficiale lmstudio.ai/download/latest/... che punta
# sempre alla release corrente — stabili anche quando cambia la versione.
# macOS Intel non è più supportato da LM Studio (solo Apple Silicon).
_DOWNLOAD_URLS = {
    ("Windows", "AMD64"):   "https://lmstudio.ai/download/latest/win32/x64",
    ("Windows", "x86_64"):  "https://lmstudio.ai/download/latest/win32/x64",
    ("Windows", "ARM64"):   "https://lmstudio.ai/download/latest/win32/arm64",
    ("Darwin",  "arm64"):   "https://lmstudio.ai/download/latest/darwin/arm64",
    ("Linux",   "x86_64"):  "https://lmstudio.ai/download/latest/linux/x64",
}

MANUAL_INSTALL_MESSAGE = f"""\
⚠  Il download automatico di LM Studio non è disponibile.
   LM Studio aggiorna frequentemente i propri URL di distribuzione.

   Per installarlo manualmente:
   1. Apri il browser e vai su: {LM_DOWNLOAD_PAGE}
   2. Scarica la versione per il tuo sistema operativo
   3. Esegui l'installer scaricato
   4. Riapri OffGallery Manager — rileverà LM Studio automaticamente
"""

# Percorsi standard dell'eseguibile lmstudio
_LM_PATHS = {
    "Windows": [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs",
                     "LM Studio", "LM Studio.exe"),
        r"C:\Program Files\LM Studio\LM Studio.exe",
    ],
    "Darwin": [
        "/Applications/LM Studio.app/Contents/MacOS/LM Studio",
        os.path.join(os.path.expanduser("~"), "Applications",
                     "LM Studio.app", "Contents", "MacOS", "LM Studio"),
    ],
    "Linux": [
        os.path.join(os.path.expanduser("~"), ".local", "bin", "lmstudio"),
        os.path.join(os.path.expanduser("~"), "Applications", "LM-Studio.AppImage"),
        "/usr/local/bin/lmstudio",
    ],
}

# Messaggio da mostrare all'utente dopo l'installazione
POST_INSTALL_INSTRUCTIONS = """\
LM Studio è stato installato.

Per collegarlo a OffGallery:
1. Apri LM Studio
2. Vai nella sezione "Discover" e scarica un modello vision compatibile
   (es. LLaVA, Qwen2-VL, oppure lo stesso qwen3-vl)
3. Nella barra laterale sinistra clicca l'icona "<->" (Local Server)
4. Seleziona il modello scaricato e clicca "Start Server"
5. Riavvia OffGallery — il plugin LM Studio si connetterà automaticamente

Il server LM Studio gira su localhost:1234.
"""


# ---------------------------------------------------------------------------
# Rilevamento
# ---------------------------------------------------------------------------

def find_lmstudio() -> Optional[str]:
    """
    Cerca l'eseguibile LM Studio nel sistema.
    Restituisce il percorso o None se non trovato.
    """
    system = platform.system()
    for path in _LM_PATHS.get(system, []):
        if path and os.path.isfile(path):
            return path
    return None


def is_installed() -> bool:
    return find_lmstudio() is not None


def is_running() -> bool:
    """True se il server locale LM Studio risponde sull'API."""
    try:
        with urllib.request.urlopen(
            f"{LM_API}/v1/models", timeout=3
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def api_models() -> list[str]:
    """
    Restituisce la lista dei modelli caricati nel server LM Studio.
    Lista vuota se il server non risponde o nessun modello è caricato.
    """
    try:
        with urllib.request.urlopen(f"{LM_API}/v1/models", timeout=5) as resp:
            import json
            data = json.loads(resp.read())
            return [m.get("id", "") for m in data.get("data", [])]
    except Exception:
        return []


def port_in_use(port: int = LM_PORT) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


# ---------------------------------------------------------------------------
# Installazione
# ---------------------------------------------------------------------------

def _resolve_url(url: str, log_cb: Optional[Callable]) -> Optional[str]:
    """
    Verifica che l'URL sia raggiungibile seguendo i redirect.
    Restituisce l'URL finale (dopo redirect) se raggiungibile, None altrimenti.
    Usa una GET leggendo solo 1 byte — urllib non segue redirect con HEAD.
    """
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "OffGalleryInstaller/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read(1)   # legge 1 byte per forzare la connessione
            final_url = resp.geturl()
            if resp.status == 200:
                return final_url
    except urllib.error.HTTPError as e:
        _log(log_cb, f"URL non raggiungibile (HTTP {e.code}): {url}")
    except Exception as e:
        _log(log_cb, f"Errore verifica URL: {e}")
    return None


def install_lmstudio(
    progress_cb: Optional[ProgressCallback] = None,
    log_cb:      Optional[Callable]         = None,
) -> str:
    """
    Scarica e installa LM Studio per la piattaforma corrente.
    Restituisce il percorso dell'eseguibile.
    Solleva RuntimeError con istruzioni manuali se l'URL non è raggiungibile.
    """
    system  = platform.system()
    machine = platform.machine()
    key     = (system, machine)

    if key not in _DOWNLOAD_URLS:
        raise RuntimeError(
            f"Piattaforma non supportata per LM Studio: {system} {machine}.\n"
            + MANUAL_INSTALL_MESSAGE
        )

    candidate = _DOWNLOAD_URLS[key]
    _log(log_cb, f"Verifica URL LM Studio...")
    url = _resolve_url(candidate, log_cb)

    if url is None:
        raise RuntimeError(MANUAL_INSTALL_MESSAGE)

    filename = url.split("/")[-1]
    _log(log_cb, f"Download LM Studio da: {url}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        dest = os.path.join(tmp_dir, filename)
        download_file(url=url, dest_path=dest, progress_cb=progress_cb)

        if system == "Windows":
            _install_windows(dest, log_cb)
        elif system == "Darwin":
            _install_macos(dest, log_cb)
        elif system == "Linux":
            _install_linux(dest, log_cb)

    exe = find_lmstudio()
    if not exe:
        raise RuntimeError(
            "Installazione LM Studio completata ma eseguibile non trovato. "
            "Potrebbe essere necessario riavviare il sistema."
        )

    _log(log_cb, f"LM Studio installato: {exe}")
    _log(log_cb, POST_INSTALL_INSTRUCTIONS)
    return exe


def _install_windows(installer_path: str, log_cb: Optional[Callable]):
    _log(log_cb, "Installazione LM Studio (Windows)...")
    try:
        proc = subprocess.run(
            [installer_path, "/VERYSILENT", "/NORESTART", "/NOCANCEL"],
            timeout=300, capture_output=True, text=True,
            creationflags=_CNW,
        )
        # Alcuni installer usano codici diversi — 0 e 3010 (riavvio) sono ok
        if proc.returncode not in (0, 3010):
            raise RuntimeError(
                f"Installer LM Studio terminato con codice {proc.returncode}.\n"
                f"{proc.stderr}"
            )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Timeout durante l'installazione di LM Studio.")


def _install_macos(dmg_path: str, log_cb: Optional[Callable]):
    """Monta il .dmg e copia l'app in ~/Applications."""
    import re

    _log(log_cb, "Installazione LM Studio (macOS)...")

    # Monta il DMG
    out = subprocess.check_output(
        ["hdiutil", "attach", dmg_path, "-nobrowse", "-quiet"],
        text=True
    )
    # Trova il mount point (es. /Volumes/LM Studio)
    mount_match = re.search(r"(/Volumes/[^\n]+)", out)
    if not mount_match:
        raise RuntimeError("Impossibile montare il DMG di LM Studio.")
    mount_point = mount_match.group(1).strip()

    try:
        apps_dir = os.path.join(os.path.expanduser("~"), "Applications")
        os.makedirs(apps_dir, exist_ok=True)

        # Trova il .app nel volume
        app_src = None
        for entry in os.listdir(mount_point):
            if entry.endswith(".app"):
                app_src = os.path.join(mount_point, entry)
                break

        if not app_src:
            raise RuntimeError("App non trovata nel DMG di LM Studio.")

        app_dst = os.path.join(apps_dir, os.path.basename(app_src))
        if os.path.exists(app_dst):
            shutil.rmtree(app_dst)

        _log(log_cb, f"Copia {os.path.basename(app_src)} in {apps_dir}...")
        shutil.copytree(app_src, app_dst)

        # Rimuovi quarantine
        subprocess.run(["xattr", "-cr", app_dst], capture_output=True)

    finally:
        subprocess.run(["hdiutil", "detach", mount_point, "-quiet"],
                       capture_output=True)


def _install_linux(appimage_path: str, log_cb: Optional[Callable]):
    """Installa LM Studio come AppImage in ~/.local/bin/."""
    _log(log_cb, "Installazione LM Studio (Linux, AppImage)...")

    bin_dir  = os.path.join(os.path.expanduser("~"), ".local", "bin")
    os.makedirs(bin_dir, exist_ok=True)
    dest     = os.path.join(bin_dir, "lmstudio")

    shutil.copy2(appimage_path, dest)
    os.chmod(dest, 0o755)
    _log(log_cb, f"LM Studio installato in: {dest}")

    # Crea voce nel menu applicazioni
    _create_linux_desktop_entry(dest)


def _create_linux_desktop_entry(exe_path: str):
    desktop_dir = os.path.join(
        os.path.expanduser("~"), ".local", "share", "applications"
    )
    os.makedirs(desktop_dir, exist_ok=True)
    entry_path = os.path.join(desktop_dir, "lmstudio.desktop")
    content = f"""\
[Desktop Entry]
Name=LM Studio
Comment=Run local LLM models
Exec={exe_path} %U
Terminal=false
Type=Application
Categories=Science;AI;
"""
    with open(entry_path, "w") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Punto di ingresso principale
# ---------------------------------------------------------------------------

def ensure_lmstudio(
    install_if_missing: bool = True,
    force_reinstall:    bool = False,
    progress_cb:        Optional[ProgressCallback] = None,
    log_cb:             Optional[Callable]          = None,
) -> dict:
    """
    Verifica che LM Studio sia installato.

    Restituisce un dict con:
        installed:    bool
        running:      bool   (server locale attivo)
        models:       list   (modelli caricati nel server, [] se non attivo)
        exe_path:     str | None
        instructions: str    (istruzioni post-installazione per l'utente)
    """
    result = {
        "installed":    False,
        "running":      False,
        "models":       [],
        "exe_path":     None,
        "instructions": POST_INSTALL_INSTRUCTIONS,
    }

    exe = find_lmstudio()

    if not exe or force_reinstall:
        if not exe and not install_if_missing:
            _log(log_cb, "LM Studio non trovato e installazione non richiesta.")
            return result
        exe = install_lmstudio(progress_cb=progress_cb, log_cb=log_cb)

    result["installed"] = True
    result["exe_path"]  = exe

    if is_running():
        result["running"] = True
        result["models"]  = api_models()
        _log(log_cb, f"LM Studio server attivo. Modelli: {result['models'] or 'nessuno caricato'}")
    else:
        _log(log_cb,
             "LM Studio installato ma il server locale non è attivo. "
             "Aprilo e avvia il server dalla sezione 'Local Server'.")

    return result


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _log(cb: Optional[Callable], msg: str):
    if cb:
        cb(msg)
