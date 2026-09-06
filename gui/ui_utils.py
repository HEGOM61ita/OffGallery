# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024-2026 Michele Mulè <hegomm@gmail.com>
"""Utilità comuni per l'interfaccia grafica."""

import logging

from PyQt6.QtWidgets import QGroupBox
from PyQt6.QtGui import QFontMetrics

logger = logging.getLogger(__name__)


def _larghezza_titolo(fm, titolo: str) -> int:
    """Larghezza del titolo tenendo conto delle emoji.

    QFontMetrics misura un'emoji con il glifo presente nel font
    dell'interfaccia: dove quel glifo manca o è stretto restituisce 7-11px,
    mentre il sistema la disegna a colori occupando una cella intera. Il
    titolo risultava così più largo della misura, e veniva troncato.
    Per ogni carattere fuori dal latino conteggiamo almeno una cella quadrata
    (l'altezza del font), che è la resa tipica di un'emoji a colori.
    """
    larghezza = fm.horizontalAdvance(titolo)
    cella = fm.height()
    for ch in titolo:
        if ord(ch) > 0x2000:  # simboli, frecce, emoji: fuori dal latino
            misurato = fm.horizontalAdvance(ch)
            if misurato < cella:
                larghezza += cella - misurato
    return larghezza


def fit_group_title(group_box, extra: int = 32):
    """Garantisce al QGroupBox la larghezza minima per mostrare tutto il titolo.

    Su Linux i font di sistema sono più larghi che su Windows: la larghezza
    minima del riquadro la decide il contenuto, non il titolo, e titoli come
    "Sorgente Immagini" venivano tagliati in "Sorgente Immagi".
    `extra` copre bordo, indentazione (`left: 8px`) e padding (6+6px) del
    foglio di stile, con un margine di sicurezza: a font grandi i 32px fissi
    di prima si esaurivano e il titolo tornava a troncarsi.
    """
    try:
        titolo = group_box.title()
        if not titolo:
            return
        fm = QFontMetrics(group_box.font())
        # Il margine cresce col font: left(8) + padding(12) + bordo(4), più
        # una riserva pari all'altezza del font per gli arrotondamenti di resa.
        margine = max(extra, 8 + 12 + 4 + fm.height())
        larghezza = _larghezza_titolo(fm, titolo) + margine
        if larghezza > group_box.minimumWidth():
            group_box.setMinimumWidth(larghezza)
    except Exception:
        # Mai far fallire la costruzione della UI per una questione estetica
        logger.warning("Impossibile adattare il titolo del riquadro", exc_info=True)


def fit_all_group_titles(root, extra: int = 32) -> int:
    """Applica fit_group_title a tutti i QGroupBox contenuti in `root`.

    Da chiamare una volta a interfaccia costruita: evita di dover ricordare la
    chiamata su ognuno dei ~66 riquadri dell'applicazione, e copre anche quelli
    aggiunti in futuro. Ritorna il numero di riquadri adattati.
    """
    try:
        riquadri = root.findChildren(QGroupBox)
    except Exception:
        logger.warning("Impossibile enumerare i riquadri", exc_info=True)
        return 0

    for gb in riquadri:
        fit_group_title(gb, extra)
    return len(riquadri)
