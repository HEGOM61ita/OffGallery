"""
Pagine del wizard di prima installazione.
Tutti i frame ricevono `app` — l'AppWindow da installer.py — come riferimento
alla finestra principale. Nessuna finestra propria.
"""

import os
import platform
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Optional

from components.conda_env  import ensure_env, python_executable
from components.core       import ensure_core
from components.miniconda  import ensure_miniconda, find_conda, default_install_path, conda_executable
from components.models     import download_models, MODELS
from components.ollama     import ensure_ollama
from components.packages   import detect_torch_variant, install_packages, torch_variant_label
from state.state_manager   import StateManager
from ui.progress           import DownloadPanel, StepIndicator, fmt_bytes, fmt_eta
from utils.preflight       import run_preflight, Severity
from utils.logger          import InstallLogger

if TYPE_CHECKING:
    from installer import AppWindow

from ui import _add_logo


# ---------------------------------------------------------------------------
# Costanti UI
# ---------------------------------------------------------------------------

BG         = "#f0f4f8"
ACCENT     = "#1565c0"
ACCENT_LT  = "#e3eaf6"
SUCCESS    = "#2e7d32"
ERROR_COL  = "#c62828"
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_HEAD  = ("Segoe UI", 12, "bold")
FONT_BODY  = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)

STEPS = [
    "Verifica sistema",
    "Miniconda",
    "Ambiente Python",
    "Codice OffGallery",
    "Librerie Python",
    "Modelli AI",
    "Ollama / LM Studio",
    "Collegamento desktop",
]


# ---------------------------------------------------------------------------
# Pagina 1 — Benvenuto e scelta profilo
# ---------------------------------------------------------------------------

class WelcomePage(tk.Frame):

    def __init__(self, parent, app: "AppWindow", **kw):
        super().__init__(parent, bg=BG, **kw)
        self.app = app
        self._profile_var = tk.StringVar(value="leggero")
        self._build()

    def on_enter(self):
        pass

    def _build(self):
        header = tk.Frame(self, bg=ACCENT, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        _add_logo(header)

        body = tk.Frame(self, bg=BG, padx=40, pady=20)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Benvenuto nell'installazione guidata di OffGallery.",
                 font=FONT_HEAD, bg=BG).pack(anchor="w", pady=(0, 6))
        tk.Label(body,
                 text="OffGallery organizza automaticamente migliaia di foto:\n"
                      "cerca un'immagine descrivendola a parole, identifica specie di piante\n"
                      "e animali, misura qualità estetica e tecnica, legge EXIF e GPS.\n"
                      "Tutto funziona sul tuo computer — senza internet dopo il primo avvio.",
                 font=FONT_BODY, bg=BG, justify="left").pack(anchor="w", pady=(0, 16))

        # Box informativo processo installazione
        info_box = tk.Frame(body, bg="#e8f4fd", padx=12, pady=8)
        info_box.pack(fill="x", pady=(0, 16))
        tk.Label(info_box,
                 text="ℹ️  La prima installazione scarica modelli AI e librerie (~8–14 GB).\n"
                      "    Potrebbe richiedere 30–70 minuti a seconda della connessione.\n"
                      "    Gli avvii successivi saranno immediati — tutto resta sul tuo computer.",
                 font=FONT_SMALL, bg="#e8f4fd", fg="#0d47a1", justify="left").pack(anchor="w")

        tk.Label(body, text="Scegli cosa installare:",
                 font=FONT_HEAD, bg=BG).pack(anchor="w", pady=(0, 8))

        for value, label, desc in [
            ("leggero",
             "◉  Organizzare e cercare le mie foto  (~14 GB, ~40 min)",
             "Ricerca per descrizione testuale · Riconoscimento specie · Score estetico e tecnico\n"
             "Lettura EXIF e GPS · Funziona su qualsiasi PC con 8+ GB di RAM"),
            ("completo",
             "◉  Anche generare descrizioni e tag automatici con AI  (~20 GB, ~70 min)",
             "Tutto quanto sopra, più: generazione automatica di titoli, descrizioni e tag\n"
             "tramite modello LLM vision locale · Richiede PC con 16+ GB di RAM"),
            ("personalizzato",
             "◉  Personalizzato — sceglierò io cosa installare",
             "Per utenti avanzati che vogliono scegliere ogni singolo componente"),
        ]:
            row = tk.Frame(body, bg=ACCENT_LT, padx=12, pady=8)
            row.pack(fill="x", pady=3)
            tk.Radiobutton(row, variable=self._profile_var, value=value,
                           text=label, font=("Segoe UI", 10, "bold"),
                           bg=ACCENT_LT, activebackground=ACCENT_LT).pack(anchor="w")
            tk.Label(row, text=desc, font=FONT_SMALL,
                     bg=ACCENT_LT, fg="#444", justify="left").pack(anchor="w", padx=22)

        footer = tk.Frame(self, bg=BG, pady=16)
        footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="Avanti →",
                   command=self._next).pack(side="right", padx=30)

    def _next(self):
        self.app.profile = self._profile_var.get()
        self.app.show_page("preflight")


# ---------------------------------------------------------------------------
# Pagina 2 — Controllo sistema
# ---------------------------------------------------------------------------

class PreflightPage(tk.Frame):

    def __init__(self, parent, app: "AppWindow", **kw):
        super().__init__(parent, bg=BG, **kw)
        self.app = app
        self._build()

    def on_enter(self):
        self._run_checks()

    def _build(self):
        tk.Label(self, text="Controllo del tuo computer",
                 font=FONT_TITLE, bg=BG).pack(anchor="w", padx=40, pady=(24, 4))

        self._checks_frame = tk.Frame(self, bg=BG, padx=40)
        self._checks_frame.pack(fill="x")

        self._spinner = ttk.Progressbar(self, mode="indeterminate", length=700)
        self._spinner.pack(padx=40, pady=8)
        self._spinner.start(15)

        self._summary = tk.Label(self, text="", font=FONT_BODY, bg=BG, fg="#555")
        self._summary.pack(anchor="w", padx=40, pady=4)

        footer = tk.Frame(self, bg=BG, pady=16)
        footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="← Indietro",
                   command=lambda: self.app.show_page("welcome")).pack(side="left", padx=30)
        self._btn_next = ttk.Button(footer, text="Continua →",
                                    command=self._next, state="disabled")
        self._btn_next.pack(side="right", padx=30)

    def _run_checks(self):
        for w in self._checks_frame.winfo_children():
            w.destroy()
        self._spinner.pack(padx=40, pady=8)
        self._spinner.start(15)
        self._btn_next.configure(state="disabled")

        def _work():
            report = run_preflight(self.app.install_path, profile=self.app.profile)
            self.after(0, self._show_results, report)

        threading.Thread(target=_work, daemon=True).start()

    def _show_results(self, report):
        self._spinner.stop()
        self._spinner.pack_forget()

        ICONS = {
            Severity.OK:      ("✅", SUCCESS),
            Severity.WARNING: ("⚠️",  "#e65100"),
            Severity.ERROR:   ("❌", ERROR_COL),
            Severity.INFO:    ("ℹ️",  "#1565c0"),
        }

        for r in report.results:
            row = tk.Frame(self._checks_frame, bg=BG)
            row.pack(fill="x", pady=2)
            icon, color = ICONS[r.severity]
            tk.Label(row, text=icon, font=("Segoe UI", 11),
                     bg=BG, width=3).pack(side="left")
            tk.Label(row, text=r.name, font=("Segoe UI", 10, "bold"),
                     bg=BG, width=22, anchor="w").pack(side="left")
            tk.Label(row, text=r.value, font=FONT_BODY,
                     bg=BG, anchor="w").pack(side="left")
            if r.message:
                msg_row = tk.Frame(self._checks_frame, bg=BG)
                msg_row.pack(fill="x")
                tk.Label(msg_row, text=f"   {r.message}",
                         font=FONT_SMALL, fg=color, bg=BG,
                         justify="left", anchor="w").pack(side="left")
                if r.action == "Cambia disco":
                    ttk.Button(msg_row, text="Cambia disco",
                               command=lambda: self.app.show_page("path")
                               ).pack(side="left", padx=8)

        size_label = f"{report.estimated_size_gb:.0f} GB"
        time_label = fmt_eta(report.estimated_minutes * 60)
        self._summary.configure(
            text=f"Spazio richiesto: {size_label}   •   Tempo stimato: {time_label}"
        )

        if report.can_proceed:
            self._btn_next.configure(state="normal")
        else:
            self._summary.configure(
                text=self._summary["text"] +
                     "\n⛔  Risolvi i problemi segnalati prima di continuare.",
                fg=ERROR_COL,
            )

    def _next(self):
        self.app.show_page("path")


# ---------------------------------------------------------------------------
# Pagina 3 — Scelta cartella
# ---------------------------------------------------------------------------

class PathPage(tk.Frame):

    def __init__(self, parent, app: "AppWindow", **kw):
        super().__init__(parent, bg=BG, **kw)
        self.app = app
        self._path_var  = tk.StringVar(value=app.install_path)
        self._conda_var = tk.StringVar(value="auto")
        self._conda_manual_var = tk.StringVar()
        self._build()

    def on_enter(self):
        self._path_var.set(self.app.install_path)
        self._check_conda()

    def _build(self):
        tk.Label(self, text="Dove installare OffGallery?",
                 font=FONT_TITLE, bg=BG).pack(anchor="w", padx=40, pady=(24, 4))
        tk.Label(self,
                 text="Scegli la cartella in cui verranno copiati tutti i file di OffGallery,\n"
                      "inclusi i modelli AI (~8 GB). Servono almeno 15 GB di spazio libero.",
                 font=FONT_BODY, bg=BG, justify="left").pack(anchor="w", padx=40)

        path_row = tk.Frame(self, bg=BG, padx=40, pady=12)
        path_row.pack(fill="x")
        ttk.Entry(path_row, textvariable=self._path_var, width=52).pack(side="left")
        ttk.Button(path_row, text="Sfoglia...",
                   command=self._browse).pack(side="left", padx=8)

        self._disk_label = tk.Label(self, text="", font=FONT_SMALL, fg="#555", bg=BG)
        self._disk_label.pack(anchor="w", padx=40)

        # Separatore
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=40, pady=(16, 0))

        tk.Label(self, text="Gestione librerie software",
                 font=FONT_HEAD, bg=BG).pack(anchor="w", padx=40, pady=(12, 2))
        tk.Label(self,
                 text="OffGallery ha bisogno di un gestore chiamato Miniconda per installare\n"
                      "le proprie librerie in modo isolato, senza toccare altri programmi.\n"
                      "Se non sai cos'è, lascia selezionato «Automatico» — pensiamo a tutto noi.",
                 font=FONT_SMALL, bg=BG, fg="#444", justify="left").pack(anchor="w", padx=40)

        self._conda_status = tk.Label(self, text="", font=FONT_SMALL, bg=BG)
        self._conda_status.pack(anchor="w", padx=40, pady=(4, 0))

        conda_row = tk.Frame(self, bg=BG, padx=40, pady=4)
        conda_row.pack(fill="x")
        tk.Radiobutton(conda_row, variable=self._conda_var, value="auto",
                       text="Automatico — rileva o installa Miniconda  (consigliato)",
                       font=FONT_BODY, bg=BG,
                       command=self._on_conda_choice).pack(anchor="w")
        tk.Radiobutton(conda_row, variable=self._conda_var, value="manual",
                       text="Ho già Anaconda/Miniconda — indica il percorso",
                       font=FONT_BODY, bg=BG,
                       command=self._on_conda_choice).pack(anchor="w")

        manual_row = tk.Frame(self, bg=BG, padx=60)
        manual_row.pack(fill="x")
        self._conda_entry = ttk.Entry(manual_row, textvariable=self._conda_manual_var,
                                      width=42, state="disabled")
        self._conda_entry.pack(side="left")
        self._conda_browse_btn = ttk.Button(manual_row, text="Sfoglia...",
                                            state="disabled",
                                            command=self._browse_conda)
        self._conda_browse_btn.pack(side="left", padx=8)

        footer = tk.Frame(self, bg=BG, pady=16)
        footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="← Indietro",
                   command=lambda: self.app.show_page("preflight")).pack(side="left", padx=30)
        ttk.Button(footer, text="Continua →",
                   command=self._next).pack(side="right", padx=30)

    def _browse(self):
        path = filedialog.askdirectory(title="Scegli la cartella di installazione",
                                       initialdir=self._path_var.get())
        if path:
            if os.path.basename(path) != "OffGallery":
                path = os.path.join(path, "OffGallery")
            self._path_var.set(path)
            self._update_disk_label()

    def _browse_conda(self):
        path = filedialog.askdirectory(title="Cartella Anaconda / Miniconda")
        if path:
            self._conda_manual_var.set(path)

    def _on_conda_choice(self):
        state = "normal" if self._conda_var.get() == "manual" else "disabled"
        self._conda_entry.configure(state=state)
        self._conda_browse_btn.configure(state=state)

    def _check_conda(self):
        found = find_conda()
        if found:
            self._conda_status.configure(
                text=f"✅  Conda trovato: {found}", fg=SUCCESS)
        else:
            self._conda_status.configure(
                text="○  Non rilevato — verrà installato Miniconda.", fg="#555")

    def _update_disk_label(self):
        import shutil
        try:
            path  = self._path_var.get()
            drive = os.path.splitdrive(path)[0] + os.sep if platform.system() == "Windows" else "/"
            free  = shutil.disk_usage(drive).free
            self._disk_label.configure(text=f"Spazio libero: {fmt_bytes(free)}")
        except Exception:
            pass

    def _next(self):
        path = self._path_var.get().strip()
        if not path:
            messagebox.showerror("Errore", "Scegli una cartella di installazione.")
            return
        self.app.install_path = path
        if self._conda_var.get() == "manual":
            cp = self._conda_manual_var.get().strip()
            self.app.user_conda_path = cp or None

        sm = StateManager(path)
        sm.load_or_create()
        sm.set_profile(self.app.profile)
        sm.set_install_path(path)
        self.app.state = sm
        self.app.show_page("install")


# ---------------------------------------------------------------------------
# Pagina 4 — Installazione in corso
# ---------------------------------------------------------------------------

class InstallPage(tk.Frame):

    def __init__(self, parent, app: "AppWindow", **kw):
        super().__init__(parent, bg=BG, **kw)
        self.app      = app
        self._started = False
        self._logger: InstallLogger | None = None
        self._results: dict[str, bool] = {}
        self._build()

    def on_enter(self):
        if not self._started:
            self._started = True
            threading.Thread(target=self._run_install, daemon=True).start()

    def _build(self):
        sidebar = tk.Frame(self, bg=ACCENT_LT, width=180)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="Installazione", font=FONT_HEAD,
                 bg=ACCENT_LT, pady=12).pack()
        self._steps = StepIndicator(sidebar, STEPS, bg=ACCENT_LT)
        self._steps.pack(fill="x", padx=8, pady=4)

        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        self._panel = DownloadPanel(main, bg=BG)
        self._panel.pack(fill="both", expand=True)

        footer = tk.Frame(main, bg=BG, pady=12)
        footer.pack(fill="x", side="bottom")
        self._footer_btn = ttk.Button(footer, text="Annulla", command=self._cancel)
        self._footer_btn.pack(side="right", padx=20)

    def _step(self, name, status, detail=""):
        self._steps.set_status(name, status, detail)

    def _log(self, msg: str):
        self._panel.log(msg)
        if self._logger:
            self._logger.log(msg)

    def _run_install(self):
        sm = self.app.state
        self._logger = InstallLogger(self.app.install_path)
        self._logger.section("Avvio installazione")

        try:
            # Miniconda
            if not sm.is_done("miniconda"):
                self._step("Miniconda", "in_progress")
                self._panel.set_step_indeterminate("Download Miniconda...")
                conda_exe, found = ensure_miniconda(
                    install_path=default_install_path(),
                    user_conda_path=self.app.user_conda_path,
                    progress_cb=self._panel.on_download_progress,
                    log_cb=self._log,
                )
                sm.mark_done("miniconda",
                             path=os.path.dirname(os.path.dirname(conda_exe)),
                             found_in_system=found)
                self._step("Miniconda", "done", "trovato" if found else "installato")
                self._results["Gestore Python (Miniconda)"] = True
            else:
                conda_exe = conda_executable(sm.get("miniconda.path", default_install_path()))
                self._step("Miniconda", "done", "(già presente)")
                self._results["Gestore Python (Miniconda)"] = True

            # Ambiente Python
            if not sm.is_done("conda_env"):
                self._step("Ambiente Python", "in_progress")
                self._panel.set_step_indeterminate("Creazione ambiente Python 3.12...")
                python_exe = ensure_env(conda_exe, log_cb=self._log)
                sm.mark_done("conda_env", python_version="3.12")
                self._step("Ambiente Python", "done", "Python 3.12")
                self._results["Ambiente Python (Python 3.12)"] = True
            else:
                python_exe = python_executable(conda_exe)
                self._step("Ambiente Python", "done", "(già presente)")
                self._results["Ambiente Python (Python 3.12)"] = True

            # Codice OffGallery
            if not sm.is_done("core"):
                self._step("Codice OffGallery", "in_progress")
                result = ensure_core(self.app.install_path,
                                     progress_cb=self._panel.on_download_progress,
                                     log_cb=self._log)
                sm.mark_done("core", version=result["version"])
                self._step("Codice OffGallery", "done", f"v{result['version']}")
                self._results["Codice OffGallery"] = True
            else:
                self._step("Codice OffGallery", "done", "(già presente)")
                self._results["Codice OffGallery"] = True

            # Librerie Python
            if not sm.is_done("packages"):
                self._step("Librerie Python", "in_progress")
                self._panel.set_step_indeterminate("Rilevamento GPU...")
                variant  = detect_torch_variant(log_cb=self._log)
                _inst_base = sys._MEIPASS if getattr(sys, "frozen", False) \
                    else os.path.dirname(os.path.dirname(__file__))
                req_file = os.path.join(_inst_base, "requirements_offgallery.txt")
                self._panel.set_step_indeterminate(
                    f"Librerie ({torch_variant_label(variant)})...")
                install_packages(
                    python_exe=python_exe, req_file=req_file,
                    variant=variant, log_cb=self._log,
                    progress_cb=lambda c, t, p: (
                        self._panel.update_step_progress(p, c, t),
                    ),
                )
                self._panel.set_step_done("Librerie installate")
                sm.mark_done("packages", torch_variant=variant)
                self._results["Librerie Python"] = True
                self._step("Librerie Python", "done")
            else:
                self._step("Librerie Python", "done", "(già installate)")

            # Modelli AI
            self._step("Modelli AI", "in_progress")
            pending = [m.key for m in MODELS if not sm.is_model_done(m.key)]
            if pending:
                results = download_models(
                    models_dir=self.app.install_path,
                    keys=pending,
                    progress_cb=self._panel.on_model_progress,
                    log_cb=self._log,
                )
                for key, ok in results.items():
                    sm.set_model_status(key, "done" if ok else "error")
                failed = [k for k, ok in results.items() if not ok]
                self._step("Modelli AI",
                           "error" if failed else "done",
                           f"{len(failed)} falliti" if failed else "")
                self._results["Modelli AI"] = not bool(failed)
            else:
                self._step("Modelli AI", "done", "(già presenti)")

            # Ollama / LM Studio
            if self.app.profile == "completo":
                self._step("Ollama / LM Studio", "in_progress")
                res = ensure_ollama(install_if_missing=True, pull_model_flag=True,
                                    progress_cb=self._panel.on_download_progress,
                                    log_cb=self._log)
                if res["model_ok"]:
                    sm.mark_done("ollama", version=res.get("version", ""))
                    self._step("Ollama / LM Studio", "done")
                    self._results["Ollama + modello LLM vision"] = True
                else:
                    sm.mark_error("ollama", "Pull modello fallito")
                    self._step("Ollama / LM Studio", "error", "riprova dopo")
                    self._results["Ollama + modello LLM vision"] = False
            else:
                sm.mark_skipped("ollama")
                sm.mark_skipped("lmstudio")
                self._step("Ollama / LM Studio", "skipped", "(non selezionato)")
                self._results["Ollama (non installato — opzionale)"] = True

            # Collegamento desktop
            self._step("Collegamento desktop", "in_progress")
            _create_shortcut(self.app.install_path, log_cb=self._log,
                             manager_exe=sys.executable)
            sm.mark_done("shortcut")
            self._step("Collegamento desktop", "done")
            self._results["Collegamento desktop"] = True

            if self._logger:
                self._logger.summary(self._results)
                self._logger.close()
            self.after(500, lambda: self.app.show_page("done"))

        except Exception as exc:
            self._log(f"\n❌ ERRORE: {exc}")
            if self._logger:
                self._logger.log(f"❌ ERRORE FATALE: {exc}")
                self._logger.close()
            self.after(0, self._on_error, str(exc))

    def _on_error(self, msg: str):
        self._panel.set_step_done("Interrotto")
        self._footer_btn.configure(text="Riprova", command=self._retry, state="normal")
        messagebox.showerror(
            "Errore installazione",
            f"{msg}\n\nPremi 'Riprova' per riprendere dall'ultimo punto completato."
        )

    def _retry(self):
        self._started = False
        self.on_enter()

    def _cancel(self):
        if messagebox.askyesno("Annulla",
                               "Vuoi annullare?\n"
                               "Potrai riprendere in seguito dall'ultimo punto completato."):
            self.app.root.destroy()


# ---------------------------------------------------------------------------
# Pagina 5 — Completamento
# ---------------------------------------------------------------------------

class DonePage(tk.Frame):

    def __init__(self, parent, app: "AppWindow", **kw):
        super().__init__(parent, bg=BG, **kw)
        self.app = app
        self._log_path_var = tk.StringVar(value="")
        self._summary_frame: Optional[tk.Frame] = None
        self._build()

    def on_enter(self):
        install_page = self._find_install_page()

        # Riepilogo dinamico dai risultati reali dell'installazione
        if self._summary_frame is not None:
            for w in self._summary_frame.winfo_children():
                w.destroy()
            results = install_page._results if install_page else {}
            if results:
                for label, ok in results.items():
                    icon  = "✅" if ok else "❌"
                    color = SUCCESS if ok else ERROR_COL
                    tk.Label(self._summary_frame, text=f"{icon}  {label}",
                             font=FONT_BODY, bg=ACCENT_LT, fg=color,
                             anchor="w").pack(fill="x")
            else:
                # Fallback statico se i risultati non sono disponibili
                for line in [
                    "✅  Gestore Python installato",
                    "✅  Ambiente OffGallery configurato",
                    "✅  Modelli AI scaricati",
                    "✅  Librerie Python installate",
                ]:
                    tk.Label(self._summary_frame, text=line, font=FONT_BODY,
                             bg=ACCENT_LT, anchor="w").pack(fill="x")

        # Percorso log
        if install_page and install_page._logger:
            self._log_path_var.set(
                f"📄 Log installazione salvato in:\n{install_page._logger.path}"
            )

    def _find_install_page(self) -> Optional["InstallPage"]:
        for page in self.master.winfo_children():
            if isinstance(page, InstallPage):
                return page
        return None

    def _build(self):
        frame = tk.Frame(self, bg=BG, padx=40)
        frame.place(relx=0.5, rely=0.45, anchor="center")

        tk.Label(frame, text="🎉", font=("Segoe UI", 48), bg=BG).pack()
        tk.Label(frame, text="Installazione completata con successo!",
                 font=FONT_TITLE, bg=BG, fg=SUCCESS).pack(pady=(4, 2))
        tk.Label(frame,
                 text="OffGallery è pronto all'uso sul tuo computer.\n"
                      "Trovi il collegamento direttamente sul Desktop.",
                 font=FONT_BODY, bg=BG, justify="center").pack(pady=(0, 12))

        # Riepilogo — popolato dinamicamente in on_enter() con i risultati reali
        self._summary_frame = tk.Frame(frame, bg=ACCENT_LT, padx=16, pady=10)
        self._summary_frame.pack(fill="x", pady=(0, 8))

        # Percorso log
        tk.Label(frame, textvariable=self._log_path_var,
                 font=("Segoe UI", 8), bg=BG, fg="#777",
                 justify="center").pack(pady=(0, 12))

        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack()
        ttk.Button(btn_frame, text="▶  Avvia OffGallery",
                   command=self._launch).pack(side="left", padx=8, ipadx=10, ipady=4)
        ttk.Button(btn_frame, text="Gestisci componenti",
                   command=lambda: self.app.show_page("dashboard")
                   ).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="Chiudi",
                   command=self.app.root.destroy).pack(side="left", padx=8)

    def _launch(self):
        import subprocess
        sm  = self.app.state
        exe = _python_exe_from_state(sm)
        launcher = os.path.join(self.app.install_path, "gui_launcher.py")
        try:
            subprocess.Popen([exe, launcher],
                             cwd=self.app.install_path,
                             start_new_session=True)
            self.app.root.destroy()
        except Exception as exc:
            messagebox.showerror("Errore avvio", f"Impossibile avviare OffGallery:\n{exc}")


# ---------------------------------------------------------------------------
# Helper condivisi
# ---------------------------------------------------------------------------

def _python_exe_from_state(sm: StateManager) -> str:
    conda_path = sm.get("miniconda.path", "")
    if conda_path:
        c_exe = conda_executable(conda_path)
        return python_executable(c_exe)
    return "python"


def _create_shortcut(install_path: str, log_cb=None, manager_exe: str = ""):
    try:
        results = _shortcut_windows(install_path, manager_exe=manager_exe, log_cb=log_cb)
        if log_cb:
            if results:
                log_cb(f"Collegamento desktop creato: {', '.join(results)}")
            else:
                log_cb("Attenzione: nessun collegamento creato (percorso desktop non trovato)")
    except Exception as exc:
        if log_cb:
            log_cb(f"Attenzione: collegamento non creato: {exc}")


def _shortcut_windows(install_path: str, manager_exe: str = "", log_cb=None):
    import shutil as _shutil

    # Copia il binario Manager in una posizione stabile
    stable_manager = os.path.join(install_path, "OffGallerySetup.exe")
    if (getattr(sys, "frozen", False)
            and manager_exe
            and os.path.isfile(manager_exe)
            and os.path.abspath(manager_exe) != os.path.abspath(stable_manager)):
        _shutil.copy2(manager_exe, stable_manager)

    def _make_lnk(lnk_path, target, workdir, description):
        # Tentativo 1: win32com (disponibile se installato sul sistema)
        try:
            from win32com.client import Dispatch
            shell = Dispatch("WScript.Shell")
            sc = shell.CreateShortCut(lnk_path)
            sc.Targetpath       = target
            sc.WorkingDirectory = workdir
            sc.Description      = description
            sc.save()
            return True
        except Exception:
            pass
        # Tentativo 2: PowerShell — sempre disponibile su Windows, non richiede moduli
        try:
            import subprocess
            ps = (
                f'$ws = New-Object -ComObject WScript.Shell; '
                f'$sc = $ws.CreateShortcut("{lnk_path}"); '
                f'$sc.TargetPath = "{target}"; '
                f'$sc.WorkingDirectory = "{workdir}"; '
                f'$sc.Description = "{description}"; '
                f'$sc.Save()'
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and os.path.isfile(lnk_path):
                return True
            if log_cb and result.stderr:
                log_cb(f"  PowerShell: {result.stderr.strip()}")
        except Exception as e:
            if log_cb:
                log_cb(f"  PowerShell fallito ({os.path.basename(lnk_path)}): {e}")
        return False

    # Usa SHGetSpecialFolderPathW (CSIDL_DESKTOP=0) per trovare il desktop reale
    # anche se l'utente lo ha spostato su un drive diverso da C:\
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetSpecialFolderPathW(None, buf, 0, False)
        desktop = buf.value if buf.value else ""
    except Exception:
        desktop = ""
    if not desktop or not os.path.isdir(desktop):
        # Secondo tentativo: variabile d'ambiente USERPROFILE
        desktop = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")

    if log_cb:
        log_cb(f"  Desktop rilevato: {desktop}")

    created = []
    if _make_lnk(
        lnk_path    = os.path.join(desktop, "OffGallery.lnk"),
        target      = os.path.join(install_path, "installer", "OffGallery_Launcher.bat"),
        workdir     = install_path,
        description = "Avvia OffGallery",
    ):
        created.append("OffGallery.lnk")

    if os.path.isfile(stable_manager):
        if _make_lnk(
            lnk_path    = os.path.join(desktop, "OffGallery Manager.lnk"),
            target      = stable_manager,
            workdir     = install_path,
            description = "Gestisci i componenti di OffGallery",
        ):
            created.append("OffGallery Manager.lnk")

    return created


