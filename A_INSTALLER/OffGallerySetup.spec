# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec per OffGallery Manager
#
# Build:
#   pip install pyinstaller
#   pyinstaller OffGallerySetup.spec
#
# Output: dist/OffGallerySetup.exe  (Windows)
#         dist/OffGallerySetup      (Linux)
#         dist/OffGallerySetup.app  (macOS)

import sys
import os
import tkinter
from pathlib import Path

ROOT = Path(SPECPATH)   # directory di questo .spec

# ---------------------------------------------------------------------------
# Rilevamento automatico Tcl/Tk — indipendente da utente e piattaforma
# ---------------------------------------------------------------------------
# tkinter conosce sempre dove sono i suoi file di runtime.
# Funziona su Windows, macOS e Linux senza percorsi hardcoded.

_TCL_DIR = Path(tkinter.__file__).parent  # es. .../lib/tkinter

# Su Windows con Conda/Anaconda, le DLL e i dati Tcl/Tk stanno in
# Library/bin e Library/lib sotto la root dell'ambiente.
# Usiamo CONDA_PREFIX se disponibile, altrimenti risaliamo da tkinter.
_CONDA_PREFIX = Path(os.environ.get("CONDA_PREFIX", "") or sys.prefix)

def _find_tcltk_binaries():
    """Trova le DLL Tcl/Tk su Windows. Restituisce lista di tuple (src, dest)."""
    if sys.platform != "win32":
        return []
    candidates = [
        _CONDA_PREFIX / "Library" / "bin" / "tcl86t.dll",
        _CONDA_PREFIX / "Library" / "bin" / "tk86t.dll",
        _CONDA_PREFIX / "Library" / "bin" / "tcl90.dll",
        _CONDA_PREFIX / "Library" / "bin" / "tk90.dll",
    ]
    return [(str(p), ".") for p in candidates if p.exists()]

def _find_tcltk_datas():
    """Trova le directory dati Tcl/Tk. Restituisce lista di tuple (src, dest)."""
    results = []

    # 1) Ambiente Conda: Library/lib sotto CONDA_PREFIX
    lib_dir = _CONDA_PREFIX / "Library" / "lib"
    for name in ("tcl8.6", "tk8.6", "tcl9.0", "tk9.0"):
        p = lib_dir / name
        if p.exists():
            results.append((str(p), name))

    # 2) Python standalone Windows (actions/setup-python, python.org):
    #    i dati TCL stanno in {sys.prefix}/tcl/tcl8.6 e tcl/tk8.6
    if not results and sys.platform == "win32":
        tcl_root = Path(sys.prefix) / "tcl"
        for name in ("tcl8.6", "tk8.6", "tcl9.0", "tk9.0"):
            p = tcl_root / name
            if p.exists():
                results.append((str(p), name))

    # 3) Fallback generico: cerca accanto a _tkinter.pyd / _tkinter.so
    if not results:
        tkdir = Path(tkinter.__file__).parent
        for name in ("tcl8.6", "tk8.6", "tcl9.0", "tk9.0"):
            p = tkdir / name
            if p.exists():
                results.append((str(p), name))

    return results

_tcl_binaries = _find_tcltk_binaries()
_tcl_datas    = _find_tcltk_datas()

# Verifica che abbiamo trovato qualcosa di necessario su Windows
if sys.platform == "win32" and not _tcl_binaries:
    print("ATTENZIONE: DLL Tcl/Tk non trovate automaticamente.")
    print(f"  CONDA_PREFIX cercato: {_CONDA_PREFIX}")
    print("  Assicurati di eseguire la build dall'ambiente conda corretto.")

# ---------------------------------------------------------------------------
# Analisi dei moduli
# ---------------------------------------------------------------------------

a = Analysis(
    [str(ROOT / "installer.py")],
    pathex=[str(ROOT)],
    binaries=_tcl_binaries,
    datas=_tcl_datas + [
        # Logo header
        ("assets/logo_header.png", "assets"),
        # Requirements pip — bundlato nell'exe, non dipende più da /installer
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
        # winshell e win32com sono opzionali (collegamento desktop)
        # Non includerli come hidden import: se non ci sono, il codice
        # usa il fallback _shortcut_windows_fallback()
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
    # icon="assets/icon.ico",   # decommentare quando disponibile l'icona
    # Per Windows: richiedi privilegi utente standard (non admin)
    uac_admin=False,
    uac_uiaccess=False,
    version_file=None,          # vedi note sotto per aggiungere info versione
)

# ---------------------------------------------------------------------------
# macOS: crea .app bundle
# ---------------------------------------------------------------------------

if sys.platform == "darwin":
    app_bundle = BUNDLE(
        exe,
        name="OffGallerySetup.app",
        # icon="assets/icon.icns",
        bundle_identifier="ai.offgallery.installer",
        info_plist={
            "CFBundleName":             "OffGallery Manager",
            "CFBundleDisplayName":      "OffGallery Manager",
            "CFBundleVersion":          "1.0.0",
            "CFBundleShortVersionString": "1.0",
            "NSHighResolutionCapable":  True,
        },
    )

# ---------------------------------------------------------------------------
# NOTE
# ---------------------------------------------------------------------------
#
# ICONA WINDOWS (.ico):
#   Creare assets/icon.ico (256x256 + 48x48 + 32x32 + 16x16)
#   Decommentare la riga icon= in EXE()
#
# ICONA macOS (.icns):
#   Creare assets/icon.icns
#   Decommentare la riga icon= in BUNDLE()
#
# INFO VERSIONE WINDOWS (proprietà file .exe):
#   Creare version_info.txt con pyinstaller --version-file
#   Decommentare version_file= in EXE()
#
# FIRMA DIGITALE:
#   Windows: signtool.exe sign /f cert.pfx /p password dist\OffGallerySetup.exe
#   macOS:   codesign --deep --sign "Developer ID" dist/OffGallerySetup.app
#
# ANTIVIRUS FALSI POSITIVI:
#   PyInstaller genera exe che alcuni antivirus flaggano.
#   La firma digitale con certificato EV riduce drasticamente i falsi positivi.
#   Senza firma, Windows SmartScreen mostrerà un avviso al primo avvio.
