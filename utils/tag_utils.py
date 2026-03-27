"""
tag_utils.py — Utility per la normalizzazione dei tag in OffGallery.

NOTA: normalize_tags è duplicata in plugins/bionomen/bionomen.py perché
      BioNomen gira come sottoprocesso separato e non può importare da utils/.
      Mantenere le due versioni sincronizzate.
"""

from typing import List, Optional


def normalize_tags(
    tags: List[str],
    scientific_name: Optional[str] = None,
    vernacular_name: Optional[str] = None,
) -> List[str]:
    """
    Normalizza e deduplica una lista di tag con ordine canonico.

    Ordine risultante:
      1. Nome scientifico (se fornito)
      2. Nome comune/vernacolare (se fornito)
      3. Tag restanti nell'ordine originale

    Regole:
    - Deduplicazione case-insensitive (mantiene la prima occorrenza)
    - Rimuove stringhe vuote o None
    - scientific_name e vernacular_name vengono posizionati correttamente
      anche se già presenti nella lista o assenti

    Args:
        tags: Lista tag esistenti (da LLM, import XMP, gallery, ecc.)
        scientific_name: Nome scientifico da BioCLIP (pos. 0)
        vernacular_name: Nome comune da BioNomen (pos. 1)

    Returns:
        Lista tag normalizzata e ordinata.
    """
    # Dedup case-insensitive mantenendo ordine, rimuovendo vuoti
    seen_lower = set()
    deduped = []
    for tag in (tags or []):
        if not isinstance(tag, str) or not tag.strip():
            continue
        tl = tag.strip().lower()
        if tl not in seen_lower:
            seen_lower.add(tl)
            deduped.append(tag.strip())

    sci_lower  = scientific_name.strip().lower()  if scientific_name  else None
    vern_lower = vernacular_name.strip().lower()  if vernacular_name  else None

    # Rimuovi scientific_name e vernacular_name dal corpo (li riposizioniamo)
    rest = [
        t for t in deduped
        if t.lower() != sci_lower and t.lower() != vern_lower
    ]

    # Assembla in ordine canonico
    result = []
    if scientific_name and scientific_name.strip():
        result.append(scientific_name.strip())
    if vernacular_name and vernacular_name.strip():
        if vern_lower != sci_lower:
            result.append(vernacular_name.strip())
    result.extend(rest)

    return result
