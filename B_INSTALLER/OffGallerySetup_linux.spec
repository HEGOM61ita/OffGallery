# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec per OffGallery Manager — Linux
#
# Build (dall'ambiente conda OffGallery attivo o tramite build_linux.sh):
#   pip install pyinstaller
#   pyinstaller OffGallerySetup_linux.spec
#
# Output: dist/OffGallerySetup  (binary ELF Linux)

import sys
import os
import tkinter
from pathlib import Path

ROOT = Path(SPECPATH)   # directory di questo .spec

# ---------------------------------------------------------------------------
# Rilevamento automatico Tcl/Tk — Linux/conda
# ---------------------------------------------------------------------------
# tkinter conosce sempre dove sono i suoi file di runtime.
# Funziona con Conda (percorsi sotto CONDA_PREFIX) e con Python di sistema.

_CONDA_PREFIX = Path(os.environ.get("CONDA_PREFIX", "") or sys.prefix)


def _find_tcltk_datas():
    """
    Trova le directory dati Tcl/Tk per Linux.
    Cerca in CONDA_PREFIX/lib e poi nei percorsi di sistema standard.
    Restituisce lista di tuple (src, dest).
    """
    results = []

    # Percorsi tipici in ambiente conda Linux
    candidates = [
        _CONDA_PREFIX / "lib",                        # conda: /lib/tcl8.6 ecc.
        _CONDA_PREFIX / "lib" / "tcl8.6",
        Path("/usr/lib/tcl8.6"),
        Path("/usr/share/tcltk"),
    ]

    # Cerca le directory nominate tcl8.x / tk8.x / tcl9.x / tk9.x
    for base in [_CONDA_PREFIX / "lib", Path("/usr/lib"), Path("/usr/share/tcltk")]:
        if base.is_dir():
            for name in ("tcl8.6", "tk8.6", "tcl9.0", "tk9.0"):
                p = base / name
                if p.is_dir():
                    results.append((str(p), name))

    # Fallback: accanto a _tkinter.so
    if not results:
        tkdir = Path(tkinter.__file__).parent
        for name in ("tcl8.6", "tk8.6", "tcl9.0", "tk9.0"):
            p = tkdir / name
            if p.is_dir():
                results.append((str(p), name))

    # Deduplicazione: mantieni la prima occorrenza per ogni nome
    seen = set()
    deduped = []
    for src, dest in results:
        if dest not in seen:
            seen.add(dest)
            deduped.append((src, dest))

    return deduped


_tcl_datas = _find_tcltk_datas()

if not _tcl_datas:
    print("ATTENZIONE: Directory Tcl/Tk non trovate automaticamente.")
    print(f"  CONDA_PREFIX cercato: {_CONDA_PREFIX}")
    print("  Se il bundle mostra 'init.tcl not found', installa:")
    print("  conda install -c conda-forge tk")

# ---------------------------------------------------------------------------
# Analisi dei moduli
# ---------------------------------------------------------------------------

a = Analysis(
    [str(ROOT / "installer.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_tcl_datas + [
        # Logo header
        ("assets/logo_header.png", "assets"),
        # Requirements pip — bundlato nel binary
        ("requirements_offgallery.txt", "."),
    ],
    hiddenimports=[
        # tkinter e ttk non sempre rilevati automaticamente
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        # Moduli stdlib usati nei componenti
        "urllib.request",
        "urllib.error",
        "zipfile",
        "hashlib",
        "shutil",
        "socket",
        "platform",
        "subprocess",
        "threading",
        "json",
        "time",
        "copy",
        "enum",
        "dataclasses",
        "utils.logger",
        # email è usato internamente da urllib
        "email",
        "email.message",
        "email.parser",
        "email.feedparser",
        "email.errors",
        "email.header",
        "email.charset",
        "email.encoders",
        "email.utils",
    ],
    excludes=[
        # Escludi framework pesanti non necessari nell'installer
        "numpy",
        "pandas",
        "matplotlib",
        "scipy",
        "PIL",
        "cv2",
        "torch",
        "transformers",
        "html",
        "http.server",
        "xmlrpc",
        "unittest",
        "pydoc",
        "doctest",
    ],
    noarchive=False,
    optimize=1,
)

# ---------------------------------------------------------------------------
# PYZ archive
# ---------------------------------------------------------------------------

pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# Eseguibile
# ---------------------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OffGallerySetup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                   # compressione UPX se disponibile
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # nessuna finestra terminale
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ---------------------------------------------------------------------------
# NOTE
# ---------------------------------------------------------------------------
#
# ICONA LINUX:
#   Aggiungi un file assets/icon.png (256x256 PNG).
#   PyInstaller su Linux usa l'icona solo per il .desktop file,
#   non per l'eseguibile stesso (i formati .ico/.icns non sono usati).
#
# DISTRIBUZIONE LINUX:
#   L'eseguibile dist/OffGallerySetup è auto-contenuto ma dipende dalla
#   presenza di libGL, libX11 e GTK/Tcl-Tk sul sistema target.
#   Per una distribuzione universale considera AppImage o Flatpak (da fare
#   in seguito quando il progetto è maturo).
#
# PERMESSI:
#   chmod +x dist/OffGallerySetup   # già impostato da PyInstaller
#
# FIRMA:
#   Su Linux non esiste un equivalente di SmartScreen/Gatekeeper.
#   Non sono necessarie firme per l'esecuzione locale.
#   Per distribuzione via repo o pacchetti: firma GPG del binary.
