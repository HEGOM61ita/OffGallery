#!/usr/bin/env python3
"""
OffGallery - Aggiornamento automatico codice
Scarica l'ultima versione da GitHub e aggiorna solo i file di codice.
I dati utente non vengono mai toccati.
"""

import urllib.request
import urllib.error
import zipfile
import shutil
import json
import sys
import os
from pathlib import Path
import tempfile

GITHUB_USER   = "HEGOM61ita"
GITHUB_REPO   = "OffGallery"
GITHUB_BRANCH = "main"
GITHUB_ZIP    = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"
GITHUB_API    = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/commits/{GITHUB_BRANCH}"

# Cartelle e file che appartengono all'utente — non vengono mai sovrascritti
PROTECTED_DIRS  = {"Models", "database", "logs", "INPUT"}
PROTECTED_FILES = {"config_new.yaml", "update.py"}


def get_local_version(app_dir: Path) -> str:
    version_file = app_dir / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "(sconosciuta)"


def get_remote_version() -> str | None:
    try:
        req = urllib.request.Request(
            GITHUB_API,
            headers={"User-Agent": "OffGallery-Updater"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data["sha"][:7]
    except Exception:
        return None


def main():
    app_dir = Path(__file__).parent.resolve()

    print("=" * 60)
    print("  OffGallery - Aggiornamento automatico")
    print("=" * 60)
    print()

    # Confronta versioni
    local  = get_local_version(app_dir)
    print(f"  Versione installata : {local}")
    print("  Controllo versione remota...")

    remote = get_remote_version()
    if remote is None:
        print("  [ERRORE] Impossibile raggiungere GitHub. Verifica la connessione.")
        input("\n  Premi INVIO per chiudere.")
        sys.exit(1)

    print(f"  Ultima versione     : {remote}")
    print()

    if local == remote:
        print("  Sei già all'ultima versione. Nessun aggiornamento necessario.")
        input("\n  Premi INVIO per chiudere.")
        return

    print("  Aggiornamento disponibile!")
    print()
    risposta = input("  Vuoi aggiornare adesso? (s/n): ").strip().lower()
    if risposta not in ("s", "si", "y", "yes"):
        print("\n  Aggiornamento annullato.")
        input("  Premi INVIO per chiudere.")
        return

    print()
    print("  Download in corso...")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        zip_path = tmp / "update.zip"

        try:
            urllib.request.urlretrieve(GITHUB_ZIP, zip_path)
        except urllib.error.URLError as e:
            print(f"  [ERRORE] Download fallito: {e}")
            input("\n  Premi INVIO per chiudere.")
            sys.exit(1)

        print("  Estrazione...")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp)

        # Lo zip estrae in una cartella tipo "OffGallery-main"
        src_dirs = [d for d in tmp.iterdir() if d.is_dir() and d.name != "__MACOSX"]
        if not src_dirs:
            print("  [ERRORE] Struttura zip non riconosciuta.")
            input("\n  Premi INVIO per chiudere.")
            sys.exit(1)
        src = src_dirs[0]

        updated = []
        skipped = []

        for item in src.rglob("*"):
            rel = item.relative_to(src)
            parts = rel.parts

            # Salta cartelle e file protetti (dati utente)
            if parts[0] in PROTECTED_DIRS:
                continue
            if len(parts) == 1 and parts[0] in PROTECTED_FILES:
                skipped.append(str(rel))
                continue

            dest = app_dir / rel
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
                updated.append(str(rel))

        # Aggiorna VERSION con il nuovo hash
        (app_dir / "VERSION").write_text(remote + "\n")

    print()
    print(f"  Aggiornati  : {len(updated)} file")
    print(f"  Non toccati : Models/, database/, logs/, config_new.yaml")
    print()
    print(f"  Aggiornamento completato! ({local} → {remote})")
    print("  Riavvia OffGallery per usare la nuova versione.")
    print()
    input("  Premi INVIO per chiudere.")


if __name__ == "__main__":
    main()
