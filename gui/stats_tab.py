"""
Stats Tab — Archivio fotografico professionale
Focus: Salute archivio, Attrezzatura, Tecnica di scatto
"""

import logging
import sqlite3
import traceback as _traceback
from pathlib import Path

logger = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QScrollArea, QFrame, QGridLayout,
    QSizePolicy, QSpacerItem, QTabWidget,
)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter
from gui.directory_dialog import DirectoryTreeWidget

_MESI_IT = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]

def _fmt_date_it(date_str: str) -> str:
    """Converte una data ISO/EXIF in formato italiano leggibile (es. '15 apr 2024')."""
    if not date_str:
        return "—"
    try:
        from datetime import datetime
        # EXIF usa "2024:04:15 12:30:00", ISO usa "2024-04-15"
        clean = date_str[:10].replace(":", "-")
        dt = datetime.strptime(clean, "%Y-%m-%d")
        return f"{dt.day} {_MESI_IT[dt.month - 1]} {dt.year}"
    except Exception:
        return date_str[:10]


COLORS = {
    'grafite':            '#2A2A2A',
    'grafite_light':      '#3A3A3A',
    'grafite_dark':       '#1E1E1E',
    'grigio_chiaro':      '#E3E3E3',
    'grigio_medio':       '#B0B0B0',
    'blu_petrolio':       '#1C4F63',
    'blu_petrolio_light': '#2A6A82',
    'verde':              '#4A7C59',
    'rosso':              '#8B4049',
    'ambra':              '#C88B2E',
    'viola':              '#6A4C93',
}


# ---------------------------------------------------------------------------
# Worker: tutte le query SQL girano in un thread separato
# ---------------------------------------------------------------------------

class StatsWorker(QObject):
    """Esegue tutte le query di statistiche in un thread separato e restituisce i dati via signal."""

    finished = pyqtSignal(dict)   # dati pronti → aggiorna UI
    error    = pyqtSignal(str)    # messaggio di errore

    def __init__(self, db_path: str, selected_dirs: list):
        super().__init__()
        self.db_path       = db_path
        self.selected_dirs = selected_dirs

    def _path_filter(self):
        if not self.selected_dirs:
            return "1=1", []
        clauses = " OR ".join(["filepath LIKE ?" for _ in self.selected_dirs])
        params  = [str(d) + "%" for d in self.selected_dirs]
        return f"({clauses})", params

    def run(self):
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cur  = conn.cursor()
            pf, pp = self._path_filter()
            data = {}
            for method in (self._info_bar, self._kpis, self._archivio,
                           self._attrezzatura, self._tecnica, self._pattern,
                           self._gear_scores):
                try:
                    data.update(method(cur, pf, pp))
                except Exception as e:
                    logger.error(f"StatsWorker {method.__name__} errore: {e}", exc_info=True)
            self.finished.emit(data)
        except Exception as e:
            logger.error(f"StatsWorker errore fatale: {e}", exc_info=True)
            self.error.emit(str(e))
        finally:
            if conn:
                conn.close()

    # --- info bar ---

    def _info_bar(self, cur, pf, pp):
        d = {}
        cur.execute(f"SELECT COUNT(*) FROM images WHERE {pf}", pp)
        total = cur.fetchone()[0]
        d["info_total"] = f"{total:,}"

        cur.execute(f"SELECT SUM(file_size) FROM images WHERE {pf} AND file_size IS NOT NULL", pp)
        size = cur.fetchone()[0] or 0
        d["info_size"] = f"{size / 1024**3:.1f} GB"

        cur.execute(f"SELECT COUNT(*) FROM images WHERE {pf} AND is_raw = 1", pp)
        raw = cur.fetchone()[0]
        d["info_raw"] = f"{raw / total * 100:.0f}%" if total else "—"

        cur.execute(f"""
            SELECT MAX(COALESCE(datetime_original, datetime_digitized, datetime_modified))
            FROM images WHERE {pf}
        """, pp)
        last = cur.fetchone()[0]
        d["info_last"] = _fmt_date_it(last)
        return d

    # --- kpi ---

    def _kpis(self, cur, pf, pp):
        d = {}
        cur.execute(f"SELECT COUNT(*) FROM images WHERE {pf}", pp)
        d["kpi_total"] = f"{cur.fetchone()[0]:,}"

        cur.execute(f"""
            SELECT AVG(lr_rating), COUNT(*) FROM images
            WHERE {pf} AND lr_rating IS NOT NULL AND lr_rating > 0
        """, pp)
        r = cur.fetchone()
        d["kpi_rating"]          = f"{r[0]:.1f}★" if r[0] else "—"
        d["kpi_rating_sub"]      = f"su {r[1]:,} foto valutate" if r[0] else "nessun rating assegnato"

        cur.execute(f"""
            SELECT AVG(aesthetic_score), COUNT(*) FROM images
            WHERE {pf} AND aesthetic_score IS NOT NULL
        """, pp)
        r = cur.fetchone()
        d["kpi_aesthetic"]     = f"{r[0]:.1f}" if r[0] else "—"
        d["kpi_aesthetic_sub"] = f"su {r[1]:,} foto analizzate" if r[0] else "score non ancora calcolato"
        return d

    # --- archivio ---

    def _archivio(self, cur, pf, pp):
        d = {}

        cur.execute(f"""
            SELECT COALESCE(lr_rating, 0), COUNT(*) FROM images WHERE {pf}
            GROUP BY COALESCE(lr_rating, 0) ORDER BY COALESCE(lr_rating, 0)
        """, pp)
        raw = {int(r[0]): r[1] for r in cur.fetchall()}
        d["rating_chart"] = {
            ("☆ Nessuno" if s == 0 else "★" * s): raw.get(s, 0)
            for s in range(0, 6)
        }

        for key in ("red", "yellow", "green", "blue", "purple"):
            cur.execute(
                f"SELECT COUNT(*) FROM images WHERE {pf} AND LOWER(color_label) = ?", pp + [key]
            )
            d[f"color_{key}"] = f"{cur.fetchone()[0]:,}"
        cur.execute(f"""
            SELECT COUNT(*) FROM images WHERE {pf} AND (color_label IS NULL OR color_label = '')
        """, pp)
        d["color_none"] = f"{cur.fetchone()[0]:,}"

        cur.execute(f"SELECT COUNT(*) FROM images WHERE {pf}", pp)
        total = cur.fetchone()[0] or 1
        for key, cond in [
            ("with_title",  "title IS NOT NULL AND title != ''"),
            ("with_desc",   "description IS NOT NULL AND description != ''"),
            ("with_tags",   "tags IS NOT NULL AND tags != '[]' AND tags != ''"),
            ("with_rating", "lr_rating IS NOT NULL AND lr_rating > 0"),
            ("with_gps",    "gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL"),
        ]:
            cur.execute(f"SELECT COUNT(*) FROM images WHERE {pf} AND {cond}", pp)
            n = cur.fetchone()[0]
            d[f"meta_{key}"] = f"{n / total * 100:.1f}%  ({n:,})"

        cur.execute(f"SELECT AVG(aesthetic_score), COUNT(*) FROM images WHERE {pf} AND aesthetic_score IS NOT NULL", pp)
        r = cur.fetchone()
        d["score_aesth_avg"] = f"{r[0]:.2f} / 10" if r[0] else "—"
        d["score_aesth_cov"] = f"{r[1]:,}  ({r[1] / total * 100:.1f}%)"

        cur.execute(f"SELECT AVG(technical_score), COUNT(*) FROM images WHERE {pf} AND technical_score IS NOT NULL", pp)
        r = cur.fetchone()
        d["score_tech_avg"] = f"{r[0]:.1f}" if r[0] else "—"
        d["score_tech_cov"] = f"{r[1]:,}  ({r[1] / total * 100:.1f}%)"

        cur.execute(f"""
            SELECT COALESCE(strftime('%Y', datetime_original),
                            strftime('%Y', datetime_digitized),
                            strftime('%Y', datetime_modified)) AS yr, COUNT(*)
            FROM images WHERE {pf}
            GROUP BY yr HAVING yr IS NOT NULL ORDER BY yr
        """, pp)
        d["timeline_chart"] = {r[0]: r[1] for r in cur.fetchall()}
        return d

    # --- attrezzatura ---

    def _attrezzatura(self, cur, pf, pp):
        d = {}

        cur.execute(f"SELECT camera_model, COUNT(*) AS n FROM images WHERE {pf} AND camera_model IS NOT NULL GROUP BY camera_model ORDER BY n DESC", pp)
        d["cameras_chart"] = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute(f"SELECT lens_model, COUNT(*) AS n FROM images WHERE {pf} AND lens_model IS NOT NULL GROUP BY lens_model ORDER BY n DESC", pp)
        d["lenses_chart"] = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute(f"""
            SELECT CASE
                WHEN focal_length < 20  THEN '<20mm'  WHEN focal_length < 35  THEN '20-35mm'
                WHEN focal_length < 50  THEN '35-50mm' WHEN focal_length < 85  THEN '50-85mm'
                WHEN focal_length < 135 THEN '85-135mm' WHEN focal_length < 200 THEN '135-200mm'
                ELSE '>200mm'
            END AS rng, COUNT(*) AS n
            FROM images WHERE {pf} AND focal_length IS NOT NULL GROUP BY rng ORDER BY n DESC
        """, pp)
        d["focal_chart"] = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute(f"SELECT aperture, COUNT(*) AS n FROM images WHERE {pf} AND aperture IS NOT NULL GROUP BY aperture ORDER BY n DESC LIMIT 8", pp)
        d["aperture_chart"] = {f"f/{r[0]}": r[1] for r in cur.fetchall()}

        cur.execute(f"SELECT COUNT(DISTINCT camera_model) FROM images WHERE {pf} AND camera_model IS NOT NULL", pp)
        d["gear_n_cameras"] = str(cur.fetchone()[0])

        cur.execute(f"SELECT COUNT(DISTINCT lens_model) FROM images WHERE {pf} AND lens_model IS NOT NULL", pp)
        d["gear_n_lenses"] = str(cur.fetchone()[0])

        cur.execute(f"SELECT focal_length, COUNT(*) AS n FROM images WHERE {pf} AND focal_length IS NOT NULL GROUP BY focal_length ORDER BY n DESC LIMIT 1", pp)
        r = cur.fetchone()
        d["gear_top_focal"] = f"{int(r[0])}mm" if r else "—"

        cur.execute(f"SELECT MIN(focal_length), MAX(focal_length) FROM images WHERE {pf} AND focal_length IS NOT NULL", pp)
        r = cur.fetchone()
        d["gear_focal_range"] = f"{int(r[0])}-{int(r[1])}mm" if (r and r[0]) else "—"
        return d

    # --- tecnica ---

    def _tecnica(self, cur, pf, pp):
        d = {}

        cur.execute(f"""
            SELECT CASE
                WHEN shutter_speed_decimal >= 1     THEN '≥1s'
                WHEN shutter_speed_decimal >= 0.5   THEN '1/2s'
                WHEN shutter_speed_decimal >= 0.1   THEN '1/10s'
                WHEN shutter_speed_decimal >= 0.02  THEN '1/50s'
                WHEN shutter_speed_decimal >= 0.008 THEN '1/125s'
                WHEN shutter_speed_decimal >= 0.004 THEN '1/250s'
                WHEN shutter_speed_decimal >= 0.002 THEN '1/500s'
                ELSE '≥1/1000s'
            END AS rng, COUNT(*) AS n
            FROM images WHERE {pf} AND shutter_speed_decimal IS NOT NULL GROUP BY rng ORDER BY n DESC
        """, pp)
        d["shutter_chart"] = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute(f"""
            SELECT CASE
                WHEN iso <= 100  THEN '≤100'   WHEN iso <= 200  THEN '101-200'
                WHEN iso <= 400  THEN '201-400' WHEN iso <= 800  THEN '401-800'
                WHEN iso <= 1600 THEN '801-1600' WHEN iso <= 3200 THEN '1601-3200'
                WHEN iso <= 6400 THEN '3201-6400' ELSE '>6400'
            END AS rng, COUNT(*) AS n
            FROM images WHERE {pf} AND iso IS NOT NULL GROUP BY rng ORDER BY n DESC
        """, pp)
        d["iso_chart"] = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute(f"SELECT focal_length FROM images WHERE {pf} AND focal_length IS NOT NULL GROUP BY focal_length ORDER BY COUNT(*) DESC LIMIT 1", pp)
        r = cur.fetchone()
        d["firma_focal"]   = f"{int(r[0])}mm" if r else "—"

        cur.execute(f"SELECT aperture FROM images WHERE {pf} AND aperture IS NOT NULL GROUP BY aperture ORDER BY COUNT(*) DESC LIMIT 1", pp)
        r = cur.fetchone()
        d["firma_aperture"] = f"f/{r[0]}" if r else "—"

        cur.execute(f"SELECT iso FROM images WHERE {pf} AND iso IS NOT NULL GROUP BY iso ORDER BY COUNT(*) DESC LIMIT 1", pp)
        r = cur.fetchone()
        d["firma_iso"] = f"ISO {r[0]}" if r else "—"

        cur.execute("PRAGMA table_info(images)")
        cols = {c[1] for c in cur.fetchall()}
        if "flash_used" in cols:
            cur.execute(f"SELECT COUNT(*) FROM images WHERE {pf} AND flash_used = 1", pp)
            n_flash = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM images WHERE {pf} AND flash_used IS NOT NULL", pp)
            n_tot = cur.fetchone()[0]
            d["firma_flash"] = f"{n_flash / n_tot * 100:.0f}%" if n_tot else "—"
        else:
            d["firma_flash"] = "N/A"

        cur.execute(f"SELECT COUNT(*) FROM images WHERE {pf}", pp)
        total = cur.fetchone()[0] or 1
        cur.execute(f"SELECT COUNT(*) FROM images WHERE {pf} AND gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL", pp)
        n_gps = cur.fetchone()[0]
        d["geo_coverage"] = f"{n_gps / total * 100:.1f}%  ({n_gps:,})"

        cur.execute(f"SELECT COUNT(DISTINCT gps_country) FROM images WHERE {pf} AND gps_country IS NOT NULL AND gps_country != ''", pp)
        d["geo_countries"] = str(cur.fetchone()[0])

        cur.execute(f"SELECT COUNT(DISTINCT gps_city) FROM images WHERE {pf} AND gps_city IS NOT NULL AND gps_city != ''", pp)
        d["geo_cities"] = str(cur.fetchone()[0])

        cur.execute(f"SELECT gps_city, COUNT(*) AS n FROM images WHERE {pf} AND gps_city IS NOT NULL AND gps_city != '' GROUP BY gps_city ORDER BY n DESC LIMIT 1", pp)
        r = cur.fetchone()
        d["geo_top"] = f"{r[0]} ({r[1]:,})" if r else "—"
        return d

    # --- pattern temporali e stile ---

    # Helper per convertire datetime EXIF "YYYY:MM:DD HH:MM:SS" in ISO per strftime SQLite
    _DT = "REPLACE(SUBSTR(datetime_original,1,10),':','-') || SUBSTR(datetime_original,11)"

    def _pattern(self, cur, pf, pp):
        d = {}

        # Ora del giorno → 6 fasce
        cur.execute(f"""
            SELECT
                CASE CAST(strftime('%H', {self._DT}) AS INTEGER)
                    WHEN 5 THEN 'Alba (5-7)' WHEN 6 THEN 'Alba (5-7)' WHEN 7 THEN 'Alba (5-7)'
                    WHEN 8 THEN 'Mattina (8-11)' WHEN 9 THEN 'Mattina (8-11)'
                    WHEN 10 THEN 'Mattina (8-11)' WHEN 11 THEN 'Mattina (8-11)'
                    WHEN 12 THEN 'Mezzogiorno (12-14)' WHEN 13 THEN 'Mezzogiorno (12-14)'
                    WHEN 14 THEN 'Mezzogiorno (12-14)'
                    WHEN 15 THEN 'Pomeriggio (15-17)' WHEN 16 THEN 'Pomeriggio (15-17)'
                    WHEN 17 THEN 'Pomeriggio (15-17)'
                    WHEN 18 THEN 'Ora d''oro (18-20)' WHEN 19 THEN 'Ora d''oro (18-20)'
                    WHEN 20 THEN 'Ora d''oro (18-20)'
                    ELSE 'Notte/Sera'
                END AS fascia,
                COUNT(*) AS n
            FROM images
            WHERE {pf} AND datetime_original IS NOT NULL
            GROUP BY fascia ORDER BY n DESC
        """, pp)
        d["pattern_ora"] = {r[0]: r[1] for r in cur.fetchall()}

        # Mese dell'anno
        _MESI = ["Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"]
        cur.execute(f"""
            SELECT CAST(strftime('%m', {self._DT}) AS INTEGER) AS m, COUNT(*) AS n
            FROM images WHERE {pf} AND datetime_original IS NOT NULL
            GROUP BY m ORDER BY m
        """, pp)
        d["pattern_mese"] = {_MESI[r[0]-1]: r[1] for r in cur.fetchall() if r[0]}

        # Giorno della settimana (SQLite: 0=Dom, 1=Lun, ..., 6=Sab)
        _GIORNI = {0:"Dom", 1:"Lun", 2:"Mar", 3:"Mer", 4:"Gio", 5:"Ven", 6:"Sab"}
        cur.execute(f"""
            SELECT CAST(strftime('%w', {self._DT}) AS INTEGER) AS wd, COUNT(*) AS n
            FROM images WHERE {pf} AND datetime_original IS NOT NULL
            GROUP BY wd ORDER BY wd
        """, pp)
        # ordina Lun→Dom
        raw_wd = {r[0]: r[1] for r in cur.fetchall()}
        d["pattern_giorno"] = {_GIORNI[k]: raw_wd[k] for k in [1,2,3,4,5,6,0] if k in raw_wd}

        # Modalità esposizione (EXIF tag numerico → etichetta)
        cur.execute(f"""
            SELECT
                CASE CAST(exposure_mode AS INTEGER)
                    WHEN 0 THEN 'Auto'
                    WHEN 1 THEN 'Manuale'
                    WHEN 2 THEN 'Auto bracket'
                    WHEN 3 THEN 'Manual bracket'
                    ELSE CAST(exposure_mode AS TEXT)
                END AS label,
                COUNT(*) AS n
            FROM images
            WHERE {pf} AND exposure_mode IS NOT NULL AND exposure_mode != ''
            GROUP BY label ORDER BY n DESC LIMIT 8
        """, pp)
        d["pattern_exposure_mode"] = {r[0]: r[1] for r in cur.fetchall()}

        # Drive mode
        cur.execute(f"""
            SELECT drive_mode, COUNT(*) AS n FROM images
            WHERE {pf} AND drive_mode IS NOT NULL AND drive_mode != ''
            GROUP BY drive_mode ORDER BY n DESC
        """, pp)
        d["pattern_drive"] = {r[0]: r[1] for r in cur.fetchall()}

        # B&N
        cur.execute(f"SELECT COUNT(*) FROM images WHERE {pf} AND is_monochrome = 1", pp)
        d["bw_count"] = f"{cur.fetchone()[0]:,}"

        return d

    # --- score per attrezzatura ---

    def _gear_scores(self, cur, pf, pp):
        d = {}

        # Score medio per fotocamera (solo dove abbiamo aesthetic_score)
        cur.execute(f"""
            SELECT camera_model, AVG(aesthetic_score) AS avg_s, COUNT(*) AS n
            FROM images
            WHERE {pf} AND camera_model IS NOT NULL AND aesthetic_score IS NOT NULL
            GROUP BY camera_model HAVING n >= 5
            ORDER BY avg_s DESC LIMIT 8
        """, pp)
        rows = cur.fetchall()
        d["score_per_camera"] = {f"{r[0]}": r[1] for r in rows}
        d["score_per_camera_n"] = {f"{r[0]}": r[2] for r in rows}

        # Score medio per obiettivo
        cur.execute(f"""
            SELECT lens_model, AVG(aesthetic_score) AS avg_s, COUNT(*) AS n
            FROM images
            WHERE {pf} AND lens_model IS NOT NULL AND aesthetic_score IS NOT NULL
            GROUP BY lens_model HAVING n >= 5
            ORDER BY avg_s DESC LIMIT 8
        """, pp)
        rows = cur.fetchall()
        d["score_per_lens"] = {f"{r[0]}": r[1] for r in rows}
        d["score_per_lens_n"] = {f"{r[0]}": r[2] for r in rows}

        # Top combinazioni camera + obiettivo
        cur.execute(f"""
            SELECT camera_model || '  +  ' || lens_model AS combo, COUNT(*) AS n
            FROM images
            WHERE {pf} AND camera_model IS NOT NULL AND lens_model IS NOT NULL
            GROUP BY combo ORDER BY n DESC LIMIT 8
        """, pp)
        d["gear_combos"] = {r[0]: r[1] for r in cur.fetchall()}

        return d


# ---------------------------------------------------------------------------
# Widget: KPI card
# ---------------------------------------------------------------------------

class KPICard(QFrame):
    """Card con valore principale grande e sottotitolo opzionale."""

    def __init__(self, title, value="—", icon="📊", color=COLORS['blu_petrolio']):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet(f"""
            KPICard {{
                background-color: {color};
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,0.1);
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 16px; color: rgba(255,255,255,0.8);")
        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.95); font-weight: 700; font-size: 10px; letter-spacing: 0.5px;"
        )
        header.addWidget(icon_lbl)
        header.addSpacerItem(QSpacerItem(8, 0))
        header.addWidget(title_lbl)
        header.addStretch()
        layout.addLayout(header)

        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet("color: white; font-size: 28px; font-weight: 700;")
        layout.addWidget(self.value_label)

        self.subtitle_label = QLabel("")
        self.subtitle_label.setStyleSheet("color: rgba(255,255,255,0.80); font-size: 10px;")
        layout.addWidget(self.subtitle_label)

    def update_value(self, value, subtitle=""):
        self.value_label.setText(str(value))
        self.subtitle_label.setText(subtitle)


# ---------------------------------------------------------------------------
# Widget: bar chart con etichette multiriga (per nomi attrezzatura lunghi)
# ---------------------------------------------------------------------------

class GearBarChart(QWidget):

    def __init__(self, data, color=COLORS['ambra'], max_bars=8):
        super().__init__()
        self.data = data
        self.color = color
        self.max_bars = max_bars
        self.setMinimumHeight(280)
        self.setStyleSheet("background-color: transparent;")

    def update_data(self, new_data):
        self.data = new_data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.data:
            painter.setPen(QColor(COLORS['grigio_medio']))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Nessun dato")
            return

        sorted_data = sorted(self.data.items(), key=lambda x: x[1], reverse=True)[: self.max_bars]
        max_val = max(v for _, v in sorted_data)
        label_w = 130
        val_w   = 58
        # barre: dal bordo label al bordo valore (valore ancorato a destra)
        bar_x0  = label_w + 8
        bar_x1  = self.width() - val_w - 6
        bar_max = max(1, bar_x1 - bar_x0)
        chart_height = self.height() - 40
        bar_h = max(18, chart_height / len(sorted_data) - 14)

        for i, (label, value) in enumerate(sorted_data):
            y = 20 + i * (bar_h + 14)
            bw = (value / max_val) * bar_max if max_val else 0

            painter.setBrush(QColor(self.color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(bar_x0), int(y), int(bw), int(bar_h), 4, 4)

            if value > 0:
                font = painter.font()
                font.setPointSize(9)
                font.setWeight(QFont.Weight.Bold)
                painter.setFont(font)
                painter.setPen(QColor(COLORS['grigio_chiaro']))
                # valore ancorato al bordo destro, sempre visibile
                painter.drawText(
                    int(bar_x1 + 4), int(y), val_w, int(bar_h),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    f"{value:,}",
                )

            font = painter.font()
            font.setPointSize(8)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            painter.setPen(QColor(COLORS['grigio_medio']))

            words = label.split()
            if len(words) <= 2 and len(label) <= 18:
                lines = [label]
            elif len(words) == 2:
                lines = words
            else:
                mid = len(words) // 2
                lines = [" ".join(words[:mid]), " ".join(words[mid:])]
            lines = [ln[:20] + ("…" if len(ln) > 20 else "") for ln in lines[:2]]

            lh = 11
            sy = y + (bar_h - len(lines) * lh) // 2
            for j, line in enumerate(lines):
                painter.drawText(
                    5, int(sy + j * lh), label_w - 10, lh,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    line,
                )


# ---------------------------------------------------------------------------
# Widget: bar chart generico (label corte)
# ---------------------------------------------------------------------------

class ProBarChart(QWidget):

    def __init__(self, data, color=COLORS['ambra'], max_bars=10, fmt="{:,}"):
        super().__init__()
        self.data = data
        self.color = color
        self.max_bars = max_bars
        self.fmt = fmt
        self.setMinimumHeight(180)
        self.setStyleSheet("background-color: transparent;")

    def update_data(self, new_data):
        self.data = new_data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.data:
            painter.setPen(QColor(COLORS['grigio_medio']))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Nessun dato")
            return

        sorted_data = sorted(self.data.items(), key=lambda x: x[1], reverse=True)[: self.max_bars]
        max_val = max(v for _, v in sorted_data)
        label_w = 100
        val_w   = 55
        bar_x0  = label_w + 8
        bar_x1  = self.width() - val_w - 6
        bar_max = max(1, bar_x1 - bar_x0)
        chart_height = self.height() - 40
        bar_h = max(12, chart_height / len(sorted_data) - 8)

        for i, (label, value) in enumerate(sorted_data):
            y = 20 + i * (bar_h + 8)
            bw = (value / max_val) * bar_max if max_val else 0

            painter.setBrush(QColor(self.color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(bar_x0), int(y), int(bw), int(bar_h), 3, 3)

            if value > 0:
                font = painter.font()
                font.setPointSize(9)
                font.setWeight(QFont.Weight.Bold)
                painter.setFont(font)
                painter.setPen(QColor(COLORS['grigio_chiaro']))
                painter.drawText(
                    int(bar_x1 + 4), int(y), val_w, int(bar_h),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    self.fmt.format(value),
                )

            font = painter.font()
            font.setPointSize(9)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            painter.setPen(QColor(COLORS['grigio_medio']))
            fm = painter.fontMetrics()
            display = label if fm.boundingRect(label).width() <= label_w - 10 else label[:14] + "…"
            painter.drawText(
                5, int(y), label_w - 10, int(bar_h),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                display,
            )


# ---------------------------------------------------------------------------
# StatsTab principale
# ---------------------------------------------------------------------------

class StatsTab(QWidget):
    """Tab statistiche per fotografi professionali e semi-professionali."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.db_manager = None
        self._selected_dirs = []

        # Info bar
        self._info_total = None
        self._info_size  = None
        self._info_raw   = None
        self._info_last  = None

        # KPI
        self.kpi_total     = None
        self.kpi_rating    = None
        self.kpi_aesthetic = None

        # Chart refs — base
        self.rating_chart   = None
        self.timeline_chart = None
        self.cameras_chart  = None
        self.lenses_chart   = None
        self.focal_chart    = None
        self.aperture_chart = None
        self.shutter_chart  = None
        self.iso_chart      = None

        # Chart refs — pattern temporali
        self.ora_chart    = None
        self.mese_chart   = None
        self.giorno_chart = None
        self.exp_mode_chart = None
        self.drive_chart  = None

        # Chart refs — score per gear
        self.score_camera_chart = None
        self.score_lens_chart   = None
        self.combos_chart       = None

        # Metric row value labels
        self._color_labels = {}
        self._metadata     = {}
        self._scores       = {}
        self._gear_summary = {}
        self._firma        = {}
        self._geo          = {}

        # Dir filter
        self._dir_widget       = None
        self._dir_inner        = None
        self._dir_status_label = None

        # Thread worker
        self._stats_thread = None
        self._stats_worker = None
        self._refresh_pending = False   # richiesta arrivata mentre giravo già

        try:
            self.init_ui()
            logger.debug("StatsTab inizializzata")
        except Exception as e:
            logger.error(f"Errore init StatsTab: {e}")
            logger.debug(_traceback.format_exc())

    # ------------------------------------------------------------------
    # Helper: filtro path
    # ------------------------------------------------------------------

    def _path_filter(self):
        """Restituisce (where_fragment, params) per il filtro directory attivo."""
        if not self._selected_dirs:
            return "1=1", []
        clauses = " OR ".join(["filepath LIKE ?" for _ in self._selected_dirs])
        params = [str(d) + "%" for d in self._selected_dirs]
        return f"({clauses})", params

    # ------------------------------------------------------------------
    # Costruzione UI
    # ------------------------------------------------------------------

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {COLORS['grafite']}; border: none; }}
            QScrollBar:vertical {{
                background-color: {COLORS['grafite_light']}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['blu_petrolio']}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        content = QWidget()
        content.setStyleSheet(f"background-color: {COLORS['grafite']};")
        main = QVBoxLayout(content)
        main.setContentsMargins(24, 20, 24, 20)
        main.setSpacing(16)

        main.addWidget(self._create_dir_filter())
        main.addWidget(self._create_info_bar())
        self._create_kpi_dashboard(main)
        self._create_tabs(main)

        scroll.setWidget(content)
        layout.addWidget(scroll)

    # --- Filtro directory ---------------------------------------------------

    def _create_dir_filter(self):
        self._dir_group = QGroupBox("📁 Ambito statistiche")
        self._dir_group.setCheckable(True)
        self._dir_group.setChecked(False)
        self._dir_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold; font-size: 12px;
                border: 1px solid {COLORS['grafite_light']}; border-radius: 5px;
                margin-top: 6px; padding-top: 4px;
                background-color: {COLORS['grafite']}; color: {COLORS['grigio_chiaro']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 12px;
                padding: 0 6px; color: {COLORS['grigio_chiaro']};
            }}
            QGroupBox::indicator {{ width: 14px; height: 14px; }}
            QGroupBox::indicator:unchecked {{
                background-color: #e0e0e0; border: 1px solid #aaa; border-radius: 2px;
            }}
            QGroupBox::indicator:checked {{
                background-color: {COLORS['blu_petrolio']};
                border: 1px solid {COLORS['blu_petrolio']}; border-radius: 2px;
            }}
        """)

        outer = QVBoxLayout(self._dir_group)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        self._dir_inner = QWidget()
        inner = QVBoxLayout(self._dir_inner)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(4)

        self._dir_status_label = QLabel("")
        self._dir_status_label.setStyleSheet(
            f"color: {COLORS['ambra']}; font-size: 11px; font-weight: bold;"
        )
        inner.addWidget(self._dir_status_label)

        self._dir_widget = DirectoryTreeWidget(self._dir_inner)
        self._dir_widget.tree.setMinimumHeight(160)
        self._dir_widget.setMaximumHeight(400)
        self._dir_widget.selection_changed.connect(self._on_dir_selection_changed)
        inner.addWidget(self._dir_widget)

        self._dir_inner.setVisible(False)
        outer.addWidget(self._dir_inner)
        self._dir_group.toggled.connect(lambda checked: self._dir_inner.setVisible(checked))

        return self._dir_group

    def _on_dir_selection_changed(self, selected_dirs):
        self._selected_dirs = selected_dirs
        if selected_dirs:
            n = len(selected_dirs)
            self._dir_status_label.setText(
                f"● {n} director{'ia' if n == 1 else 'ie'} selezionate"
            )
        else:
            self._dir_status_label.setText("Intero archivio")
        if self.db_manager:
            self.refresh_stats()

    # --- Info bar -----------------------------------------------------------

    def _create_info_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"""
            QFrame {{ background-color: {COLORS['grafite_dark']}; border-radius: 8px; }}
            QLabel {{ background: transparent; }}
        """)
        bar.setFixedHeight(56)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(0)

        self._info_total = self._add_info_item(layout, "FOTO IN ARCHIVIO")
        layout.addWidget(self._make_sep())
        self._info_size = self._add_info_item(layout, "DIMENSIONE")
        layout.addWidget(self._make_sep())
        self._info_raw = self._add_info_item(layout, "FILE RAW")
        layout.addWidget(self._make_sep())
        self._info_last = self._add_info_item(layout, "ULTIMO SCATTO")
        layout.addStretch()

        return bar

    def _add_info_item(self, layout, label_text):
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 6, 0, 6)
        vl.setSpacing(1)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(
            f"color: {COLORS['grigio_medio']}; font-size: 8px; font-weight: 600; letter-spacing: 0.5px;"
        )
        val = QLabel("—")
        val.setStyleSheet(f"color: {COLORS['grigio_chiaro']}; font-size: 15px; font-weight: 700;")
        vl.addWidget(lbl)
        vl.addWidget(val)
        layout.addWidget(w)
        return val

    def _make_sep(self):
        sep = QLabel("│")
        sep.setStyleSheet(f"color: {COLORS['grafite_light']}; font-size: 22px; padding: 0 20px;")
        return sep

    # --- KPI ----------------------------------------------------------------

    def _create_kpi_dashboard(self, layout):
        row = QHBoxLayout()
        row.setSpacing(16)
        self.kpi_total     = KPICard("Foto nel perimetro", "—", "📁", COLORS['blu_petrolio'])
        self.kpi_rating    = KPICard("Rating medio",       "—", "⭐", COLORS['ambra'])
        self.kpi_aesthetic = KPICard("Score estetico",     "—", "🎨", COLORS['viola'])
        row.addWidget(self.kpi_total)
        row.addWidget(self.kpi_rating)
        row.addWidget(self.kpi_aesthetic)
        layout.addLayout(row)

    # --- Tab container ------------------------------------------------------

    def _create_tabs(self, layout):
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS['grafite_light']};
                background-color: {COLORS['grafite_light']};
                border-radius: 8px;
            }}
            QTabBar::tab {{
                background-color: {COLORS['grafite_dark']};
                color: {COLORS['grigio_medio']};
                padding: 12px 20px; margin-right: 2px;
                border-top-left-radius: 8px; border-top-right-radius: 8px;
                font-weight: 600; font-size: 11px;
            }}
            QTabBar::tab:selected {{
                background-color: {COLORS['grafite_light']};
                color: {COLORS['grigio_chiaro']};
            }}
            QTabBar::tab:hover {{
                background-color: {COLORS['grafite']};
                color: {COLORS['grigio_chiaro']};
            }}
        """)
        self.tab_widget.addTab(self._create_archivio_tab(),     "📁 Archivio")
        self.tab_widget.addTab(self._create_attrezzatura_tab(), "📸 Attrezzatura")
        self.tab_widget.addTab(self._create_tecnica_tab(),      "🎯 Tecnica")
        self.tab_widget.addTab(self._create_ritmo_tab(),        "📅 Pattern")
        layout.addWidget(self.tab_widget)

    # ------------------------------------------------------------------
    # Style helpers
    # ------------------------------------------------------------------

    def _groupbox_style(self):
        return f"""
            QGroupBox {{
                font-weight: 600; font-size: 12px;
                color: {COLORS['grigio_chiaro']};
                border: 2px solid {COLORS['grafite_dark']};
                border-radius: 8px; margin-top: 8px; padding-top: 8px;
                background-color: {COLORS['grafite_light']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 12px;
                padding: 0 8px; color: {COLORS['grigio_chiaro']};
                background-color: {COLORS['grafite_light']};
            }}
            QLabel {{ padding: 4px 8px; margin: 1px 0; }}
        """

    def _metric_row(self, label_text, key, target_dict, even=True):
        """Riga label + valore con zebra striping. Salva il QLabel del valore in target_dict[key]."""
        row = QWidget()
        bg = COLORS['grafite_light'] if even else COLORS['grafite']
        row.setStyleSheet(f"""
            QWidget {{ background-color: {bg}; border-radius: 4px; margin: 1px 0; }}
            QLabel {{ background: transparent; padding: 6px 8px; }}
        """)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(f"{label_text}:")
        lbl.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-weight: 500;")
        val = QLabel("—")
        val.setStyleSheet(f"color: {COLORS['grigio_chiaro']}; font-weight: 600;")
        target_dict[key] = val
        rl.addWidget(lbl)
        rl.addStretch()
        rl.addWidget(val)
        return row

    # ------------------------------------------------------------------
    # Tab: Archivio
    # ------------------------------------------------------------------

    def _create_archivio_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        grid = QGridLayout()
        grid.setSpacing(16)

        # Rating distribution
        rg = QGroupBox("⭐ Distribuzione Rating")
        rg.setStyleSheet(self._groupbox_style())
        rg_l = QVBoxLayout(rg)
        self.rating_chart = ProBarChart({}, COLORS['ambra'], max_bars=6)
        self.rating_chart.setMinimumHeight(200)
        rg_l.addWidget(self.rating_chart)

        # Color label
        cg = QGroupBox("🏷️ Color Label")
        cg.setStyleSheet(self._groupbox_style())
        cg_l = QVBoxLayout(cg)
        self._color_labels = {}
        for i, (key, icon, name) in enumerate([
            ("red",    "🔴", "Rossa"),
            ("yellow", "🟡", "Gialla"),
            ("green",  "🟢", "Verde"),
            ("blue",   "🔵", "Blu"),
            ("purple", "🟣", "Viola"),
            ("none",   "⬜", "Nessuna"),
        ]):
            cg_l.addWidget(self._metric_row(f"{icon} {name}", key, self._color_labels, i % 2 == 0))

        # Metadata completeness
        mg = QGroupBox("📝 Completezza Metadata")
        mg.setStyleSheet(self._groupbox_style())
        mg_l = QVBoxLayout(mg)
        self._metadata = {}
        for i, (label, key) in enumerate([
            ("Con titolo",      "with_title"),
            ("Con descrizione", "with_desc"),
            ("Con tag",         "with_tags"),
            ("Con rating",      "with_rating"),
            ("Con GPS",         "with_gps"),
        ]):
            mg_l.addWidget(self._metric_row(label, key, self._metadata, i % 2 == 0))

        # Score qualità AI
        sg = QGroupBox("🎨 Score Qualità AI")
        sg.setStyleSheet(self._groupbox_style())
        sg_l = QVBoxLayout(sg)
        self._scores = {}
        for i, (label, key) in enumerate([
            ("Score estetico medio",    "aesth_avg"),
            ("Foto con score estetico", "aesth_cov"),
            ("Score tecnico medio",     "tech_avg"),
            ("Foto con score tecnico",  "tech_cov"),
            ("Foto in B&N",             "bw_count"),
        ]):
            sg_l.addWidget(self._metric_row(label, key, self._scores, i % 2 == 0))

        grid.addWidget(rg, 0, 0)
        grid.addWidget(cg, 0, 1)
        grid.addWidget(mg, 1, 0)
        grid.addWidget(sg, 1, 1)
        layout.addLayout(grid)

        # Timeline — larghezza piena
        tg = QGroupBox("📅 Distribuzione Temporale")
        tg.setStyleSheet(self._groupbox_style())
        tg_l = QVBoxLayout(tg)
        self.timeline_chart = ProBarChart({}, COLORS['blu_petrolio'], max_bars=20)
        self.timeline_chart.setMinimumHeight(200)
        tg_l.addWidget(self.timeline_chart)
        layout.addWidget(tg)

        return widget

    # ------------------------------------------------------------------
    # Tab: Attrezzatura
    # ------------------------------------------------------------------

    def _create_attrezzatura_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Riga 1: tre chart
        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)

        cam_g = QGroupBox("📷 Fotocamere")
        cam_g.setStyleSheet(self._groupbox_style())
        cam_l = QVBoxLayout(cam_g)
        self.cameras_chart = GearBarChart({}, COLORS['verde'])
        cam_l.addWidget(self.cameras_chart)

        lens_g = QGroupBox("🔍 Obiettivi")
        lens_g.setStyleSheet(self._groupbox_style())
        lens_l = QVBoxLayout(lens_g)
        self.lenses_chart = GearBarChart({}, COLORS['ambra'])
        lens_l.addWidget(self.lenses_chart)

        focal_g = QGroupBox("📏 Focali")
        focal_g.setStyleSheet(self._groupbox_style())
        focal_l = QVBoxLayout(focal_g)
        self.focal_chart = GearBarChart({}, COLORS['viola'])
        focal_l.addWidget(self.focal_chart)

        charts_row.addWidget(cam_g)
        charts_row.addWidget(lens_g)
        charts_row.addWidget(focal_g)
        layout.addLayout(charts_row)

        # Riga 2: apertura + riepilogo
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        ap_g = QGroupBox("🎯 Distribuzione Apertura")
        ap_g.setStyleSheet(self._groupbox_style())
        ap_l = QVBoxLayout(ap_g)
        self.aperture_chart = ProBarChart({}, COLORS['verde'], max_bars=8)
        self.aperture_chart.setMinimumHeight(200)
        ap_l.addWidget(self.aperture_chart)

        sum_g = QGroupBox("📋 Riepilogo")
        sum_g.setStyleSheet(self._groupbox_style())
        sum_l = QVBoxLayout(sum_g)
        self._gear_summary = {}
        for i, (label, key) in enumerate([
            ("Fotocamere diverse", "n_cameras"),
            ("Obiettivi diversi",  "n_lenses"),
            ("Focale più usata",   "top_focal"),
            ("Range focali",       "focal_range"),
        ]):
            sum_l.addWidget(self._metric_row(label, key, self._gear_summary, i % 2 == 0))

        bottom_row.addWidget(ap_g, stretch=2)
        bottom_row.addWidget(sum_g, stretch=1)
        layout.addLayout(bottom_row)

        # Riga 3: score per attrezzatura + combinazioni top
        scores_row = QHBoxLayout()
        scores_row.setSpacing(16)

        sc_cam_g = QGroupBox("🏆 Score Estetico per Fotocamera")
        sc_cam_g.setStyleSheet(self._groupbox_style())
        sc_cam_l = QVBoxLayout(sc_cam_g)
        sc_cam_note = QLabel("Media score estetico (min. 5 foto con score)")
        sc_cam_note.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 9px; padding: 0 8px 4px 8px;")
        sc_cam_l.addWidget(sc_cam_note)
        self.score_camera_chart = ProBarChart({}, COLORS['verde'], max_bars=8, fmt="{:.2f}")
        self.score_camera_chart.setMinimumHeight(220)
        sc_cam_l.addWidget(self.score_camera_chart)

        sc_lens_g = QGroupBox("🏆 Score Estetico per Obiettivo")
        sc_lens_g.setStyleSheet(self._groupbox_style())
        sc_lens_l = QVBoxLayout(sc_lens_g)
        sc_lens_note = QLabel("Media score estetico (min. 5 foto con score)")
        sc_lens_note.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 9px; padding: 0 8px 4px 8px;")
        sc_lens_l.addWidget(sc_lens_note)
        self.score_lens_chart = ProBarChart({}, COLORS['viola'], max_bars=8, fmt="{:.2f}")
        self.score_lens_chart.setMinimumHeight(220)
        sc_lens_l.addWidget(self.score_lens_chart)

        combo_g = QGroupBox("🔗 Combinazioni Camera + Obiettivo")
        combo_g.setStyleSheet(self._groupbox_style())
        combo_l = QVBoxLayout(combo_g)
        self.combos_chart = GearBarChart({}, COLORS['ambra'], max_bars=8)
        self.combos_chart.setMinimumHeight(220)
        combo_l.addWidget(self.combos_chart)

        scores_row.addWidget(sc_cam_g)
        scores_row.addWidget(sc_lens_g)
        scores_row.addWidget(combo_g)
        layout.addLayout(scores_row)

        return widget

    # ------------------------------------------------------------------
    # Tab: Tecnica
    # ------------------------------------------------------------------

    def _create_tecnica_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Riga 1: shutter + ISO
        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)

        sh_g = QGroupBox("⏱️ Tempi di Scatto")
        sh_g.setStyleSheet(self._groupbox_style())
        sh_l = QVBoxLayout(sh_g)
        self.shutter_chart = ProBarChart({}, COLORS['ambra'], max_bars=8)
        sh_l.addWidget(self.shutter_chart)

        iso_g = QGroupBox("📊 ISO")
        iso_g.setStyleSheet(self._groupbox_style())
        iso_l = QVBoxLayout(iso_g)
        self.iso_chart = ProBarChart({}, COLORS['rosso'], max_bars=8)
        iso_l.addWidget(self.iso_chart)

        charts_row.addWidget(sh_g)
        charts_row.addWidget(iso_g)
        layout.addLayout(charts_row)

        # Riga 2: firma + geo
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        firma_g = QGroupBox("✍️ Firma di Scatto")
        firma_g.setStyleSheet(self._groupbox_style())
        firma_l = QVBoxLayout(firma_g)
        self._firma = {}
        for i, (label, key) in enumerate([
            ("Focale preferita",   "focal_top"),
            ("Apertura preferita", "aperture_top"),
            ("ISO più frequente",  "iso_top"),
            ("Flash usato",        "flash"),
        ]):
            firma_l.addWidget(self._metric_row(label, key, self._firma, i % 2 == 0))

        geo_g = QGroupBox("🌍 Copertura Geografica")
        geo_g.setStyleSheet(self._groupbox_style())
        geo_l = QVBoxLayout(geo_g)
        self._geo = {}
        for i, (label, key) in enumerate([
            ("Foto con GPS",      "gps_coverage"),
            ("Paesi visitati",    "countries"),
            ("Città fotografate", "cities"),
            ("Location top",      "top_location"),
        ]):
            geo_l.addWidget(self._metric_row(label, key, self._geo, i % 2 == 0))

        bottom_row.addWidget(firma_g)
        bottom_row.addWidget(geo_g)
        layout.addLayout(bottom_row)

        return widget

    # ------------------------------------------------------------------
    # Tab: Ritmo & Stile
    # ------------------------------------------------------------------

    def _create_ritmo_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Riga 1: ora del giorno + mese
        row1 = QHBoxLayout()
        row1.setSpacing(16)

        ora_g = QGroupBox("🌅 Ora del Giorno")
        ora_g.setStyleSheet(self._groupbox_style())
        ora_l = QVBoxLayout(ora_g)
        self.ora_chart = ProBarChart({}, COLORS['ambra'], max_bars=6)
        self.ora_chart.setMinimumHeight(200)
        ora_l.addWidget(self.ora_chart)

        mese_g = QGroupBox("📆 Stagionalità (per Mese)")
        mese_g.setStyleSheet(self._groupbox_style())
        mese_l = QVBoxLayout(mese_g)
        self.mese_chart = ProBarChart({}, COLORS['blu_petrolio'], max_bars=12)
        self.mese_chart.setMinimumHeight(200)
        mese_l.addWidget(self.mese_chart)

        row1.addWidget(ora_g)
        row1.addWidget(mese_g)
        layout.addLayout(row1)

        # Riga 2: giorno settimana + stile scatto
        row2 = QHBoxLayout()
        row2.setSpacing(16)

        giorno_g = QGroupBox("📅 Giorno della Settimana")
        giorno_g.setStyleSheet(self._groupbox_style())
        giorno_l = QVBoxLayout(giorno_g)
        self.giorno_chart = ProBarChart({}, COLORS['verde'], max_bars=7)
        self.giorno_chart.setMinimumHeight(180)
        giorno_l.addWidget(self.giorno_chart)

        exp_g = QGroupBox("🎛️ Modalità Esposizione")
        exp_g.setStyleSheet(self._groupbox_style())
        exp_l = QVBoxLayout(exp_g)
        self.exp_mode_chart = ProBarChart({}, COLORS['viola'], max_bars=8)
        self.exp_mode_chart.setMinimumHeight(180)
        exp_l.addWidget(self.exp_mode_chart)

        drive_g = QGroupBox("📸 Drive Mode")
        drive_g.setStyleSheet(self._groupbox_style())
        drive_l = QVBoxLayout(drive_g)
        self.drive_chart = ProBarChart({}, COLORS['rosso'], max_bars=6)
        self.drive_chart.setMinimumHeight(180)
        drive_l.addWidget(self.drive_chart)

        row2.addWidget(giorno_g)
        row2.addWidget(exp_g)
        row2.addWidget(drive_g)
        layout.addLayout(row2)

        return widget

    # ------------------------------------------------------------------
    # Database manager & refresh
    # ------------------------------------------------------------------

    def set_database_manager(self, db_manager):
        self.db_manager = db_manager
        if db_manager:
            self._load_dir_filter()

    def _load_dir_filter(self):
        if not self._dir_widget or not self.db_manager:
            return
        try:
            self.db_manager.cursor.execute(
                "SELECT filepath FROM images WHERE filepath IS NOT NULL"
            )
            dir_counts = {}
            for (fp,) in self.db_manager.cursor.fetchall():
                d = str(Path(fp).parent)
                dir_counts[d] = dir_counts.get(d, 0) + 1
            self._dir_widget.refresh(dir_counts)
        except Exception as e:
            logger.warning(f"Caricamento albero directory stats: {e}", exc_info=True)

    def on_activated(self):
        if self.db_manager:
            self.refresh_stats()

    def refresh_stats(self):
        if not self.db_manager:
            return

        # Se un worker sta già girando, segna la richiesta come pending e aspetta
        if self._stats_thread and self._stats_thread.isRunning():
            self._refresh_pending = True
            return

        self._refresh_pending = False
        worker = StatsWorker(self.db_manager.db_path, list(self._selected_dirs))
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_stats_ready)
        worker.finished.connect(lambda _: thread.quit())
        worker.error.connect(lambda msg: logger.error(f"StatsWorker: {msg}"))
        worker.error.connect(lambda _: thread.quit())
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_done)
        self._stats_thread = thread
        self._stats_worker = worker
        thread.start()

    def _on_thread_done(self):
        """Rilancia refresh se era arrivata una richiesta mentre girava il thread."""
        self._stats_thread = None
        self._stats_worker = None
        if self._refresh_pending:
            self.refresh_stats()

    # ------------------------------------------------------------------
    # Aggiornamento UI dai dati del worker (main thread)
    # ------------------------------------------------------------------

    def _on_stats_ready(self, d: dict):
        """Riceve il dizionario dati dal worker e aggiorna tutti i widget UI."""
        # Info bar
        if self._info_total: self._info_total.setText(d.get("info_total", "—"))
        if self._info_size:  self._info_size.setText(d.get("info_size",  "—"))
        if self._info_raw:   self._info_raw.setText(d.get("info_raw",   "—"))
        if self._info_last:  self._info_last.setText(d.get("info_last",  "—"))

        # KPI
        if self.kpi_total:
            self.kpi_total.update_value(d.get("kpi_total", "—"))
        if self.kpi_rating:
            self.kpi_rating.update_value(d.get("kpi_rating", "—"), d.get("kpi_rating_sub", ""))
        if self.kpi_aesthetic:
            self.kpi_aesthetic.update_value(d.get("kpi_aesthetic", "—"), d.get("kpi_aesthetic_sub", ""))

        # Charts archivio
        if self.rating_chart:   self.rating_chart.update_data(d.get("rating_chart", {}))
        if self.timeline_chart: self.timeline_chart.update_data(d.get("timeline_chart", {}))

        # Color labels
        for key in ("red", "yellow", "green", "blue", "purple", "none"):
            if key in self._color_labels:
                self._color_labels[key].setText(d.get(f"color_{key}", "—"))

        # Metadata
        for key in ("with_title", "with_desc", "with_tags", "with_rating", "with_gps"):
            if key in self._metadata:
                self._metadata[key].setText(d.get(f"meta_{key}", "—"))

        # Scores + B&W
        for key, dkey in [
            ("aesth_avg", "score_aesth_avg"), ("aesth_cov", "score_aesth_cov"),
            ("tech_avg",  "score_tech_avg"),  ("tech_cov",  "score_tech_cov"),
            ("bw_count",  "bw_count"),
        ]:
            if key in self._scores:
                self._scores[key].setText(d.get(dkey, "—"))

        # Charts attrezzatura
        if self.cameras_chart:  self.cameras_chart.update_data(d.get("cameras_chart", {}))
        if self.lenses_chart:   self.lenses_chart.update_data(d.get("lenses_chart", {}))
        if self.focal_chart:    self.focal_chart.update_data(d.get("focal_chart", {}))
        if self.aperture_chart: self.aperture_chart.update_data(d.get("aperture_chart", {}))

        # Gear summary
        for key, dkey in [
            ("n_cameras", "gear_n_cameras"), ("n_lenses", "gear_n_lenses"),
            ("top_focal", "gear_top_focal"), ("focal_range", "gear_focal_range"),
        ]:
            if key in self._gear_summary:
                self._gear_summary[key].setText(d.get(dkey, "—"))

        # Charts tecnica
        if self.shutter_chart: self.shutter_chart.update_data(d.get("shutter_chart", {}))
        if self.iso_chart:     self.iso_chart.update_data(d.get("iso_chart", {}))

        # Firma di scatto
        for key, dkey in [
            ("focal_top", "firma_focal"), ("aperture_top", "firma_aperture"),
            ("iso_top", "firma_iso"),     ("flash", "firma_flash"),
        ]:
            if key in self._firma:
                self._firma[key].setText(d.get(dkey, "—"))

        # Geo
        for key, dkey in [
            ("gps_coverage", "geo_coverage"), ("countries", "geo_countries"),
            ("cities", "geo_cities"),         ("top_location", "geo_top"),
        ]:
            if key in self._geo:
                self._geo[key].setText(d.get(dkey, "—"))

        # Pattern temporali e stile
        if self.ora_chart:      self.ora_chart.update_data(d.get("pattern_ora", {}))
        if self.mese_chart:     self.mese_chart.update_data(d.get("pattern_mese", {}))
        if self.giorno_chart:   self.giorno_chart.update_data(d.get("pattern_giorno", {}))
        if self.exp_mode_chart: self.exp_mode_chart.update_data(d.get("pattern_exposure_mode", {}))
        if self.drive_chart:    self.drive_chart.update_data(d.get("pattern_drive", {}))

        # Score per gear e combinazioni
        if self.score_camera_chart: self.score_camera_chart.update_data(d.get("score_per_camera", {}))
        if self.score_lens_chart:   self.score_lens_chart.update_data(d.get("score_per_lens", {}))
        if self.combos_chart:       self.combos_chart.update_data(d.get("gear_combos", {}))

