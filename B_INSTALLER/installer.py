"""
Entry point del manager OffGallery — Linux.
Unica finestra tk.Tk() — decide se mostrare wizard o dashboard.
"""

import os
import sys
import platform

# Fix Tcl/Tk e SSL quando eseguito come bundle PyInstaller
if getattr(sys, "frozen", False):
    _base = sys._MEIPASS

    # Linux: le directory tcl/tk sono bundlate nella stessa cartella dell'exe
    for _name in ("tcl8.6", "tk8.6", "tcl9.0", "tk9.0"):
        _p = os.path.join(_base, _name)
        if os.path.isdir(_p):
            if "tcl" in _name:
                os.environ["TCL_LIBRARY"] = _p
            else:
                os.environ["TK_LIBRARY"] = _p

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


def _center_window(win: tk.Tk, w: int, h: int) -> int:
    """Centra la finestra, riducendone l'altezza se lo schermo non la contiene.

    Su Linux i caratteri di sistema sono mediamente più grandi che su Windows,
    quindi le stesse righe occupano più spazio in verticale: con un'altezza
    fissa l'ultima sezione della dashboard (riga Ollama e il suo pulsante)
    finiva tagliata dal bordo inferiore — segnalato su Linux Mint, 13/08/2026.
    Si tiene un margine per barra delle applicazioni e decorazioni della
    finestra, che qui non sono misurabili in modo affidabile.

    Ritorna l'altezza effettivamente usata, così il chiamante può regolare di
    conseguenza l'altezza minima.
    """
    win.update_idletasks()
    h = min(h, int(win.winfo_screenheight() * 0.85))
    x = (win.winfo_screenwidth()  - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")
    return h


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
        # Ridimensionabile: se il contenuto non entra (caratteri di sistema più
        # grandi, tema con più spaziatura) l'utente può allargare la finestra
        # invece di trovarsi un pulsante tagliato a metà e nessun rimedio.
        self.root.resizable(True, True)
        _h = _center_window(self.root, 780, 680)
        # L'altezza minima non deve superare quella concessa dallo schermo,
        # altrimenti su schermi bassi la finestra tornerebbe a sforare.
        self.root.minsize(780, min(560, _h))

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
# Avvio
# ---------------------------------------------------------------------------

def main():
    app = AppWindow()

    # Cerca un'installazione esistente nel percorso predefinito
    state = StateManager(app.install_path)
    already_installed = state.load_or_create()

    if already_installed and state.has_partial_install():
        # Installazione parziale o completa → dashboard
        app.state = state
        app.show_page("dashboard")
    else:
        # Prima volta → wizard dal benvenuto
        app.show_page("welcome")

    app.run()


if __name__ == "__main__":
    main()
