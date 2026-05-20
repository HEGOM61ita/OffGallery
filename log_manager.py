"""
Gestione centralizzata del file di log di sessione.

Crea un FileHandler al primo avvio (DEBUG) che rimane aperto per tutta la sessione.
Dopo lo startup, applica la modalità configurata dall'utente:
  - debug mode (show_debug=True):  root logger a DEBUG, tutto nel log UI + file
  - produzione (show_debug=False): root logger a WARNING, il runtime non genera
                                   DEBUG/INFO, file riceve solo WARNING+

Il flag _startup_complete impedisce che load_config() cambi il livello
durante l'init della MainWindow (quando vogliamo ancora catturare tutto).
"""

import logging
from datetime import datetime
from pathlib import Path

_file_handler: "logging.FileHandler | None" = None
_debug_mode: bool = True
_startup_complete: bool = False


def setup(app_dir: Path) -> None:
    """
    Da chiamare prima di tutto il resto (in gui_launcher.py).
    Crea la directory logs/ e apre il file di log per questa sessione.
    """
    global _file_handler

    logs_dir = app_dir / 'logs'
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = logs_dir / f'{timestamp}.log'

    _file_handler = logging.FileHandler(log_path, encoding='utf-8')
    _file_handler.setLevel(logging.DEBUG)  # il file raccoglie sempre tutto
    _file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    ))

    root = logging.getLogger()
    root.addHandler(_file_handler)
    root.setLevel(logging.DEBUG)


def startup_complete(debug_mode: bool) -> None:
    """
    Da chiamare in run_with_splash() dopo restore_log_capture(), a splash chiusa.
    Da questo momento applica la modalità configurata dall'utente.
    """
    global _startup_complete
    _startup_complete = True
    set_debug_mode(debug_mode)


def set_debug_mode(enabled: bool) -> None:
    """
    Cambia modalità a runtime (es. quando l'utente modifica lo switch in config).
    Durante lo startup (_startup_complete=False) il livello rimane DEBUG
    per catturare interamente la fase di inizializzazione.
    """
    global _debug_mode
    _debug_mode = enabled

    if not _startup_complete:
        return  # startup non ancora completato: il livello rimane DEBUG

    level = logging.DEBUG if enabled else logging.WARNING
    logging.getLogger().setLevel(level)


def is_debug_mode() -> bool:
    return _debug_mode
