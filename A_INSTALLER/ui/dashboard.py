"""
Dashboard di manutenzione — frame puro, nessuna finestra propria.
Vive dentro AppWindow insieme alle pagine del wizard.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Optional

from components.conda_env  import ensure_env, python_executable
from components.core       import ensure_core, installed_version, update_available
from components.miniconda  import conda_executable, find_conda, conda_version
from components.models     import MODELS, download_models, model_exists
from components.ollama     import (ensure_ollama, find_ollama, ollama_version,
                                   is_running as ollama_running, is_model_pulled,
                                   pull_model, start_server, OLLAMA_MODEL)
from components.lmstudio   import (ensure_lmstudio, find_lmstudio,
                                   is_running as lm_running, api_models,
                                   POST_INSTALL_INSTRUCTIONS)
from utils.config_yaml     import read_llm_backend, write_llm_backend, config_exists
from components.packages   import detect_torch_variant, install_packages, torch_variant_label
from state.state_manager   import StateManager
from ui.progress           import DownloadPanel

if TYPE_CHECKING:
    from installer import AppWindow

from ui import _add_logo


BG        = "#f0f4f8"
ACCENT    = "#1565c0"
ACCENT_LT = "#e3eaf6"
SUCCESS   = "#2e7d32"
ERROR_COL = "#c62828"
WARN_COL  = "#e65100"
FONT_HEAD = ("Segoe UI", 12, "bold")
FONT_BODY = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 9)

STATUS_ICONS = {
    "done":          ("✅", SUCCESS),
    "pending":       ("○",  "#aaa"),
    "in_progress":   ("⟳",  ACCENT),
    "error":         ("❌", ERROR_COL),
    "skipped":       ("—",  "#aaa"),
    "not_installed": ("❌", ERROR_COL),
    "update":        ("🔄", WARN_COL),
    "warning":       ("⚠️",  WARN_COL),
}

# ---------------------------------------------------------------------------
# Tooltip
# ---------------------------------------------------------------------------

class _Tooltip:
    """Tooltip a comparsa su hover (500 ms di ritardo)."""

    def __init__(self, widget: tk.Widget, text: str):
        self._widget = widget
        self._text   = text
        self._win    = None
        self._job    = None
        widget.bind("<Enter>",       self._schedule,  add="+")
        widget.bind("<Leave>",       self._cancel,    add="+")
        widget.bind("<ButtonPress>", self._cancel,    add="+")

    def _schedule(self, _=None):
        self._cancel()
        self._job = self._widget.after(500, self._show)

    def _cancel(self, _=None):
        if self._job:
            self._widget.after_cancel(self._job)
            self._job = None
        if self._win:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None

    def _show(self):
        x = self._widget.winfo_rootx() + 16
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._win = tk.Toplevel(self._widget)
        self._win.wm_overrideredirect(True)
        self._win.wm_geometry(f"+{x}+{y}")
        self._win.wm_attributes("-topmost", True)
        outer = tk.Frame(self._win, bg="#1a1a2e", bd=1, relief="solid")
        outer.pack()
        tk.Label(
            outer, text=self._text,
            font=("Segoe UI", 9), bg="#1a1a2e", fg="#e8e8f0",
            justify="left", padx=10, pady=7, wraplength=320,
        ).pack()


# ---------------------------------------------------------------------------
# Testi tooltip per ogni componente
# ---------------------------------------------------------------------------

TOOLTIP_TEXT: dict[str, str] = {
    # AMBIENTE
    "core": (
        "Codice principale di OffGallery.\n\n"
        "Cliccando [Aggiorna] scarica l'ultima versione da GitHub "
        "preservando configurazione, modelli e database. "
        "Puoi aggiornare in qualsiasi momento."
    ),
    "miniconda": (
        "Gestore di ambienti Python isolati (Anaconda/Miniconda).\n\n"
        "Permette a OffGallery di avere le proprie librerie senza "
        "interferire con altri programmi Python installati sul computer."
    ),
    "conda_env": (
        "Ambiente Python 3.12 dedicato a OffGallery.\n\n"
        "Spazio di lavoro isolato che contiene tutte le dipendenze. "
        "Usa [Ricrea] solo se l'ambiente è corrotto: richiederà poi "
        "di reinstallare le librerie (~20 min)."
    ),
    "packages": (
        "Librerie Python richieste da OffGallery:\n"
        "PyTorch, Transformers, OpenCLIP, rawpy, ecc.\n\n"
        "Include automaticamente la variante GPU (CUDA) se rilevata, "
        "altrimenti CPU-only. "
        "Si possono reinstallare in qualsiasi momento se qualcosa smette "
        "di funzionare (~20 min)."
    ),
    # MODELLI AI
    "model_clip": (
        "CLIP ViT-L/14 — Ricerca semantica testuale.  (~1.6 GB)\n\n"
        "Permette di cercare foto con frasi come \"tramonto sulle Dolomiti\" "
        "o \"rana verde su foglia\". Le query in italiano vengono tradotte "
        "automaticamente in inglese per ottenere risultati migliori."
    ),
    "model_dinov2": (
        "DINOv2 (Meta/Facebook) — Similarità visiva.  (~330 MB)\n\n"
        "Trova foto con composizione, texture e colori simili a "
        "un'immagine di riferimento, indipendentemente dal contenuto "
        "semantico. Utile per raggruppare scatti simili."
    ),
    "model_aesthetic": (
        "Aesthetic Scorer — Valutazione estetica.  (~1.7 GB)\n\n"
        "Assegna un punteggio 0–10 alla qualità artistica di ogni foto: "
        "luce, composizione, impatto visivo. Permette di filtrare e "
        "ordinare le foto per qualità estetica."
    ),
    "model_bioclip": (
        "BioCLIP v2 (OpenCLIP) — Classificazione naturalistica.  (~2 GB)\n\n"
        "Riconosce piante, animali e funghi a livello di specie tra "
        "~450.000 taxa del TreeOfLife. Richiede anche il modello "
        "TreeOfLife Embeddings per funzionare."
    ),
    "model_treeoflife": (
        "TreeOfLife Embeddings — Database specie.  (~2.6 GB)\n\n"
        "Vettori pre-calcolati per ~450.000 specie biologiche. "
        "Necessario per la classificazione tassonomica di BioCLIP. "
        "Non può essere usato da solo."
    ),
    "model_musiq": (
        "MUSIQ (Google) — Qualità tecnica.  (~104 MB)\n\n"
        "Valuta nitidezza, rumore, esposizione e distorsione "
        "indipendentemente dalla composizione artistica. "
        "Complementare all'Aesthetic Scorer."
    ),
    "model_argos": (
        "Argos Translate IT→EN — Traduttore offline.  (~92 MB)\n\n"
        "Traduce le query di ricerca dall'italiano all'inglese prima "
        "di passarle a CLIP, che è stato addestrato principalmente su "
        "testi inglesi. Migliora sensibilmente la qualità dei risultati."
    ),
    # LLM
    "ollama": (
        "Ollama — Server LLM locale.  (opzionale)\n\n"
        "Necessario per la generazione automatica di descrizioni, "
        "titoli e tag AI tramite modello LLM vision "
        "(qwen3-vl:8b, ~5 GB aggiuntivi).\n\n"
        "Non installato ora? Puoi aggiungerlo in qualsiasi momento "
        "cliccando [Installa] da questa schermata."
    ),
    "lmstudio": (
        "LM Studio — Interfaccia LLM locale.  (opzionale)\n\n"
        "Alternativa grafica a Ollama: permette di caricare e gestire "
        "modelli AI locali tramite un'interfaccia visiva.\n\n"
        "LM Studio si aggiorna autonomamente tramite il suo auto-updater. "
        "Usa [Reinstalla] solo se l'installazione è corrotta.\n\n"
        "Non installato ora? Puoi aggiungerlo in qualsiasi momento "
        "cliccando [Installa] da questa schermata."
    ),
    "model_llm": (
        f"Modello LLM vision per la generazione automatica di descrizioni,\n"
        f"titoli e tag fotografici.\n\n"
        f"Backend Ollama — Modello: {OLLAMA_MODEL}  (~5.2 GB)\n"
        f"  Scaricato automaticamente dall'installer.\n\n"
        "Backend LM Studio — il modello va scaricato manualmente:\n"
        "  1. Apri LM Studio → Discover → scarica un modello vision\n"
        "  2. Local Server → carica il modello → Start Server\n"
        "  3. Torna qui — verrà rilevato automaticamente.\n\n"
        "Cambia backend con i pulsanti radio qui sopra."
    ),
}


class DashboardPage(tk.Frame):

    def __init__(self, parent, app: "AppWindow", **kw):
        super().__init__(parent, bg=BG, **kw)
        self.app = app
        self._rows: dict[str, "_ComponentRow"] = {}
        self._backend_var = tk.StringVar(value="ollama")
        self._build()

    def on_enter(self):
        if self.app.state:
            self._backend_var.set(
                read_llm_backend(self.app.state.install_path)
            )
        self._refresh_all()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self):
        # Header
        header = tk.Frame(self, bg=ACCENT, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        _add_logo(header)
        self._version_lbl = tk.Label(header, text="",
                                     font=("Segoe UI", 9),
                                     bg=ACCENT, fg="#bbdefb")
        self._version_lbl.pack(side="right", padx=20)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # Colonna sinistra: lista componenti
        left = tk.Frame(body, bg=BG, width=420)
        left.pack(side="left", fill="y", padx=(16, 8), pady=12)
        left.pack_propagate(False)

        canvas    = tk.Canvas(left, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        self._comp_frame = tk.Frame(canvas, bg=BG)
        self._comp_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._comp_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._build_section("AMBIENTE", [
            ("core",      "OffGallery Core"),
            ("miniconda", "Miniconda"),
            ("conda_env", "Ambiente Python"),
            ("packages",  "Librerie Python"),
        ])
        self._build_section("MODELLI AI", [
            (f"model_{m.key}", m.label) for m in MODELS
        ])
        # Sezione LLM — costruita manualmente per aggiungere il selettore backend
        tk.Label(self._comp_frame, text="LLM (opzionale)",
                 font=FONT_HEAD, bg=BG, anchor="w", pady=6).pack(fill="x")

        backend_row = tk.Frame(self._comp_frame, bg=BG)
        backend_row.pack(fill="x", pady=(0, 4))
        tk.Label(backend_row, text="  Backend:", font=FONT_BODY,
                 bg=BG, width=10, anchor="w").pack(side="left")
        for val, lbl in [("ollama", "Ollama  (consigliato)"), ("lmstudio", "LM Studio")]:
            tk.Radiobutton(backend_row, variable=self._backend_var, value=val,
                           text=lbl, font=FONT_BODY, bg=BG,
                           activebackground=BG,
                           command=self._on_backend_change).pack(side="left", padx=8)

        for key, label in [
            ("ollama",    "Ollama"),
            ("lmstudio",  "LM Studio"),
            ("model_llm", "Modello LLM"),
        ]:
            row = _ComponentRow(self._comp_frame, key=key, label=label,
                                dashboard=self, tooltip=TOOLTIP_TEXT.get(key, ""))
            row.pack(fill="x", pady=2)
            self._rows[key] = row
        ttk.Separator(self._comp_frame, orient="horizontal").pack(fill="x", pady=6)

        # Colonna destra: download panel + bottoni
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=12)

        self._panel = DownloadPanel(right, bg=BG)
        self._panel.pack(fill="both", expand=True)

        btn_frame = tk.Frame(right, bg=BG, pady=8)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="▶  Avvia OffGallery",
                   command=self._launch).pack(side="left", ipadx=10, ipady=4)
        ttk.Button(btn_frame, text="↻  Aggiorna stato",
                   command=self._refresh_all).pack(side="right")

    def _build_section(self, title: str, items: list):
        tk.Label(self._comp_frame, text=title,
                 font=FONT_HEAD, bg=BG, anchor="w", pady=6).pack(fill="x")
        for key, label in items:
            row = _ComponentRow(self._comp_frame, key=key, label=label,
                                dashboard=self, tooltip=TOOLTIP_TEXT.get(key, ""))
            row.pack(fill="x", pady=2)
            self._rows[key] = row
        ttk.Separator(self._comp_frame, orient="horizontal").pack(fill="x", pady=6)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh_all(self):
        sm = self.app.state
        if not sm:
            return
        self._sync_backend_rows()

        ver     = installed_version(sm.install_path)
        new_ver = None
        try:
            new_ver = update_available(sm.install_path)
        except Exception:
            pass

        self._version_lbl.configure(text=f"versione {ver}" if ver else "")

        if new_ver:
            core_action_label = "Aggiorna"
            core_action       = self._action_update_core
        elif ver:
            core_action_label = "Riscarica"
            core_action       = self._action_redownload_core
        else:
            core_action_label = "Installa"
            core_action       = self._action_update_core

        self._set_row("core",
                      "update" if new_ver else ("done" if ver else "pending"),
                      ver or "—",
                      action_label=core_action_label,
                      action=core_action)

        conda_exe = _find_conda_exe(sm)
        cver      = conda_version(conda_exe) if conda_exe else None
        self._set_row("miniconda",
                      "done" if conda_exe else "not_installed",
                      cver or "—",
                      action_label=None if conda_exe else "Installa",
                      action=None if conda_exe else lambda: self._action_install("miniconda"))

        env_ok = bool(conda_exe and os.path.isfile(python_executable(conda_exe)))
        self._set_row("conda_env",
                      "done" if env_ok else "not_installed",
                      "Python 3.12" if env_ok else "—",
                      action_label="Ricrea" if env_ok else "Crea",
                      action=self._action_recreate_env)

        pkg_ok = sm.is_done("packages")
        self._set_row("packages",
                      "done" if pkg_ok else sm.status("packages"),
                      torch_variant_label(sm.get("packages.torch_variant", "")) if pkg_ok else "—",
                      action_label="Reinstalla",
                      action=self._action_reinstall_packages)

        for m in MODELS:
            key    = f"model_{m.key}"
            exists = model_exists(sm.install_path, m.key)
            self._set_row(key,
                          "done" if exists else sm.model_status(m.key),
                          f"{sum(f.size_mb for f in m.files)} MB" if exists else "—",
                          action_label="Riscarica" if exists else "Scarica",
                          action=lambda k=m.key, f=exists: self._action_download_model(k, force=f))

        ollama_exe = find_ollama()
        ollama_ver = ollama_version(ollama_exe) if ollama_exe else None
        running    = ollama_running() if ollama_exe else False
        self._set_row("ollama",
                      "done" if ollama_exe else "not_installed",
                      (f"v{ollama_ver}" + (" ▶" if running else "")) if ollama_ver else "—",
                      action_label="Aggiorna" if ollama_exe else "Installa",
                      action=lambda: self._action_install("ollama"))

        lm_exe = find_lmstudio()
        lm_run = lm_running() if lm_exe else False
        self._set_row("lmstudio",
                      "done" if lm_exe else "not_installed",
                      ("installato" + (" ▶" if lm_run else "")) if lm_exe else "—",
                      action_label="Reinstalla" if lm_exe else "Installa",
                      action=lambda: self._action_install("lmstudio"))

        backend = self._backend_var.get()
        if backend == "ollama":
            state_ok = sm.is_done("ollama_model")
            live_ok  = is_model_pulled(OLLAMA_MODEL) if (ollama_exe and not state_ok) else False
            model_ok = state_ok or live_ok
            if live_ok and not state_ok:
                sm.mark_done("ollama_model")
            self._set_row("model_llm",
                          "done" if model_ok else ("not_installed" if ollama_exe else "pending"),
                          OLLAMA_MODEL.split(":")[0] if model_ok else ("—" if ollama_exe else "Richiede Ollama"),
                          action_label="Riscarica" if model_ok else ("Scarica" if ollama_exe else None),
                          action=self._action_pull_llm_model if ollama_exe else None)
        else:
            lms_models = api_models() if lm_exe and lm_run else []
            if not lm_exe:
                st, val, btn = "pending", "Richiede LM Studio", None
            elif not lm_run:
                st, val, btn = "not_installed", "Server non attivo", "Istruzioni"
            elif lms_models:
                st, val, btn = "done", lms_models[0].split("/")[-1], "Istruzioni"
            else:
                st, val, btn = "warning", "Nessun modello caricato", "Istruzioni"
            self._set_row("model_llm", st, val,
                          action_label=btn,
                          action=self._action_lms_instructions if btn else None)

    def _set_row(self, key, status, value, action_label=None, action=None):
        row = self._rows.get(key)
        if row:
            row.update(status, value, action_label, action)

    # ------------------------------------------------------------------
    # Azioni
    # ------------------------------------------------------------------

    def _run_bg(self, fn):
        self._set_busy(True)
        def _wrapper():
            try:
                fn()
            finally:
                self.after(0, self._set_busy, False)
        threading.Thread(target=_wrapper, daemon=True).start()

    def _set_busy(self, busy: bool):
        """Disabilita/abilita tutti i pulsanti azione durante un'operazione."""
        for row in self._rows.values():
            row.set_btn_enabled(not busy)
        if not busy:
            self._refresh_all()

    def _action_update_core(self):
        if not messagebox.askyesno("Aggiorna Core",
                                   "Scarica l'ultima versione da GitHub?\n"
                                   "Configurazione e modelli non verranno toccati."):
            return
        def _do():
            try:
                self._set_row("core", "in_progress", "Download...")
                result = ensure_core(self.app.state.install_path, force_update=True,
                                     progress_cb=self._panel.on_download_progress,
                                     log_cb=self._panel.log)
                self.app.state.mark_done("core", version=result["version"])
            except Exception as exc:
                self._panel.log(f"❌ {exc}")
        self._run_bg(_do)

    def _action_redownload_core(self):
        if not messagebox.askyesno("Riscarica Core",
                                   "Riscaricàre il codice di OffGallery?\n"
                                   "Configurazione, modelli e database non verranno toccati."):
            return
        def _do():
            try:
                self._set_row("core", "in_progress", "Download...")
                result = ensure_core(self.app.state.install_path, force_update=True,
                                     progress_cb=self._panel.on_download_progress,
                                     log_cb=self._panel.log)
                self.app.state.mark_done("core", version=result["version"])
            except Exception as exc:
                self._panel.log(f"❌ {exc}")
        self._run_bg(_do)

    def _action_reinstall_packages(self):
        if not messagebox.askyesno("Reinstalla librerie",
                                   "Reinstallare tutte le librerie Python? (~20 min)"):
            return
        def _do():
            try:
                sm         = self.app.state
                conda_exe  = _find_conda_exe(sm)
                python_exe = python_executable(conda_exe)
                variant    = detect_torch_variant()
                _inst_base = sys._MEIPASS if getattr(sys, "frozen", False) \
                    else os.path.dirname(os.path.dirname(__file__))
                req_file   = os.path.join(_inst_base, "requirements_offgallery.txt")
                self._set_row("packages", "in_progress", "Reinstallazione...")
                self._panel.set_step_indeterminate(
                    f"Librerie ({torch_variant_label(variant)})...")
                install_packages(
                    python_exe=python_exe, req_file=req_file,
                    variant=variant, log_cb=self._panel.log,
                    progress_cb=lambda c, t, p: (
                        self._panel.update_step_progress(p, c, t),
                    ),
                )
                self._panel.set_step_done("Librerie installate")
                sm.mark_done("packages", torch_variant=variant)
            except Exception as exc:
                self._panel.log(f"❌ {exc}")
        self._run_bg(_do)

    def _action_recreate_env(self):
        if not messagebox.askyesno("Ricrea ambiente",
                                   "Ricreare l'ambiente Python da zero?\n"
                                   "Le librerie andranno reinstallate dopo."):
            return
        def _do():
            try:
                conda_exe = _find_conda_exe(self.app.state)
                self._set_row("conda_env", "in_progress", "Ricreo...")
                ensure_env(conda_exe, log_cb=self._panel.log)
                self.app.state.mark_done("conda_env")
                self.app.state.reset_component("packages")
            except Exception as exc:
                self._panel.log(f"❌ {exc}")
        self._run_bg(_do)

    def _action_download_model(self, model_key: str, force: bool = False):
        if force:
            spec = next((m for m in MODELS if m.key == model_key), None)
            label = spec.label if spec else model_key
            size  = sum(f.size_mb for f in spec.files) if spec else 0
            if not messagebox.askyesno(
                "Riscarica modello",
                f"Riscaricàre {label} ({size} MB)?\n"
                f"I file esistenti verranno eliminati e riscaricati."
            ):
                return
        def _do():
            try:
                self.app.state.set_model_status(model_key, "in_progress")
                results = download_models(
                    models_dir=self.app.state.install_path,
                    keys=[model_key],
                    progress_cb=self._panel.on_model_progress,
                    log_cb=self._panel.log,
                    force=force,
                )
                status = "done" if results.get(model_key) else "error"
                self.app.state.set_model_status(model_key, status)
            except Exception as exc:
                self._panel.log(f"❌ {exc}")
        self._run_bg(_do)

    def _action_install(self, component: str):
        def _do():
            try:
                sm = self.app.state
                if component == "ollama":
                    self._set_row("ollama", "in_progress", "Installazione...")
                    res = ensure_ollama(install_if_missing=True, pull_model_flag=False,
                                        progress_cb=self._panel.on_download_progress,
                                        log_cb=self._panel.log)
                    sm.mark_done("ollama", version=res.get("version", ""))
                elif component == "lmstudio":
                    reinstall = find_lmstudio() is not None
                    self._set_row("lmstudio", "in_progress",
                                  "Reinstallazione..." if reinstall else "Installazione...")
                    ensure_lmstudio(install_if_missing=True,
                                    force_reinstall=reinstall,
                                    progress_cb=self._panel.on_download_progress,
                                    log_cb=self._panel.log)
                    sm.mark_done("lmstudio")
                elif component == "miniconda":
                    from components.miniconda import ensure_miniconda, default_install_path
                    self._set_row("miniconda", "in_progress", "Installazione...")
                    conda_exe, _ = ensure_miniconda(
                        install_path=default_install_path(),
                        progress_cb=self._panel.on_download_progress,
                        log_cb=self._panel.log)
                    sm.mark_done("miniconda",
                                 path=os.path.dirname(os.path.dirname(conda_exe)))
            except Exception as exc:
                self._panel.log(f"❌ {exc}")
        self._run_bg(_do)

    def _on_backend_change(self):
        backend = self._backend_var.get()
        if self.app.state and config_exists(self.app.state.install_path):
            ok = write_llm_backend(self.app.state.install_path, backend)
            if ok:
                self._panel.log(f"Backend LLM impostato: {backend}")
            else:
                self._panel.log("⚠ config_new.yaml non trovato — backend non salvato.")
        self._sync_backend_rows()
        self._refresh_all()

    def _sync_backend_rows(self):
        backend = self._backend_var.get()
        for key, show in [("ollama", backend == "ollama"),
                          ("lmstudio", backend == "lmstudio")]:
            row = self._rows.get(key)
            if row:
                if show:
                    row.pack(fill="x", pady=2)
                else:
                    row.pack_forget()

    def _action_lms_instructions(self):
        messagebox.showinfo("Modello LM Studio", POST_INSTALL_INSTRUCTIONS)

    def _action_pull_llm_model(self):
        model_ok = self.app.state.is_done("ollama_model") if self.app.state else False
        if model_ok:
            if not messagebox.askyesno(
                "Riscarica modello",
                f"Il modello '{OLLAMA_MODEL}' è già presente.\n"
                f"Riscaricarlo da zero?"
            ):
                return
        def _do():
            try:
                ollama_exe = find_ollama()
                if not ollama_exe:
                    self._panel.log("❌ Ollama non installato. Installa prima Ollama.")
                    return
                self._set_row("model_llm", "in_progress", "Download...")
                if not ollama_running():
                    self._panel.log("Avvio Ollama...")
                    start_server(ollama_exe, log_cb=self._panel.log)
                ok = pull_model(ollama_exe, log_cb=self._panel.log,
                                progress_cb=self._panel.on_download_progress,
                                force=model_ok)
                if ok:
                    self.app.state.mark_done("ollama_model")
            except Exception as exc:
                self._panel.log(f"❌ {exc}")
        self._run_bg(_do)

    def _launch(self):
        import subprocess
        sm  = self.app.state
        exe = python_executable(_find_conda_exe(sm)) if _find_conda_exe(sm) else "python"
        launcher = os.path.join(sm.install_path, "gui_launcher.py")
        try:
            subprocess.Popen([exe, launcher], cwd=sm.install_path, start_new_session=True)
        except Exception as exc:
            messagebox.showerror("Errore", f"Impossibile avviare OffGallery:\n{exc}")


# ---------------------------------------------------------------------------
# Riga componente
# ---------------------------------------------------------------------------

class _ComponentRow(tk.Frame):

    def __init__(self, parent, key: str, label: str, dashboard: DashboardPage,
                 tooltip: str = "", **kw):
        super().__init__(parent, bg=BG, **kw)
        self._action   = None
        self._icon_var = tk.StringVar(value="○")
        self._val_var  = tk.StringVar(value="—")

        self._icon_lbl = tk.Label(self, textvariable=self._icon_var,
                                  font=("Segoe UI", 11), bg=BG, width=3)
        self._icon_lbl.pack(side="left")

        name_lbl = tk.Label(self, text=label, font=FONT_BODY,
                             bg=BG, width=22, anchor="w")
        name_lbl.pack(side="left")

        # Indicatore tooltip
        if tooltip:
            info_lbl = tk.Label(self, text="ⓘ", font=("Segoe UI", 9),
                                bg=BG, fg="#90a4ae", cursor="question_arrow")
            info_lbl.pack(side="left", padx=(0, 6))
            _Tooltip(name_lbl, tooltip)
            _Tooltip(info_lbl, tooltip)
        else:
            tk.Label(self, text=" ", font=("Segoe UI", 9), bg=BG,
                     width=2).pack(side="left", padx=(0, 6))

        tk.Label(self, textvariable=self._val_var, font=FONT_MONO,
                 bg=BG, fg="#555", width=16, anchor="w").pack(side="left")
        self._btn = ttk.Button(self, text="", width=9, command=self._on_action)
        self._btn.pack(side="right", padx=2)
        self._btn.pack_forget()

    def update(self, status: str, value: str,
               action_label: Optional[str], action):
        icon, color = STATUS_ICONS.get(status, ("?", "#aaa"))
        def _do():
            self._icon_var.set(icon)
            self._icon_lbl.configure(fg=color)
            self._val_var.set(value)
            self._action = action
            if action_label and action:
                self._btn.configure(text=action_label)
                self._btn.pack(side="right", padx=4)
            else:
                self._btn.pack_forget()
        try:
            self.after(0, _do)
        except RuntimeError:
            pass

    def set_btn_enabled(self, enabled: bool):
        try:
            self._btn.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass

    def _on_action(self):
        if self._action:
            self._action()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _find_conda_exe(sm: StateManager) -> Optional[str]:
    conda_path = sm.get("miniconda.path", "")
    if conda_path:
        exe = conda_executable(conda_path)
        if os.path.isfile(exe):
            return exe
    return find_conda()
