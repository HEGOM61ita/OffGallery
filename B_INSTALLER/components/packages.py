"""
Installazione delle librerie Python nell'ambiente conda OffGallery.
Rileva la GPU/CUDA e sceglie la variante PyTorch corretta.
"""

import os
import platform
import re
import subprocess
from typing import Optional

from utils.preflight import check_gpu


# ---------------------------------------------------------------------------
# Varianti PyTorch per CUDA
# ---------------------------------------------------------------------------

TORCH_VARIANTS = {
    "cuda121":   "https://download.pytorch.org/whl/cu121",
    "cuda118":   "https://download.pytorch.org/whl/cu118",
    "rocm":      "https://download.pytorch.org/whl/rocm6.0",  # AMD Linux
    "directml":  None,   # AMD/Intel/NVIDIA su Windows via DirectX 12 — pacchetto separato
    "cpu":       "https://download.pytorch.org/whl/cpu",
    "mps":       None,   # macOS Apple Silicon: PyPI standard, MPS incluso
}

# Versioni pinnate critiche per compatibilità con CLIP ViT-L/14
PINNED_PACKAGES = [
    "transformers==4.57.3",
    "huggingface-hub==0.36.0",
    "open-clip-torch==3.2.0",
]


# ---------------------------------------------------------------------------
# Rilevamento variante PyTorch
# ---------------------------------------------------------------------------

def detect_torch_variant(log_cb: Optional[callable] = None) -> str:
    """
    Rileva la GPU e restituisce la variante PyTorch da installare.

    Valori possibili: "cuda121" | "cuda118" | "rocm" | "mps" | "cpu"
    """
    result = check_gpu()

    # macOS Apple Silicon → MPS
    if "Apple Silicon" in result.value or "Metal" in result.value:
        _log(log_cb, f"✓ GPU rilevata: {result.value} → variante mps")
        return "mps"

    # NVIDIA con CUDA
    if "CUDA" in result.message:
        cuda_ver = _extract_cuda_version(result.message)
        if cuda_ver and cuda_ver >= (12, 1):
            variant = "cuda121"
        elif cuda_ver and cuda_ver >= (11, 8):
            variant = "cuda118"
        else:
            variant = "cpu"
            _log(log_cb, f"⚠ GPU NVIDIA rilevata ({result.value}) ma driver troppo vecchio"
                         f" — aggiornare i driver NVIDIA → variante cpu")
            return variant
        _log(log_cb, f"✓ GPU rilevata: {result.value} — {result.message.split('—')[0].strip()}"
                     f" → variante {variant}")
        return variant

    # AMD su Linux con ROCm
    if "ROCm" in result.message:
        _log(log_cb, f"✓ GPU AMD rilevata: {result.value} — {result.message.split('—')[0].strip()}"
                     f" → variante rocm")
        return "rocm"

    # AMD su Windows con DirectML
    if "DirectML" in result.message:
        _log(log_cb, f"✓ GPU AMD rilevata: {result.value} — DirectX 12 compatibile"
                     f" → variante directml (torch-directml)")
        return "directml"

    # CPU fallback — log con motivo specifico per piattaforma
    if platform.system() == "Windows":
        _log(log_cb, "⚠ Nessuna GPU NVIDIA o AMD DirectX 12 rilevata"
                     " → variante cpu")
    elif platform.system() == "Linux":
        _log(log_cb, "⚠ nvidia-smi e rocminfo non trovati — nessuna GPU dedicata rilevata"
                     " → variante cpu")
    else:
        _log(log_cb, "⚠ Nessuna GPU rilevata → variante cpu")
    return "cpu"


def torch_variant_label(variant: str) -> str:
    """Etichetta leggibile della variante per la UI."""
    return {
        "cuda121":  "NVIDIA GPU (CUDA 12.1)",
        "cuda118":  "NVIDIA GPU (CUDA 11.8)",
        "rocm":     "AMD GPU (ROCm 6.0, Linux)",
        "directml": "AMD GPU (DirectML, Windows)",
        "mps":      "Apple Silicon (Metal/MPS)",
        "cpu":      "CPU (senza GPU)",
    }.get(variant, variant)


# ---------------------------------------------------------------------------
# Installazione pacchetti
# ---------------------------------------------------------------------------

def install_packages(
    python_exe:  str,
    req_file:    str,
    variant:     str,
    log_cb:      Optional[callable] = None,
    progress_cb: Optional[callable] = None,
) -> None:
    """
    Installa tutte le librerie da `req_file` nell'env OffGallery.

    1. Installa PyTorch con l'index-url corretto per la variante GPU.
    2. Installa il resto dei requirements.
    3. Forza le versioni pinnate critiche.

    `progress_cb(current, total, package_name)` viene chiamato
    ad ogni pacchetto installato.
    """
    _log(log_cb, f"Variante PyTorch selezionata: {torch_variant_label(variant)}")

    # Step 1: PyTorch
    _install_torch(python_exe, variant, log_cb, progress_cb)

    # Step 2: requirements completi (pip salta torch già installato)
    _log(log_cb, f"Installazione librerie da: {req_file}")
    _pip_install_requirements(python_exe, req_file, log_cb, progress_cb)

    # Step 3: forza versioni pinnate (sovrascrive eventuali versioni diverse)
    _log(log_cb, "Applicazione versioni pinnate critiche...")
    _pip_install_packages(python_exe, PINNED_PACKAGES, log_cb)

    _log(log_cb, "Installazione librerie completata.")


def verify_packages(python_exe: str, log_cb: Optional[callable] = None) -> bool:
    """
    Verifica che i pacchetti critici siano importabili.
    Restituisce True se tutto OK, False se qualcosa manca.
    """
    checks = [
        ("torch",          "import torch; print(torch.__version__)"),
        ("transformers",   "import transformers; print(transformers.__version__)"),
        ("open_clip",      "import open_clip; print(open_clip.__version__)"),
        ("PIL",            "from PIL import Image; print('ok')"),
    ]
    all_ok = True
    for name, code in checks:
        try:
            out = subprocess.check_output(
                [python_exe, "-c", code],
                text=True, stderr=subprocess.DEVNULL, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
            ).strip()
            _log(log_cb, f"  ✓ {name}: {out}")
        except Exception:
            _log(log_cb, f"  ✗ {name}: non importabile")
            all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# Installazione PyTorch
# ---------------------------------------------------------------------------

def _install_torch(
    python_exe:  str,
    variant:     str,
    log_cb:      Optional[callable],
    progress_cb: Optional[callable],
):
    # DirectML: PyTorch CPU standard + torch-directml come backend
    # torch-directml non richiede un index-url separato ed è compatibile
    # con PyTorch CPU. Non installare torchvision/torchaudio da whl GPU.
    if variant == "directml":
        _log(log_cb, "Installazione PyTorch CPU (base per DirectML)...")
        cmd_torch = [python_exe, "-m", "pip", "install",
                     "torch", "torchvision", "torchaudio",
                     "--index-url", TORCH_VARIANTS["cpu"]]
        _run_pip(cmd_torch, log_cb, progress_cb, phase_label="PyTorch")

        _log(log_cb, "Installazione torch-directml (backend AMD/DirectX 12)...")
        cmd_dml = [python_exe, "-m", "pip", "install", "torch-directml"]
        _run_pip(cmd_dml, log_cb, progress_cb, phase_label="torch-directml")
        return

    packages = ["torch", "torchvision", "torchaudio"]
    index_url = TORCH_VARIANTS.get(variant)

    cmd = [python_exe, "-m", "pip", "install"] + packages

    if index_url:
        cmd += ["--index-url", index_url]

    _log(log_cb, f"Installazione PyTorch ({variant})...")
    _run_pip(cmd, log_cb, progress_cb, phase_label="PyTorch")


# ---------------------------------------------------------------------------
# Installazione requirements
# ---------------------------------------------------------------------------

def _pip_install_requirements(
    python_exe:  str,
    req_file:    str,
    log_cb:      Optional[callable],
    progress_cb: Optional[callable],
):
    if not os.path.isfile(req_file):
        raise FileNotFoundError(f"File requirements non trovato: {req_file}")

    cmd = [
        python_exe, "-m", "pip", "install",
        "-r", req_file,
        "--no-warn-script-location",
    ]
    _run_pip(cmd, log_cb, progress_cb, phase_label="Librerie")


def _pip_install_packages(
    python_exe: str,
    packages:   list[str],
    log_cb:     Optional[callable],
):
    cmd = [python_exe, "-m", "pip", "install"] + packages
    _run_pip(cmd, log_cb, progress_cb=None, phase_label="Versioni pinnate")


# ---------------------------------------------------------------------------
# Runner pip con parsing output
# ---------------------------------------------------------------------------

def _run_pip(
    cmd:          list[str],
    log_cb:       Optional[callable],
    progress_cb:  Optional[callable],
    phase_label:  str = "",
):
    """
    Lancia pip e processa l'output riga per riga.
    Chiama progress_cb(current, total, package_name) quando rileva
    "Installing collected packages: a, b, c" nell'output di pip.
    """
    _log(log_cb, f"$ {' '.join(cmd)}")

    flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=_pip_env(),
            creationflags=flags,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Python non trovato: {cmd[0]}") from exc

    packages_to_install: list[str] = []
    installed_count = 0

    for line in proc.stdout:
        line = line.replace("\r", "").rstrip()
        if not line:
            continue
        _log(log_cb, line)

        # "Collecting package-name"
        if line.startswith("Collecting "):
            pkg = line.removeprefix("Collecting ").split()[0]
            if pkg not in packages_to_install:
                packages_to_install.append(pkg)

        # "Installing collected packages: a, b, c"
        elif line.startswith("Installing collected packages:"):
            pkgs_str = line.split(":", 1)[1].strip()
            packages_to_install = [p.strip() for p in pkgs_str.split(",")]
            installed_count = 0

        # "  Successfully installed package-1.0 other-2.0"
        elif "Successfully installed" in line:
            installed_count = len(packages_to_install)
            if progress_cb and packages_to_install:
                progress_cb(installed_count, len(packages_to_install),
                            phase_label)

        # Aggiorna progresso ad ogni pacchetto durante il download
        elif line.startswith("  Downloading ") or line.startswith("  Using cached "):
            installed_count += 1
            if progress_cb and packages_to_install:
                pkg_name = _parse_downloading_pkg(line)
                progress_cb(installed_count, max(len(packages_to_install), 1),
                            pkg_name or phase_label)

    try:
        proc.wait(timeout=1800)   # 30 minuti max
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError("Timeout: pip ha impiegato più di 30 minuti.")

    if proc.returncode != 0:
        raise RuntimeError(
            f"pip terminato con codice {proc.returncode}. "
            "Controlla il log per i dettagli."
        )


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _extract_cuda_version(message: str) -> Optional[tuple[int, int]]:
    """Estrae la versione CUDA da stringhe tipo 'CUDA 12.1 compatibile'."""
    match = re.search(r"CUDA\s+(\d+)\.(\d+)", message)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def _parse_downloading_pkg(line: str) -> Optional[str]:
    """Estrae il nome pacchetto da 'Downloading package_name-1.0-...'."""
    match = re.search(r"Downloading\s+([\w\-]+)", line)
    return match.group(1) if match else None


def _pip_env() -> dict:
    """Variabili d'ambiente per pip: disabilita output con colori ANSI."""
    env = os.environ.copy()
    env["PIP_NO_COLOR"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    # Evita che pip mostri la progress bar interna (usiamo la nostra)
    env["PIP_PROGRESS_BAR"] = "off"
    return env


def _log(cb: Optional[callable], msg: str):
    if cb:
        cb(msg)
