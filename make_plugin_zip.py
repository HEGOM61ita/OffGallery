"""Rigenera lo zip di un plugin per la Release `plugins-latest`.

Include SOLO il codice, con approccio ALLOWLIST: si spedisce ciò che e'
esplicitamente ammesso, non "tutto tranne". Una denylist e' fragile — sotto WSL
il data_dir Windows di config.json crea cartelle con nomi letterali tipo
'D:\\AI\\...\\data' che nessun filtro per nome intercetta.
"""
import sys, zipfile
from pathlib import Path

ALLOWED_EXT   = {".py", ".json", ".md", ".txt"}
EXCLUDE_FILES = {"config.json"}          # contiene percorsi personali
EXCLUDE_DIRS  = {"__pycache__", ".git"}

def build(plugin_dir: Path, out: Path) -> list:
    files = []
    for p in sorted(plugin_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(plugin_dir)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if rel.name in EXCLUDE_FILES:
            continue
        if p.suffix.lower() not in ALLOWED_EXT:
            continue
        # Difesa in profondita': nessun file dentro una cartella che somigli a dati
        if any("data" in part.lower() or "cache" in part.lower() for part in rel.parts[:-1]):
            continue
        files.append(rel)
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            z.write(plugin_dir / rel, f"{plugin_dir.name}/{rel.as_posix()}")
    return files

if __name__ == "__main__":
    src, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    for rel in build(src, out):
        print("  +", rel.as_posix())
    print(f"\n{out.name}: {out.stat().st_size} byte")
