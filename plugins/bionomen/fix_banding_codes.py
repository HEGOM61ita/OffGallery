"""Ripara i DB BioNomen scaricati prima del fix sui codici di banding.

Fino alla versione precedente il downloader salvava come nome comune il primo
entry restituito da GBIF nella lingua richiesta. Per gli uccelli quel primo
entry è spesso il codice alpha-4 del ringing scheme ("BEVU" per Gypaetus
barbatus) invece del nome vero. Il difetto riguarda circa il 10% delle voci di
aves; gli altri taxa non sono interessati.

Riscaricare l'intero DB non serve: le voci sbagliate sono riconoscibili e sono
poche, quindi qui si ri-interrogano solo quelle. Le voci corrette non vengono
toccate e il DB resta lo stesso file.

Un secondo difetto, corretto insieme al primo, riguardava la scelta del nome
quando GBIF ne offre molti: si prendeva il primo della lista, che è in ordine
alfabetico e non per rilevanza ("American Cross Fox" invece di "Red Fox"). Le
voci sbagliate così non sono riconoscibili guardando il DB, quindi correggerle
richiede di ri-interrogare ogni specie: è l'opzione --all, molto più lenta.

Uso:
    python fix_banding_codes.py                    # ripara i DB in ./data
    python fix_banding_codes.py /percorso/data     # ripara i DB in quella cartella
    python fix_banding_codes.py --dry-run          # elenca soltanto, non scrive
    python fix_banding_codes.py --all              # ricontrolla ogni voce (lento)
"""

import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bionomen import (  # noqa: E402
    _LANG_MAP,
    _is_banding_code,
    _is_pronunciation_note,
    _pick_vernacular,
)

_WORKERS = 3


def _find_dbs(data_dir: str):
    if not os.path.isdir(data_dir):
        return []
    return sorted(
        os.path.join(data_dir, f)
        for f in os.listdir(data_dir)
        if f.startswith("bionomen_") and f.endswith(".db")
    )


def _is_junk(name: str) -> bool:
    """Voce da scartare riconoscibile dal DB: sigla di banding o nota di pronuncia.

    Entrambe sono peggio dell'assenza — nella ricerca compaiono come se fossero
    una specie a sé ("BEVU", "(Pronounce: Sha-mee or Sham-wa)").
    """
    return _is_banding_code(name) or _is_pronunciation_note(name)


def _bad_rows(conn, all_rows: bool = False):
    """Voci da ri-interrogare.

    Di default solo quelle il cui 'nome comune' è spazzatura riconoscibile dal
    DB: un codice di banding ("BEVU") o una nota di pronuncia ("(Pronounce:
    ...)"). Sono riconoscibili dalla forma, quindi si correggono in pochi minuti.

    Con all_rows si riprendono TUTTE le voci. Serve per il secondo difetto —
    il nome scelto in ordine alfabetico invece che per numero di fonti
    ("American Cross Fox" al posto di "Red Fox") — che dal DB non è
    riconoscibile: l'unico modo è richiedere di nuovo ogni specie.
    """
    rows = conn.execute(
        "SELECT scientific_name, vernacular_name, language FROM vernacular_names"
    ).fetchall()
    if all_rows:
        return rows
    return [r for r in rows if _is_junk(r[1])]


def _refetch(args):
    """Ri-interroga GBIF per una specie, scartando stavolta le sigle."""
    import requests

    sci_name, language = args
    lang_code = _LANG_MAP.get(language, language)
    try:
        murl = "https://api.gbif.org/v1/species/match"
        resp = requests.get(
            murl, params={"name": sci_name, "verbose": "false"},
            timeout=8, headers={"User-Agent": "BioNomen/2.0"},
        )
        resp.raise_for_status()
        key = resp.json().get("usageKey") or resp.json().get("speciesKey")
        if not key:
            return (sci_name, None)

        vurl = f"https://api.gbif.org/v1/species/{key}/vernacularNames?limit=100"
        resp2 = requests.get(vurl, timeout=8, headers={"User-Agent": "BioNomen/2.0"})
        resp2.raise_for_status()
        results = resp2.json().get("results", [])
        return (sci_name, _pick_vernacular(results, lang_code, language))
    except Exception as exc:
        print(f"  ! {sci_name}: {exc}")
        return (sci_name, None)


def fix_db(db_path: str, dry_run: bool = False, all_rows: bool = False) -> None:
    conn = sqlite3.connect(db_path)
    try:
        bad = _bad_rows(conn, all_rows=all_rows)
        name = os.path.basename(db_path)
        if not bad:
            print(f"{name}: nessuna voce spazzatura (sigle/pronuncia), niente da fare")
            return

        print(f"{name}: {len(bad)} voci da ricontrollare")
        if dry_run:
            for sci, vern, _ in bad[:20]:
                print(f"  {sci} -> '{vern}'")
            if len(bad) > 20:
                print(f"  ... e altre {len(bad) - 20}")
            return

        # Una voce senza sostituto va rimossa solo se quella attuale è spazzatura
        # (sigla di banding o nota di pronuncia): è peggio dell'assenza, nella
        # ricerca compare come se fosse una specie a sé. In modalità --all invece
        # la si lascia com'è: qui un
        # "nessun risultato" è quasi sempre GBIF irraggiungibile, e cancellare
        # cancellerebbe nomi validi.
        old_by_sci = {r[0]: r[1] for r in bad}
        updated = removed = kept = 0
        with ThreadPoolExecutor(max_workers=_WORKERS) as ex:
            futures = [
                ex.submit(_refetch, (sci, lang)) for sci, _, lang in bad
            ]
            for i, fut in enumerate(as_completed(futures), 1):
                sci, new_name = fut.result()
                if new_name:
                    if new_name != old_by_sci.get(sci):
                        conn.execute(
                            "UPDATE vernacular_names SET vernacular_name=? "
                            "WHERE scientific_name=?",
                            (new_name, sci),
                        )
                        updated += 1
                    else:
                        kept += 1
                elif _is_junk(old_by_sci.get(sci, "")):
                    conn.execute(
                        "DELETE FROM vernacular_names WHERE scientific_name=?",
                        (sci,),
                    )
                    removed += 1
                else:
                    kept += 1
                if i % 50 == 0:
                    conn.commit()
                    print(f"  {i}/{len(bad)}...")
        conn.commit()
        print(
            f"{name}: {updated} corrette, {kept} già giuste, "
            f"{removed} rimosse (nessun nome vero su GBIF)"
        )
    finally:
        conn.close()


def main():
    flags = {"--dry-run", "--all"}
    args = [a for a in sys.argv[1:] if a not in flags]
    dry_run = "--dry-run" in sys.argv
    all_rows = "--all" in sys.argv
    data_dir = args[0] if args else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data"
    )

    dbs = _find_dbs(data_dir)
    if not dbs:
        print(f"Nessun DB BioNomen trovato in {data_dir}")
        return 1

    if all_rows:
        print("Modalità --all: ricontrollo di ogni voce, può richiedere a lungo.\n")

    for db in dbs:
        fix_db(db, dry_run=dry_run, all_rows=all_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
