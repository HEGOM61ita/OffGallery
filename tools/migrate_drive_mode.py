#!/usr/bin/env python3
"""
OffGallery — migrate_drive_mode.py
====================================
Popola la colonna drive_mode nel database OffGallery leggendo i dati
EXIF già presenti in exif_json, senza rielaborare nessun file immagine.

Necessario per archivi indicizzati prima della versione che ha introdotto
il filtro "Modalità scatto" nella Search Tab.

Uso / Usage
-----------
  # Anteprima (nessuna modifica al DB):
  python migrate_drive_mode.py

  # Esecuzione effettiva:
  python migrate_drive_mode.py --apply

  # Percorso DB manuale (se config_new.yaml non trovato):
  python migrate_drive_mode.py --db /path/to/offgallery.sqlite --apply

Compatibilità / Compatibility
------------------------------
  Python 3.8+  —  Windows, Linux, macOS
  Nessuna dipendenza esterna oltre la stdlib.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Ricerca automatica del DB (identica agli altri script migrate_*)
# ---------------------------------------------------------------------------

def find_project_root() -> Path | None:
    candidate = Path(__file__).resolve().parent
    for _ in range(5):
        if (candidate / "config_new.yaml").exists():
            return candidate
        candidate = candidate.parent
    return None


def find_db_from_config(project_root: Path) -> Path | None:
    config_path = project_root / "config_new.yaml"
    try:
        text = config_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("database:"):
                raw = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                db_path = Path(raw)
                if not db_path.is_absolute():
                    db_path = project_root / db_path
                return db_path.resolve()
    except Exception:
        pass
    return None


def resolve_db_path(cli_db: str | None) -> Path:
    if cli_db:
        p = Path(cli_db).resolve()
        if not p.exists():
            print(f"[ERRORE] DB non trovato: {p}", file=sys.stderr)
            sys.exit(1)
        return p
    root = find_project_root()
    if root:
        db = find_db_from_config(root)
        if db and db.exists():
            return db
        fallback = root / "database" / "offgallery.sqlite"
        if fallback.exists():
            return fallback
    print(
        "[ERRORE] Impossibile trovare il database.\n"
        "Specifica il percorso con: --db /percorso/offgallery.sqlite",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Normalizzazione drive mode
# ---------------------------------------------------------------------------

def parse_drive_mode(value) -> str | None:
    """
    Normalizza la modalità di scatto a: single|continuous|bracketing|timer|silent.
    Gestisce stringhe composite Nikon (es. "Continuous, Exposure Bracketing").
    """
    if not value:
        return None
    s = str(value).lower()
    if any(x in s for x in ('bracket', 'bkt')):
        return 'bracketing'
    if any(x in s for x in ('continuous', 'cont', 'burst', 'high speed', 'low speed')):
        return 'continuous'
    if any(x in s for x in ('self-timer', 'selftimer', 'timer', 'delay', 'remote')):
        return 'timer'
    if any(x in s for x in ('silent', 'quiet', 'electronic shutter', 'e-shutter')):
        return 'silent'
    if any(x in s for x in ('single', 'one shot', 'one-shot', 'single-frame', 'single shot')):
        return 'single'
    return None


def extract_drive_mode(exif: dict) -> str | None:
    """Estrae e normalizza la modalità di scatto dall'exif dict."""
    for key in (
        'MakerNotes:DriveMode',        # Olympus
        'MakerNotes:ContinuousDrive',  # Canon
        'MakerNotes:ShootingMode',     # Nikon
    ):
        v = exif.get(key)
        if v:
            result = parse_drive_mode(v)
            if result:
                return result
    return None


# ---------------------------------------------------------------------------
# Migrazione
# ---------------------------------------------------------------------------

def progress_bar(current: int, total: int, width: int = 40) -> str:
    filled = int(width * current / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = 100 * current // total if total else 0
    return f"[{bar}] {pct:3d}%  {current}/{total}"


def run_migration(db_path: Path, apply: bool) -> None:
    print(f"\n  Database : {db_path}")
    print(f"  Modalità : {'SCRITTURA (--apply)' if apply else 'DRY-RUN (solo anteprima)'}")
    print()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cols = {row[1] for row in conn.execute("PRAGMA table_info(images)")}
    if "drive_mode" not in cols:
        print(
            "[ERRORE] La colonna 'drive_mode' non esiste nel DB.\n"
            "Aggiorna OffGallery all'ultima versione e avvialo almeno una volta\n"
            "per eseguire la migrazione dello schema, poi riesegui questo script.",
            file=sys.stderr,
        )
        conn.close()
        sys.exit(1)

    rows = conn.execute(
        "SELECT id, exif_json FROM images "
        "WHERE exif_json IS NOT NULL AND drive_mode IS NULL"
    ).fetchall()

    total = len(rows)
    if total == 0:
        already = conn.execute(
            "SELECT COUNT(*) FROM images WHERE drive_mode IS NOT NULL"
        ).fetchone()[0]
        print(f"  Nessuna immagine da aggiornare ({already} già hanno drive_mode).")
        conn.close()
        return

    print(f"  Immagini da elaborare: {total}")
    print()

    updates = []
    no_data = 0
    invalid_json = 0

    for i, row in enumerate(rows, 1):
        if i % 100 == 0 or i == total:
            print(f"\r  {progress_bar(i, total)}", end="", flush=True)
        try:
            exif = json.loads(row["exif_json"])
        except (json.JSONDecodeError, TypeError):
            invalid_json += 1
            continue
        dm = extract_drive_mode(exif)
        if dm:
            updates.append((dm, row["id"]))
        else:
            no_data += 1

    print(f"\r  {progress_bar(total, total)}")
    print()

    from collections import Counter
    counts = Counter(dm for dm, _ in updates)
    print(f"  Estratti con successo : {len(updates)}")
    for mode in ('single', 'continuous', 'bracketing', 'timer', 'silent'):
        if counts[mode]:
            print(f"    - {mode:<12}: {counts[mode]}")
    print(f"  Senza dato EXIF       : {no_data}")
    if invalid_json:
        print(f"  exif_json non valido  : {invalid_json}")
    print()

    if not updates:
        print("  Nessun valore da scrivere.")
        conn.close()
        return

    if apply:
        conn.executemany("UPDATE images SET drive_mode = ? WHERE id = ?", updates)
        conn.commit()
        print(f"  ✓ {len(updates)} righe aggiornate nel database.")

        stats = conn.execute(
            """
            SELECT drive_mode, COUNT(*) as n
            FROM images WHERE drive_mode IS NOT NULL
            GROUP BY drive_mode ORDER BY n DESC
            """
        ).fetchall()
        print()
        print("  Distribuzione finale:")
        for row in stats:
            print(f"    {row[0]:<14}: {row[1]}")
    else:
        print(
            f"  [DRY-RUN] {len(updates)} righe verrebbero aggiornate.\n"
            f"  Esegui con --apply per applicare le modifiche."
        )

    print()
    conn.close()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OffGallery — migrazione drive_mode da exif_json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db", metavar="PATH",
                        help="Percorso esplicito al file offgallery.sqlite")
    parser.add_argument("--apply", action="store_true",
                        help="Applica le modifiche al DB (default: dry-run)")
    args = parser.parse_args()

    print("=" * 60)
    print("  OffGallery — Migrazione Drive Mode")
    print("=" * 60)

    db_path = resolve_db_path(args.db)
    run_migration(db_path, apply=args.apply)


if __name__ == "__main__":
    main()
