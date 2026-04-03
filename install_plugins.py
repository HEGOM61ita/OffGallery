"""
OffGallery Plugin Installer — Beta Tester Edition
==================================================

Installa i plugin ufficiali OffGallery nell'installazione locale di OffGallery.

Utilizzo:
    Clona la repo OffGallery_BETA in una cartella qualsiasi, poi esegui:

        Windows (Anaconda Prompt):
            conda activate OffGallery
            python install_plugins.py

        macOS / Linux (terminale):
            conda activate OffGallery
            python install_plugins.py

    Se OffGallery è installato in una cartella non standard, specifica il percorso:
        python install_plugins.py --target "C:/MyApps/OffGallery"
"""

import sys
import json
import shutil
import argparse
import textwrap
import subprocess
from pathlib import Path

# Plugin inclusi in questa repo beta
PLUGINS = ["llm_ollama", "llm_lmstudio", "bionomen", "naturarea", "weather_context"]

# File/cartelle da copiare dalla root della repo beta alla root di OffGallery
# (oltre alla cartella plugins/)
EXTRA_FILES = []


def _find_offgallery(hint: Path | None) -> Path | None:
    """Cerca la directory di installazione di OffGallery."""
    candidates = []

    # 1. Percorso esplicitato dall'utente
    if hint:
        candidates.append(hint)

    # 2. Directory corrente dello script (caso: lo script è già dentro OffGallery_BETA
    #    che è una replica della repo, quindi gui_launcher.py è accanto a questo file)
    candidates.append(Path(__file__).parent)

    # 3. Percorsi comuni Windows
    for drive in ["C", "D", "E"]:
        for sub in ["OffGallery", "AI/Scripts/OffGallery", "Apps/OffGallery"]:
            candidates.append(Path(f"{drive}:/{sub}"))

    # 4. Home utente
    home = Path.home()
    for sub in ["OffGallery", "Documents/OffGallery", "Apps/OffGallery"]:
        candidates.append(home / sub)

    for path in candidates:
        if path and (path / "gui_launcher.py").exists():
            return path.resolve()

    return None


def _confirm(msg: str) -> bool:
    """Chiede conferma all'utente."""
    try:
        answer = input(f"{msg} [s/N] ").strip().lower()
        return answer in ("s", "si", "sì", "y", "yes")
    except (KeyboardInterrupt, EOFError):
        return False


def _copy_plugin(src: Path, dst: Path, plugin_name: str) -> bool:
    """Copia la cartella di un plugin nella destinazione."""
    src_plugin = src / "plugins" / plugin_name
    dst_plugin = dst / "plugins" / plugin_name

    if not src_plugin.exists():
        print(f"  ⚠️  Plugin '{plugin_name}' non trovato in questa repo — saltato.")
        return False

    if dst_plugin.exists():
        print(f"  ♻️  '{plugin_name}' già presente — aggiornamento in corso...")
        shutil.rmtree(dst_plugin)

    # Copia intera cartella escludendo __pycache__
    shutil.copytree(
        src_plugin,
        dst_plugin,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    print(f"  ✓  '{plugin_name}' installato.")

    # Installa dipendenze pip dichiarate nel manifest
    manifest_path = dst_plugin / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            pip_deps = manifest.get("pip_dependencies", [])
            for dep in pip_deps:
                print(f"  📦 Installazione dipendenza: {dep} ...")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", dep],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    print(f"     ✓ {dep} installato.")
                else:
                    print(f"     ⚠️  Errore installazione {dep}: {result.stderr.strip()}")
        except Exception as e:
            print(f"  ⚠️  Impossibile leggere manifest per dipendenze: {e}")

    return True


def _copy_plugin_base(src: Path, dst: Path) -> None:
    """Aggiorna plugins/base.py e plugins/loader.py se presenti nella repo beta."""
    for fname in ("base.py", "loader.py", "__init__.py", "PLUGIN_LICENSE_EXCEPTION.md"):
        src_f = src / "plugins" / fname
        dst_f = dst / "plugins" / fname
        if src_f.exists():
            shutil.copy2(src_f, dst_f)


def main():
    parser = argparse.ArgumentParser(
        description="Installa i plugin OffGallery nell'installazione locale.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Esempi:
              python install_plugins.py
              python install_plugins.py --target "C:/MyApps/OffGallery"
              python install_plugins.py --plugin llm_ollama
        """),
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Percorso della cartella OffGallery (rilevato automaticamente se omesso)",
    )
    parser.add_argument(
        "--plugin",
        choices=PLUGINS,
        default=None,
        help="Installa solo il plugin specificato (default: tutti)",
    )
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  OffGallery Plugin Installer — Beta Tester Edition")
    print("=" * 60)
    print()

    # --- Cartella sorgente (questa repo beta) ---
    src = Path(__file__).parent.resolve()
    if not (src / "plugins").exists():
        print("ERRORE: la cartella 'plugins/' non è stata trovata accanto a questo script.")
        print("        Assicurati di eseguire install_plugins.py dalla root della repo beta.")
        sys.exit(1)

    # --- Cartella destinazione (installazione OffGallery) ---
    dst = _find_offgallery(args.target)
    if dst is None:
        print("ERRORE: installazione di OffGallery non trovata automaticamente.")
        print("        Specifica il percorso con --target:")
        print('        python install_plugins.py --target "C:/percorso/a/OffGallery"')
        sys.exit(1)

    # Caso speciale: src == dst (lo script è già dentro la cartella OffGallery)
    # — nessuna copia necessaria, i plugin sono già al posto giusto
    if src == dst:
        print(f"📁 OffGallery rilevato in: {dst}")
        print()
        print("I plugin si trovano già nella cartella corretta (sei dentro la repo beta")
        print("che coincide con la cartella OffGallery). Nessuna copia necessaria.")
        print()
        print("Puoi avviare OffGallery normalmente. I plugin saranno riconosciuti")
        print("automaticamente all'avvio.")
        _print_bionomen_note(dst)
        return

    print(f"📁 Repo beta:        {src}")
    print(f"📁 OffGallery in:    {dst}")
    print()

    plugins_to_install = [args.plugin] if args.plugin else PLUGINS
    print(f"Plugin da installare: {', '.join(plugins_to_install)}")
    print()

    if not _confirm("Procedere con l'installazione?"):
        print("Installazione annullata.")
        sys.exit(0)

    print()

    # --- Copia file base plugin (base.py, loader.py) ---
    _copy_plugin_base(src, dst)

    # --- Copia plugin ---
    installed = 0
    for plugin_name in plugins_to_install:
        if _copy_plugin(src, dst, plugin_name):
            installed += 1

    print()
    print(f"✅ Installazione completata: {installed}/{len(plugins_to_install)} plugin installati.")
    print()

    _print_bionomen_note(dst)

    print("Avvia OffGallery normalmente. I plugin saranno riconosciuti all'avvio.")
    print()


def _print_bionomen_note(dst: Path) -> None:
    """Stampa istruzioni per il database BioNomen se il plugin è presente."""
    bionomen_dir = dst / "plugins" / "bionomen"
    if not bionomen_dir.exists():
        return

    data_dir = bionomen_dir / "data"
    has_db = data_dir.exists() and any(data_dir.glob("*.db"))

    print("─" * 60)
    print("  Plugin BioNomen — database specie")
    print("─" * 60)
    if has_db:
        dbs = list(data_dir.glob("*.db"))
        print(f"  Database trovati: {len(dbs)}")
        for db in sorted(dbs):
            print(f"    • {db.name}")
        print()
        print("  Per aggiungere altri taxa, apri BioNomen da OffGallery →")
        print("  Config → Plugin → BioNomen → Configura → taxa da scaricare.")
    else:
        print("  Il database delle specie NON è incluso nella repo.")
        print()
        print("  Per scaricarlo, avvia OffGallery, vai in:")
        print("    Config → Plugin → BioNomen → Configura")
        print("  Seleziona i taxa di interesse (Aves, Mammalia, Plantae, …)")
        print("  e clicca 'Scarica database'.")
        print()
        print("  Il download avviene da GBIF e richiede connessione internet")
        print("  (solo la prima volta). L'uso successivo è completamente offline.")
    print("─" * 60)
    print()


if __name__ == "__main__":
    main()
