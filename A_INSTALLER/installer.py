"""
Entry point del manager OffGallery.
Unica finestra tk.Tk() — decide se mostrare wizard o dashboard.
"""

import os
import sys
import logging
import platform

# Fix Tcl/Tk e SSL quando eseguito come bundle PyInstaller
if getattr(sys, "frozen", False):
    _base = sys._MEIPASS
    os.environ["TCL_LIBRARY"] = os.path.join(_base, "tcl8.6")
    os.environ["TK_LIBRARY"]  = os.path.join(_base, "tk8.6")
    # SSL: i certificati CA non sono disponibili nel bundle PyInstaller.
    # Disabilitiamo la verifica — le URL sono hardcoded e da fonti fidate.
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context

import tkinter as tk
from tkinter import ttk
from typing import Optional

from state.state_manager import StateManager
from ui.dashboard        import DashboardPage
from ui.wizard           import (WelcomePage, PreflightPage, PathPage,
                                  InstallPage, DonePage)
from components.miniconda  import find_conda, conda_version, conda_executable
from components.conda_env  import env_exists, python_version_ok
from components.models     import MODELS, model_exists


# ---------------------------------------------------------------------------
# Helper  (devono stare prima di AppWindow e main)
# ---------------------------------------------------------------------------

def _default_install_path() -> str:
    return os.path.join(os.path.expanduser("~"), "OffGallery")


def logo_path() -> str:
    """Percorso del logo header, sia in bundle PyInstaller che in sviluppo."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(__file__)
    return os.path.join(base, "assets", "logo_header.png")


def _center_window(win: tk.Tk, w: int, h: int):
    win.update_idletasks()
    x = (win.winfo_screenwidth()  - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")


# ---------------------------------------------------------------------------
# Finestra principale
# ---------------------------------------------------------------------------

class AppWindow:
    """
    Unica finestra dell'applicazione.
    Contiene tutte le pagine — wizard e dashboard — e le naviga con show_page().

    Stato condiviso accessibile da tutte le pagine:
        app.profile           str
        app.install_path      str
        app.user_conda_path   str | None
        app.state             StateManager | None
        app.root              tk.Tk
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("OffGallery Manager")
        # 900 e non 780: a 780 la colonna destra offriva 324px ai tre pulsanti
        # che ne chiedono 426, e "Aggiorna stato" usciva come "Agg..."
        # (segnalazione 2026-08-28). Ridimensionabile perche' con i font di
        # sistema ingranditi (125%) neanche 900 basterebbero: chi ha quella
        # impostazione allarga la finestra invece di restare col testo mozzato.
        self.root.geometry("900x680")
        self.root.resizable(True, True)
        self.root.minsize(900, 620)
        _center_window(self.root, 900, 680)

        # Stato condiviso fra le pagine
        self.profile:          str               = "leggero"
        self.install_path:     str               = _default_install_path()
        self.user_conda_path:  Optional[str]     = None
        self.state:            Optional[StateManager] = None

        # Container unico per tutte le pagine
        container = tk.Frame(self.root)
        container.pack(fill="both", expand=True)

        # Istanzia tutte le pagine nello stesso container
        self._pages: dict[str, tk.Frame] = {}
        for name, cls in [
            ("welcome",   WelcomePage),
            ("preflight", PreflightPage),
            ("path",      PathPage),
            ("install",   InstallPage),
            ("done",      DonePage),
            ("dashboard", DashboardPage),
        ]:
            page = cls(container, app=self)
            page.place(relwidth=1, relheight=1)
            self._pages[name] = page

    def show_page(self, name: str):
        """Porta in primo piano la pagina indicata e chiama on_enter()."""
        for page in self._pages.values():
            page.lower()
        page = self._pages[name]
        page.lift()
        page.on_enter()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Rilevamento installazioni legacy (senza installer_state.json)
# ---------------------------------------------------------------------------

def _detect_legacy_install(install_path: str) -> Optional[StateManager]:
    """
    Cerca un'installazione OffGallery fatta con i vecchi .bat (nessun installer_state.json).
    Se trova conda + env + gui_launcher.py, ricostruisce lo stato e lo salva.
    Restituisce un StateManager già salvato, oppure None se non trova nulla.
    """
    # Condizione minima: gui_launcher.py nella cartella
    if not os.path.isfile(os.path.join(install_path, "gui_launcher.py")):
        return None

    # Cerca conda nel sistema
    conda_exe = find_conda()
    if not conda_exe:
        return None

    # Verifica env OffGallery
    if not env_exists(conda_exe):
        return None

    # Installazione legacy confermata — ricostruiamo lo stato
    sm = StateManager(install_path)
    sm.load_or_create()  # crea un file nuovo con tutti pending

    # Miniconda
    import os as _os
    miniconda_path = _os.path.dirname(_os.path.dirname(conda_exe))
    ver = conda_version(conda_exe) or ""
    sm.mark_done("miniconda", path=miniconda_path, conda_version=ver, found_in_system=True)

    # Ambiente Python
    if python_version_ok(conda_exe):
        sm.mark_done("conda_env", python_version="3.12")
    else:
        sm.mark_done("conda_env", python_version="?")

    # Codice OffGallery (gui_launcher.py già verificato sopra)
    sm.mark_done("core", version="legacy")

    # Librerie Python — considerate presenti se l'env esiste e ha python
    sm.mark_done("packages", torch_variant="unknown")

    # Modelli AI — verifica file per file
    for spec in MODELS:
        if model_exists(install_path, spec.key):
            sm.set_model_status(spec.key, "done")

    # Ollama e shortcut — non gestiti dal vecchio installer, lasciamo pending
    sm.mark_skipped("lmstudio")

    sm.set_profile("leggero")
    sm.set_install_path(install_path)

    return sm


# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------

def _find_existing_install() -> Optional[StateManager]:
    """Cerca un'installazione gia' presente nel percorso predefinito.

    Serve per non far attraversare a chi ha gia' OffGallery tre schermate
    che parlano solo di installazione ("~14 GB, ~40 min", "Scegli cosa
    installare") prima di arrivare al pulsante Aggiorna: chi voleva solo
    aggiornare temeva di reinstallare tutto da capo (segnalazione 2026-08-28).

    Restituisce lo stato dell'installazione trovata, oppure None: in quel
    caso il wizard parte normalmente e nulla cambia.
    """
    try:
        path = _default_install_path()
        if not os.path.isdir(path):
            return None

        # Solo LETTURA: si controlla che il file esista prima di chiamare
        # load_or_create(), che altrimenti ne creerebbe uno nuovo. Un semplice
        # avvio del Manager non deve lasciare tracce in una cartella che non
        # contiene un'installazione.
        if os.path.isfile(os.path.join(path, "installer_state.json")):
            sm = StateManager(path)
            if sm.load_or_create() and sm.has_partial_install():
                return sm

        # Installazioni fatte con i vecchi .bat: nessun installer_state.json
        return _detect_legacy_install(path)
    except Exception:
        # Un rilevamento che fallisce non deve impedire l'avvio: si riparte
        # dal wizard, che e' il comportamento di sempre.
        logging.getLogger(__name__).warning(
            "Rilevamento installazione esistente fallito", exc_info=True)
        return None


def main():
    app = AppWindow()

    # Se OffGallery e' gia' installato si va dritti alla dashboard, dove il
    # pulsante Aggiorna e' subito visibile. Il wizard resta la strada per chi
    # installa la prima volta, o per chi ha OffGallery in un percorso diverso
    # da quello predefinito (da la' si arriva comunque alla dashboard).
    esistente = _find_existing_install()
    if esistente:
        app.state = esistente
        app.install_path = esistente.install_path_saved or _default_install_path()
        app.show_page("dashboard")
    else:
        app.show_page("welcome")
    app.run()


if __name__ == "__main__":
    main()
