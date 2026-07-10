"""
Widget di progresso riutilizzabili per l'installer.
Thread-safe: gli aggiornamenti da thread secondari usano widget.after().
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional

from components.models import ModelProgress
from utils.download import DownloadProgress


# ---------------------------------------------------------------------------
# Formattatori
# ---------------------------------------------------------------------------

def fmt_bytes(n: int) -> str:
    """Formatta bytes in stringa leggibile (es. '2.3 GB', '450 MB')."""
    if n < 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_speed(bps: float) -> str:
    """Formatta velocità in stringa leggibile (es. '8.3 MB/s')."""
    if bps <= 0:
        return "—"
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024:
            return f"{bps:.1f} {unit}"
        bps /= 1024
    return f"{bps:.1f} GB/s"


def fmt_eta(seconds: float) -> str:
    """Formatta ETA in stringa leggibile (es. '4 min 23 sec', '~2 ore')."""
    if seconds < 0:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} sec"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m} min {s:02d} sec"
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"~{h} ore {m} min"


# ---------------------------------------------------------------------------
# ProgressBar — singola barra con etichette
# ---------------------------------------------------------------------------

class ProgressBar(tk.Frame):
    """
    Barra di progresso con:
    - Titolo / nome file
    - Barra grafica ttk
    - "X MB / Y MB"
    - Velocità e ETA su una riga
    - Modalità indeterminata (spinner) quando il totale non è noto
    """

    def __init__(self, parent, title: str = "", **kw):
        super().__init__(parent, **kw)
        self._build(title)

    def _build(self, title: str):
        self.configure(bg=self.master["bg"] if hasattr(self.master, "__getitem__") else "#f5f5f5")

        self._title_var = tk.StringVar(value=title)
        self._size_var  = tk.StringVar(value="")
        self._info_var  = tk.StringVar(value="")

        tk.Label(self, textvariable=self._title_var,
                 anchor="w", font=("Segoe UI", 10),
                 bg=self["bg"]).pack(fill="x", pady=(4, 0))

        self._bar = ttk.Progressbar(self, length=400, mode="determinate")
        self._bar.pack(fill="x", pady=2)

        info_frame = tk.Frame(self, bg=self["bg"])
        info_frame.pack(fill="x")

        tk.Label(info_frame, textvariable=self._size_var,
                 anchor="w", font=("Segoe UI", 9), fg="#555",
                 bg=self["bg"]).pack(side="left")

        tk.Label(info_frame, textvariable=self._info_var,
                 anchor="e", font=("Segoe UI", 9), fg="#555",
                 bg=self["bg"]).pack(side="right")

    # ---- API pubblica ----

    def set_title(self, title: str):
        self._safe(self._title_var.set, title)

    def set_indeterminate(self, running: bool):
        def _do():
            if running:
                self._bar.configure(mode="indeterminate")
                self._bar.start(15)
            else:
                self._bar.stop()
                self._bar.configure(mode="determinate")
        self._safe(_do)

    def update_progress(self, done: int, total: int,
                        speed_bps: float = 0, eta_sec: float = -1):
        """Aggiorna la barra. Può essere chiamato da qualsiasi thread."""
        def _do():
            if total > 0:
                pct = min(done / total * 100, 100)
                self._bar["value"] = pct
                self._size_var.set(f"{fmt_bytes(done)} / {fmt_bytes(total)}")
            else:
                self._bar["value"] = 0
                self._size_var.set(fmt_bytes(done) if done > 0 else "")

            parts = []
            if speed_bps > 0:
                parts.append(fmt_speed(speed_bps))
            if eta_sec >= 0:
                parts.append(f"Rimanente: {fmt_eta(eta_sec)}")
            self._info_var.set("  •  ".join(parts))

        self._safe(_do)

    def set_complete(self, label: str = "Completato"):
        def _do():
            self._bar["value"] = 100
            self._size_var.set(label)
            self._info_var.set("")
        self._safe(_do)

    def reset(self, title: str = ""):
        def _do():
            self._bar["value"] = 0
            self._title_var.set(title)
            self._size_var.set("")
            self._info_var.set("")
        self._safe(_do)

    def _safe(self, fn, *args):
        """Esegue fn sul thread principale anche se chiamato da un thread secondario."""
        try:
            if args:
                self.after(0, fn, *args)
            else:
                self.after(0, fn)
        except RuntimeError:
            pass   # widget distrutto


# ---------------------------------------------------------------------------
# DownloadPanel — barra file + barra globale + log
# ---------------------------------------------------------------------------

class DownloadPanel(tk.Frame):
    """
    Pannello completo per il download dei modelli con:
    - Barra del file corrente
    - Barra globale (modello N di M)
    - Box di log scrollabile
    """

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._build()

    def _build(self):
        bg = "#f5f5f5"
        self.configure(bg=bg)

        # -- Unica barra: spinner o download
        self._file_bar = ProgressBar(self, bg=bg)
        self._file_bar.pack(fill="x", padx=12, pady=(12, 4))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=12, pady=4)

        # -- Log
        log_frame = tk.Frame(self, bg=bg)
        log_frame.pack(fill="both", expand=True, padx=(12, 4), pady=(4, 12))

        tk.Label(log_frame, text="Dettagli:", anchor="w",
                 font=("Segoe UI", 9), bg=bg).pack(anchor="w")

        self._log_text = tk.Text(
            log_frame, height=6, state="disabled",
            font=("Consolas", 8), bg="#1e1e1e", fg="#d4d4d4",
            relief="flat", wrap="word",
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True, side="left")
        self._log_text.configure(yscrollcommand=scrollbar.set)

    # ---- Aggiornamenti download modello ----

    def on_model_progress(self, p: ModelProgress):
        """
        Callback da passare a models.download_models().
        Può essere chiamato da qualsiasi thread.
        """
        title = (f"Modello {p.model_index + 1}/{p.model_count}  —  "
                 f"{p.model_label}  —  {p.file_name}")
        self._file_bar.set_title(title)
        self._file_bar.update_progress(
            p.bytes_done, p.bytes_total,
            speed_bps=p.speed_bps, eta_sec=p.eta_sec,
        )

    def on_download_progress(self, p: DownloadProgress):
        """Callback per download singoli (Miniconda, Ollama, ecc.)."""
        self._file_bar.set_title(p.filename)
        self._file_bar.update_progress(
            p.bytes_done, p.bytes_total,
            speed_bps=p.speed_bps, eta_sec=p.eta_sec,
        )

    def on_plugin_progress(self, p):
        """Callback da passare a plugins.download_plugins()."""
        title = (f"Plugin {p.plugin_index + 1}/{p.plugin_count}  —  "
                 f"{p.plugin_label}")
        self._file_bar.set_title(title)
        self._file_bar.update_progress(
            p.bytes_done, p.bytes_total,
            speed_bps=p.speed_bps, eta_sec=p.eta_sec,
        )

    def log(self, message: str):
        """Aggiunge una riga al log. Thread-safe."""
        def _do():
            self._log_text.configure(state="normal")
            self._log_text.insert("end", message + "\n")
            self._log_text.see("end")
            self._log_text.configure(state="disabled")
        try:
            self.after(0, _do)
        except RuntimeError:
            pass

    def set_step_indeterminate(self, title: str):
        """Mostra uno spinner per operazioni senza progresso misurabile."""
        self._file_bar.set_title(title)
        self._file_bar.set_indeterminate(True)

    def set_step_done(self, label: str = "Completato"):
        self._file_bar.set_indeterminate(False)
        self._file_bar.set_complete(label)

    def update_step_progress(self, title: str, done: int, total: int):
        """Aggiorna la barra con progresso determinato (es. pacchetti pip)."""
        self._file_bar.set_indeterminate(False)
        self._file_bar.set_title(f"{title}  ({done}/{total})")
        self._file_bar.update_progress(done, total)


# ---------------------------------------------------------------------------
# StepIndicator — fasi dell'installazione
# ---------------------------------------------------------------------------

class StepIndicator(tk.Frame):
    """
    Lista verticale delle fasi con icona di stato:
    ○ In attesa  →  ⟳ In corso  →  ✓ Fatto  |  ✗ Errore
    """

    _ICONS = {
        "pending":     ("○", "#aaa"),
        "in_progress": ("⟳", "#1976d2"),
        "done":        ("✓", "#388e3c"),
        "error":       ("✗", "#c62828"),
        "skipped":     ("—", "#aaa"),
    }

    def __init__(self, parent, steps: list[str], **kw):
        super().__init__(parent, **kw)
        self._rows: dict[str, tuple[tk.Label, tk.Label]] = {}
        self._build(steps)

    def _build(self, steps: list[str]):
        bg = self["bg"] if self["bg"] else "#f5f5f5"
        for step in steps:
            row = tk.Frame(self, bg=bg)
            row.pack(fill="x", pady=2)

            icon_lbl = tk.Label(row, text="○", fg="#aaa",
                                font=("Segoe UI", 12), bg=bg, width=2)
            icon_lbl.pack(side="left")

            text_lbl = tk.Label(row, text=step, anchor="w",
                                font=("Segoe UI", 10), bg=bg)
            text_lbl.pack(side="left", fill="x", expand=True)

            self._rows[step] = (icon_lbl, text_lbl)

    def set_status(self, step: str, status: str, detail: str = ""):
        if step not in self._rows:
            return
        icon_lbl, text_lbl = self._rows[step]
        icon, color = self._ICONS.get(status, ("?", "#aaa"))

        def _do():
            icon_lbl.configure(text=icon, fg=color)
            label = step if not detail else f"{step}  {detail}"
            text_lbl.configure(text=label)

        try:
            self.after(0, _do)
        except RuntimeError:
            pass
