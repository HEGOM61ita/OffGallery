# -*- mode: python ; coding: utf-8 -*-
"""
OffGallery - PyInstaller Spec File
Genera: dist/OffGallery/OffGallery.exe
"""

import sys
from pathlib import Path

# Directory sorgente
SRC_DIR = Path(SPECPATH)

a = Analysis(
    ['gui_launcher.py'],
    pathex=[str(SRC_DIR)],
    binaries=[],
    datas=[
        # Risorse grafiche
        ('assets', 'assets'),
        # Modelli BRISQUE (piccoli, inclusi)
        ('brisque_models', 'brisque_models'),
        # ExifTool (perl + dll)
        ('exiftool_files', 'exiftool_files'),
        # Utils module
        ('utils', 'utils'),
    ],
    hiddenimports=[
        # PyQt6
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',

        # Torch
        'torch',
        'torch.nn',
        'torch.nn.functional',
        'torchvision',
        'torchvision.transforms',

        # Transformers / HuggingFace
        'transformers',
        'transformers.models.clip',
        'transformers.models.auto',
        'huggingface_hub',
        'safetensors',
        'tokenizers',

        # BioCLIP
        'bioclip',
        'open_clip',
        'timm',

        # Image processing
        'PIL',
        'PIL.Image',
        'rawpy',
        'cv2',
        'numpy',

        # Translation
        'argostranslate',
        'argostranslate.translate',
        'argostranslate.package',
        'ctranslate2',
        'sentencepiece',

        # Utils
        'yaml',
        'requests',
        'tqdm',
        'regex',
        'ftfy',

        # Standard
        'sqlite3',
        'json',
        'logging',
        'pathlib',
        'concurrent.futures',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Escludi moduli non necessari per ridurre dimensione
        'matplotlib',
        'notebook',
        'jupyter',
        'IPython',
        'sphinx',
        'pytest',
        'setuptools',
        'pip',
        'wheel',
        'tkinter',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OffGallery',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Icona (opzionale - crea assets/icon.ico se vuoi)
    # icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OffGallery',
)
