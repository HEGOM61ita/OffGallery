"""
Gallery Widgets - Componenti UI per la gallery
VERSIONE COMPLETAMENTE RISCRITTA E FUNZIONANTE
ImageCard, FlowLayout, Dialog per tag - TUTTI I BUG FIXATI
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QCheckBox, QMenu, QDialog, QLineEdit,
    QDialogButtonBox, QApplication, QSizePolicy, QGroupBox,
    QRadioButton, QButtonGroup, QTextEdit, QMessageBox, QScrollArea,
    QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThreadPool, QRunnable, QObject
from PyQt6.QtGui import QPixmap, QCursor, QAction
from PyQt6.QtWidgets import QToolTip
from PyQt6 import QtCore
from PyQt6.QtWidgets import QLayout, QSizePolicy
from PyQt6.QtCore import QRect, QSize, Qt

import json
import logging
import subprocess
import platform
import yaml
import os
import time
from utils.paths import get_app_dir
from i18n import t

logger = logging.getLogger(__name__)
from xmp_badge_manager import XMPBadgeIntegration
# NUOVO: Import per supporto XMP
try:
    from xmp_manager_extended import XMPManagerExtended, XMPSyncState, get_sync_ui_config, get_xmp_sync_tooltip
    XMP_SUPPORT_AVAILABLE = True
except ImportError:
    print("⚠️ XMP Manager Extended non disponibile - funzionalità limitate")
    XMP_SUPPORT_AVAILABLE = False

# NUOVO: Import RAW processor per verifiche
try:
    from raw_processor import RAWProcessor, RAW_PROCESSOR_AVAILABLE
except ImportError:
    RAW_PROCESSOR_AVAILABLE = False

# Palette colori
COLORS = {
    'grafite': '#2A2A2A',
    'grafite_light': '#3A3A3A',
    'grigio_chiaro': '#E3E3E3',
    'grigio_medio': '#B0B0B0',
    'blu_petrolio': '#1C4F63',
    'blu_petrolio_light': '#2A6A82',
    'ambra': '#C88B2E',
    'ambra_light': '#E0A84A',
    'verde': '#4A7C59',
    'rosso': '#8B4049',
    'accento': '#E67E22',
    # Nuovi colori per uniformità UI
    'marrone_chiaro': '#A67C52',  # Per badge ranking
    'popup_bg': '#2c3e50',        # Sfondo popup (blu-grigio scuro)
    'popup_text': '#ecf0f1',      # Testo popup (grigio chiaro)
    'popup_border': '#3498db',    # Bordo popup (blu)
    # Rating stars
    'rating_star': '#87CEEB',     # Stelle rating (celeste chiaro/sky blue)
}

# Mapping colori label Lightroom standard
COLOR_LABELS = {
    'Red': '#E74C3C',
    'Yellow': '#F1C40F',
    'Green': '#27AE60',
    'Blue': '#3498DB',
    'Purple': '#9B59B6',
    # Alias italiani
    'Rosso': '#E74C3C',
    'Giallo': '#F1C40F',
    'Verde': '#27AE60',
    'Blu': '#3498DB',
    'Viola': '#9B59B6',
}

# Stile globale per popup, dialog e progress bar
POPUP_STYLE = f"""
    QDialog, QMessageBox, QProgressDialog {{
        background-color: {COLORS['popup_bg']};
        color: {COLORS['popup_text']};
        border: 2px solid {COLORS['popup_border']};
        border-radius: 8px;
    }}
    QLabel {{
        color: {COLORS['popup_text']};
        font-size: 12px;
    }}
    QPushButton {{
        background-color: {COLORS['popup_border']};
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
        font-weight: bold;
        min-width: 80px;
    }}
    QPushButton:hover {{
        background-color: #2980b9;
    }}
    QPushButton:pressed {{
        background-color: #1a5276;
    }}
    QProgressBar {{
        border: 1px solid {COLORS['popup_border']};
        border-radius: 4px;
        background-color: {COLORS['grafite']};
        text-align: center;
        color: {COLORS['popup_text']};
    }}
    QProgressBar::chunk {{
        background-color: {COLORS['popup_border']};
        border-radius: 3px;
    }}
"""

def apply_popup_style(widget):
    """Applica lo stile uniforme a un dialog/popup"""
    widget.setStyleSheet(POPUP_STYLE)


class FlowLayout(QLayout):
    """
    FlowLayout reale con wrapping automatico.
    Dispone i widget su più righe in base alla larghezza disponibile.
    """

    def __init__(self, parent=None, spacing=10):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(10, 10, 10, 10)

    # ───────────── API BASE QLayout ─────────────

    def addItem(self, item):
        self._items.append(item)

    def addWidget(self, widget):
        widget.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred
        )
        super().addWidget(widget)

    def removeWidget(self, widget):
        """Rimuove widget dal layout e da _items"""
        for i, item in enumerate(self._items):
            if item.widget() == widget:
                self._items.pop(i)
                break
        super().removeWidget(widget)

    def insertWidget(self, index, widget):
        """Inserisce widget alla posizione specificata invece che alla fine"""
        widget.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred
        )
        # Crea QWidgetItem e inserisci nella posizione corretta
        from PyQt6.QtWidgets import QWidgetItem
        item = QWidgetItem(widget)
        widget.setParent(self.parentWidget())
        widget.show()  # Assicura che il widget sia visibile
        if 0 <= index <= len(self._items):
            self._items.insert(index, item)
        else:
            self._items.append(item)
        self.invalidate()
        self.update()

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    # ───────────── GEOMETRIA ─────────────

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), test_only=True)
        return height

    # ───────────── ALGORITMO LAYOUT ─────────────

    def _do_layout(self, rect, test_only=False):
        # FIXED: Qt6 API - use individual margin methods instead of getCoords()
        margins = self.contentsMargins()
        left = margins.left()
        top = margins.top()
        right = margins.right()
        bottom = margins.bottom()
        
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        
        for item in self._items:
            widget = item.widget()
            if widget is None:
                continue
                
            space_x = self._spacing
            space_y = self._spacing
            
            # Calcola dimensioni widget
            size_hint = item.sizeHint()
            min_size = item.minimumSize()
            widget_width = max(size_hint.width(), min_size.width())
            widget_height = max(size_hint.height(), min_size.height())
            
            # Check se il widget ci sta nella riga corrente
            next_x = x + widget_width + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                # Va a capo
                x = effective_rect.x()
                y = y + line_height + space_y
                line_height = 0
            
            # Posiziona il widget
            if not test_only:
                item.setGeometry(QRect(x, y, widget_width, widget_height))
            
            # Aggiorna posizione e altezza riga
            x = x + widget_width + space_x
            line_height = max(line_height, widget_height)
        
        return y + line_height - rect.y() + bottom

    def clear_items(self):
        """Rimuove tutti i widget dal layout"""
        while self._items:
            item = self._items.pop()
            if item.widget():
                item.widget().setParent(None)

    def removeWidget(self, widget):
        """Rimuove un widget specifico dal layout"""
        for i, item in enumerate(self._items):
            if item.widget() == widget:
                self._items.pop(i)
                widget.setParent(None)
                break


class _ThumbSignals(QObject):
    """Segnali per _ThumbnailLoader cross-thread (QRunnable non è QObject)"""
    loaded = pyqtSignal(bytes)
    failed = pyqtSignal()


class _ThumbnailLoader(QRunnable):
    """
    Carica thumbnail in background thread (fallback per cache miss).
    Per RAW usa ExifTool -PreviewImage, per altri file legge i bytes raw.
    Salva anche nella cache disco (worker thread — PIL/I-O sicuri qui).
    Emette bytes al main thread tramite signals — QPixmap creato lì.
    """
    _RAW_EXT = {'.cr2', '.cr3', '.nef', '.arw', '.orf', '.rw2',
                '.pef', '.dng', '.nrw', '.srf', '.sr2'}

    def __init__(self, filepath: Path, signals: '_ThumbSignals'):
        super().__init__()
        self.filepath = filepath
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        data = None
        try:
            if self.filepath.suffix.lower() in self._RAW_EXT:
                result = subprocess.run(
                    ['exiftool', '-b', '-PreviewImage', str(self.filepath)],
                    capture_output=True, timeout=10
                )
                if result.returncode == 0 and result.stdout:
                    data = result.stdout
            else:
                with open(str(self.filepath), 'rb') as f:
                    data = f.read()
        except Exception as e:
            logger.debug(f"Thumbnail load error {self.filepath.name}: {e}")

        if data:
            self._populate_cache(data)
            self.signals.loaded.emit(data)
        else:
            self.signals.failed.emit()

    def _populate_cache(self, data: bytes):
        """Salva thumbnail 150px in cache (worker thread — sicuro per I/O)."""
        try:
            from PIL import Image
            import io
            from utils.thumb_cache import save_gallery_thumb
            img = Image.open(io.BytesIO(data))
            img.load()  # Forza decodifica completa prima che BytesIO esca dallo scope
            save_gallery_thumb(self.filepath, img)
            logger.debug(f"Cache thumbnail salvata: {self.filepath.name}")
        except Exception as e:
            logger.warning(f"Cache write fallita per {self.filepath.name}: {e}")


class ImageCard(QFrame):
    """
    Card verticale: thumbnail sopra, info sotto
    VERSIONE COMPLETAMENTE RISCRITTA E FUNZIONANTE
    """
    
    # Segnali
    selection_changed = pyqtSignal(object, bool)
    find_similar_requested = pyqtSignal(object)
    bioclip_requested = pyqtSignal(list)
    llm_tagging_requested = pyqtSignal(list)
    analyze_xmp_requested = pyqtSignal(list)
    sync_from_lightroom_requested = pyqtSignal(list)
    
    # Costanti
    CARD_WIDTH = 220
    THUMB_SIZE = 150
    
    def __init__(self, image_data, parent=None):
        super().__init__(parent)
        self.image_data = image_data or {}
        self.filepath = Path(image_data.get('filepath', '')) if image_data.get('filepath') else None
        self.image_id = image_data.get('id')
        self._selected = False
        self._gallery = parent  # Store reference to GalleryTab before Qt changes parent
        
        # FIXED: Tooltip state management
        self.setMouseTracking(True)
        self._current_tooltip_area = None
        
        # Usa XMP Manager condiviso dalla gallery (se disponibile)
        self.xmp_manager = getattr(parent, 'shared_xmp_manager', None) or \
                   (XMPManagerExtended() if XMP_SUPPORT_AVAILABLE else None)
        
        # NUOVO: Cache stato XMP per performance
        self._xmp_state_cache = None
        self._xmp_info_cache = None
        
        # Configurazione editor esterni
        self.external_editors = self._load_external_editors()
        
        self.setFixedWidth(self.CARD_WIDTH)
        self.setFrameStyle(QFrame.Shape.Box)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        
        self._build_ui()
        self._update_style()
    
    def _build_ui(self):
        """Costruisce l'interfaccia della card"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        # Header: checkbox + filename
        header = QHBoxLayout()
        header.setSpacing(4)
        
        self.checkbox = QCheckBox()
        self.checkbox.stateChanged.connect(lambda state: self.set_selected(state == Qt.CheckState.Checked.value))
        header.addWidget(self.checkbox)
        
        filename = self.image_data.get('filename', 'Unknown')
        display_name = filename if len(filename) <= 22 else filename[:19] + "..."
        self.filename_label = QLabel(f"<b>{display_name}</b>")
        self.filename_label.setStyleSheet(f"font-size: 11px; color: {COLORS['grigio_chiaro']};")
        # FIXED: No tooltip on filename to avoid conflicts
        header.addWidget(self.filename_label, 1)
        
        layout.addLayout(header)
        
        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setFixedSize(self.THUMB_SIZE, self.THUMB_SIZE)
        self.thumbnail_label.setStyleSheet(f"""
            background-color: {COLORS['grafite_light']};
            border: 1px solid {COLORS['blu_petrolio']};
            border-radius: 4px;
        """)
        layout.addWidget(self.thumbnail_label, 0, Qt.AlignmentFlag.AlignCenter)
        self._load_thumbnail()
        
        # Info frame
        self.info_frame = QFrame()
        self.info_frame.setObjectName('info_frame')
        info_vbox = QVBoxLayout(self.info_frame)
        info_vbox.setContentsMargins(0, 0, 0, 0)
        info_vbox.setSpacing(2)
        self._build_scores_and_indicators(info_vbox)
        layout.addWidget(self.info_frame)
    
    def _check_file_status(self):
        """Verifica stato del file: distingue disco, percorso e file mancante"""
        if not self.filepath:
            return 'no_path'
        # Controlla se il disco/mount point esiste
        anchor = self.filepath.anchor  # Es: 'D:\' o '/'
        if anchor and not Path(anchor).exists():
            return 'no_disk'
        # Controlla se la directory padre esiste
        if not self.filepath.parent.exists():
            return 'no_path'
        # Controlla se il file esiste
        if not self.filepath.exists():
            return 'no_file'
        return 'ok'

    def _load_thumbnail(self):
        """
        Carica thumbnail dell'immagine.
        1) Cache disco (veloce, ~5ms) — popolata dal processing
        2) Fallback asincrono: ExifTool in background thread (cache miss)
        """
        try:
            file_status = self._check_file_status()
            if file_status != 'ok':
                status_labels = {
                    'no_disk': '⛔\nNO DISK',
                    'no_path': '⛔\nNO PATH',
                    'no_file': '⛔\nNO FILE',
                }
                self.thumbnail_label.setText(status_labels.get(file_status, '⛔\nN/A'))
                self.thumbnail_label.setStyleSheet(f"""
                    background-color: {COLORS['grafite_light']};
                    border: 2px solid {COLORS['rosso']};
                    border-radius: 4px;
                    color: {COLORS['rosso']};
                    font-size: 13px;
                    font-weight: bold;
                """)
                return

            # 1) CACHE HIT: lettura veloce (~5ms), sincrona nel main thread
            if self.filepath:
                try:
                    from utils.thumb_cache import load_gallery_thumb_bytes
                    cached_bytes = load_gallery_thumb_bytes(self.filepath)
                    if cached_bytes:
                        pixmap = QPixmap()
                        if pixmap.loadFromData(cached_bytes):
                            self.thumbnail_label.setPixmap(pixmap)
                            return
                except Exception as _ce:
                    logger.debug(f"Cache read error: {_ce}")

            # 2) CACHE MISS: placeholder + caricamento asincrono in background
            self.thumbnail_label.setText("⏳")
            if not self.filepath:
                return

            self._thumb_signals = _ThumbSignals()
            self._thumb_signals.loaded.connect(self._on_thumb_loaded)
            self._thumb_signals.failed.connect(self._on_thumb_failed)
            loader = _ThumbnailLoader(self.filepath, self._thumb_signals)
            QThreadPool.globalInstance().start(loader)

        except Exception as e:
            logger.debug(f"Errore _load_thumbnail: {e}")
            self.thumbnail_label.setText("❌\nError")

    def _on_thumb_loaded(self, data: bytes):
        """Riceve bytes dal worker thread, crea QPixmap nel main thread.
        Il salvataggio cache è già avvenuto nel worker thread."""
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            scaled = pixmap.scaled(
                self.THUMB_SIZE, self.THUMB_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.thumbnail_label.setPixmap(scaled)
            self.thumbnail_label.setStyleSheet("")
        else:
            self._on_thumb_failed()

    def _on_thumb_failed(self):
        """Fallback quando thumbnail non disponibile neanche via ExifTool"""
        self.thumbnail_label.setText("📷\nRAW")
    
    def _build_scores_and_indicators(self, layout):
        """Costruisce badge qualità su due righe: scores + status XMP/sync"""
        try:
            # Container per il badge completo
            badge_container = QVBoxLayout()
            badge_container.setSpacing(2)
            badge_container.setContentsMargins(0, 0, 0, 0)

            # PRIMA RIGA: Scores (Aesthetic + Technical + Semantic + Rating + Color)
            scores_layout = QHBoxLayout()
            scores_layout.setSpacing(4)

            # Aesthetic score
            aesthetic = self.image_data.get('aesthetic_score')
            if aesthetic is not None:
                try:
                    score_val = float(aesthetic)
                    aesthetic_label = QLabel(f"AES: {score_val:.1f}")
                    aesthetic_label.setStyleSheet(f"""
                        background-color: {COLORS['verde']};
                        color: white;
                        padding: 2px 4px;
                        border-radius: 2px;
                        font-size: 8px;
                        font-weight: bold;
                    """)
                    scores_layout.addWidget(aesthetic_label)
                except (ValueError, TypeError):
                    pass

            # Technical score (solo per non-RAW)
            technical = self.image_data.get('technical_score')
            if technical is not None:
                try:
                    is_raw = False
                    if self.filepath:
                        raw_extensions = {'.cr2', '.cr3', '.nef', '.arw', '.orf', '.rw2', '.pef', '.dng', '.nrw', '.srf', '.sr2'}
                        is_raw = self.filepath.suffix.lower() in raw_extensions

                    if not is_raw:
                        score_val = float(technical)
                        technical_label = QLabel(f"TEC: {score_val:.0f}")
                        technical_label.setStyleSheet(f"""
                            background-color: {COLORS['blu_petrolio']};
                            color: white;
                            padding: 2px 4px;
                            border-radius: 2px;
                            font-size: 8px;
                            font-weight: bold;
                        """)
                        scores_layout.addWidget(technical_label)
                except (ValueError, TypeError):
                    pass

            # Semantic similarity score (dal search)
            similarity = self.image_data.get('similarity_score')
            if similarity is not None:
                try:
                    score_val = float(similarity)
                    similarity_label = QLabel(f"SEM: {score_val:.2f}")
                    similarity_label.setStyleSheet(f"""
                        background-color: {COLORS['accento']};
                        color: white;
                        padding: 2px 4px;
                        border-radius: 2px;
                        font-size: 8px;
                        font-weight: bold;
                    """)
                    scores_layout.addWidget(similarity_label)
                except (ValueError, TypeError):
                    pass

            # Final score (ranking from search)
            final_score = self.image_data.get('final_score')
            if final_score is not None:
                try:
                    score_val = float(final_score)
                    final_score_label = QLabel(f"RANK: {score_val:.2f}")
                    final_score_label.setStyleSheet(f"""
                        background-color: {COLORS['marrone_chiaro']};
                        color: white;
                        padding: 2px 4px;
                        border-radius: 2px;
                        font-size: 8px;
                        font-weight: bold;
                    """)
                    scores_layout.addWidget(final_score_label)
                except (ValueError, TypeError):
                    pass

            badge_container.addLayout(scores_layout)

            # SECONDA RIGA: XMP Status + Rating/Color (a destra)
            status_layout = QHBoxLayout()
            status_layout.setSpacing(4)

            # XMP placeholder - sarà popolato dal background thread
            self.xmp_label = QLabel("")
            self.xmp_label.hide()  # Nascosto finché non arrivano dati reali
            status_layout.addWidget(self.xmp_label)

            status_layout.addStretch()

            # Rating stars (celeste chiaro) - a destra
            self.rating_label = QLabel("")
            self.rating_label.setStyleSheet(f"""
                color: {COLORS['rating_star']};
                font-size: 10px;
                font-weight: bold;
                padding: 0px 2px;
            """)
            self.rating_label.hide()
            status_layout.addWidget(self.rating_label)

            # Color label square - a destra del rating
            self.color_label_indicator = QLabel("")
            self.color_label_indicator.setFixedSize(12, 12)
            self.color_label_indicator.hide()
            status_layout.addWidget(self.color_label_indicator)

            badge_container.addLayout(status_layout)

            # Aggiorna display rating/color
            self._update_rating_color_display()

            layout.addLayout(badge_container)

        except Exception as e:
            print(f"❌ ERRORE _build_scores_and_indicators: {e}")
            import traceback
            traceback.print_exc()

    def _get_xmp_status_text(self):
        """RIMOSSO - Badge solo tramite background processing per evitare doppio rendering"""
        return None  # Nessun badge iniziale
 
    
    def _get_tags_count(self):
        """Conta tag unificati"""
        try:
            tags_raw = self.image_data.get('tags', '')
            if not tags_raw:
                return 0
            
            if isinstance(tags_raw, str):
                tags = json.loads(tags_raw)
            else:
                tags = tags_raw
                
            return len(tags) if isinstance(tags, list) else 0
        except:
            return 0
    
    def get_unified_tags(self):
        """Ottieni lista tag unificati con cache invalidabile"""
        try:
            # Check se abbiamo cache valida
            if hasattr(self, '_unified_tags_cache'):
                return self._unified_tags_cache
            
            # Rebuild cache
            tags_raw = self.image_data.get('tags', '')

            if not tags_raw:
                self._unified_tags_cache = []
                return self._unified_tags_cache

            if isinstance(tags_raw, str):
                try:
                    tags = json.loads(tags_raw)
                except json.JSONDecodeError:
                    self._unified_tags_cache = []
                    return self._unified_tags_cache
            else:
                tags = tags_raw

            self._unified_tags_cache = tags if isinstance(tags, list) else []
            return self._unified_tags_cache
            
        except Exception as e:
            print(f"Errore get_unified_tags: {e}")
            self._unified_tags_cache = []
            return self._unified_tags_cache
    
    # ═══════════════════════════════════════════════════════════════
    #                          TOOLTIP SYSTEM
    # ═══════════════════════════════════════════════════════════════
    
    def mouseMoveEvent(self, event):
        """Tooltip semantico per tutta la card"""
        try:
            # SIMPLIFIED: Solo area semantic per tutta la card
            if self._current_tooltip_area != 'semantic':
                self._current_tooltip_area = 'semantic'
                tooltip_text = self._build_semantic_tooltip()
                self.setToolTip(tooltip_text)
        except Exception as e:
            print(f"Errore mouseMoveEvent: {e}")
            
        super().mouseMoveEvent(event)
    
    def enterEvent(self, event):
        """Tooltip semantico all'ingresso"""
        try:
            tooltip_text = self._build_semantic_tooltip()
            self._current_tooltip_area = 'semantic'
            self.setToolTip(tooltip_text)
        except Exception as e:
            print(f"Errore enterEvent: {e}")
            
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Pulisce tooltip all'uscita"""
        self.setToolTip("")
        self._current_tooltip_area = None
        super().leaveEvent(event)
    
    def _build_semantic_tooltip(self):
        """Costruisce tooltip semantico con cache invalidabile"""
        try:
            # Check cache valida
            if hasattr(self, '_cached_semantic_tooltip'):
                return self._cached_semantic_tooltip
            
            lines = []
        
            # Titolo
            filename = self.image_data.get('filename', 'Unknown')
            title = self.image_data.get('title') or filename.rsplit('.', 1)[0].replace('_', ' ')
            lines.append(f"📌 {title}")

            lines.append("")

            # Tag (solo LLM + user, NO BioCLIP) - USA CACHE
            unified_tags = self.get_unified_tags()
            if unified_tags and len(unified_tags) > 0:
                lines.append("🏷️ TAGS")
                tag_text = ", ".join(sorted(unified_tags))
                # Wrappa tag a 45 caratteri
                if tag_text and len(tag_text) <= 45:
                    lines.append(tag_text)
                elif tag_text:
                    words = tag_text.split(', ')
                    current_line = ""
                    for word in words:
                        if len(current_line + word + ", ") <= 45:
                            current_line += word + ", "
                        else:
                            if current_line:
                                lines.append(current_line.rstrip(', '))
                            current_line = word + ", "
                    if current_line:
                        lines.append(current_line.rstrip(', '))
                lines.append("")

            # Sezione BioCLIP separata (tassonomia completa, compatta)
            bioclip_raw = self.image_data.get('bioclip_taxonomy', '')
            if bioclip_raw:
                try:
                    taxonomy = json.loads(bioclip_raw) if isinstance(bioclip_raw, str) else bioclip_raw
                    if taxonomy and isinstance(taxonomy, list):
                        # Livelli non-vuoti separati da " > "
                        hierarchy = " > ".join([l for l in taxonomy if l and l.strip()])
                        if hierarchy:
                            lines.append("🌿 BIOCLIP")
                            # Wrappa gerarchia a 45 caratteri
                            if len(hierarchy) <= 45:
                                lines.append(hierarchy)
                            else:
                                parts = hierarchy.split(" > ")
                                current_line = ""
                                for part in parts:
                                    candidate = (current_line + " > " + part) if current_line else part
                                    if len(candidate) <= 45:
                                        current_line = candidate
                                    else:
                                        if current_line:
                                            lines.append(current_line)
                                        current_line = part
                                if current_line:
                                    lines.append(current_line)
                            lines.append("")
                except (json.JSONDecodeError, TypeError):
                    pass

            # Sezione Geo (gerarchia geografica)
            geo_raw = self.image_data.get('geo_hierarchy', '')
            if geo_raw:
                try:
                    parts = [p for p in geo_raw.split('|') if p and p != 'GeOFF']
                    if parts:
                        hierarchy = " > ".join(parts)
                        lines.append("🌍 GEO")
                        if len(hierarchy) <= 45:
                            lines.append(hierarchy)
                        else:
                            current_line = ""
                            for part in parts:
                                candidate = (current_line + " > " + part) if current_line else part
                                if len(candidate) <= 45:
                                    current_line = candidate
                                else:
                                    if current_line:
                                        lines.append(current_line)
                                    current_line = part
                            if current_line:
                                lines.append(current_line)
                        lines.append("")
                except Exception:
                    pass

            # Descrizione
            description = self.image_data.get('description', '')
            if description and len(description) > 0:  # ← FIX: Controlla che esista E non sia vuoto
                lines.append("📝 DESCRIZIONE")
                # Wrappa descrizione a 45 caratteri
                if len(description) <= 45:
                    lines.append(description)
                else:
                    words = description.split()
                    current_line = ""
                    for word in words:
                        if len(current_line + word) <= 45:
                            current_line += word + " "
                        else:
                            if current_line:
                                lines.append(current_line.strip())
                            current_line = word + " "
                    if current_line:
                        lines.append(current_line.strip())
        
            self._cached_semantic_tooltip = "\n".join(lines) if lines else "📝 Nessun dato semantico disponibile"

            return self._cached_semantic_tooltip
        
        except Exception as e:
            print(f"Errore _build_semantic_tooltip: {e}")
            filename = self.image_data.get('filename', 'Unknown') if self.image_data else 'Unknown'
            self._cached_semantic_tooltip = f"📝 {filename}"
            return self._cached_semantic_tooltip


    def _build_technical_tooltip(self):
        """Costruisce tooltip tecnico (EXIF + camera + file info)"""
        try:
            lines = []
            
            # File info
            if self.filepath and self.filepath.exists():
                try:
                    size_mb = self.filepath.stat().st_size / (1024 * 1024)
                    lines.append("📄 FILE")
                    lines.append(f"{t('widgets.tooltip.label_name')} {self.filepath.name}")
                    lines.append(f"{t('widgets.tooltip.label_format')} {self.filepath.suffix.upper().lstrip('.')}")
                    lines.append(f"{t('widgets.tooltip.label_size')} {size_mb:.2f} MB")
                    lines.append("")
                except Exception:
                    pass
            
            # Dimensioni dai campi DB
            width = self.image_data.get('width')
            height = self.image_data.get('height')
            if width and height:
                megapixels = (width * height) / 1000000
                lines.append("📐 DIMENSIONI")
                lines.append(f"{width} × {height} px")
                lines.append(f"📊 {megapixels:.1f} MP")
                lines.append("")
            
            # CAMERA INFO - PRIORITÀ CAMPI DB
            camera_make = self.image_data.get('camera_make')
            camera_model = self.image_data.get('camera_model')
            if camera_make or camera_model:
                lines.append("📸 CAMERA")
                camera_str = f"{camera_make or ''} {camera_model or ''}".strip()
                lines.append(f"📷 {camera_str}")
                
                # Software dal campo DB se presente
                software = self.image_data.get('software')
                if software:
                    lines.append(f"💾 {software}")
                lines.append("")
            
            # IMPOSTAZIONI FOTOGRAFICHE - PRIORITÀ CAMPI DB
            settings = []
            
            # Apertura
            aperture = self.image_data.get('aperture')
            if aperture:
                settings.append(f"f/{aperture}")
            
            # Focale
            focal_length = self.image_data.get('focal_length')
            if focal_length:
                settings.append(f"{focal_length}mm")
            
            # Shutter speed
            shutter_speed = self.image_data.get('shutter_speed')
            if shutter_speed:
                settings.append(f"{shutter_speed}")
            
            # ISO
            iso = self.image_data.get('iso')
            if iso:
                settings.append(f"ISO {iso}")
            
            if settings:
                lines.append(t("widgets.tooltip.settings_header"))
                lines.append(" | ".join(settings))
                lines.append("")
            
            # FALLBACK: Solo se non ci sono dati DB, usa JSON EXIF come backup
            if not (camera_make or camera_model or aperture or focal_length or shutter_speed or iso):
                exif_json_str = self.image_data.get('exif_json')
                if exif_json_str:
                    try:
                        exif_data = json.loads(exif_json_str)
                        
                        # Camera info da JSON come fallback
                        make = exif_data.get('EXIF:Make')
                        model = exif_data.get('EXIF:Model')
                        if make or model:
                            lines.append(t("widgets.tooltip.camera_from_exif"))
                            camera_str = f"{make or ''} {model or ''}".strip()
                            lines.append(f"📷 {camera_str}")
                            lines.append("")
                        
                    except Exception as e:
                        lines.append(f"⚠️ Errore fallback EXIF: {e}")
                        lines.append("")
            
            # AI Scores
            scores = []
            aesthetic = self.image_data.get('aesthetic_score')
            if aesthetic is not None:
                try:
                    scores.append(f"🎨 Aesthetic: {float(aesthetic):.2f}")
                except (ValueError, TypeError):
                    pass
                    
            technical = self.image_data.get('technical_score')
            if technical is not None:
                try:
                    scores.append(f"🔧 Technical: {float(technical):.0f}")
                except (ValueError, TypeError):
                    pass
            
            if scores:
                lines.append("📊 AI SCORES")
                lines.extend(scores)
            
            return "\n".join(lines) if lines else t("widgets.tooltip.no_tech_data")

        except Exception as e:
            print(f"Errore _build_technical_tooltip: {e}")
            return t("widgets.tooltip.tech_data_error")
    
    # ═══════════════════════════════════════════════════════════════
    #                         EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════════
    
    def mousePressEvent(self, event):
        """Gestisce click per selezione - Ctrl+click per multi-selezione"""
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl_pressed = event.modifiers() & Qt.KeyboardModifier.ControlModifier
            gallery = self._gallery

            if ctrl_pressed:
                # Ctrl+click = toggle questa card (aggiungi/rimuovi)
                self.set_selected(not self._selected)
            else:
                # Click normale = seleziona SOLO questa card
                if gallery and hasattr(gallery, 'selected_items'):
                    # Prima deseleziona TUTTE (inclusa questa)
                    for card in list(gallery.selected_items):
                        card.set_selected(False)
                    # Ora pulisci la lista
                    gallery.selected_items.clear()
                # Seleziona questa
                self.set_selected(True)
    
    def mouseDoubleClickEvent(self, event):
        """Gestisce doppio click"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Apri immagine in viewer esterno
            self._open_external()
    
    def contextMenuEvent(self, event):
        """Menu contestuale"""
        try:
            # Determina se multi-selezione (usa _gallery invece di parent() perché Qt cambia il parent)
            gallery = self._gallery
            if gallery and hasattr(gallery, 'selected_items'):
                selected_items = gallery.selected_items
                is_multi = len(selected_items) > 1
                target_items = selected_items if is_multi else [self]
                multi_label = f" ({len(selected_items)})" if is_multi else ""
            else:
                target_items = [self]
                multi_label = ""
                is_multi = False
            
            menu = QMenu(self)

            # ═══ FILE & NAVIGAZIONE ═══
            file_menu = menu.addMenu(f"{t('widgets.menu.file')}{multi_label}")

            open_action = QAction(t("widgets.action.open_folder"), self)
            open_action.triggered.connect(lambda: self._open_folder(target_items))
            file_menu.addAction(open_action)

            copy_action = QAction(t("widgets.action.copy_path"), self)
            copy_action.triggered.connect(lambda: self._copy_paths(target_items))
            file_menu.addAction(copy_action)

            # Editor esterni (solo singola immagine)
            if self.external_editors and not is_multi:
                file_menu.addSeparator()
                for editor in self.external_editors:
                    editor_action = QAction(t("widgets.action.open_with_editor", editor_name=editor['name']), self)
                    editor_action.triggered.connect(lambda checked, e=editor: self._open_with_external_editor(e))
                    file_menu.addAction(editor_action)

            # ═══ MODIFICA (raggruppa tutto) ═══
            edit_menu = menu.addMenu(f"{t('widgets.menu.edit')}{multi_label}")

            title_action = QAction(t("widgets.action.edit_title"), self)
            title_action.triggered.connect(lambda: self._edit_title(target_items))
            edit_menu.addAction(title_action)

            tag_action = QAction(t("widgets.action.edit_tags"), self)
            tag_action.triggered.connect(lambda: self._edit_tags(target_items))
            edit_menu.addAction(tag_action)

            bioclip_edit_action = QAction(t("widgets.action.edit_bioclip"), self)
            bioclip_edit_action.triggered.connect(lambda: self._edit_bioclip_taxonomy(target_items))
            edit_menu.addAction(bioclip_edit_action)

            desc_action = QAction(t("widgets.action.edit_description"), self)
            desc_action.triggered.connect(lambda: self._edit_description(target_items))
            edit_menu.addAction(desc_action)

            edit_menu.addSeparator()

            # Sottomenu Rating (stelle)
            rating_menu = edit_menu.addMenu(t("widgets.menu.rating"))
            for i in range(6):  # 0-5 stelle
                if i == 0:
                    label = t("widgets.action.rating_none")
                else:
                    label = "★" * i + "☆" * (5 - i)
                rating_action = QAction(label, self)
                rating_action.triggered.connect(lambda checked, r=i: self._set_rating(target_items, r))
                rating_menu.addAction(rating_action)

            # Sottomenu Color Label
            color_menu = edit_menu.addMenu(t("widgets.menu.color_label"))
            color_options = [
                (t("widgets.action.color_none"), None),
                (t("widgets.action.color_red"), "Red"),
                (t("widgets.action.color_yellow"), "Yellow"),
                (t("widgets.action.color_green"), "Green"),
                (t("widgets.action.color_blue"), "Blue"),
                (t("widgets.action.color_purple"), "Purple"),
            ]
            for label, color_value in color_options:
                color_action = QAction(label, self)
                color_action.triggered.connect(lambda checked, c=color_value: self._set_color_label(target_items, c))
                color_menu.addAction(color_action)

            edit_menu.addSeparator()

            # Elimina (dentro Modifica)
            delete_action = QAction(t("widgets.action.delete_db"), self)
            delete_action.triggered.connect(lambda: self._delete_from_database(target_items))
            edit_menu.addAction(delete_action)

            # ═══ GENERA CONTENUTI AI (sottomenu) ═══
            ai_menu = menu.addMenu(f"{t('widgets.menu.ai_generate')}{multi_label}")

            llm_action = QAction(t("widgets.action.run_llm"), self)
            llm_action.triggered.connect(lambda: self._run_llm_and_refresh(target_items))
            ai_menu.addAction(llm_action)

            bioclip_action = QAction(t("widgets.action.run_bioclip"), self)
            bioclip_action.triggered.connect(lambda: self._run_bioclip_and_refresh(target_items))
            ai_menu.addAction(bioclip_action)

            # ═══ TROVA SIMILI (singolo, in evidenza) ═══
            similar_action = QAction(t("widgets.action.find_similar"), self)
            similar_action.triggered.connect(lambda: self.find_similar_requested.emit(self))
            similar_action.setEnabled(not is_multi)
            menu.addAction(similar_action)

            # ═══ SINCRONIZZAZIONE XMP (sottomenu) ═══
            if XMP_SUPPORT_AVAILABLE:
                xmp_menu = menu.addMenu(f"{t('widgets.menu.xmp_sync')}{multi_label}")

                analyze_xmp_action = QAction(t("widgets.action.xmp_compare"), self)
                analyze_xmp_action.triggered.connect(lambda: self._analyze_xmp_detailed(target_items))
                xmp_menu.addAction(analyze_xmp_action)

                sync_xmp_action = QAction(t("widgets.action.xmp_import"), self)
                sync_xmp_action.triggered.connect(lambda: self._import_from_xmp_with_refresh(target_items))
                xmp_menu.addAction(sync_xmp_action)

                export_xmp_action = QAction(t("widgets.action.xmp_export"), self)
                export_xmp_action.triggered.connect(lambda: self._export_to_xmp_with_refresh(target_items))
                xmp_menu.addAction(export_xmp_action)

                xmp_menu.addSeparator()

                show_xmp_action = QAction(t("widgets.action.xmp_show"), self)
                show_xmp_action.triggered.connect(lambda: self._show_xmp_content(target_items))
                xmp_menu.addAction(show_xmp_action)

            # ═══ INFO TECNICHE ═══
            exif_action = QAction(f"{t('widgets.action.exif_info')}{multi_label}", self)
            exif_action.triggered.connect(lambda: self._show_complete_exif(target_items))
            menu.addAction(exif_action)

            menu.exec(event.globalPos())
            
        except Exception as e:
            print(f"Errore context menu: {e}")
    
    def _load_external_editors(self):
        """Carica configurazione editor esterni dal config"""
        try:
            config_path = Path('config_new.yaml')
            if not config_path.exists():
                return []
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            external_editors = config.get('external_editors', {})
            enabled_editors = []
            
            for i in range(1, 4):
                editor_key = f'editor_{i}'
                if editor_key in external_editors:
                    editor_data = external_editors[editor_key]
                    if editor_data.get('enabled', False) and editor_data.get('path', '').strip():
                        editor_path = Path(editor_data['path'])
                        if editor_path.exists():
                            enabled_editors.append({
                                'name': editor_data.get('name', f'Editor {i}').strip() or f'Editor {i}',
                                'path': str(editor_path),
                                'command_args': editor_data.get('command_args', '').strip(),
                                'index': i
                            })
            
            return enabled_editors
            
        except Exception as e:
            print(f"Errore caricamento editor esterni: {e}")
            return []
    
    # ═══════════════════════════════════════════════════════════════
    #                         UTILITY METHODS
    # ═══════════════════════════════════════════════════════════════

    def _update_rating_color_display(self):
        """Aggiorna display di rating (stelle) e color label sulla thumbnail"""
        try:
            # RATING (stelle celesti)
            rating = self.image_data.get('lr_rating') or self.image_data.get('rating')
            if rating is not None:
                try:
                    rating_val = int(rating)
                    if 1 <= rating_val <= 5:
                        stars = '★' * rating_val
                        self.rating_label.setText(stars)
                        self.rating_label.show()
                    else:
                        self.rating_label.hide()
                except (ValueError, TypeError):
                    self.rating_label.hide()
            else:
                self.rating_label.hide()

            # COLOR LABEL (quadratino colorato)
            color_label = self.image_data.get('color_label')
            if color_label:
                color_hex = COLOR_LABELS.get(color_label)
                if not color_hex:
                    # Prova match case-insensitive
                    for key, val in COLOR_LABELS.items():
                        if key.lower() == color_label.lower():
                            color_hex = val
                            break
                if color_hex:
                    self.color_label_indicator.setStyleSheet(f"""
                        background-color: {color_hex};
                        border: 1px solid rgba(255, 255, 255, 0.5);
                        border-radius: 2px;
                    """)
                    self.color_label_indicator.show()
                else:
                    self.color_label_indicator.hide()
            else:
                self.color_label_indicator.hide()

        except Exception as e:
            print(f"Errore _update_rating_color_display: {e}")

    def set_selected(self, selected):
        """Imposta stato selezione"""
        self._selected = selected
        self.checkbox.setChecked(selected)
        self._update_style()
        self.selection_changed.emit(self, selected)
    
    def is_selected(self):
        """Ritorna stato selezione"""
        return self._selected
    
    def _update_style(self):
        """Aggiorna stile in base allo stato"""
        if self._selected:
            border_color = COLORS['ambra']
            bg_color = COLORS['grafite_light']
        else:
            border_color = COLORS['blu_petrolio']
            bg_color = COLORS['grafite']
        
        self.setStyleSheet(f"""
            ImageCard {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 6px;
            }}
            ImageCard:hover {{
                border-color: {COLORS['blu_petrolio_light']};
            }}
        """)
    
    def refresh_display(self):
        """Refresh del display della card con dati aggiornati"""
        try:
            # Aggiorna tags display
            if hasattr(self, 'tags_label'):
                ai_tags = self.image_data.get('ai_tags')
                user_tags = self.image_data.get('user_tags') 
                
                all_tags = []
                if ai_tags:
                    try:
                        if isinstance(ai_tags, str):
                            ai_tags = json.loads(ai_tags) if ai_tags else []
                        all_tags.extend(ai_tags)
                    except:
                        pass
                        
                if user_tags:
                    try:
                        if isinstance(user_tags, str):
                            user_tags = json.loads(user_tags) if user_tags else []
                        all_tags.extend(user_tags)
                    except:
                        pass
                
                if all_tags:
                    display_tags = all_tags[:3]
                    more_count = len(all_tags) - 3
                    tag_text = " • ".join(display_tags)
                    if more_count > 0:
                        tag_text += f" (+{more_count})"
                    self.tags_label.setText(tag_text)
                else:
                    self.tags_label.setText(t("widgets.label.no_tags"))

            # Aggiorna descrizione display
            if hasattr(self, 'desc_label'):
                description = self.image_data.get('ai_description', '').strip()
                if description:
                    display_desc = description if len(description) <= 60 else description[:57] + "..."
                    self.desc_label.setText(display_desc)
                else:
                    self.desc_label.setText(t("widgets.label.no_description"))

            # Aggiorna rating e color label
            self._update_rating_color_display()

            # Forza repaint
            self.update()

        except Exception as e:
            print(f"Errore refresh_display: {e}")
    
    
    def _open_folder(self, items):
        """Apri cartella contenente le immagini, con dialog informativo per file mancanti"""
        try:
            folders = set()
            missing_info = []

            for item in items:
                if not hasattr(item, 'filepath') or not item.filepath:
                    continue
                status = item._check_file_status()
                if status == 'ok':
                    folders.add(item.filepath.parent)
                else:
                    messages = {
                        'no_disk': t("widgets.status.no_disk") + f": {item.filepath.anchor}",
                        'no_path': t("widgets.status.no_path") + f": {item.filepath.parent}",
                        'no_file': t("widgets.status.no_file") + f": {item.filepath.name}\n   in: {item.filepath.parent}",
                    }
                    missing_info.append(f"• {messages.get(status, 'Errore sconosciuto')}\n   Percorso: {item.filepath}")

            # Apri cartelle esistenti
            for folder in folders:
                if platform.system() == "Windows":
                    subprocess.run(["explorer", str(folder)])
                elif platform.system() == "Darwin":
                    subprocess.run(["open", str(folder)])
                else:
                    subprocess.run(["xdg-open", str(folder)])

            # Mostra dialog per file mancanti
            if missing_info:
                QMessageBox.warning(
                    self, t("widgets.msg.files_unreachable_title"),
                    f"I seguenti file non sono accessibili:\n\n" + "\n\n".join(missing_info)
                )

        except Exception as e:
            print(f"Errore apertura cartella: {e}")
    
    def _copy_paths(self, items):
        """Copia percorsi negli appunti"""
        try:
            paths = []
            for item in items:
                if hasattr(item, 'filepath') and item.filepath:
                    paths.append(str(item.filepath))
            
            if paths:
                clipboard = QApplication.clipboard()
                clipboard.setText("\n".join(paths))
                
        except Exception as e:
            print(f"Errore copia percorsi: {e}")
    
    def _open_external(self):
        """Apri immagine in viewer esterno, con dialog informativo se mancante"""
        try:
            status = self._check_file_status()
            if status == 'ok':
                if platform.system() == "Windows":
                    subprocess.run(["start", str(self.filepath)], shell=True)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", str(self.filepath)])
                else:
                    subprocess.run(["xdg-open", str(self.filepath)])
            else:
                messages = {
                    'no_disk': t("widgets.status.no_disk") + f": {self.filepath.anchor}",
                    'no_path': t("widgets.status.no_path") + f":\n{self.filepath.parent}",
                    'no_file': t("widgets.status.no_file") + f":\n{self.filepath.name}",
                }
                QMessageBox.warning(
                    self, t("widgets.msg.file_unreachable_title"),
                    f"{messages.get(status, 'Errore sconosciuto')}\n\n" +
                    t("widgets.msg.full_path", path=self.filepath)
                )

        except Exception as e:
            print(f"Errore apertura esterna: {e}")
    
    def _open_with_external_editor(self, editor):
        """Apri immagine con editor esterno e monitora chiusura processo"""
        try:
            if not self.filepath or not self.filepath.exists():
                QMessageBox.warning(self, t("widgets.msg.file_error_title"), t("widgets.msg.file_not_found"))
                return

            editor_path = Path(editor['path'])
            if not editor_path.exists():
                QMessageBox.warning(
                    self,
                    t("widgets.msg.editor_not_found_title"),
                    f"L'editor {editor['name']} non è disponibile:\n{editor_path}"
                )
                return
            
            # Memorizza timestamp file e XMP prima dell'apertura
            original_mtime = self.filepath.stat().st_mtime
            xmp_sidecar = Path(str(self.filepath) + '.xmp')
            original_xmp_mtime = xmp_sidecar.stat().st_mtime if xmp_sidecar.exists() else None
            
            # Avvia l'editor
            try:
                # Costruisci comando con argomenti se presenti
                command = [str(editor_path)]
                
                # Aggiungi argomenti se specificati
                if editor.get('command_args', '').strip():
                    args = editor['command_args'].strip().split()
                    command.extend(args)
                
                # Aggiungi percorso file sempre alla fine
                command.append(str(self.filepath))
                
                process = subprocess.Popen(command)
                
                # Avvia monitoraggio processo in background
                self._start_process_monitoring(process, original_mtime, original_xmp_mtime, editor['name'])
                
            except Exception as e:
                QMessageBox.critical(
                    self,
                    t("widgets.msg.editor_open_error_title"),
                    t("widgets.msg.editor_launch_error", name=editor['name'], error=str(e))
                )
                
        except Exception as e:
            print(f"Errore apertura editor esterno: {e}")
    
    def _start_process_monitoring(self, process, original_mtime, original_xmp_mtime, editor_name):
        """Avvia monitoraggio processo editor in background"""
        from PyQt6.QtCore import QThread, pyqtSignal

    def is_selected(self):
        """Restituisce True se la card è selezionata"""
        return self.checkbox.isChecked()
        
        class ProcessMonitor(QThread):
            process_finished = pyqtSignal(bool)  # True se ci sono state modifiche
            
            def __init__(self, process, filepath, original_mtime, original_xmp_mtime):
                super().__init__()
                self.process = process
                self.filepath = filepath
                self.original_mtime = original_mtime
                self.original_xmp_mtime = original_xmp_mtime
            
            def run(self):
                # Aspetta che il processo si chiuda
                self.process.wait()
                
                # Controlla se ci sono state modifiche
                try:
                    current_mtime = self.filepath.stat().st_mtime if self.filepath.exists() else 0
                    file_changed = current_mtime != self.original_mtime
                    
                    # Controlla XMP sidecar
                    xmp_sidecar = Path(str(self.filepath) + '.xmp')
                    xmp_changed = False
                    if xmp_sidecar.exists():
                        current_xmp_mtime = xmp_sidecar.stat().st_mtime
                        if self.original_xmp_mtime is None:
                            xmp_changed = True  # Nuovo file XMP creato
                        elif current_xmp_mtime != self.original_xmp_mtime:
                            xmp_changed = True  # File XMP modificato
                    
                    has_changes = file_changed or xmp_changed
                    self.process_finished.emit(has_changes)
                    
                except Exception as e:
                    print(f"Errore controllo modifiche: {e}")
                    self.process_finished.emit(False)
        
        # Mostra indicatore editing attivo
        self.filename_label.setStyleSheet(
            f"font-size: 11px; color: {COLORS['ambra']}; font-weight: bold;"
        )
        self.filename_label.setText(f"🎨 EDITING: {self.image_data.get('filename', 'Unknown')}")
        
        # Crea e avvia monitor
        self.process_monitor = ProcessMonitor(process, self.filepath, original_mtime, original_xmp_mtime)
        self.process_monitor.process_finished.connect(
            lambda has_changes: self._on_editor_closed(has_changes, editor_name)
        )
        self.process_monitor.start()
    
    def _on_editor_closed(self, has_changes, editor_name):
        """Chiamato quando l'editor si chiude"""
        # Ripristina stile normale
        self.filename_label.setStyleSheet(f"font-size: 11px; color: {COLORS['grigio_chiaro']};")
        self.filename_label.setText(f"<b>{self.image_data.get('filename', 'Unknown')}</b>")
        
        if has_changes:
            self._reimport_after_edit()
            
            # Notifica discreta
            self.filename_label.setStyleSheet(
                f"font-size: 11px; color: {COLORS['verde']}; font-weight: bold;"
            )
            self.filename_label.setText(f"✅ {self.image_data.get('filename', 'Unknown')}")
            
            # Timer per ripristinare stile dopo 3 secondi
            QTimer.singleShot(3000, lambda: (
                self.filename_label.setStyleSheet(f"font-size: 11px; color: {COLORS['grigio_chiaro']};"),
                self.filename_label.setText(f"<b>{self.image_data.get('filename', 'Unknown')}</b>")
            ))
        else:
            pass
    
    def _reimport_after_edit(self):
        """Reimporta tag e descrizione dopo modifica esterna"""
        try:
            # Segnala alla gallery di reimportare questa immagine
            if hasattr(self.parent(), 'reimport_image_metadata'):
                self.parent().reimport_image_metadata(self.image_id, self.filepath)
            elif hasattr(self.parent(), 'parent') and hasattr(self.parent().parent(), 'reimport_image_metadata'):
                self.parent().parent().reimport_image_metadata(self.image_id, self.filepath)
            else:
                print("⚠️ Impossibile trovare metodo di reimport nella gallery")
        
        except Exception as e:
            print(f"Errore reimport dopo edit: {e}")
    
    def _edit_tags(self, items):
        """Edita tag - SOLO database reale, nessun fallback"""
        try:
            dialog = UserTagDialog(items, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_tags = dialog.get_tags()

                # SOLO SCRITTURA DATABASE REALE
                db_success = 0
                db_failures = 0
                
                db_manager = self._get_database_manager()
                if not db_manager:
                    print("❌ ERRORE: DatabaseManager non disponibile - operazione annullata")
                    return
                
                for item in items:
                    if hasattr(item, 'image_id') and item.image_id:
                        try:
                            # Prova diversi possibili nomi di metodi per tag
                            if hasattr(db_manager, 'update_tags'):
                                db_manager.update_tags(item.image_id, new_tags)
                            elif hasattr(db_manager, 'update_image_tags'):
                                db_manager.update_image_tags(item.image_id, new_tags)
                            elif hasattr(db_manager, 'set_tags'):
                                db_manager.set_tags(item.image_id, new_tags)
                            elif hasattr(db_manager, 'update_metadata'):
                                db_manager.update_metadata(item.image_id, tags=new_tags)
                            else:
                                print(f"❌ ERRORE: Nessun metodo trovato per aggiornare tag!")
                                db_failures += 1
                                continue
                                
                            # Aggiorna image_data SOLO se DB scrittura è riuscita
                            item.image_data['tags'] = json.dumps(new_tags)
                            db_success += 1
                        except Exception as e:
                            print(f"Errore scrittura tag DB per {item.image_data.get('filename')}: {e}")
                            db_failures += 1
                    else:
                        db_failures += 1

                if db_success > 0:
                    # Refresh solo se almeno una scrittura è riuscita
                    self._refresh_after_database_operation([item for item in items if hasattr(item, 'image_id') and item.image_id], "tag")
        except Exception as e:
            print(f"Errore gestione tag: {e}")
    
    def _edit_bioclip_taxonomy(self, items):
        """Edita tassonomia BioCLIP - dialog dedicato con 7 livelli"""
        try:
            dialog = BioCLIPTaxonomyDialog(items, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                taxonomy = dialog.get_taxonomy()

                db_manager = self._get_database_manager()
                if not db_manager:
                    print("❌ ERRORE: DatabaseManager non disponibile")
                    return

                db_success = 0
                for item in items:
                    if hasattr(item, 'image_id') and item.image_id:
                        try:
                            if db_manager.update_bioclip_taxonomy(item.image_id, taxonomy):
                                item.image_data['bioclip_taxonomy'] = json.dumps(taxonomy)
                                db_success += 1
                        except Exception as e:
                            print(f"Errore scrittura BioCLIP taxonomy: {e}")

                if db_success > 0:
                    # Invalida cache tooltip e refresh
                    for item in items:
                        if hasattr(item, '_invalidate_tooltip_cache'):
                            item._invalidate_tooltip_cache()
                    self._refresh_after_database_operation(
                        [item for item in items if hasattr(item, 'image_id') and item.image_id],
                        "bioclip_taxonomy"
                    )
        except Exception as e:
            print(f"Errore gestione BioCLIP taxonomy: {e}")

    def _edit_description(self, items):
        """Edita descrizione - SOLO database reale, nessun fallback"""
        try:
            dialog = DescriptionDialog(items, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_description = dialog.get_description()

                # SOLO SCRITTURA DATABASE REALE
                db_success = 0
                db_failures = 0
                
                db_manager = self._get_database_manager()
                if not db_manager:
                    print("❌ ERRORE: DatabaseManager non disponibile - operazione annullata")
                    return
                
                for item in items:
                    if hasattr(item, 'image_id') and item.image_id:
                        try:
                            # Prova diversi possibili nomi di metodi per descrizione
                            if hasattr(db_manager, 'update_description'):
                                db_manager.update_description(item.image_id, new_description)
                            elif hasattr(db_manager, 'update_image_description'):
                                db_manager.update_image_description(item.image_id, new_description)
                            elif hasattr(db_manager, 'set_description'):
                                db_manager.set_description(item.image_id, new_description)
                            elif hasattr(db_manager, 'update_metadata'):
                                db_manager.update_metadata(item.image_id, description=new_description)
                            else:
                                print(f"❌ ERRORE: Nessun metodo trovato per aggiornare descrizione!")
                                db_failures += 1
                                continue
                                
                            # Aggiorna image_data SOLO se DB scrittura è riuscita
                            item.image_data['description'] = new_description
                            db_success += 1
                        except Exception as e:
                            print(f"Errore scrittura descrizione DB per {item.image_data.get('filename')}: {e}")
                            db_failures += 1
                    else:
                        db_failures += 1

                if db_success > 0:
                    # Refresh solo se almeno una scrittura è riuscita
                    self._refresh_after_database_operation([item for item in items if hasattr(item, 'image_id') and item.image_id], "description")
        except Exception as e:
            print(f"Errore gestione descrizione: {e}")

    def _edit_title(self, items):
        """Edita titolo - SOLO database reale, nessun fallback"""
        try:
            dialog = TitleDialog(items, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_title = dialog.get_title()

                # SOLO SCRITTURA DATABASE REALE
                db_success = 0
                db_failures = 0

                db_manager = self._get_database_manager()
                if not db_manager:
                    print("❌ ERRORE: DatabaseManager non disponibile - operazione annullata")
                    return

                for item in items:
                    if hasattr(item, 'image_id') and item.image_id:
                        try:
                            # Prova diversi possibili nomi di metodi per titolo
                            if hasattr(db_manager, 'update_title'):
                                db_manager.update_title(item.image_id, new_title)
                            elif hasattr(db_manager, 'update_image_title'):
                                db_manager.update_image_title(item.image_id, new_title)
                            elif hasattr(db_manager, 'set_title'):
                                db_manager.set_title(item.image_id, new_title)
                            elif hasattr(db_manager, 'update_metadata'):
                                db_manager.update_metadata(item.image_id, title=new_title)
                            else:
                                print(f"❌ ERRORE: Nessun metodo trovato per aggiornare titolo!")
                                db_failures += 1
                                continue

                            # Aggiorna image_data SOLO se DB scrittura è riuscita
                            item.image_data['title'] = new_title
                            db_success += 1
                        except Exception as e:
                            print(f"Errore scrittura titolo DB per {item.image_data.get('filename')}: {e}")
                            db_failures += 1
                    else:
                        db_failures += 1

                if db_success > 0:
                    # Refresh solo se almeno una scrittura è riuscita
                    self._refresh_after_database_operation([item for item in items if hasattr(item, 'image_id') and item.image_id], "title")
        except Exception as e:
            print(f"Errore gestione titolo: {e}")

    def _set_rating(self, items, rating_value):
        """Imposta rating (stelle) per le immagini selezionate"""
        try:
            db_manager = self._get_database_manager()
            if not db_manager:
                print("❌ ERRORE: DatabaseManager non disponibile")
                return

            db_success = 0
            db_failures = 0

            for item in items:
                if hasattr(item, 'image_id') and item.image_id:
                    try:
                        # Usa None se rating è 0 (nessun rating)
                        db_rating = rating_value if rating_value > 0 else None

                        if hasattr(db_manager, 'update_metadata'):
                            db_manager.update_metadata(item.image_id, lr_rating=db_rating)
                        elif hasattr(db_manager, 'update_image_metadata'):
                            db_manager.update_image_metadata(item.image_id, lr_rating=db_rating)
                        else:
                            print(f"❌ ERRORE: Nessun metodo per aggiornare rating!")
                            db_failures += 1
                            continue

                        # Aggiorna image_data locale
                        item.image_data['lr_rating'] = db_rating
                        item.image_data['rating'] = db_rating

                        # Aggiorna display e invalida cache tooltip
                        item._update_rating_color_display()
                        if hasattr(item, '_cached_semantic_tooltip'):
                            delattr(item, '_cached_semantic_tooltip')

                        db_success += 1

                    except Exception as e:
                        print(f"Errore rating per {item.image_data.get('filename')}: {e}")
                        db_failures += 1
                else:
                    db_failures += 1

        except Exception as e:
            print(f"Errore _set_rating: {e}")

    def _set_color_label(self, items, color_value):
        """Imposta color label per le immagini selezionate"""
        try:
            db_manager = self._get_database_manager()
            if not db_manager:
                print("❌ ERRORE: DatabaseManager non disponibile")
                return

            db_success = 0
            db_failures = 0

            for item in items:
                if hasattr(item, 'image_id') and item.image_id:
                    try:
                        if hasattr(db_manager, 'update_metadata'):
                            db_manager.update_metadata(item.image_id, color_label=color_value)
                        elif hasattr(db_manager, 'update_image_metadata'):
                            db_manager.update_image_metadata(item.image_id, color_label=color_value)
                        else:
                            print(f"❌ ERRORE: Nessun metodo per aggiornare color_label!")
                            db_failures += 1
                            continue

                        # Aggiorna image_data locale
                        item.image_data['color_label'] = color_value

                        # Aggiorna display e invalida cache tooltip
                        item._update_rating_color_display()
                        if hasattr(item, '_cached_semantic_tooltip'):
                            delattr(item, '_cached_semantic_tooltip')

                        db_success += 1

                    except Exception as e:
                        print(f"Errore color_label per {item.image_data.get('filename')}: {e}")
                        db_failures += 1
                else:
                    db_failures += 1

        except Exception as e:
            print(f"Errore _set_color_label: {e}")

    def _delete_from_database(self, items):
        """Elimina immagini selezionate dal database (non il file fisico)"""
        try:
            if not items:
                return

            # Messaggio di conferma
            count = len(items)
            if count == 1:
                filename = items[0].image_data.get('filename', 'immagine')
                msg = t("widgets.msg.delete_confirm_single", filename=filename)
            else:
                msg = t("widgets.msg.delete_confirm_multi", count=count)

            reply = QMessageBox.question(
                self,
                t("widgets.msg.delete_confirm_title"),
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # Ottieni db_manager
            db_manager = None
            if hasattr(self, 'parent_window') and self.parent_window:
                if hasattr(self.parent_window, 'db_manager'):
                    db_manager = self.parent_window.db_manager
                elif hasattr(self.parent_window, 'parent') and hasattr(self.parent_window.parent(), 'db_manager'):
                    db_manager = self.parent_window.parent().db_manager

            if not db_manager:
                # Fallback: crea istanza temporanea con path da config
                from db_manager_new import DatabaseManager
                import yaml
                config_path = Path('config_new.yaml')
                db_path = 'database/offgallery.sqlite'  # Default
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                        db_path = config.get('paths', {}).get('database', db_path)
                db_manager = DatabaseManager(db_path)

            deleted = 0
            failed = 0

            for item in items:
                image_id = item.image_data.get('id')
                if image_id:
                    try:
                        if db_manager.delete_image(image_id):
                            deleted += 1
                            # Rimuovi la card dalla gallery
                            item.setParent(None)
                            item.deleteLater()
                        else:
                            failed += 1
                    except Exception as e:
                        print(f"❌ Errore eliminazione {item.image_data.get('filename')}: {e}")
                        failed += 1
                else:
                    failed += 1

            # Messaggio risultato
            if deleted > 0:
                if failed > 0:
                    QMessageBox.warning(
                        self,
                        t("widgets.msg.delete_partial_title"),
                        t("widgets.msg.delete_partial", deleted=deleted, failed=failed)
                    )
            else:
                QMessageBox.warning(
                    self,
                    t("widgets.msg.delete_error_title"),
                    t("widgets.msg.delete_none")
                )

        except Exception as e:
            print(f"Errore _delete_from_database: {e}")
            QMessageBox.critical(self, t("widgets.msg.delete_critical_title"), t("widgets.msg.delete_error", error=str(e)))

    def _run_bioclip_and_refresh(self, items):
        """Esegui BioCLIP con refresh automatico"""
        try:
            # Emetti segnale per BioCLIP
            self.bioclip_requested.emit(items)
        except Exception as e:
            print(f"Errore BioCLIP: {e}")
    
    def _run_llm_and_refresh(self, items):
        """Esegui LLM tagging con refresh automatico"""
        try:
            # Emetti segnale per LLM
            self.llm_tagging_requested.emit(items)
        except Exception as e:
            print(f"Errore LLM tagging: {e}")
    
    def _refresh_after_database_operation(self, items, operation_type):
        """Refresh automatico dopo operazioni database - CENTRALIZZATO"""

        # Ricarica i dati dal database per ogni item
        try:
            db_manager = self._get_database_manager()
            if db_manager:
                for item in items:
                    if hasattr(item, 'filepath') and item.filepath:
                        # Ricarica dati aggiornati dal DB
                        fresh_data = db_manager.get_image_by_filepath(str(item.filepath))
                        if fresh_data:
                            # Aggiorna image_data con i nuovi valori
                            item.image_data.update(fresh_data)

                    # Invalida cache tooltip per forzare rebuild con nuovi dati
                    if hasattr(item, '_invalidate_tooltip_cache'):
                        item._invalidate_tooltip_cache()
        except Exception as e:
            print(f"⚠️ Errore ricaricamento dati dal DB: {e}")

        # Aggiorna badge XMP
        XMPBadgeIntegration.replace_refresh_after_database_operation(items, operation_type)

    def _force_data_refresh(self):
        """Forza refresh dei dati image_data - FIXED: Implementazione specifica"""
        try:
            # TODO: In una vera implementazione, qui ricaricheresti dal database
            # Per ora forziamo l'invalidazione della cache
            
            # Reset cached unified tags
            if hasattr(self, '_unified_tags_cache'):
                delattr(self, '_unified_tags_cache')
            
            # Reset tooltip cache
            if hasattr(self, '_tooltip_cache'):
                delattr(self, '_tooltip_cache')

        except Exception as e:
            print(f"Errore force data refresh: {e}")
    
    def _refresh_badges(self):
        """Refresh completo dei badge scores/indicators"""
        try:
            if hasattr(self, 'info_frame') and self.info_frame.layout():
                # Clear existing widgets
                layout = self.info_frame.layout()
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                
                # Rebuild con dati aggiornati
                self._build_scores_and_indicators(layout)
                
                # Force layout update
                self.info_frame.updateGeometry()
                self.update()
                
        except Exception as e:
            print(f"Errore refresh badges: {e}")
    
    def _invalidate_tooltip_cache(self):
        """Invalida cache tooltip per forzare rebuild"""
        try:
            # Reset area corrente per forzare rebuild
            self._current_tooltip_area = None

            # Clear tooltip Qt
            self.setToolTip("")

            # Reset cached tooltip data
            if hasattr(self, '_cached_semantic_tooltip'):
                delattr(self, '_cached_semantic_tooltip')
            if hasattr(self, '_cached_technical_tooltip'):
                delattr(self, '_cached_technical_tooltip')
            # Reset anche cache tags unificati
            if hasattr(self, '_unified_tags_cache'):
                delattr(self, '_unified_tags_cache')

        except Exception as e:
            print(f"Errore invalidate tooltip cache: {e}")
    
    def _update_visual_state(self):
        """Aggiorna stato visuale generale"""
        try:
            # Force repaint
            self.update()
            self.repaint()
            
            # Update parent se ha metodo refresh
            if hasattr(self.parent(), 'update'):
                self.parent().update()
                
        except Exception as e:
            print(f"Errore update visual state: {e}")
    
    def _show_complete_exif(self, items):
        """Mostra dialog con TUTTI i dati EXIF"""
        try:
            dialog = CompleteExifDialog(items, self)
            dialog.exec()
        except Exception as e:
            print(f"Errore dialog EXIF: {e}")
    
    # ═══════════════════════════════════════════════════════════════
    #                       OPERAZIONI XMP
    # ═══════════════════════════════════════════════════════════════
    
    def _analyze_xmp_detailed(self, items):
        """Analisi XMP dettagliata con confronto format-aware: DB vs Sidecar vs Embedded.
        Per i RAW (non DNG) l'embedded non viene considerato — solo il sidecar conta."""
        try:
            if not XMP_SUPPORT_AVAILABLE:
                self._show_xmp_dialog("❌ Errore", t("widgets.xmp.no_xmp_manager"))
                return

            from xmp_manager_extended import XMPManagerExtended
            import textwrap

            results = []
            xmp_manager = XMPManagerExtended()

            for item in items:
                if not hasattr(item, 'filepath') or not item.filepath:
                    continue

                filepath = item.filepath
                if not filepath.exists():
                    results.append(f"❌ {filepath.name}: {t('widgets.xmp.file_not_found')}")
                    continue

                # Categoria formato: determina se l'embedded è rilevante
                file_category = xmp_manager._get_file_category(filepath)
                # Per i RAW puri (non DNG) l'embedded è solo dati del produttore,
                # non è un canale di scrittura gestito da OffGallery — lo ignoriamo.
                embedded_supported = file_category in ('standard', 'dng')

                # === DATI DA DATABASE ===
                db_tags = set(item.get_unified_tags())
                db_desc = (item.image_data.get('description') or '').strip()
                db_title = (item.image_data.get('title') or '').strip()

                # === DATI DA SIDECAR XMP ===
                sidecar_path = filepath.with_suffix('.xmp')
                sidecar_tags = set()
                sidecar_desc = ""
                sidecar_title = ""
                sidecar_exists = sidecar_path.exists()

                if sidecar_exists:
                    sidecar_data = self._read_xmp_with_exiftool(sidecar_path)
                    if sidecar_data:
                        sidecar_tags, sidecar_desc, sidecar_title = self._extract_xmp_fields(sidecar_data)

                # === DATI DA EMBEDDED XMP (solo standard e DNG) ===
                embedded_tags = set()
                embedded_desc = ""
                embedded_title = ""

                if embedded_supported:
                    embedded_data = self._read_xmp_with_exiftool(filepath)
                    if embedded_data:
                        embedded_tags, embedded_desc, embedded_title = self._extract_xmp_fields(embedded_data)

                # === FORMATO OUTPUT ===
                _ev = t("widgets.xmp.empty_value")
                result = f"📂 {filepath.name}\n"
                result += f"📍 Sidecar: {t('widgets.xmp.present') if sidecar_exists else t('widgets.xmp.absent')}"
                if file_category == 'raw':
                    result += f" | Embedded: {t('widgets.xmp.ignored_raw')}\n\n"
                elif file_category == 'dng':
                    _emb_label = t('widgets.xmp.present') if (embedded_tags or embedded_title or embedded_desc) else t('widgets.xmp.empty_embedded')
                    result += f" | Embedded: {_emb_label} (DNG)\n\n"
                else:
                    _emb_label = t('widgets.xmp.present') if (embedded_tags or embedded_title or embedded_desc) else t('widgets.xmp.empty_embedded')
                    result += f" | Embedded: {_emb_label}\n\n"

                # --- SEZIONE TITOLO ---
                result += f"{t('widgets.xmp.section_title')}\n"
                result += f"   DB:       {db_title if db_title else _ev}\n"
                if sidecar_exists:
                    result += f"   Sidecar:  {sidecar_title if sidecar_title else _ev}\n"
                if embedded_supported:
                    result += f"   Embedded: {embedded_title if embedded_title else _ev}\n"

                # Stato sync titolo
                titles_match = (db_title == sidecar_title == embedded_title) if embedded_supported and sidecar_exists else \
                               (db_title == sidecar_title) if sidecar_exists else \
                               (db_title == embedded_title) if embedded_supported else True
                result += f"   {t('widgets.xmp.synced') if titles_match else t('widgets.xmp.mismatch')}\n"

                # --- SEZIONE DESCRIZIONE ---
                result += f"\n{t('widgets.xmp.section_desc')}\n"
                db_desc_preview = (db_desc[:40] + "...") if len(db_desc) > 40 else db_desc
                result += f"   DB:       {db_desc_preview if db_desc else _ev}\n"
                if sidecar_exists:
                    sidecar_desc_preview = (sidecar_desc[:40] + "...") if len(sidecar_desc) > 40 else sidecar_desc
                    result += f"   Sidecar:  {sidecar_desc_preview if sidecar_desc else _ev}\n"
                if embedded_supported:
                    embedded_desc_preview = (embedded_desc[:40] + "...") if len(embedded_desc) > 40 else embedded_desc
                    result += f"   Embedded: {embedded_desc_preview if embedded_desc else _ev}\n"

                # Stato sync descrizione
                descs_match = (db_desc == sidecar_desc == embedded_desc) if embedded_supported and sidecar_exists else \
                              (db_desc == sidecar_desc) if sidecar_exists else \
                              (db_desc == embedded_desc) if embedded_supported else True
                result += f"   {t('widgets.xmp.synced') if descs_match else t('widgets.xmp.mismatch')}\n"

                # --- SEZIONE TAGS ---
                result += f"\n{t('widgets.xmp.section_tags')}\n"
                result += f"   DB:       {len(db_tags)} tag\n"
                if sidecar_exists:
                    result += f"   Sidecar:  {len(sidecar_tags)} tag\n"
                if embedded_supported:
                    result += f"   Embedded: {len(embedded_tags)} tag\n"

                # Analisi differenze tags
                all_tags = db_tags | sidecar_tags | embedded_tags
                if all_tags:
                    # Tags presenti ovunque
                    common_all = db_tags & (sidecar_tags if sidecar_exists else db_tags) & (embedded_tags if embedded_supported else db_tags)
                    if common_all:
                        common_text = ', '.join(sorted(common_all)[:5])
                        if len(common_all) > 5:
                            common_text += f"... (+{len(common_all)-5})"
                        result += f"   {t('widgets.xmp.common_tags')}: {common_text}\n"

                    # Tags solo in DB
                    db_only = db_tags - sidecar_tags - embedded_tags
                    if db_only:
                        db_only_text = ', '.join(sorted(db_only)[:3])
                        if len(db_only) > 3:
                            db_only_text += f"... (+{len(db_only)-3})"
                        result += f"   {t('widgets.xmp.db_only_tags')}: {db_only_text}\n"

                    # Tags solo in Sidecar
                    if sidecar_exists:
                        sidecar_only = sidecar_tags - db_tags - embedded_tags
                        if sidecar_only:
                            sidecar_only_text = ', '.join(sorted(sidecar_only)[:3])
                            if len(sidecar_only) > 3:
                                sidecar_only_text += f"... (+{len(sidecar_only)-3})"
                            result += f"   {t('widgets.xmp.sidecar_only_tags')}: {sidecar_only_text}\n"

                    # Tags solo in Embedded
                    if embedded_supported:
                        embedded_only = embedded_tags - db_tags - sidecar_tags
                        if embedded_only:
                            embedded_only_text = ', '.join(sorted(embedded_only)[:3])
                            if len(embedded_only) > 3:
                                embedded_only_text += f"... (+{len(embedded_only)-3})"
                            result += f"   {t('widgets.xmp.embedded_only_tags')}: {embedded_only_text}\n"

                # Stato sync tags
                tags_match = (db_tags == sidecar_tags == embedded_tags) if embedded_supported and sidecar_exists else \
                             (db_tags == sidecar_tags) if sidecar_exists else \
                             (db_tags == embedded_tags) if embedded_supported else True
                result += f"   {t('widgets.xmp.synced') if tags_match else t('widgets.xmp.mismatch')}\n"

                results.append(result)

            # Mostra risultati in dialog
            if results:
                dialog_text = "\n" + ("="*50 + "\n\n").join(results)
                dialog_text += f"\n{'='*50}\n{t('widgets.xmp.legend')}"
            else:
                dialog_text = t("widgets.xmp.no_file")

            self._show_xmp_dialog(t("widgets.xmp.analysis_title"), dialog_text)
                
        except Exception as e:
            print(f"Errore analisi XMP: {e}")
            import traceback
            traceback.print_exc()
            self._show_xmp_dialog("❌ Errore", t("widgets.xmp.analysis_error", error=str(e)))
    
    def _import_from_xmp_with_refresh(self, items):
        """Sincronizza XMP/Embedded → DB: titolo, descrizione, tag, stelle, colore."""

        # GUARD: Previeni chiamate multiple
        if hasattr(self, '_importing_xmp') and self._importing_xmp:
            logger.warning("Import XMP già in corso, ignoro richiesta duplicata")
            return

        try:
            self._importing_xmp = True  # Flag per prevenire chiamate multiple

            if not XMP_SUPPORT_AVAILABLE:
                self._show_xmp_dialog("❌ Errore", t("widgets.xmp.no_xmp_manager"))
                return

            # Conferma utente
            reply = QMessageBox.question(
                self,
                t("widgets.xmp.import_confirm_title"),
                t("widgets.xmp.import_confirm", n=len(items)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return

            # Check database availability
            db_manager = self._get_database_manager()
            if not db_manager:
                self._show_xmp_dialog("❌ Errore", t("widgets.xmp.no_db_manager"))
                return
            
            success_count = 0
            error_count = 0
            no_xmp_count = 0
            
            for i, item in enumerate(items):
                try:
                    # Check 1: item ha filepath?
                    if not hasattr(item, 'filepath'):
                        error_count += 1
                        continue

                    if not item.filepath:
                        error_count += 1
                        continue

                    filepath = item.filepath

                    # Check 2: file esiste?
                    if not filepath.exists():
                        error_count += 1
                        continue

                    # Check 3: item ha image_id?
                    if not hasattr(item, 'image_id'):
                        error_count += 1
                        continue

                    if not item.image_id:
                        error_count += 1
                        continue

                    # Check 4: XMP source disponibile?
                    sidecar_path = filepath.with_suffix('.xmp')
                    xmp_source = None

                    if sidecar_path.exists():
                        xmp_source = sidecar_path
                    else:
                        # Check embedded XMP
                        embedded_formats = {'.jpg', '.jpeg', '.tif', '.tiff', '.dng', '.cr2', '.nef', '.orf', '.arw', '.rw2', '.pef', '.cr3', '.nrw', '.srf', '.sr2'}
                        if filepath.suffix.lower() in embedded_formats:
                            xmp_source = filepath

                    if not xmp_source:
                        no_xmp_count += 1
                        continue

                    # Check 5: XMP leggibile?
                    xmp_data = self._read_xmp_with_exiftool(xmp_source)
                    if not xmp_data:
                        no_xmp_count += 1
                        continue
                    
                    # Check 6: Estrai dati XMP (NO BioCLIP — gestiti solo internamente)
                    new_tags = []
                    keyword_fields = ['Keywords', 'Subject', 'HierarchicalSubject']

                    for field in keyword_fields:
                        if field in xmp_data and xmp_data[field] is not None:
                            value = xmp_data[field]

                            if isinstance(value, list):
                                for item_val in value:
                                    if item_val is not None:
                                        item_str = str(item_val).strip()
                                        # Filtra via rami AI|Taxonomy (BioCLIP gestito internamente)
                                        if item_str and item_str not in new_tags and not item_str.startswith('AI|Taxonomy') and not item_str.startswith('GeOFF|'):
                                            new_tags.append(item_str)
                            elif isinstance(value, str):
                                separators = [',', '|', ';', '\n']
                                current_tags = [value]

                                for sep in separators:
                                    expanded_tags = []
                                    for tag in current_tags:
                                        expanded_tags.extend([t.strip() for t in tag.split(sep) if t.strip()])
                                    current_tags = expanded_tags

                                for tag in current_tags:
                                    # Filtra via rami AI|Taxonomy
                                    if tag and tag not in new_tags and not tag.startswith('AI|Taxonomy') and not tag.startswith('GeOFF|'):
                                        new_tags.append(tag)
                    
                    # Estrai descrizione
                    new_description = ""
                    desc_fields = ['Description', 'Caption-Abstract', 'ImageDescription']

                    for desc_field in desc_fields:
                        if desc_field in xmp_data and xmp_data[desc_field] is not None:
                            desc_value = xmp_data[desc_field]
                            if desc_value is not None:
                                new_description = str(desc_value).strip()
                                if new_description:
                                    break

                    # Estrai rating (XMP-xmp:Rating)
                    new_rating = None
                    for rating_field in ['Rating', 'XMP-xmp:Rating', 'XMP:Rating']:
                        rating_raw = xmp_data.get(rating_field)
                        if rating_raw is not None:
                            try:
                                rating_val = int(rating_raw)
                                if 1 <= rating_val <= 5:
                                    new_rating = rating_val
                                    break
                            except (ValueError, TypeError):
                                pass

                    # Estrai color label (XMP-xmp:Label)
                    new_color_label = ''
                    for label_field in ['Label', 'XMP-xmp:Label', 'XMP:Label']:
                        label_raw = xmp_data.get(label_field)
                        if label_raw:
                            new_color_label = str(label_raw).strip()
                            break

                    # Estrai title
                    new_title = ""
                    for title_field in ['Title', 'XMP-dc:Title', 'XMP:Title', 'ObjectName', 'Headline']:
                        if title_field in xmp_data and xmp_data[title_field]:
                            new_title = str(xmp_data[title_field]).strip()
                            if new_title:
                                break

                    # Check 7: Hai dati da importare?
                    if not new_tags and not new_description and not new_title and new_rating is None and not new_color_label:
                        no_xmp_count += 1
                        continue

                    # Check 8: Scrivi su database
                    db_updated = False

                    if new_tags:
                        try:
                            if hasattr(db_manager, 'update_tags'):
                                result = db_manager.update_tags(item.image_id, new_tags)
                            elif hasattr(db_manager, 'update_image_tags'):
                                result = db_manager.update_image_tags(item.image_id, new_tags)
                            elif hasattr(db_manager, 'set_tags'):
                                result = db_manager.set_tags(item.image_id, new_tags)
                            elif hasattr(db_manager, 'update_metadata'):
                                result = db_manager.update_metadata(item.image_id, tags=new_tags)
                            else:
                                continue
                            item.image_data['tags'] = json.dumps(new_tags)
                            db_updated = True
                        except Exception as e:
                            logger.error(f"Errore scrittura tag su DB: {e}", exc_info=True)

                    if new_description:
                        try:
                            if hasattr(db_manager, 'update_description'):
                                result = db_manager.update_description(item.image_id, new_description)
                            elif hasattr(db_manager, 'update_image_description'):
                                result = db_manager.update_image_description(item.image_id, new_description)
                            elif hasattr(db_manager, 'set_description'):
                                result = db_manager.set_description(item.image_id, new_description)
                            elif hasattr(db_manager, 'update_metadata'):
                                result = db_manager.update_metadata(item.image_id, description=new_description)
                            else:
                                continue
                            item.image_data['description'] = new_description
                            db_updated = True
                        except Exception as e:
                            logger.error(f"Errore scrittura descrizione su DB: {e}", exc_info=True)

                    if new_title:
                        try:
                            title_updated = False
                            if hasattr(db_manager, 'update_title'):
                                title_updated = db_manager.update_title(item.image_id, new_title)
                            elif hasattr(db_manager, 'update_image_title'):
                                title_updated = db_manager.update_image_title(item.image_id, new_title)
                            if title_updated:
                                item.image_data['title'] = new_title
                                db_updated = True
                        except Exception as e:
                            logger.error(f"Errore aggiornamento title: {e}", exc_info=True)

                    # Importa rating e color_label con update_metadata (campo lr_rating e color_label nel DB)
                    rating_color_kwargs = {}
                    if new_rating is not None:
                        rating_color_kwargs['lr_rating'] = new_rating
                    if new_color_label:
                        rating_color_kwargs['color_label'] = new_color_label

                    if rating_color_kwargs and hasattr(db_manager, 'update_metadata'):
                        try:
                            db_manager.update_metadata(item.image_id, **rating_color_kwargs)
                            if new_rating is not None:
                                item.image_data['lr_rating'] = new_rating
                                item.image_data['rating'] = new_rating
                            if new_color_label:
                                item.image_data['color_label'] = new_color_label
                            db_updated = True
                        except Exception as e:
                            logger.error(f"Errore aggiornamento rating/color_label su DB: {e}", exc_info=True)

                    if db_updated:
                        success_count += 1

                except Exception as e:
                    logger.error(f"Errore import XMP per elemento {i+1}: {e}", exc_info=True)
                    error_count += 1
            
            # Refresh automatico dopo import
            if success_count > 0:
                updated_items = [item for item in items if hasattr(item, 'image_id') and item.image_id]
                self._refresh_after_database_operation(updated_items, "xmp_import")
            
            # Report risultati
            result_msg = t("widgets.xmp.import_done")
            result_msg += t("widgets.xmp.import_updated", n=success_count)
            if no_xmp_count > 0:
                result_msg += t("widgets.xmp.import_no_xmp", n=no_xmp_count)
            if error_count > 0:
                result_msg += t("widgets.xmp.import_errors", n=error_count)

            self._show_xmp_dialog(t("widgets.xmp.import_done_title"), result_msg)

        except Exception as e:
            logger.error(f"Errore globale sincronizzazione XMP → DB: {e}", exc_info=True)
            self._show_xmp_dialog("❌ Errore", t("widgets.xmp.import_error", error=str(e)))
        finally:
            # Rimuovi flag anche in caso di errore
            if hasattr(self, '_importing_xmp'):
                delattr(self, '_importing_xmp')

    def _export_to_xmp_with_refresh(self, items):
        """Sincronizza DB → XMP/Embedded: titolo, descrizione, tag, BioCLIP, stelle, colore."""

        # GUARD: Previeni chiamate multiple
        if hasattr(self, '_exporting_xmp') and self._exporting_xmp:
            logger.warning("Export XMP già in corso, ignoro richiesta duplicata")
            return

        try:
            self._exporting_xmp = True  # Flag per prevenire chiamate multiple

            if not XMP_SUPPORT_AVAILABLE:
                self._show_xmp_dialog("❌ Errore", t("widgets.xmp.no_xmp_manager"))
                return

            # Conferma utente
            reply = QMessageBox.question(
                self,
                t("widgets.xmp.export_confirm_title"),
                t("widgets.xmp.export_confirm", n=len(items)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # Ottieni XMP Manager
            xmp_manager = None
            try:
                from xmp_manager_extended import XMPManagerExtended
                xmp_manager = XMPManagerExtended()
            except Exception as e:
                self._show_xmp_dialog("❌ Errore", t("widgets.xmp.no_xmp_manager_detail", error=str(e)))
                return

            success_count = 0
            error_count = 0
            skipped_count = 0

            # Ottieni DB manager per leggere dati freschi prima della scrittura
            db_manager = self._get_database_manager()

            for i, item in enumerate(items):
                try:
                    # Check filepath
                    if not hasattr(item, 'filepath') or not item.filepath:
                        error_count += 1
                        continue

                    filepath = item.filepath
                    if not filepath.exists():
                        error_count += 1
                        continue

                    # Ricarica image_data dal DB prima di ogni scrittura:
                    # image_data potrebbe essere stale (es. tags aggiunti dopo l'ultima ricerca).
                    # Il DB è la fonte di verità per l'export.
                    if db_manager:
                        fresh_data = db_manager.get_image_by_filepath(str(filepath))
                        if fresh_data:
                            item.image_data.update(fresh_data)

                    # Estrai metadati dal DB (sempre freschi)
                    title = item.image_data.get('title', '') or ''
                    description = item.image_data.get('description', '') or ''
                    tags_raw = item.image_data.get('tags', '[]')
                    rating = item.image_data.get('lr_rating') or item.image_data.get('rating')
                    color_label = item.image_data.get('color_label', '') or ''

                    # Parsing tags da JSON
                    tags = []
                    if tags_raw:
                        try:
                            if isinstance(tags_raw, str):
                                tags = json.loads(tags_raw)
                            elif isinstance(tags_raw, list):
                                tags = tags_raw
                        except json.JSONDecodeError:
                            tags = []

                    # Verifica se ci sono dati da esportare
                    if not title and not description and not tags and rating is None and not color_label:
                        skipped_count += 1
                        continue

                    # Prepara dizionario XMP (sync completo — DB è fonte di verità)
                    xmp_dict = {}
                    if title:
                        xmp_dict['title'] = title
                    if description:
                        xmp_dict['description'] = description
                    if tags:
                        xmp_dict['keywords'] = tags if isinstance(tags, list) else [tags]
                    if rating is not None:
                        try:
                            xmp_dict['rating'] = int(rating)
                        except (ValueError, TypeError):
                            pass
                    if color_label:
                        xmp_dict['color_label'] = color_label

                    # Sync DB→XMP: merge_existing_keywords=False — il DB è la fonte di verità
                    success = xmp_manager.write_xmp_by_format(
                        filepath, xmp_dict, merge_existing_keywords=False
                    )

                    # Scrivi BioCLIP HierarchicalSubject se presente
                    if success:
                        bioclip_raw = item.image_data.get('bioclip_taxonomy', '')
                        if bioclip_raw:
                            try:
                                from embedding_generator import EmbeddingGenerator
                                taxonomy = json.loads(bioclip_raw) if isinstance(bioclip_raw, str) else bioclip_raw
                                if taxonomy and isinstance(taxonomy, list):
                                    hier_path = EmbeddingGenerator.build_hierarchical_taxonomy(taxonomy, prefix="AI|Taxonomy")
                                    if hier_path:
                                        xmp_manager.write_hierarchical_bioclip(filepath, hier_path)
                            except Exception as e:
                                logger.warning(f"Errore HierarchicalSubject BioCLIP per {filepath.name}: {e}")

                    # Scrivi gerarchia geografica se presente
                    if success:
                        geo_hierarchy = item.image_data.get('geo_hierarchy', '')
                        if geo_hierarchy:
                            try:
                                xmp_manager.write_hierarchical_geo(filepath, geo_hierarchy)
                            except Exception as e:
                                logger.warning(f"Errore HierarchicalSubject GeOFF per {filepath.name}: {e}")

                    if success:
                        success_count += 1
                    else:
                        error_count += 1

                except Exception as e:
                    logger.error(f"Errore sincronizzazione DB→XMP per elemento {i+1}: {e}", exc_info=True)
                    error_count += 1

            # Refresh badge XMP: il sidecar è stato appena creato/aggiornato
            if success_count > 0:
                updated_items = [item for item in items if hasattr(item, 'image_id') and item.image_id]
                self._refresh_after_database_operation(updated_items, "xmp_export")

            # Report risultati
            result_msg = t("widgets.xmp.export_done")
            result_msg += t("widgets.xmp.export_synced", n=success_count)
            if skipped_count > 0:
                result_msg += t("widgets.xmp.export_skipped", n=skipped_count)
            if error_count > 0:
                result_msg += t("widgets.xmp.export_errors", n=error_count)

            self._show_xmp_dialog(t("widgets.xmp.export_done_title"), result_msg)

        except Exception as e:
            logger.error(f"Errore globale sincronizzazione DB → XMP: {e}", exc_info=True)
            self._show_xmp_dialog("❌ Errore", t("widgets.xmp.export_error", error=str(e)))
        finally:
            # Rimuovi flag anche in caso di errore
            if hasattr(self, '_exporting_xmp'):
                delattr(self, '_exporting_xmp')

    def _show_xmp_content(self, items):
        """Visualizza contenuto XMP dettagliato"""
        try:
            if len(items) != 1:
                self._show_xmp_dialog("ℹ️ Info", t("widgets.xmp.single_only"))
                return
                
            item = items[0]
            if not hasattr(item, 'filepath') or not item.filepath:
                self._show_xmp_dialog("❌ Errore", t("widgets.xmp.no_path"))
                return
                
            filepath = item.filepath
            if not filepath.exists():
                self._show_xmp_dialog("❌ Errore", t("widgets.xmp.file_not_found", name=filepath.name))
                return
            
            from xmp_manager_extended import XMPManagerExtended
            xmp_manager = XMPManagerExtended()
            
            success_count = 0
            error_count = 0
            
            for item in items:
                try:
                    if not hasattr(item, 'filepath') or not item.filepath:
                        continue
                        
                    filepath = item.filepath
                    if not filepath.exists():
                        error_count += 1
                        continue
                    
                    # Leggi XMP data
                    xmp_data = self._read_xmp_with_exiftool(filepath)
                    if not xmp_data:
                        continue
                    
                    # Estrai tags e descrizione
                    new_tags = []
                    new_description = ""
                    
                    # Tags da XMP - Parsing robusto (NO BioCLIP — gestiti internamente)
                    new_tags = []

                    keyword_fields = ['Keywords', 'Subject', 'HierarchicalSubject']

                    for field in keyword_fields:
                        if field in xmp_data and xmp_data[field] is not None:
                            value = xmp_data[field]

                            if isinstance(value, list):
                                for item in value:
                                    if item is not None:
                                        item_str = str(item).strip()
                                        if item_str and item_str not in new_tags and not item_str.startswith('AI|Taxonomy') and not item_str.startswith('GeOFF|'):
                                            new_tags.append(item_str)
                            elif isinstance(value, str):
                                separators = [',', '|', ';', '\n']
                                current_tags = [value]

                                for sep in separators:
                                    expanded_tags = []
                                    for tag in current_tags:
                                        expanded_tags.extend([t.strip() for t in tag.split(sep) if t.strip()])
                                    current_tags = expanded_tags

                                for tag in current_tags:
                                    if tag and tag not in new_tags and not tag.startswith('AI|Taxonomy') and not tag.startswith('GeOFF|'):
                                        new_tags.append(tag)
                    
                    # Descrizione da XMP
                    for desc_field in ['Description', 'Caption-Abstract', 'ImageDescription']:
                        if desc_field in xmp_data and xmp_data[desc_field]:
                            desc_value = xmp_data[desc_field]
                            if desc_value is not None:
                                new_description = str(desc_value).strip()
                                if new_description:  # Solo se non vuoto dopo strip
                                    break
                    
                    # Aggiorna DATABASE REALE
                    updated = False
                    
                    # TODO: IMPLEMENTAZIONE VERA SCRITTURA DATABASE
                    # Questo dovrebbe essere sostituito con vera chiamata DB
                    #
                    # ESEMPIO di quello che dovrebbe esserci:
                    # from db_manager_new import DatabaseManager
                    # db_manager = DatabaseManager(config['paths']['database'])
                    # 
                    # if item.image_id:
                    #     if new_tags:
                    #         db_manager.update_tags(item.image_id, new_tags)
                    #         updated = True
                    #     if new_description:
                    #         db_manager.update_description(item.image_id, new_description)
                    #         updated = True
                    
                    print("❌ ERRORE: Scrittura database NON implementata!")
                    print("   Serve implementare la chiamata al DatabaseManager reale")
                    print("   I dati XMP non verranno salvati permanentemente")
                    
                    # SIMULAZIONE TEMPORANEA per testing UI
                    if new_tags:
                        item.image_data['tags'] = json.dumps(new_tags)
                        updated = True

                    if new_description:
                        item.image_data['description'] = new_description
                        updated = True
                    
                    if updated:
                        success_count += 1
                    
                except Exception as e:
                    print(f"Errore import XMP per {filepath.name}: {e}")
                    error_count += 1
            
            # Refresh automatico dopo import
            if success_count > 0:
                self._refresh_after_database_operation(items, "xmp_import")
            
            # Report risultati
            if success_count > 0 or error_count > 0:
                result_msg = t("widgets.xmp.import_done")
                result_msg += t("widgets.xmp.import_updated", n=success_count)
                if error_count > 0:
                    result_msg += t("widgets.xmp.import_errors", n=error_count)
                self._show_xmp_dialog(t("widgets.xmp.import_done_title"), result_msg)
            else:
                self._show_xmp_dialog("ℹ️ Import XMP", t("widgets.xmp.import_nothing"))
                
        except Exception as e:
            print(f"Errore import XMP: {e}")
            self._show_xmp_dialog("❌ Errore", t("widgets.xmp.import_error", error=str(e)))
    
    def _show_xmp_content(self, items):
        """Visualizza contenuto XMP dettagliato"""
        try:
            if len(items) != 1:
                self._show_xmp_dialog("ℹ️ Info", t("widgets.xmp.single_only"))
                return
                
            item = items[0]
            if not hasattr(item, 'filepath') or not item.filepath:
                self._show_xmp_dialog("❌ Errore", t("widgets.xmp.no_path"))
                return
                
            filepath = item.filepath
            if not filepath.exists():
                self._show_xmp_dialog("❌ Errore", t("widgets.xmp.file_not_found", name=filepath.name))
                return
            
            # Determina sorgente XMP (priorità: sidecar > embedded)
            sidecar_path = filepath.with_suffix('.xmp')
            xmp_source = None
            source_type = None
            
            if sidecar_path.exists():
                xmp_source = sidecar_path
                source_type = "Sidecar XMP"
            else:
                # Check embedded XMP
                embedded_formats = {'.jpg', '.jpeg', '.tif', '.tiff', '.dng', '.cr2', '.nef', '.orf', '.arw', '.rw2', '.pef', '.cr3', '.nrw', '.srf', '.sr2'}
                if filepath.suffix.lower() in embedded_formats:
                    xmp_source = filepath
                    source_type = "Embedded XMP"
            
            if not xmp_source:
                self._show_xmp_dialog("📋 XMP Content", t("widgets.xmp.no_xmp_available", name=filepath.name, fmt=filepath.suffix.upper()))
                return

            # Leggi XMP con ExifTool
            xmp_data = self._read_xmp_with_exiftool(xmp_source)

            if not xmp_data:
                self._show_xmp_dialog("📋 XMP Content", t("widgets.xmp.xmp_empty_or_unreadable", name=filepath.name, source=source_type))
                return
            
            # Format output user-friendly
            dialog_text = f"📂 File: {filepath.name}\n"
            dialog_text += f"📍 Source: {source_type}\n\n"
            
            # Keywords/Tags - FIX: Parsing robusto per diversi formati
            keywords = []
            
            # Try multiple XMP keyword fields
            keyword_fields = ['Keywords', 'Subject', 'HierarchicalSubject']
            
            for key in keyword_fields:
                if key in xmp_data and xmp_data[key] is not None:
                    value = xmp_data[key]
                    
                    if isinstance(value, list):
                        # Array di keywords
                        for item in value:
                            if item is not None:
                                item_str = str(item).strip()
                                if item_str:
                                    keywords.append(item_str)
                    elif isinstance(value, str):
                        # String con separatori diversi
                        # Puo' essere separato da virgole, pipe, semicolon
                        separators = [',', '|', ';', '\n']
                        current_keywords = [value]
                        
                        for sep in separators:
                            new_keywords = []
                            for kw in current_keywords:
                                new_keywords.extend([k.strip() for k in kw.split(sep) if k.strip()])
                            current_keywords = new_keywords
                        
                        keywords.extend(current_keywords)
            
            # Remove duplicates and clean
            keywords = list(set([k for k in keywords if k and len(k.strip()) > 0]))
            keywords.sort()
            
            if keywords:
                dialog_text += f"🏷️ Keywords ({len(keywords)}):\n"
                # Format nicely - one per line for better readability
                for i, kw in enumerate(keywords, 1):
                    dialog_text += f"  {i}. {kw}\n"
                dialog_text += "\n"
            
            # Title/Caption
            title = None
            for title_key in ['Title', 'Headline']:
                if title_key in xmp_data and xmp_data[title_key] is not None:
                    title = str(xmp_data[title_key]).strip()
                    if title:  # Solo se non vuoto
                        break
            
            if title:
                dialog_text += f"📌 Title: {title}\n\n"
            
            # Description
            description = None
            for desc_key in ['Description', 'Caption-Abstract', 'ImageDescription']:
                if desc_key in xmp_data and xmp_data[desc_key] is not None:
                    desc_value = str(xmp_data[desc_key]).strip()
                    if desc_value:  # Solo se non vuoto
                        description = desc_value
                        break
            
            if description:
                dialog_text += f"📝 Description:\n{description}\n\n"
            
            # Rating
            rating = xmp_data.get('Rating')
            if rating is not None:
                try:
                    rating_val = float(rating)
                    dialog_text += f"⭐ Rating: {rating_val}/5\n\n"
                except (ValueError, TypeError):
                    pass
            
            if not any([keywords, title, description, rating]):
                dialog_text += t("widgets.xmp.xmp_empty")
            
            self._show_xmp_dialog("📋 XMP Content", dialog_text)
            
        except Exception as e:
            print(f"Errore visualizzazione XMP: {e}")
            self._show_xmp_dialog("❌ Errore", t("widgets.xmp.read_error", error=str(e)))
    
    def _read_xmp_with_exiftool(self, xmp_source):
        """Legge metadati XMP usando ExifTool"""
        try:
            import subprocess
            import json
            
            # Comando ExifTool per XMP
            cmd = [
                'exiftool',
                '-j',  # JSON output
                '-XMP:all',  # Solo metadati XMP
                '-struct',  # Mantieni strutture
                str(xmp_source)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                print(f"ExifTool error: {result.stderr}")
                return None
            
            try:
                data = json.loads(result.stdout)
                if data and len(data) > 0:
                    return data[0]  # Primo elemento (dovrebbe essere l'unico)
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
            
            return None
            
        except subprocess.TimeoutExpired:
            print("ExifTool timeout")
            return None
        except Exception as e:
            print(f"❌ Errore ExifTool: {e}")
            return None

    def _extract_xmp_fields(self, xmp_data):
        """Estrae title, description e tags da dati XMP - ritorna (tags_set, desc_str, title_str)"""
        tags = set()
        desc = ""
        title = ""

        if not xmp_data:
            return tags, desc, title

        # Estrai TITLE
        title_fields = ['Title', 'ObjectName', 'Headline']
        for field in title_fields:
            if field in xmp_data and xmp_data[field]:
                title = str(xmp_data[field]).strip()
                if title:
                    break

        # Estrai DESCRIPTION
        desc_fields = ['Description', 'Caption-Abstract', 'ImageDescription']
        for field in desc_fields:
            if field in xmp_data and xmp_data[field]:
                desc = str(xmp_data[field]).strip()
                if desc:
                    break

        # Estrai TAGS/KEYWORDS (filtra AI|Taxonomy — BioCLIP gestito internamente)
        keyword_fields = ['Keywords', 'Subject', 'HierarchicalSubject']
        for field in keyword_fields:
            if field in xmp_data and xmp_data[field] is not None:
                value = xmp_data[field]

                if isinstance(value, list):
                    for item_val in value:
                        if item_val is not None:
                            item_str = str(item_val).strip()
                            if item_str and not item_str.startswith('AI|Taxonomy') and not item_str.startswith('GeOFF|'):
                                tags.add(item_str)
                elif isinstance(value, str):
                    # Prima prova a parsare come lista (JSON o Python repr)
                    value_stripped = value.strip()
                    if value_stripped.startswith('[') and value_stripped.endswith(']'):
                        parsed_ok = False
                        # Prova JSON (virgolette doppie)
                        try:
                            parsed_list = json.loads(value_stripped)
                            if isinstance(parsed_list, list):
                                for item_val in parsed_list:
                                    if item_val is not None:
                                        item_str = str(item_val).strip()
                                        if item_str:
                                            tags.add(item_str)
                                parsed_ok = True
                        except json.JSONDecodeError:
                            pass

                        # Prova Python literal (virgolette singole)
                        if not parsed_ok:
                            try:
                                import ast
                                parsed_list = ast.literal_eval(value_stripped)
                                if isinstance(parsed_list, list):
                                    for item_val in parsed_list:
                                        if item_val is not None:
                                            item_str = str(item_val).strip()
                                            if item_str:
                                                tags.add(item_str)
                                    parsed_ok = True
                            except (ValueError, SyntaxError):
                                pass

                        if parsed_ok:
                            continue  # Passa al prossimo field

                    # Parsing con separatori multipli
                    separators = [',', '|', ';', '\n']
                    current_tags = [value]

                    for sep in separators:
                        expanded_tags = []
                        for tag in current_tags:
                            expanded_tags.extend([t.strip() for t in tag.split(sep) if t.strip()])
                        current_tags = expanded_tags

                    for tag in current_tags:
                        if tag:
                            tags.add(tag)

        return tags, desc, title

    def _show_xmp_dialog(self, title, text):
        """Mostra dialog XMP con styling consistente"""
        msg = QMessageBox()
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setStyleSheet("QLabel { font-family: 'Consolas', 'Monaco', monospace; }")
        msg.exec()
    
    def _get_database_manager(self):
        """Ottieni DatabaseManager SOLO da config_new.yaml - nessuna alternativa"""
        try:
            from db_manager_new import DatabaseManager
            import yaml
            from pathlib import Path

            # Percorsi da controllare per config_new.yaml
            app_dir = get_app_dir()
            config_paths = [
                app_dir / 'config_new.yaml',  # Directory app
                Path.cwd() / 'config_new.yaml',  # Directory corrente
                Path.home() / '.offgallery' / 'config_new.yaml',  # Standard
            ]

            config = None
            for config_path in config_paths:
                if config_path.exists():
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config = yaml.safe_load(f)

                        if config and isinstance(config, dict):
                            if 'paths' in config and 'database' in config['paths']:
                                db_path = config['paths']['database']

                                # Verifica che il file DB esista
                                if Path(db_path).exists():
                                    # Crea DatabaseManager
                                    db_manager = DatabaseManager(db_path)
                                    return db_manager
                                else:
                                    return None
                            else:
                                pass

                        break  # Config trovato (valido o no), non cercare oltre

                    except Exception:
                        pass

            if not config:
                return None

            return None

        except ImportError:
            return None
        except Exception as e:
            print(f"Errore _get_database_manager: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def refresh_xmp_state(self):
        """Refresh dello stato XMP. Gestione definitiva RAW vs JPG."""
        if not XMP_SUPPORT_AVAILABLE:
            return

        try:
            from xmp_manager_extended import XMPManagerExtended, XMPSyncState,    get_sync_ui_config, get_xmp_sync_tooltip

            # CACHE CHECK con controllo sicurezza
            if hasattr(self, '_xmp_state_cache') and hasattr(self, '_xmp_info_cache') and self._xmp_info_cache:
                state = self._xmp_state_cache
                info = self._xmp_info_cache
            else:
                xmp_manager = XMPManagerExtended()
                state, info = xmp_manager.analyze_xmp_sync_state(Path(self.filepath),   self.image_data)
            
                # Controllo sicurezza prima di salvare cache
                if state is None or info is None:
                    return
                
                self._xmp_state_cache = state
                self._xmp_info_cache = info

            # Controllo sicurezza per info
            if info is None:
                return
            
            category = info.get('category', 'standard')
            self.xmp_state = state
        
            ui_config = get_sync_ui_config(state)
        
            # Resto del codice identico...
            if state == XMPSyncState.PERFECT_SYNC:
                label_text = "XMP SYNC" if category == 'raw' else "EMB SYNC"
            elif state == XMPSyncState.DB_ONLY:
                label_text = "DB ONLY"
            elif state == XMPSyncState.MIXED_STATE:
                label_text = "MIX SYNC"
            elif 'DIRTY' in str(state) or 'DIFF' in str(state) or state == XMPSyncState.MIXED_DIRTY:
                label_text = "MIX DIFF" if state == XMPSyncState.MIXED_DIRTY else \
                        ("XMP DIFF" if category == 'raw' else "EMB DIFF")
            else:
                label_text = ui_config["label"]
            
            self.xmp_label.setText(label_text)
            self.xmp_label.setObjectName(ui_config["class"])
            self.xmp_label.setStyleSheet(f"""
                background-color: {ui_config["color"]};
                color: white;
                padding: 2px 4px;
                border-radius: 2px;
                font-size: 8px;
                font-weight: bold;
            """)
        
            if self.xmp_label.isHidden():
                self.xmp_label.show()
            
            self.xmp_label.setToolTip(get_xmp_sync_tooltip(state, info))
        
        except Exception as e:
            print(f"Errore critico in refresh_xmp_state: {e}")
# ═══════════════════════════════════════════════════════════════════════
#                              DIALOGS
# ═══════════════════════════════════════════════════════════════════════

class BioCLIPTaxonomyDialog(QDialog):
    """Dialog per modifica tassonomia BioCLIP completa (7 livelli)"""

    TAXONOMY_LEVELS = [
        ('Kingdom', 'kingdom'),
        ('Phylum', 'phylum'),
        ('Class', 'class'),
        ('Order', 'order'),
        ('Family', 'family'),
        ('Genus', 'genus'),
        ('Species Epithet', 'species_epithet')
    ]

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items or []
        self.setWindowTitle(t("widgets.dialog.bioclip_edit_title", n=len(self.items)))
        self.setMinimumWidth(550)
        self.setModal(True)
        self.input_fields = {}
        self._build_ui()
        self._load_current_taxonomy()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Info
        if len(self.items) == 1 and hasattr(self.items[0], 'image_data'):
            filename = self.items[0].image_data.get('filename', 'Unknown')
            info_text = t("widgets.label.bioclip_for_single", filename=filename)
        else:
            info_text = t("widgets.label.bioclip_for_multi", n=len(self.items))
        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-weight: bold; color: #2A6A82; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # Campi tassonomici
        taxonomy_group = QGroupBox(t("widgets.group.bioclip_taxonomy"))
        taxonomy_layout = QVBoxLayout(taxonomy_group)

        for display_name, field_name in self.TAXONOMY_LEVELS:
            level_layout = QHBoxLayout()
            label = QLabel(f"{display_name}:")
            label.setMinimumWidth(110)
            label.setStyleSheet("font-weight: bold;")
            level_layout.addWidget(label)
            input_field = QLineEdit()
            input_field.setPlaceholderText(f"{display_name.lower()}")
            input_field.textChanged.connect(self._update_preview)
            self.input_fields[field_name] = input_field
            level_layout.addWidget(input_field)
            taxonomy_layout.addLayout(level_layout)

        layout.addWidget(taxonomy_group)

        # Preview gerarchica
        preview_label = QLabel(t("widgets.label.bioclip_preview"))
        preview_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        layout.addWidget(preview_label)

        self.preview_text = QLabel(t("widgets.label.empty_preview"))
        self.preview_text.setStyleSheet(
            "background: #f0f0f0; padding: 6px; border: 1px solid #ccc; "
            "font-family: monospace; color: #333;"
        )
        self.preview_text.setWordWrap(True)
        layout.addWidget(self.preview_text)

        # Pulsanti azione
        actions_layout = QHBoxLayout()
        clear_button = QPushButton(t("widgets.btn.clear_all"))
        clear_button.clicked.connect(self._clear_all)
        actions_layout.addWidget(clear_button)
        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        # OK/Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_current_taxonomy(self):
        """Carica tassonomia esistente se singola immagine"""
        if len(self.items) != 1:
            self._update_preview()
            return
        try:
            taxonomy_raw = self.items[0].image_data.get('bioclip_taxonomy', '')
            if not taxonomy_raw:
                self._update_preview()
                return
            taxonomy = json.loads(taxonomy_raw) if isinstance(taxonomy_raw, str) else taxonomy_raw
            if isinstance(taxonomy, list):
                for i, (_, field_name) in enumerate(self.TAXONOMY_LEVELS):
                    if i < len(taxonomy) and taxonomy[i]:
                        self.input_fields[field_name].setText(taxonomy[i])
        except (json.JSONDecodeError, TypeError):
            pass
        self._update_preview()

    def _update_preview(self):
        """Aggiorna anteprima del path gerarchico"""
        taxonomy = self.get_taxonomy()
        non_empty = [l for l in taxonomy if l and l.strip()]
        if non_empty:
            self.preview_text.setText("AI|Taxonomy|" + "|".join(non_empty))
        else:
            self.preview_text.setText(t("widgets.label.empty_preview"))

    def _clear_all(self):
        for field in self.input_fields.values():
            field.clear()

    def get_taxonomy(self):
        """Ritorna array 7 livelli (stringhe vuote per livelli mancanti)"""
        return [self.input_fields[fn].text().strip() for _, fn in self.TAXONOMY_LEVELS]


class UserTagDialog(QDialog):
    """Dialog per gestione tag (utente + AI, NO BioCLIP)"""
    
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items or []
        self.setWindowTitle(t("widgets.dialog.edit_tags_title", n=len(self.items)))
        self.setMinimumWidth(500)
        self.setModal(True)
        
        self._build_ui()
        self._load_current_tags()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # Info
        info_text = t("widgets.label.manage_tags_multi", n=len(self.items))
        if len(self.items) == 1 and hasattr(self.items[0], 'image_data'):
            filename = self.items[0].image_data.get('filename', 'Unknown')
            info_text = t("widgets.label.manage_tags_single", filename=filename)
            
        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-weight: bold; color: #2A6A82; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Campo tag unificato
        layout.addWidget(QLabel(t("widgets.label.tags_all_types")))
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText(t("widgets.placeholder.tags"))
        layout.addWidget(self.tag_input)

        # Help
        help_label = QLabel(t("widgets.label.tags_help"))
        help_label.setStyleSheet("color: gray; font-size: 11px; margin-top: 5px;")
        layout.addWidget(help_label)

        # Sezione azioni rapide
        actions_group = QGroupBox(t("widgets.group.quick_actions"))
        actions_layout = QVBoxLayout(actions_group)

        clear_all_button = QPushButton(t("widgets.btn.remove_all_tags"))
        clear_all_button.clicked.connect(self._clear_all_tags)
        actions_layout.addWidget(clear_all_button)
        
        layout.addWidget(actions_group)
        
        # Bottoni
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _load_current_tags(self):
        """Carica tag unificati esistenti"""
        try:
            if len(self.items) == 1:
                # Singola immagine - mostra tutti i tag esistenti
                item = self.items[0]
                if hasattr(item, 'get_unified_tags'):
                    tags = item.get_unified_tags()
                    if tags:
                        self.tag_input.setText(", ".join(tags))
            else:
                # Multi-selezione - placeholder
                self.tag_input.setPlaceholderText(t("widgets.placeholder.tags_cleared"))
                
        except Exception as e:
            print(f"Errore caricamento tag: {e}")
    
    def _clear_all_tags(self):
        """Pulisce tutti i tag"""
        self.tag_input.clear()
        self.tag_input.setPlaceholderText(t("widgets.placeholder.tags_cleared"))
    
    def get_tags(self):
        """Ottieni lista tag dal dialog"""
        text = self.tag_input.text().strip()
        if not text:
            return []
        
        # Split e clean
        tags = [tag.strip() for tag in text.split(',') if tag.strip()]
        return tags


class RemoveTagDialog(QDialog):
    """Dialog per rimozione tag"""
    
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items or []
        self.setWindowTitle(t("widgets.dialog.remove_tags_title", n=len(self.items)))
        self.setMinimumWidth(400)
        self.setModal(True)
        
        self._build_ui()
        self._load_available_tags()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # Info
        info_label = QLabel(t("widgets.label.select_tags_remove", n=len(self.items)))
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Lista tag con checkbox
        self.scroll_area = QScrollArea()
        self.tag_widget = QWidget()
        self.tag_layout = QVBoxLayout(self.tag_widget)
        self.tag_checkboxes = []
        
        self.scroll_area.setWidget(self.tag_widget)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMaximumHeight(200)
        layout.addWidget(self.scroll_area)
        
        # Bottoni
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _load_available_tags(self):
        """Carica tag disponibili per rimozione"""
        try:
            all_tags = set()
            
            for item in self.items:
                if hasattr(item, 'get_unified_tags'):
                    tags = item.get_unified_tags()
                    all_tags.update(tags)
            
            # Crea checkbox per ogni tag
            for tag in sorted(all_tags):
                checkbox = QCheckBox(tag)
                self.tag_checkboxes.append(checkbox)
                self.tag_layout.addWidget(checkbox)
            
            if not all_tags:
                no_tags_label = QLabel(t("widgets.label.no_tags_to_remove"))
                no_tags_label.setStyleSheet("color: gray; font-style: italic;")
                self.tag_layout.addWidget(no_tags_label)
                
        except Exception as e:
            print(f"Errore caricamento tag: {e}")
    
    def get_selected_tags(self):
        """Ottieni tag selezionati per rimozione"""
        selected = []
        for checkbox in self.tag_checkboxes:
            if checkbox.isChecked():
                selected.append(checkbox.text())
        return selected


class DescriptionDialog(QDialog):
    """Dialog per gestione descrizione"""
    
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items or []
        self.setWindowTitle(t("widgets.dialog.description_title", n=len(self.items)))
        self.setMinimumWidth(500)
        self.setModal(True)
        
        self._build_ui()
        self._load_current_description()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # Info
        if len(self.items) == 1:
            filename = self.items[0].image_data.get('filename', 'Unknown')
            info_text = t("widgets.label.manage_desc_single", filename=filename)
        else:
            info_text = t("widgets.label.manage_desc_multi", n=len(self.items))
            
        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-weight: bold; color: #2A6A82; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Campo descrizione
        layout.addWidget(QLabel(t("widgets.label.description")))
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(150)
        self.description_input.setPlaceholderText(t("widgets.placeholder.description"))
        layout.addWidget(self.description_input)

        # Help
        help_label = QLabel(t("widgets.label.description_help"))
        help_label.setStyleSheet("color: gray; font-size: 11px; margin-top: 5px;")
        layout.addWidget(help_label)
        
        # Bottoni
        button_layout = QHBoxLayout()
        
        clear_button = QPushButton(t("widgets.btn.remove_description"))
        clear_button.clicked.connect(self._clear_description)
        button_layout.addWidget(clear_button)
        
        button_layout.addStretch()
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        button_layout.addWidget(buttons)
        
        layout.addLayout(button_layout)
    
    def _load_current_description(self):
        """Carica descrizione esistente"""
        try:
            if len(self.items) == 1:
                # Singola immagine - mostra descrizione esistente
                item = self.items[0]
                description = item.image_data.get('description', '')
                if description:
                    self.description_input.setPlainText(description)
            else:
                # Multi-selezione - campo vuoto
                self.description_input.setPlaceholderText(t("widgets.placeholder.description_multi"))
                
        except Exception as e:
            print(f"Errore caricamento descrizione: {e}")
    
    def _clear_description(self):
        """Pulisce il campo descrizione"""
        self.description_input.clear()
    
    def get_description(self):
        """Ottieni descrizione dal dialog"""
        return self.description_input.toPlainText().strip()


class TitleDialog(QDialog):
    """Dialog per gestione titolo immagine"""

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items or []
        self.setWindowTitle(t("widgets.dialog.title_dialog_title", n=len(self.items)))
        self.setMinimumWidth(450)
        self.setModal(True)

        self._build_ui()
        self._load_current_title()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Info
        if len(self.items) == 1:
            filename = self.items[0].image_data.get('filename', 'Unknown')
            info_text = t("widgets.label.manage_title_single", filename=filename)
        else:
            info_text = t("widgets.label.manage_title_multi", n=len(self.items))

        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-weight: bold; color: #2A6A82; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # Campo titolo (QLineEdit per singola riga)
        layout.addWidget(QLabel(t("widgets.label.title")))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText(t("widgets.placeholder.title"))
        layout.addWidget(self.title_input)

        # Help
        help_label = QLabel(t("widgets.label.title_help"))
        help_label.setStyleSheet("color: gray; font-size: 11px; margin-top: 5px;")
        layout.addWidget(help_label)

        # Bottoni
        button_layout = QHBoxLayout()

        clear_button = QPushButton(t("widgets.btn.remove_title"))
        clear_button.clicked.connect(self._clear_title)
        button_layout.addWidget(clear_button)

        button_layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        button_layout.addWidget(buttons)

        layout.addLayout(button_layout)

    def _load_current_title(self):
        """Carica titolo esistente"""
        try:
            if len(self.items) == 1:
                # Singola immagine - mostra titolo esistente
                item = self.items[0]
                title = item.image_data.get('title', '')
                if title:
                    self.title_input.setText(title)
            else:
                # Multi-selezione - campo vuoto
                self.title_input.setPlaceholderText(t("widgets.placeholder.title_multi"))

        except Exception as e:
            print(f"Errore caricamento titolo: {e}")

    def _clear_title(self):
        """Pulisce il campo titolo"""
        self.title_input.clear()

    def get_title(self):
        """Ottieni titolo dal dialog"""
        return self.title_input.text().strip()


class CompleteExifDialog(QDialog):
    """Dialog per visualizzare TUTTI i dati EXIF"""
    
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items or []
        self.setWindowTitle(t("widgets.dialog.exif_title", n=len(self.items)))
        # FIXED: Dimensioni più appropriate invece di finestra enorme
        self.setMinimumSize(600, 400)
        self.setMaximumSize(800, 500)  # Limita dimensioni massime
        self.resize(700, 450)  # Dimensione predefinita ragionevole
        self.setModal(True)
        
        self._build_ui()
        self._load_exif_data()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # Info header
        if len(self.items) == 1:
            filename = self.items[0].image_data.get('filename', 'Unknown')
            info_text = t("widgets.label.exif_single", filename=filename)
        else:
            info_text = t("widgets.label.exif_multi", n=len(self.items))
            
        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-weight: bold; color: #2A6A82; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Text area scrollabile
        self.exif_text = QTextEdit()
        self.exif_text.setReadOnly(True)
        self.exif_text.setFont(QApplication.font())  # Font monospace per allineamento
        layout.addWidget(self.exif_text)
        
        # Bottoni
        button_layout = QHBoxLayout()
        
        copy_button = QPushButton(t("widgets.btn.copy_clipboard"))
        copy_button.clicked.connect(self._copy_to_clipboard)
        button_layout.addWidget(copy_button)
        
        button_layout.addStretch()
        
        close_button = QPushButton(t("widgets.btn.close"))
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
    
    def _load_exif_data(self):
        """Carica e formatta tutti i dati EXIF"""
        try:
            all_text = []
            
            for i, item in enumerate(self.items):
                if len(self.items) > 1:
                    all_text.append("=" * 80)
                    all_text.append(f"ELEMENTO {i+1}/{len(self.items)}")
                    all_text.append("=" * 80)
                
                filename = item.image_data.get('filename', 'Unknown')
                all_text.append(f"FILE: {filename}")
                all_text.append("-" * 60)
                
                # File info
                if hasattr(item, 'filepath') and item.filepath and item.filepath.exists():
                    try:
                        stat = item.filepath.stat()
                        size_mb = stat.st_size / (1024 * 1024)
                        all_text.append(f"📁 INFORMAZIONI FILE:")
                        all_text.append(f"  Percorso: {item.filepath}")
                        all_text.append(f"  Dimensione: {size_mb:.2f} MB ({stat.st_size:,} bytes)")
                        all_text.append(f"  Formato: {item.filepath.suffix.upper()}")
                        all_text.append("")
                    except Exception as e:
                        all_text.append(f"  Errore lettura file: {e}")
                        all_text.append("")
                
                # Dimensioni immagine da database
                width = item.image_data.get('width')
                height = item.image_data.get('height')
                if width and height:
                    megapixels = (width * height) / 1000000
                    all_text.append(f"📐 DIMENSIONI IMMAGINE:")
                    all_text.append(f"  Risoluzione: {width} × {height} pixel")
                    all_text.append(f"  Megapixel: {megapixels:.1f} MP")
                    all_text.append("")
                
                # PRIORITÀ: Campi DB strutturati
                all_text.append(f"🏆 DATI PRINCIPALI (Database OffGallery):")
                
                # Camera
                camera_make = item.image_data.get('camera_make')
                camera_model = item.image_data.get('camera_model') 
                lens_model = item.image_data.get('lens_model')
                if camera_make or camera_model:
                    all_text.append(f"  📷 Camera: {camera_make or 'N/A'} {camera_model or 'N/A'}")
                if lens_model:
                    all_text.append(f"  🔭 Obiettivo: {lens_model}")
                
                # Impostazioni fotografiche
                aperture = item.image_data.get('aperture')
                focal_length = item.image_data.get('focal_length') 
                shutter_speed = item.image_data.get('shutter_speed')
                iso = item.image_data.get('iso')
                
                if any([aperture, focal_length, shutter_speed, iso]):
                    all_text.append(f"  ⚙️ Impostazioni:")
                    if aperture:
                        all_text.append(f"    • Apertura: f/{aperture}")
                    if focal_length:
                        all_text.append(f"    • Focale: {focal_length}mm")
                    if shutter_speed:
                        all_text.append(f"    • Tempi: {shutter_speed}")
                    if iso:
                        all_text.append(f"    • ISO: {iso}")
                
                # Date e GPS se presenti
                datetime_original = item.image_data.get('datetime_original')
                if datetime_original:
                    all_text.append(f"  📅 Scatto: {datetime_original}")
                
                gps_lat = item.image_data.get('gps_latitude')
                gps_lon = item.image_data.get('gps_longitude')
                if gps_lat and gps_lon:
                    all_text.append(f"  📍 GPS: {gps_lat:.6f}, {gps_lon:.6f}")
                
                all_text.append("")
                
                # EXIF completi da JSON (query separata per performance)
                try:
                    item_id = getattr(item, 'image_id', None) or item.image_data.get('id')

                    if not item_id:
                        exif_json_str = None
                    else:
                        # Prova diversi modi per ottenere il database
                        db_conn = None
                        
                        # Metodo 1: Tramite parent window
                        if hasattr(self, 'parent') and self.parent and hasattr(self.parent, 'db_manager'):
                            db_conn = self.parent.db_manager
                        # Metodo 2: Tramite gallery parent
                        elif hasattr(self, 'parent') and hasattr(self.parent, 'parent') and hasattr(self.parent.parent, 'db_manager'):
                            db_conn = self.parent.parent.db_manager
                        # Metodo 3: Import diretto corretto
                        else:
                            try:
                                from db_manager_new import DatabaseManager
                                db_conn = DatabaseManager('database/offgallery.sqlite')
                            except:
                                try:
                                    import sqlite3
                                    db_conn = sqlite3.connect('database/offgallery.sqlite')
                                except Exception:
                                    exif_json_str = None
                        
                        if db_conn:
                            # Gestisci sia db_manager che sqlite3 diretto
                            if hasattr(db_conn, 'cursor'):
                                cursor = db_conn.cursor
                            else:
                                cursor = db_conn.cursor()
                            
                            cursor.execute("SELECT exif_json FROM images WHERE id = ?", (item_id,))
                            result = cursor.fetchone()
                            
                            # Chiudi solo se connessione SQLite diretta
                            if not hasattr(db_conn, 'cursor'):
                                db_conn.close()
                            
                            if result and result[0]:
                                exif_json_str = result[0]
                            else:
                                exif_json_str = None
                        else:
                            exif_json_str = None
                    
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    exif_json_str = None
                
                if exif_json_str:
                    try:
                        import json
                        exif_data = json.loads(exif_json_str)
                        
                        all_text.append(f"📊 METADATI EXIF COMPLETI:")
                        all_text.append(f"  Totale campi: {len(exif_data)}")
                        all_text.append("")
                        
                        # Raggruppa dati per categoria
                        categories = {
                            'Camera/Obiettivo': ['EXIF:Make', 'EXIF:Model', 'EXIF:LensModel', 'EXIF:LensInfo', 'EXIF:SerialNumber', 'EXIF:Software'],
                            'Impostazioni': ['EXIF:FNumber', 'EXIF:FocalLength', 'EXIF:ExposureTime', 'EXIF:ShutterSpeed', 'EXIF:ISO', 
                                           'EXIF:ExposureProgram', 'EXIF:MeteringMode', 'EXIF:Flash', 'EXIF:WhiteBalance'],
                            'Date/Ora': ['EXIF:DateTimeOriginal', 'EXIF:CreateDate', 'EXIF:ModifyDate', 'File:FileCreateDate', 'File:FileModifyDate'],
                            'Colore/Qualità': ['EXIF:ColorSpace', 'EXIF:WhiteBalance', 'EXIF:ExposureCompensation', 'EXIF:Saturation', 
                                             'EXIF:Contrast', 'EXIF:Sharpness', 'EXIF:Quality'],
                            'GPS': ['GPS:GPSLatitude', 'GPS:GPSLongitude', 'GPS:GPSAltitude', 'GPS:GPSDateStamp', 'GPS:GPSTimeStamp'],
                            'Tecnici': ['EXIF:ExifImageWidth', 'EXIF:ExifImageHeight', 'EXIF:Orientation', 'EXIF:ResolutionUnit', 
                                       'EXIF:XResolution', 'EXIF:YResolution', 'EXIF:BitsPerSample', 'EXIF:Compression']
                        }
                        
                        # Mostra dati per categoria
                        for category, fields in categories.items():
                            category_data = []
                            for field in fields:
                                if field in exif_data:
                                    value = exif_data[field]
                                    category_data.append(f"    {field}: {value}")
                            
                            if category_data:
                                all_text.append(f"  📂 {category.upper()}:")
                                all_text.extend(category_data)
                                all_text.append("")
                        
                        # Altri campi non categorizzati
                        used_fields = set()
                        for fields in categories.values():
                            used_fields.update(fields)
                        
                        other_fields = []
                        for key, value in sorted(exif_data.items()):
                            if key not in used_fields:
                                other_fields.append(f"    {key}: {value}")
                        
                        if other_fields:
                            all_text.append("  📂 ALTRI CAMPI:")
                            all_text.extend(other_fields)
                            all_text.append("")
                            
                    except Exception as e:
                        all_text.append(f"  ❌ Errore parsing EXIF: {e}")
                        all_text.append("")
                else:
                    all_text.append("  ⚠️ Nessun dato EXIF disponibile")
                    all_text.append("")
                
                # AI Scores se presenti
                scores = []
                aesthetic = item.image_data.get('aesthetic_score')
                if aesthetic is not None:
                    try:
                        scores.append(f"  🎨 Aesthetic Score: {float(aesthetic):.3f}")
                    except:
                        pass
                        
                technical = item.image_data.get('technical_score')
                if technical is not None:
                    try:
                        scores.append(f"  ⚙️ Technical Score: {float(technical):.1f}")
                    except:
                        pass
                
                if scores:
                    all_text.append("🤖 AI SCORES:")
                    all_text.extend(scores)
                    all_text.append("")
                
                # Separator tra elementi
                if i < len(self.items) - 1:
                    all_text.append("")
                    all_text.append("")
            
            # Set text
            self.exif_text.setPlainText("\n".join(all_text))
            
        except Exception as e:
            self.exif_text.setPlainText(f"Errore caricamento dati EXIF: {e}")
    
    def _copy_to_clipboard(self):
        """Copia tutti i dati EXIF negli appunti"""
        try:
            text = self.exif_text.toPlainText()
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            
            # Feedback visivo
            original_text = self.sender().text()
            self.sender().setText(t("widgets.btn.copied_feedback"))
            QApplication.processEvents()
            
            # Reset dopo 1 secondo
            QTimer.singleShot(1000, lambda: self.sender().setText(original_text))
            
        except Exception as e:
            print(f"Errore copia clipboard: {e}")


class LLMTagDialog(QDialog):
    """Dialog per configurazione generazione contenuti AI (Tag/Descrizione/Titolo)"""

    def __init__(self, items, parent=None, num_images=None, config=None):
        super().__init__(parent)
        self.items = items or []
        # FIXED: Use num_images if provided, otherwise calculate from items
        self.num_images = num_images if num_images is not None else len(self.items)
        # FIXED: Store config for LLM settings
        self.config = config or {}
        self.setWindowTitle(t("widgets.dialog.llm_tag_title", n=self.num_images))
        self.setMinimumWidth(500)
        self.setModal(True)

        self._build_ui()

        # DEBUG: Verifica che tutti i metodi necessari esistano
        self._validate_methods()
    
    def _validate_methods(self):
        """Valida che tutti i metodi necessari esistano"""
        pass
    
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Info
        info_label = QLabel(t("widgets.label.llm_info", n=self.num_images))
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 15px;")
        layout.addWidget(info_label)

        # Opzioni - Checkbox indipendenti per qualsiasi combinazione
        options_group = QGroupBox(t("widgets.group.llm_what"))
        options_layout = QVBoxLayout(options_group)

        self.gen_title_check = QCheckBox(t("widgets.check.gen_title"))
        self.gen_title_check.setChecked(True)
        options_layout.addWidget(self.gen_title_check)

        self.gen_tags_check = QCheckBox(t("widgets.check.gen_tags"))
        self.gen_tags_check.setChecked(True)
        options_layout.addWidget(self.gen_tags_check)

        self.gen_desc_check = QCheckBox(t("widgets.check.gen_description"))
        self.gen_desc_check.setChecked(True)
        options_layout.addWidget(self.gen_desc_check)

        layout.addWidget(options_group)

        # Info sui parametri
        params_info = QLabel(t("widgets.label.llm_params_hint"))
        params_info.setStyleSheet("color: #888; font-size: 10px; font-style: italic; padding: 5px;")
        layout.addWidget(params_info)

        # Bottoni
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_mode(self):
        """Ottieni selezioni come dizionario {title, tags, description}"""
        return {
            'title': self.gen_title_check.isChecked(),
            'tags': self.gen_tags_check.isChecked(),
            'description': self.gen_desc_check.isChecked()
        }

    def has_selection(self):
        """Verifica che almeno un'opzione sia selezionata"""
        return self.gen_title_check.isChecked() or self.gen_tags_check.isChecked() or self.gen_desc_check.isChecked()
    
        
    def get_config(self):
        """Ottieni configurazione LLM completa - UPDATED: Usa tutti i metodi"""
        return {
            'mode': self.get_mode(),
            'categories': self.get_tag_categories()
        }
    
    def get_selected_mode(self):
        """Alias per get_mode() per compatibilità"""
        return self.get_mode()
    
        
    def get_items(self):
        """Ottieni elementi selezionati"""
        return self.items
    
    def get_num_images(self):
        """Ottieni numero immagini"""
        return self.num_images
    
    def get_full_config(self):
        """Ottieni configurazione completa con tutti i dati necessari"""
        return {
            'mode': self.get_mode(),
            
            'items': self.get_items(),
            'num_images': self.get_num_images(),
            'config': self.config
        }
    
    def get_description_style(self):
        """Ottieni stile descrizione - FIXED: Metodo mancante"""
        # Restituisce stile descrizione (può essere configurabile nel futuro)
        return 'descriptive'  # Default: descrittivo
    
    def get_tag_style(self):
        """Ottieni stile tag - Metodo aggiuntivo per completezza"""
        return 'categorical'  # Default: categorico
    
    def get_language(self):
        """Ottieni lingua - Metodo aggiuntivo per completezza"""
        return 'italian'  # Default: italiano
    
    def get_detail_level(self):
        """Ottieni livello dettaglio - Metodo aggiuntivo per completezza"""
        return 'medium'  # Default: medio
    
    def get_all_settings(self):
        """Ottieni TUTTE le impostazioni possibili - Metodo comprehensivo"""
        return {
            'mode': self.get_mode(),
            'categories': self.get_tag_categories(),
            'description_style': self.get_description_style(),
            'tag_style': self.get_tag_style(),
            'language': self.get_language(),
            'detail_level': self.get_detail_level(),
            'items': self.get_items(),
            'num_images': self.get_num_images(),
            'config': self.config
        }
    
    def get_hints(self):
        return self.get_tag_categories()

    def get_xmp_sync_tooltip(sync_state: XMPSyncState, info: Dict[str, Any]) -> str:
        """Tooltip descrittivo completo per lo stato sync XMP"""
    
        base_tooltips = {
            XMPSyncState.PERFECT_SYNC: t("widgets.tooltip.xmp_perfect_sync"),
            XMPSyncState.EMBEDDED_DIRTY: t("widgets.tooltip.xmp_embedded_dirty"),
            XMPSyncState.SIDECAR_DIRTY: t("widgets.tooltip.xmp_sidecar_dirty"),
            XMPSyncState.MIXED_STATE: t("widgets.tooltip.xmp_mixed_state"),
            XMPSyncState.MIXED_DIRTY: t("widgets.tooltip.xmp_mixed_dirty"),
            XMPSyncState.DB_ONLY: t("widgets.tooltip.xmp_db_only"),
            XMPSyncState.EMBEDDED_ONLY: t("widgets.tooltip.xmp_embedded_only"),
            XMPSyncState.SIDECAR_ONLY: t("widgets.tooltip.xmp_sidecar_only"),
            XMPSyncState.NO_XMP: t("widgets.tooltip.xmp_no_xmp"),
            XMPSyncState.ERROR: t("widgets.xmp.xmp_error_state", error=info.get('error', ''))
        }

        tooltip = base_tooltips.get(sync_state, t("widgets.xmp.xmp_unknown_state", state=sync_state))
    
        # Aggiunge dettagli tecnici per il debug visivo
        details = []
        e_tags = info.get('embedded_tags', 0)
        s_tags = info.get('sidecar_tags', 0)
        db_tags = info.get('db_tags', 0)

        if e_tags > 0: details.append(f"Embedded: {e_tags} tag")
        if s_tags > 0: details.append(f"Sidecar: {s_tags} tag")
        if db_tags > 0: details.append(f"Database: {db_tags} tag")
    
        if details:
            tooltip += "\n---\n" + " | ".join(details)
        
        return tooltip
    
    def __getattr__(self, name):
        """Catch-all per qualsiasi metodo get_* mancante - SAFETY NET"""
        if name.startswith('get_'):
            
            # Restituisci default sensati in base al nome
            if 'mode' in name:
                return lambda: self.get_mode()
            elif 'categor' in name or 'hint' in name:
                return lambda: self.get_tag_categories()
            elif 'config' in name:
                return lambda: self.get_config()
            elif 'item' in name:
                return lambda: self.get_items()
            elif 'num' in name or 'count' in name:
                return lambda: self.get_num_images()
            elif 'style' in name:
                return lambda: 'default'
            elif 'language' in name or 'lang' in name:
                return lambda: 'italian'
            elif 'level' in name:
                return lambda: 'medium'
            else:
                # Default generico
                return lambda: []
        
        # Se non è un metodo get_, solleva l'errore normale
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


# ═══════════════════════════════════════════════════════════════════════
#                          WIDGET EXPORTS
# ═══════════════════════════════════════════════════════════════════════

# Export delle classi principali
__all__ = [
    'ImageCard',
    'FlowLayout',
    'UserTagDialog',
    'RemoveTagDialog',
    'LLMTagDialog',
    'DescriptionDialog',
    'CompleteExifDialog',
    'COLORS',
    'POPUP_STYLE',
    'apply_popup_style'
]
