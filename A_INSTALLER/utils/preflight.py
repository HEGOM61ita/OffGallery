"""
Controlli preliminari del sistema prima dell'installazione.
Nessuna dipendenza esterna — solo stdlib.
"""

import glob
import os
import platform
import shutil
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(Enum):
    OK      = "ok"
    WARNING = "warning"
    ERROR   = "error"
    INFO    = "info"


@dataclass
class CheckResult:
    name: str
    severity: Severity
    value: str        # testo da mostrare nella colonna valore (es. "16 GB")
    message: str      # testo da mostrare nella riga di dettaglio sotto (vuoto se OK)
    action: str = ""  # etichetta del pulsante azione opzionale (es. "Cambia disco")


@dataclass
class PreflightReport:
    results: list[CheckResult] = field(default_factory=list)
    estimated_size_gb: float = 0.0
    estimated_minutes: int = 0
    can_proceed: bool = True   # False se almeno un check è ERROR

    def add(self, result: CheckResult):
        self.results.append(result)
        if result.severity == Severity.ERROR:
            self.can_proceed = False


# ---------------------------------------------------------------------------
# Soglie
# ---------------------------------------------------------------------------

RAM_WARN_GB   = 8
RAM_ERROR_GB  = 4
DISK_WARN_GB  = 20
DISK_ERROR_GB = 15
NET_WARN_MBPS = 5.0

# File da Cloudflare via HTTP — evita problemi SSL nel bundle PyInstaller
SPEED_TEST_URL   = "http://speed.cloudflare.com/__down?bytes=100000"
SPEED_TEST_BYTES = 100_000  # 100 KB


# ---------------------------------------------------------------------------
# Check individuali
# ---------------------------------------------------------------------------

def check_os() -> CheckResult:
    system  = platform.system()
    machine = platform.machine()
    version = platform.version()

    if system == "Windows":
        # platform.version() → "10.0.19041" su Win10, "10.0.22000" su Win11
        try:
            build = int(platform.version().split(".")[2])
        except (IndexError, ValueError):
            build = 0
        if build >= 22000:
            label = "Windows 11 64-bit"
        else:
            label = "Windows 10 64-bit"
        ok = (machine in ("AMD64", "x86_64"))
        return CheckResult(
            name="Sistema operativo",
            severity=Severity.OK if ok else Severity.ERROR,
            value=label,
            message="" if ok else "Richiede Windows 10 a 64-bit o superiore.",
        )

    if system == "Darwin":
        mac_ver = platform.mac_ver()[0]   # es. "13.5.1"
        is_arm  = (machine == "arm64")
        chip    = "Apple Silicon" if is_arm else "Intel"
        try:
            major = int(mac_ver.split(".")[0])
            ok = (major >= 12)
        except (IndexError, ValueError):
            ok = False
        label = f"macOS {mac_ver} ({chip})"
        return CheckResult(
            name="Sistema operativo",
            severity=Severity.OK if ok else Severity.ERROR,
            value=label,
            message="" if ok else "Richiede macOS 12 Monterey o superiore.",
        )

    if system == "Linux":
        distro = _linux_distro()
        ok = (machine in ("x86_64", "aarch64"))
        return CheckResult(
            name="Sistema operativo",
            severity=Severity.OK if ok else Severity.ERROR,
            value=f"Linux {distro} 64-bit",
            message="" if ok else "Richiede Linux a 64-bit.",
        )

    return CheckResult(
        name="Sistema operativo",
        severity=Severity.ERROR,
        value=system,
        message="Sistema operativo non supportato.",
    )


def check_ram() -> CheckResult:
    gb = _ram_total_gb()
    if gb is None:
        return CheckResult(
            name="RAM disponibile",
            severity=Severity.INFO,
            value="Non rilevata",
            message="Impossibile rilevare la RAM. Si procede comunque.",
        )

    label = f"{gb:.0f} GB"
    if gb >= RAM_WARN_GB:
        return CheckResult(name="RAM disponibile", severity=Severity.OK,
                           value=label, message="")
    if gb >= RAM_ERROR_GB:
        return CheckResult(
            name="RAM disponibile",
            severity=Severity.WARNING,
            value=label,
            message="Con meno di 8 GB l'elaborazione sarà lenta. "
                    "Si consiglia di non installare Ollama.",
        )
    return CheckResult(
        name="RAM disponibile",
        severity=Severity.ERROR,
        value=label,
        message="OffGallery richiede almeno 4 GB di RAM.",
    )


def check_disk(path: str) -> CheckResult:
    """Controlla lo spazio libero sul disco che contiene `path`."""
    try:
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024 ** 3)
    except OSError:
        return CheckResult(
            name="Spazio disco",
            severity=Severity.ERROR,
            value="Errore lettura disco",
            message=f"Impossibile leggere il disco: {path}",
            action="Cambia disco",
        )

    label = f"{free_gb:.0f} GB liberi su {_drive_label(path)}"
    if free_gb >= DISK_WARN_GB:
        return CheckResult(name="Spazio disco", severity=Severity.OK,
                           value=label, message="")
    if free_gb >= DISK_ERROR_GB:
        return CheckResult(
            name="Spazio disco",
            severity=Severity.WARNING,
            value=label,
            message="Spazio appena sufficiente. Si consiglia almeno 25 GB liberi.",
            action="Cambia disco",
        )
    return CheckResult(
        name="Spazio disco",
        severity=Severity.ERROR,
        value=label,
        message="Servono almeno 15 GB liberi. Libera spazio o scegli un altro disco.",
        action="Cambia disco",
    )


def check_internet() -> CheckResult:
    """Verifica connessione e stima la velocità scaricando pochi KB."""
    # 1. Ping rapido
    if not _has_connectivity():
        return CheckResult(
            name="Connessione internet",
            severity=Severity.ERROR,
            value="Non disponibile",
            message="Connessione internet assente. Necessaria per scaricare i componenti.",
        )

    # 2. Stima velocità
    mbps = _estimate_speed_mbps()
    if mbps is None:
        return CheckResult(
            name="Connessione internet",
            severity=Severity.WARNING,
            value="Disponibile (velocità non stimabile)",
            message="Impossibile stimare la velocità. I tempi potrebbero essere più lunghi del previsto.",
        )

    label = f"{mbps:.1f} Mb/s (stimati)"
    if mbps >= NET_WARN_MBPS:
        return CheckResult(name="Connessione internet", severity=Severity.OK,
                           value=label, message="")
    return CheckResult(
        name="Connessione internet",
        severity=Severity.WARNING,
        value=label,
        message="Connessione lenta. Il download dei modelli (~7 GB) potrebbe richiedere ore.",
    )


def check_gpu() -> CheckResult:
    """Rileva GPU e compatibilità CUDA (Windows/Linux) o Metal (macOS Apple Silicon)."""
    system  = platform.system()
    machine = platform.machine()

    # macOS Apple Silicon — Metal/MPS garantito
    if system == "Darwin" and machine == "arm64":
        return CheckResult(
            name="GPU",
            severity=Severity.OK,
            value="Apple Silicon — Metal/MPS",
            message="",
        )

    # Prova nvidia-smi
    gpu_name, cuda_ver = _nvidia_smi_info()
    if gpu_name:
        return CheckResult(
            name="GPU",
            severity=Severity.OK,
            value=f"{gpu_name}",
            message=f"CUDA {cuda_ver} compatibile — PyTorch GPU verrà installato.",
        )

    # AMD su Linux (ROCm)
    amd_name, rocm_ver = _amd_rocm_info()
    if amd_name:
        rocm_label = f"ROCm {rocm_ver}" if rocm_ver else "ROCm"
        return CheckResult(
            name="GPU",
            severity=Severity.OK,
            value=f"{amd_name}",
            message=f"{rocm_label} compatibile — PyTorch ROCm verrà installato.",
        )

    # AMD su Windows (DirectML — richiede DirectX 12 e driver aggiornati)
    amd_win_name = _amd_dx12_info()
    if amd_win_name:
        return CheckResult(
            name="GPU",
            severity=Severity.OK,
            value=amd_win_name,
            message="DirectX 12 compatibile — PyTorch DirectML verrà installato "
                    "(torch-directml). Prestazioni inferiori a CUDA ma superiori a CPU.",
        )

    # Nessuna GPU dedicata — CPU-only, non è un errore
    return CheckResult(
        name="GPU",
        severity=Severity.INFO,
        value="Non rilevata (CPU-only)",
        message="OffGallery funziona senza GPU, ma l'elaborazione sarà più lenta.",
    )


# ---------------------------------------------------------------------------
# Report completo
# ---------------------------------------------------------------------------

def run_preflight(install_path: str, profile: str = "leggero") -> PreflightReport:
    """
    Esegue tutti i check e restituisce un PreflightReport.
    `profile` influenza le stime di spazio e tempo.
    """
    report = PreflightReport()

    report.add(check_os())
    report.add(check_ram())
    report.add(check_disk(install_path))
    report.add(check_internet())
    report.add(check_gpu())

    # Stima spazio e tempo in base al profilo e alla GPU presente
    gpu_result = next((r for r in report.results if r.name == "GPU"), None)
    has_cuda     = gpu_result and "CUDA" in gpu_result.message
    has_directml = gpu_result and "DirectML" in gpu_result.message
    has_rocm     = gpu_result and "ROCm" in gpu_result.message
    has_ollama   = (profile == "completo")

    size_gb = 7.0   # env CPU-only
    if has_cuda or has_rocm:
        size_gb = 10.5  # env CUDA/ROCm (~3.5 GB PyTorch GPU)
    elif has_directml:
        size_gb = 7.5   # env CPU + torch-directml (~500 MB extra)
    size_gb += 6.7   # modelli AI
    if has_ollama:
        size_gb += 5.5  # Ollama + qwen3-vl

    # Stima tempo: approssimata, dipende molto dalla connessione
    net_result = next((r for r in report.results if r.name == "Connessione internet"), None)
    mbps = _parse_mbps(net_result.value) if net_result else None
    if mbps and mbps > 0:
        download_gb = size_gb * 0.85  # ~85% è download
        download_min = (download_gb * 1024 * 8) / (mbps * 60)
        install_min = 10
        total_min = int(download_min + install_min)
    else:
        total_min = 60  # fallback conservativo

    report.estimated_size_gb = round(size_gb, 1)
    report.estimated_minutes = max(total_min, 10)

    return report


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _ram_total_gb() -> Optional[float]:
    system = platform.system()
    try:
        if system == "Windows":
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
                text=True, stderr=subprocess.DEVNULL, timeout=10,
                creationflags=flags,
            )
            bytes_ = int(out.strip())
            return bytes_ / (1024 ** 3)

        if system == "Darwin":
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"],
                text=True, stderr=subprocess.DEVNULL
            )
            return int(out.strip()) / (1024 ** 3)

        if system == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024 ** 2)
    except Exception:
        pass
    return None


def _nvidia_smi_info() -> tuple[Optional[str], Optional[str]]:
    """
    Restituisce (nome GPU, versione CUDA) o (None, None).
    Cerca nvidia-smi nel PATH e, su Windows, anche nel DriverStore
    dove i driver NVIDIA lo installano senza aggiungerlo al PATH.
    """
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

    candidates = ["nvidia-smi"]
    if platform.system() == "Windows":
        pattern = (r"C:\Windows\System32\DriverStore\FileRepository"
                   r"\nv_dispi.inf_amd64_*\nvidia-smi.exe")
        candidates += glob.glob(pattern)

    for cmd in candidates:
        try:
            out = subprocess.check_output(
                [cmd, "--query-gpu=name,driver_version",
                 "--format=csv,noheader,nounits"],
                text=True, stderr=subprocess.DEVNULL, timeout=10,
                creationflags=flags,
            )
            line = out.strip().splitlines()[0]
            name, driver = [x.strip() for x in line.split(",", 1)]
            return name, _driver_to_cuda(driver)
        except Exception:
            continue

    return None, None


def _amd_rocm_info() -> tuple[Optional[str], Optional[str]]:
    """
    Restituisce (nome GPU AMD, versione ROCm) o (None, None).
    Funziona solo su Linux con driver ROCm installati.
    """
    if platform.system() != "Linux":
        return None, None

    try:
        out = subprocess.check_output(
            ["rocminfo"], text=True, stderr=subprocess.DEVNULL, timeout=15
        )
        gpu_name = None
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("Marketing Name:"):
                name = stripped.split(":", 1)[1].strip()
                if name and "CPU" not in name.upper():
                    gpu_name = name
                    break
        if not gpu_name:
            return None, None
    except Exception:
        return None, None

    # Legge versione ROCm dal file standard
    rocm_ver = None
    try:
        ver_file = "/opt/rocm/.info/version"
        if os.path.isfile(ver_file):
            with open(ver_file) as f:
                rocm_ver = f.read().strip().split("-")[0]  # "6.0.2-..." → "6.0.2"
    except Exception:
        pass

    return gpu_name, rocm_ver


def _amd_dx12_info() -> Optional[str]:
    """
    Rileva GPU AMD su Windows tramite WMI.
    Restituisce il nome della GPU se trovata e compatibile con DirectX 12, None altrimenti.
    Funziona solo su Windows — non richiede driver ROCm.
    """
    if platform.system() != "Windows":
        return None

    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | "
             "Select-Object -ExpandProperty Name"],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
            creationflags=flags,
        )
        for line in out.splitlines():
            name = line.strip()
            if name and "AMD" in name.upper() or "RADEON" in name.upper():
                return name
    except Exception:
        pass
    return None


def _driver_to_cuda(driver_version: str) -> str:
    """Mappa versione driver NVIDIA → versione CUDA supportata."""
    try:
        major = int(driver_version.split(".")[0])
    except (ValueError, IndexError):
        return "sconosciuta"

    if major >= 525:
        return "12.1"
    if major >= 520:
        return "11.8"
    if major >= 450:
        return "11.0"
    return "< 11.0 (aggiornare i driver)"


def _has_connectivity() -> bool:
    # Prova su più host/porte per robustezza
    targets = [("8.8.8.8", 80), ("1.1.1.1", 80), ("www.google.com", 80)]
    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=5):
                return True
        except Exception:
            continue
    return False


def _estimate_speed_mbps() -> Optional[float]:
    try:
        req = urllib.request.Request(SPEED_TEST_URL,
                                     headers={"User-Agent": "OffGalleryInstaller/1.0"})
        start = time.time()
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read(SPEED_TEST_BYTES)
        elapsed = time.time() - start
        if elapsed <= 0 or len(data) == 0:
            return None
        mbps = (len(data) * 8) / (elapsed * 1_000_000)
        return mbps
    except Exception:
        return None


def _parse_mbps(value_str: str) -> Optional[float]:
    """Estrae il numero da stringhe tipo '45.3 Mb/s (stimati)'."""
    try:
        return float(value_str.split()[0])
    except (ValueError, IndexError):
        return None


def _linux_distro() -> str:
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return "sconosciuta"


def _drive_label(path: str) -> str:
    """Restituisce la lettera di drive su Windows o il mount point su Unix."""
    if platform.system() == "Windows":
        return os.path.splitdrive(path)[0] or path
    return path
