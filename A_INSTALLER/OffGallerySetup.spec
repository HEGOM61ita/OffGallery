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
from pathlib import Path

ROOT = Path(SPECPATH)   # directory di questo .spec

# ---------------------------------------------------------------------------
# Analisi dei moduli
# ---------------------------------------------------------------------------

a = Analysis(
    [str(ROOT / "installer.py")],
    pathex=[str(ROOT)],
    binaries=[
        # DLL Tcl/Tk — necessarie per tkinter su Windows
        (r"C:\Users\HEGOM\anaconda3\Library\bin\tcl86t.dll", "."),
        (r"C:\Users\HEGOM\anaconda3\Library\bin\tk86t.dll",  "."),
    ],
    datas=[
        # Tcl/Tk runtime — necessario per tkinter
        (r"C:\Users\HEGOM\anaconda3\Library\lib\tcl8.6", "tcl8.6"),
        (r"C:\Users\HEGOM\anaconda3\Library\lib\tk8.6",  "tk8.6"),
        # Logo header
        (r"assets\logo_header.png", "assets"),
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
