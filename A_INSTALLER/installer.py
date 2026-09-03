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

def _abilita_dpi_windows():
    """Dice a Windows che la finestra sa gestire da se' gli schermi ad alta
    densita'.

    Senza questo, su uno schermo 4K con la scalatura al 200% o 300% Windows
    disegna la finestra a 1280x720 e poi la STIRA come un'immagine: i testi
    si sgranano e le etichette dei pulsanti escono tagliate, perche' il
    pulsante ha calcolato la propria larghezza su un font piu' piccolo di
    quello che viene poi mostrato (segnalazione 2026-08-28, schermo a 288 DPI).

    Va chiamata PRIMA di creare qualsiasi finestra, altrimenti non ha effetto.
    Su sistemi diversi da Windows, o su versioni che non espongono queste
    funzioni, non fa nulla e il programma prosegue come prima.
    """
    if sys.platform != "win32":
        return
    import ctypes
    try:
        # Windows 8.1 e successivi: 2 = per-monitor DPI aware
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError) as e:
        logging.getLogger(__name__).debug("SetProcessDpiAwareness non disponibile: %s", e)
    try:
        # Ripiego per Windows 7/8
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError) as e:
        logging.getLogger(__name__).debug("SetProcessDPIAware non disponibile: %s", e)


_abilita_dpi_windows()

import tkinter as tk
from tkinter import ttk
from typing import Optional

from state.state_manager import StateManager
from state.last_path     import load_last_path, save_last_path
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


def _fattore_scala() -> float:
    """Di quanto e' ingrandito lo schermo dell'utente (1.0 = 100%, 3.0 = 300%)."""
    if sys.platform != "win32":
        return 1.0
    import ctypes
    try:
        dc = ctypes.windll.user32.GetDC(0)
        try:
            dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
        finally:
            ctypes.windll.user32.ReleaseDC(0, dc)
        if dpi:
            return dpi / 96.0
    except (AttributeError, OSError) as e:
        logging.getLogger(__name__).debug("Lettura DPI fallita: %s", e)
    return 1.0


def _adegua_scalatura(win: tk.Tk) -> float:
    """Di quanto risultano ingranditi i contenuti sullo schermo dell'utente.

    NON tocca i font: dopo _abilita_dpi_windows() Tk imposta gia' da se'
    la propria scalatura (su uno schermo al 300% "Segoe UI 9pt" viene reso
    a 151px, non a 51). Ingrandire anche i font qui li moltiplicava una
    seconda volta e le scritte diventavano enormi.

    Serve solo a sapere quanto spazio chiederanno i contenuti, per dare
    alla finestra e alla colonna sinistra una dimensione proporzionata.
    """
    try:
        # 'tk scaling' e' in punti per pixel: 1.333 corrisponde al 100%
        scaling = float(win.tk.call("tk", "scaling"))
        fattore = scaling * 72.0 / 96.0
    except (tk.TclError, ValueError) as e:
        logging.getLogger(__name__).debug("Lettura di 'tk scaling' fallita: %s", e)
        fattore = _fattore_scala()
    return fattore if fattore > 1.05 else 1.0


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
        self._fattore = _adegua_scalatura(self.root)
        # 940 e non 780 (segnalazione 2026-08-28): a 780 la colonna destra
        # offriva 324px ai tre pulsanti che ne chiedono 444, e "Aggiorna stato"
        # usciva come "Agg...". Servono 440 per la colonna sinistra (le righe
        # componente col loro pulsante) + 444 per quella destra + margini.
        # Ridimensionabile perche' con i font di sistema ingranditi neanche 940
        # basterebbero: chi ha quella impostazione allarga la finestra invece
        # di restare col testo mozzato e nessun rimedio.
        # Su schermi ingranditi la finestra cresce quanto il resto, altrimenti
        # i contenuti appena ingranditi non ci starebbero piu' dentro.
        _w = int(940 * self._fattore)
        _h = int(680 * self._fattore)
        # Non oltre l'85% dello schermo: a scalature alte la finestra
        # arriverebbe a 2820x2040 su un 4K, cioe' quasi tutto lo schermo in
        # altezza. Il contenuto e' comunque raggiungibile — la lista dei
        # componenti scorre e la finestra si puo' allargare.
        _w = min(_w, int(self.root.winfo_screenwidth() * 0.85))
        _h = min(_h, int(self.root.winfo_screenheight() * 0.85))
        self.root.geometry(f"{_w}x{_h}")
        self.root.resizable(True, True)
        self.root.minsize(min(_w, 940), min(_h, 620))
        _center_window(self.root, _w, _h)

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

def _try_install_dir(path: str) -> Optional[StateManager]:
    """Verifica se `path` contiene un'installazione valida (nuova o legacy)."""
    if not path or not os.path.isdir(path):
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


def _find_existing_install() -> Optional[StateManager]:
    """Cerca un'installazione gia' presente.

    Serve per non far attraversare a chi ha gia' OffGallery tre schermate
    che parlano solo di installazione ("~14 GB, ~40 min", "Scegli cosa
    installare") prima di arrivare al pulsante Aggiorna: chi voleva solo
    aggiornare temeva di reinstallare tutto da capo (segnalazione 2026-08-28).

    Prova prima la cartella predefinita (~/OffGallery), poi l'ultima cartella
    scelta a mano dall'utente: chi installa altrove veniva rimandato al
    wizard ad ogni avvio, perche' il Manager non aveva memoria di quella
    scelta al di fuori della cartella stessa (segnalazione 2026-09-03).

    Restituisce lo stato dell'installazione trovata, oppure None: in quel
    caso il wizard parte normalmente e nulla cambia.
    """
    try:
        trovata = _try_install_dir(_default_install_path())
        if trovata:
            return trovata
        return _try_install_dir(load_last_path())
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
        save_last_path(app.install_path)
        app.show_page("dashboard")
    else:
        app.show_page("welcome")
    app.run()


if __name__ == "__main__":
    main()
