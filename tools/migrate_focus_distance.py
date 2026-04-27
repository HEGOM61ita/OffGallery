#!/usr/bin/env python3
"""
OffGallery — migrate_focus_distance.py
=======================================
Popola la colonna focus_distance nel database OffGallery leggendo i dati
EXIF già presenti in exif_json, senza rielaborare nessun file immagine.

Necessario per archivi indicizzati prima della versione che ha introdotto
il filtro "Distanza fuoco" nella Search Tab.

Uso / Usage
-----------
  # Anteprima (nessuna modifica al DB):
  python migrate_focus_distance.py

  # Esecuzione effettiva:
  python migrate_focus_distance.py --apply

  # Percorso DB manuale (se config_new.yaml non trovato):
  python migrate_focus_distance.py --db /path/to/offgallery.sqlite --apply

Compatibilità / Compatibility
------------------------------
  Python 3.8+  —  Windows, Linux, macOS
  Nessuna dipendenza esterna oltre la stdlib.
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Ricerca automatica del DB
# ---------------------------------------------------------------------------

def find_project_root() -> Path | None:
    """Risale l'albero delle directory cercando config_new.yaml."""
    candidate = Path(__file__).resolve().parent
    for _ in range(5):
        if (candidate / "config_new.yaml").exists():
            return candidate
        candidate = candidate.parent
    return None


def find_db_from_config(project_root: Path) -> Path | None:
    """Legge il percorso del DB da config_new.yaml (parsing minimale, senza PyYAML)."""
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
    """Risolve il percorso del DB da argomento CLI o config_new.yaml."""
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

    # Fallback: posizione di default relativa alla root progetto
    if root:
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
# Parser distanza fuoco
# ---------------------------------------------------------------------------

def parse_meters(value) -> float | None:
    """
    Converte un valore EXIF in float (metri).
    Ritorna -1.0 per Infinity, None se non interpretabile.
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("inf", "infinity", "∞", "undef", "unknown", ""):
        return -1.0
    s = re.sub(r"\s*m$", "", s).strip()
    try:
        result = float(s)
        if result > 9999.0:   # overflow Nikon (4294967295 m)
            return -1.0
        if result < 0:
            return None
        return result
    except (ValueError, TypeError):
        return None


def extract_focus_distance(exif: dict, camera_make: str) -> float | None:
    """
    Estrae la migliore stima di distanza fuoco dall'exif dict.

    Strategia per brand:
      Nikon / Olympus  →  MakerNotes:FocusDistance  (il più preciso)
      Canon            →  media(FocusDistanceUpper, FocusDistanceLower)
                          o solo Lower se Upper = Infinity
      Tutti            →  fallback su EXIF:SubjectDistance,
                          XMP:ApproximateFocusDistance, XMP:SubjectDistance
    """
    make = (camera_make or "").lower()

    # --- Nikon / Olympus ---
    if "nikon" in make or "olympus" in make:
        v = exif.get("MakerNotes:FocusDistance")
        if v is not None:
            result = parse_meters(v)
            if result is not None:
                return result

    # --- Canon ---
    if "canon" in make:
        upper = parse_meters(exif.get("MakerNotes:FocusDistanceUpper"))
        lower = parse_meters(exif.get("MakerNotes:FocusDistanceLower"))
        if upper is not None and upper != -1.0 and lower is not None and lower != -1.0:
            return (upper + lower) / 2.0
        if lower is not None:
            return lower
        if upper is not None:
            return upper

    # --- Fallback universale ---
    for key in (
        "EXIF:SubjectDistance",
        "XMP:ApproximateFocusDistance",
        "XMP:SubjectDistance",
        "MakerNotes:FocusDistance",
        "MakerNotes:FocusDistanceLower",
    ):
        v = exif.get(key)
        if v is not None:
            result = parse_meters(v)
            if result is not None:
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

    # Verifica che la colonna focus_distance esista
    cols = {row[1] for row in conn.execute("PRAGMA table_info(images)")}
    if "focus_distance" not in cols:
        print(
            "[ERRORE] La colonna 'focus_distance' non esiste nel DB.\n"
            "Aggiorna OffGallery all'ultima versione e avvialo almeno una volta\n"
            "per eseguire la migrazione dello schema, poi riesegui questo script.",
            file=sys.stderr,
        )
        conn.close()
        sys.exit(1)

    rows = conn.execute(
        "SELECT id, exif_json, camera_make FROM images "
        "WHERE exif_json IS NOT NULL AND focus_distance IS NULL"
    ).fetchall()

    total = len(rows)
    if total == 0:
        already = conn.execute(
            "SELECT COUNT(*) FROM images WHERE focus_distance IS NOT NULL"
        ).fetchone()[0]
        print(f"  Nessuna immagine da aggiornare ({already} già hanno focus_distance).")
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

        fd = extract_focus_distance(exif, row["camera_make"] or "")
        if fd is not None:
            updates.append((fd, row["id"]))
        else:
            no_data += 1

    print(f"\r  {progress_bar(total, total)}")
    print()

    # Statistiche estrazione
    infinity_count = sum(1 for fd, _ in updates if fd == -1.0)
    metric_count = len(updates) - infinity_count

    print(f"  Estratti con successo : {len(updates)}")
    print(f"    - con distanza metrica : {metric_count}")
    print(f"    - Infinity (∞)         : {infinity_count}")
    print(f"  Senza dato EXIF        : {no_data}")
    if invalid_json:
        print(f"  exif_json non valido   : {invalid_json}")
    print()

    if not updates:
        print("  Nessun valore da scrivere.")
        conn.close()
        return

    if apply:
        conn.executemany("UPDATE images SET focus_distance = ? WHERE id = ?", updates)
        conn.commit()
        print(f"  ✓ {len(updates)} righe aggiornate nel database.")

        # Statistiche finali dal DB
        stats = conn.execute(
            """
            SELECT
                COUNT(*)                                                AS tot,
                COUNT(focus_distance)                                   AS with_fd,
                SUM(CASE WHEN focus_distance = -1.0 THEN 1 ELSE 0 END) AS infinity,
                MIN(CASE WHEN focus_distance >= 0 THEN focus_distance END) AS min_m,
                MAX(CASE WHEN focus_distance >= 0 AND focus_distance < 9999 THEN focus_distance END) AS max_m
            FROM images
            """
        ).fetchone()
        print()
        print("  Stato finale del database:")
        print(f"    Totale immagini      : {stats['tot']}")
        print(f"    Con focus_distance   : {stats['with_fd']}")
        print(f"    Infinity             : {stats['infinity']}")
        if stats["min_m"] is not None and stats["max_m"] is not None:
            print(f"    Range metrico        : {stats['min_m']:.2f} m – {stats['max_m']:.2f} m")
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
        description="OffGallery — migrazione focus_distance da exif_json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="Percorso esplicito al file offgallery.sqlite (opzionale)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Applica le modifiche al DB (default: dry-run)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  OffGallery — Migrazione Focus Distance")
    print("=" * 60)

    db_path = resolve_db_path(args.db)
    run_migration(db_path, apply=args.apply)


if __name__ == "__main__":
    main()
