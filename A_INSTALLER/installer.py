"""
Entry point del manager OffGallery.
Unica finestra tk.Tk() — decide se mostrare wizard o dashboard.
"""

import os
import sys
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
        self.root.geometry("780x680")
        self.root.resizable(False, False)
        _center_window(self.root, 780, 680)

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

def main():
    app = AppWindow()

    # Cerca un'installazione esistente nel percorso predefinito
    state = StateManager(app.install_path)
    already_installed = state.load_or_create()

    if already_installed and state.has_partial_install():
        # Installazione parziale o completa (con installer_state.json) → dashboard
        app.state = state
        app.show_page("dashboard")
    else:
        # Nessun installer_state.json — cerca installazione legacy
        legacy_state = _detect_legacy_install(app.install_path)
        if legacy_state:
            app.state = legacy_state
            app.show_page("dashboard")
        else:
            # Prima volta → wizard dal benvenuto
            app.show_page("welcome")

    app.run()


if __name__ == "__main__":
    main()
