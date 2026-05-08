"""
Download chunked con resume, verifica hash SHA256 e callback di progresso.
Nessuna dipendenza esterna — solo stdlib.
"""

import hashlib
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional


# Dimensione chunk di lettura (512 KB)
CHUNK_SIZE = 512 * 1024

# Timeout connessione e lettura (secondi)
CONNECT_TIMEOUT = 30
READ_TIMEOUT    = 60

# Quante volte ritentare in caso di errore transitorio
MAX_RETRIES = 3

# Pausa iniziale fra retry (raddoppia ad ogni tentativo — exponential backoff)
RETRY_DELAY_SEC = 5


@dataclass
class DownloadProgress:
    """Passato al callback ad ogni chunk scaricato."""
    filename:        str
    bytes_done:      int
    bytes_total:     int      # -1 se il server non fornisce Content-Length
    speed_bps:       float    # byte/secondo, media mobile
    elapsed_sec:     float
    eta_sec:         float    # -1 se non calcolabile


ProgressCallback = Callable[[DownloadProgress], None]


class DownloadError(Exception):
    pass

class HashMismatchError(DownloadError):
    pass

class DiskFullError(DownloadError):
    pass


# ---------------------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------------------

def download_file(
    url:              str,
    dest_path:        str,
    expected_sha256:  Optional[str] = None,
    progress_cb:      Optional[ProgressCallback] = None,
    headers:          Optional[dict] = None,
) -> str:
    """
    Scarica `url` in `dest_path` con supporto a resume, retry e verifica hash.

    - Se `dest_path` esiste già e l'hash corrisponde, salta il download.
    - Se esiste un file `.part`, riprende da dove era arrivato.
    - Chiama `progress_cb` ad ogni chunk con un oggetto DownloadProgress.
    - Se `expected_sha256` è fornito, verifica l'hash al termine e rilancia
      HashMismatchError se non corrisponde (poi cancella il file corrotto).

    Restituisce il percorso del file scaricato.
    """
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    filename = os.path.basename(dest_path)

    # File già completo e verificato?
    if os.path.isfile(dest_path) and expected_sha256:
        if _sha256(dest_path) == expected_sha256.lower():
            if progress_cb:
                size = os.path.getsize(dest_path)
                progress_cb(DownloadProgress(
                    filename=filename, bytes_done=size, bytes_total=size,
                    speed_bps=0, elapsed_sec=0, eta_sec=0,
                ))
            return dest_path

    part_path = dest_path + ".part"
    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _download_attempt(url, dest_path, part_path, filename,
                              expected_sha256, progress_cb, headers or {})
            return dest_path
        except HashMismatchError:
            raise
        except DiskFullError:
            raise
        except (urllib.error.URLError, OSError, DownloadError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY_SEC * (2 ** (attempt - 1))
                time.sleep(delay)
            continue

    raise DownloadError(
        f"Download fallito dopo {MAX_RETRIES} tentativi: {last_error}"
    )


def download_text(url: str, headers: Optional[dict] = None) -> str:
    """Scarica e restituisce il contenuto testuale di un URL (per file piccoli)."""
    req = _make_request(url, headers or {})
    try:
        with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise DownloadError(f"Impossibile scaricare {url}: {exc}") from exc


# ---------------------------------------------------------------------------
# Implementazione interna
# ---------------------------------------------------------------------------

def _download_attempt(
    url:             str,
    dest_path:       str,
    part_path:       str,
    filename:        str,
    expected_sha256: Optional[str],
    progress_cb:     Optional[ProgressCallback],
    headers:         dict,
):
    resume_from = os.path.getsize(part_path) if os.path.isfile(part_path) else 0

    req_headers = {
        "User-Agent": "OffGalleryInstaller/1.0",
        **headers,
    }
    if resume_from > 0:
        req_headers["Range"] = f"bytes={resume_from}-"

    req = _make_request(url, req_headers)

    try:
        resp = urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT)
    except urllib.error.HTTPError as exc:
        if exc.code == 416:
            # Range non soddisfacibile — il file è già completo lato server?
            # Verifica localmente.
            if os.path.isfile(part_path):
                os.replace(part_path, dest_path)
                _verify_hash(dest_path, expected_sha256)
                return
        raise

    content_length = _parse_content_length(resp)
    server_supports_resume = (resp.status == 206)

    if not server_supports_resume and resume_from > 0:
        # Il server non supporta Range → ricomincia da zero
        resume_from = 0
        if os.path.isfile(part_path):
            os.remove(part_path)

    total_bytes = (resume_from + content_length) if content_length and content_length > 0 else -1

    mode = "ab" if server_supports_resume and resume_from > 0 else "wb"
    start_time   = time.monotonic()
    bytes_done   = resume_from
    speed_window = _SpeedWindow()

    try:
        with open(part_path, mode) as out:
            while True:
                try:
                    chunk = resp.read(CHUNK_SIZE)
                except Exception as exc:
                    raise DownloadError(f"Errore lettura rete: {exc}") from exc

                if not chunk:
                    break

                try:
                    out.write(chunk)
                except OSError as exc:
                    if _is_disk_full(exc):
                        raise DiskFullError("Disco pieno durante il download.") from exc
                    raise

                bytes_done += len(chunk)
                speed_window.update(len(chunk))
                elapsed = time.monotonic() - start_time

                if progress_cb:
                    speed = speed_window.speed_bps()
                    remaining = total_bytes - bytes_done if total_bytes > 0 else -1
                    eta = (remaining / speed) if speed > 0 and remaining > 0 else -1
                    progress_cb(DownloadProgress(
                        filename=filename,
                        bytes_done=bytes_done,
                        bytes_total=total_bytes,
                        speed_bps=speed,
                        elapsed_sec=elapsed,
                        eta_sec=eta,
                    ))
    finally:
        resp.close()

    # Download completato: rinomina e verifica
    os.replace(part_path, dest_path)
    _verify_hash(dest_path, expected_sha256)


def _verify_hash(path: str, expected: Optional[str]):
    if not expected:
        return
    actual = _sha256(path)
    if actual != expected.lower():
        os.remove(path)
        raise HashMismatchError(
            f"Hash SHA256 non corrisponde per {os.path.basename(path)}.\n"
            f"Atteso:   {expected}\n"
            f"Ottenuto: {actual}"
        )


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _make_request(url: str, headers: dict) -> urllib.request.Request:
    return urllib.request.Request(url, headers=headers)


def _parse_content_length(resp) -> int:
    try:
        return int(resp.headers.get("Content-Length", -1))
    except (ValueError, TypeError):
        return -1


def _is_disk_full(exc: OSError) -> bool:
    import errno
    return exc.errno in (errno.ENOSPC, errno.EDQUOT) if hasattr(errno, "EDQUOT") \
        else exc.errno == errno.ENOSPC


class _SpeedWindow:
    """Media mobile della velocità di download su una finestra temporale."""

    WINDOW_SEC = 5.0

    def __init__(self):
        self._samples: list[tuple[float, int]] = []  # (timestamp, bytes)

    def update(self, bytes_received: int):
        now = time.monotonic()
        self._samples.append((now, bytes_received))
        cutoff = now - self.WINDOW_SEC
        self._samples = [(t, b) for t, b in self._samples if t >= cutoff]

    def speed_bps(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        total_bytes = sum(b for _, b in self._samples)
        window = self._samples[-1][0] - self._samples[0][0]
        return total_bytes / window if window > 0 else 0.0
