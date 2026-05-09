"""
Logger su disco per l'installazione.
Scrive ogni messaggio con timestamp; marca WARNING ed ERROR in modo leggibile.
"""

import os
import threading
from datetime import datetime


class InstallLogger:
    """
    Scrive i messaggi di installazione in un file di testo con timestamp.

    Uso:
        logger = InstallLogger(install_path)
        logger.log("messaggio")          # usabile come log_cb
        logger.log("⚠️ qualcosa")        # riconoscerà warning da simboli
        logger.close()
    """

    def __init__(self, install_path: str):
        os.makedirs(install_path, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = os.path.join(install_path, f"installer_log_{timestamp}.txt")
        self._lock = threading.Lock()
        self._f = open(self.log_path, "w", encoding="utf-8")
        self._write_header()

    def _write_header(self):
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self._f.write(f"{'='*60}\n")
        self._f.write(f"  OffGallery Manager — Log installazione\n")
        self._f.write(f"  Avviato il {now}\n")
        self._f.write(f"{'='*60}\n\n")
        self._f.flush()

    def log(self, message: str):
        """Scrive una riga nel log. Thread-safe. Usabile come log_cb."""
        if not message:
            return
        ts = datetime.now().strftime("%H:%M:%S")

        # Classifica il livello dal contenuto del messaggio
        upper = message.upper()
        if any(x in upper for x in ("❌", "ERRORE", "ERROR", "FALLITO", "FAILED", "EXCEPTION")):
            level = "ERROR  "
        elif any(x in upper for x in ("⚠", "WARNING", "ATTENZIONE", "WARN")):
            level = "WARNING"
        else:
            level = "INFO   "

        line = f"[{ts}] {level}  {message}\n"
        with self._lock:
            self._f.write(line)
            self._f.flush()

    def section(self, title: str):
        """Scrive un separatore di sezione leggibile."""
        with self._lock:
            self._f.write(f"\n{'─'*60}\n  {title}\n{'─'*60}\n")
            self._f.flush()

    def summary(self, results: dict[str, bool]):
        """Scrive il riepilogo finale con esito per ogni componente."""
        with self._lock:
            self._f.write(f"\n{'='*60}\n  RIEPILOGO INSTALLAZIONE\n{'='*60}\n")
            for component, ok in results.items():
                mark = "✓ OK    " if ok else "✗ ERRORE"
                self._f.write(f"  {mark}  {component}\n")
            self._f.write(f"\n  Log completo: {self.log_path}\n")
            self._f.write(f"{'='*60}\n")
            self._f.flush()

    def close(self):
        with self._lock:
            try:
                self._f.write(f"\n[{datetime.now().strftime('%H:%M:%S')}] Log chiuso.\n")
                self._f.close()
            except Exception:
                pass

    @property
    def path(self) -> str:
        return self.log_path
