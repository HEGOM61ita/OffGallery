# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024-2026 Michele Mulè <hegomm@gmail.com>
"""Utilità comuni per l'interfaccia grafica."""

import logging

from PyQt6.QtWidgets import QGroupBox
from PyQt6.QtGui import QFontMetrics

logger = logging.getLogger(__name__)


def fit_group_title(group_box, extra: int = 32):
    """Garantisce al QGroupBox la larghezza minima per mostrare tutto il titolo.

    Su Linux i font di sistema sono più larghi che su Windows: la larghezza
    minima del riquadro la decide il contenuto, non il titolo, e titoli come
    "Sorgente Immagini" venivano tagliati in "Sorgente Immagi".
    `extra` copre bordo, indentazione e l'eventuale emoji iniziale.
    """
    try:
        titolo = group_box.title()
        if not titolo:
            return
        fm = QFontMetrics(group_box.font())
        larghezza = fm.horizontalAdvance(titolo) + extra
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
