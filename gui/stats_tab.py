"""
Stats Tab 
Focus: Database health, Gear analysis, Shooting patterns, Metadata quality
Schema: Compatibile con db_manager_new.py (tags unificati, sync_state)
"""

import json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QGridLayout,
    QProgressBar, QSizePolicy, QSpacerItem, QTabWidget
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter

# Palette professionale
COLORS = {
    'grafite': '#2A2A2A',
    'grafite_light': '#3A3A3A',
    'grafite_dark': '#1E1E1E',
    'grigio_chiaro': '#E3E3E3',
    'grigio_medio': '#B0B0B0',
    'blu_petrolio': '#1C4F63',
    'blu_petrolio_light': '#2A6A82',
    'verde': '#4A7C59',
    'verde_light': '#5A8C69',
    'rosso': '#8B4049',
    'ambra': '#C88B2E',
    'viola': '#6A4C93',
    'arancio': '#D2691E',
}

class KPICard(QFrame):
    """Card KPI professionale con trend indicator"""
    def __init__(self, title, value, unit="", icon="📊", color=COLORS['blu_petrolio'], trend=None):
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
        self.setFixedHeight(100)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        
        # Header row
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Icon
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 16px; color: rgba(255,255,255,0.8);")
        
        # Title
        title_label = QLabel(title.upper())
        title_label.setStyleSheet("color: rgba(255,255,255,0.7); font-weight: 600; font-size: 9px; letter-spacing: 0.5px;")
        
        # Trend
        if trend:
            trend_label = QLabel(trend)
            trend_label.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 8px;")
            header_layout.addWidget(trend_label)
        
        header_layout.addWidget(icon_label)
        header_layout.addSpacerItem(QSpacerItem(8, 0))
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Value row
        value_layout = QHBoxLayout()
        value_layout.setContentsMargins(0, 0, 0, 0)
        
        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet("color: white; font-size: 32px; font-weight: 700; line-height: 1;")
        
        if unit:
            unit_label = QLabel(unit)
            unit_label.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 14px; font-weight: 500; margin-left: 4px;")
            value_layout.addWidget(self.value_label)
            value_layout.addWidget(unit_label)
            value_layout.addStretch()
        else:
            value_layout.addWidget(self.value_label)
            value_layout.addStretch()
        
        layout.addLayout(value_layout)
    
    def update_value(self, new_value, unit=""):
        if unit:
            self.value_label.setText(f"{new_value}")
        else:
            self.value_label.setText(str(new_value))

class GearBarChart(QWidget):
    """Bar chart orizzontale per attrezzature con multirighe per scritte lunghe"""
    def __init__(self, data, title="", color=COLORS['ambra'], max_bars=8):
        super().__init__()
        self.data = data  # {label: value} dict
        self.title = title
        self.color = color
        self.max_bars = max_bars
        self.setMinimumHeight(300)
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
        
        # Ordina e limita i dati
        sorted_data = sorted(self.data.items(), key=lambda x: x[1], reverse=True)[:self.max_bars]
        
        if not sorted_data:
            return
            
        max_val = max(item[1] for item in sorted_data)
        
        # Layout orizzontale con più spazio per multirighe
        label_width = 140  # Più spazio per label multiriga
        chart_width = self.width() - label_width - 20
        chart_height = self.height() - 40  # Top/bottom margin
        
        # Calcola altezza di ogni barra (più alta per multirighe)
        bar_height = max(20, (chart_height / len(sorted_data)) - 15)  # Min 20px, spacing 15px
        
        for i, (label, value) in enumerate(sorted_data):
            # Coordinate barra
            y = 20 + i * (bar_height + 15)  # 15px spacing tra barre
            x = label_width + 10
            
            if max_val == 0:
                width = 0
            else:
                width = (value / max_val) * chart_width * 0.8  # Max 80% della larghezza
            
            # Disegna barra orizzontale
            painter.setBrush(QColor(self.color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(x), int(y), int(width), int(bar_height), 4, 4)
            
            # Valore alla fine della barra
            if value > 0:
                painter.setPen(QColor(COLORS['grigio_chiaro']))
                font = painter.font()
                font.setPointSize(10)
                font.setWeight(QFont.Weight.Bold)
                painter.setFont(font)
                value_x = x + width + 5
                painter.drawText(int(value_x), int(y), 50, int(bar_height), 
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(value))
            
            # Label a sinistra con supporto multiriga
            painter.setPen(QColor(COLORS['grigio_medio']))
            font.setPointSize(8)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            
            # Gestione multiriga per label lunghe
            words = label.split(' ')
            lines = []
            
            if len(words) <= 2:
                # Poche parole
                if len(label) > 18:
                    if len(words) == 2:
                        lines = words  # Una parola per riga
                    else:
                        # Singola parola lunga, dividila
                        mid = len(label) // 2
                        lines = [label[:mid], label[mid:]]
                else:
                    lines = [label]
            else:
                # Molte parole, dividi intelligentemente
                if len(words) <= 4:
                    mid = len(words) // 2
                    lines = [' '.join(words[:mid]), ' '.join(words[mid:])]
                else:
                    # 3 righe per nomi molto lunghi
                    third = len(words) // 3
                    lines = [
                        ' '.join(words[:third]),
                        ' '.join(words[third:third*2]),
                        ' '.join(words[third*2:])
                    ]
            
            # Limita a 3 righe e tronca se necessario
            lines = lines[:3]
            for j, line in enumerate(lines):
                if len(line) > 20:
                    lines[j] = line[:20] + "..."
            
            # Disegna multiriga centrata verticalmente
            line_height = 12
            total_text_height = len(lines) * line_height
            start_y = y + (bar_height - total_text_height) // 2
            
            for j, line in enumerate(lines):
                line_y = start_y + j * line_height
                painter.drawText(5, int(line_y), label_width - 10, line_height,
                               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, 
                               line)

class ProBarChart(QWidget):
    """Bar chart orizzontale per tag e altri utilizzi"""
    def __init__(self, data, title="", color=COLORS['ambra'], max_bars=10):
        super().__init__()
        self.data = data  # {label: value} dict
        self.title = title
        self.color = color
        self.max_bars = max_bars
        self.setMinimumHeight(200)
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
        
        # Ordina e limita i dati
        sorted_data = sorted(self.data.items(), key=lambda x: x[1], reverse=True)[:self.max_bars]
        
        if not sorted_data:
            return
            
        max_val = max(item[1] for item in sorted_data)
        
        # Layout orizzontale per tag
        label_width = 120  # Spazio fisso per label a sinistra
        chart_width = self.width() - label_width - 20
        chart_height = self.height() - 40  # Top/bottom margin
        
        # Calcola altezza di ogni barra
        bar_height = chart_height / len(sorted_data) - 10  # 10px spacing tra barre
        
        for i, (label, value) in enumerate(sorted_data):
            # Coordinate barra
            y = 20 + i * (bar_height + 10)
            x = label_width + 10
            
            if max_val == 0:
                width = 0
            else:
                width = (value / max_val) * chart_width * 0.8  # Max 80% della larghezza
            
            # Disegna barra orizzontale
            painter.setBrush(QColor(self.color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(x), int(y), int(width), int(bar_height), 4, 4)
            
            # Valore alla fine della barra
            if value > 0:
                painter.setPen(QColor(COLORS['grigio_chiaro']))
                font = painter.font()
                font.setPointSize(10)
                font.setWeight(QFont.Weight.Bold)
                painter.setFont(font)
                value_x = x + width + 5
                painter.drawText(int(value_x), int(y), 50, int(bar_height), 
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(value))
            
            # Label a sinistra (orizzontale, non verticale per leggibilità)
            painter.setPen(QColor(COLORS['grigio_medio']))
            font.setPointSize(9)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            
            # Tronca label se troppo lunga per lo spazio disponibile
            label_rect = painter.fontMetrics().boundingRect(label)
            if label_rect.width() > label_width - 10:
                # Tronca mantenendo leggibilità
                display_label = label[:15] + "..." if len(label) > 15 else label
            else:
                display_label = label
                
            painter.drawText(5, int(y), label_width - 10, int(bar_height), 
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, 
                           display_label)


class StatsTab(QWidget):
    """Tab statistiche per fotografi professionali e semi-professionali"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.db_manager = None
        
        # Initialize all attributes to prevent AttributeError
        self.db_stats = {}
        self.sync_stats = {}
        self.proc_stats = {}
        self.gear_summary = {}
        self.shooting_patterns = {}
        self.quality_stats = {}
        self.metadata_completeness = {}
        self.geo_stats = {}
        self.file_stats = {}
        
        # Initialize chart references
        self.cameras_chart = None
        self.lenses_chart = None
        self.focal_chart = None
        self.tags_chart = None
        self.timeline_chart = None
        self.aperture_chart = None
        self.shutter_chart = None
        self.iso_chart = None
        
        try:
            self.init_ui()
            print("✅ StatsTab professionale inizializzata")
        except Exception as e:
            print(f"❌ Errore inizializzazione StatsTab: {e}")
            import traceback
            traceback.print_exc()
        
    def init_ui(self):
        """Inizializza UI con layout professionale"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Scroll area principale
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ 
                background-color: {COLORS['grafite']}; 
                border: none; 
            }}
            QScrollBar:vertical {{ 
                background-color: {COLORS['grafite_light']}; 
                width: 8px; 
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{ 
                background-color: {COLORS['blu_petrolio']}; 
                border-radius: 4px; 
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        
        # Widget contenuto principale
        content = QWidget()
        content.setStyleSheet(f"background-color: {COLORS['grafite']};")
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(24)
        
        # Header
        self.create_header(main_layout)
        
        # KPI Dashboard (4 cards principali)
        self.create_kpi_dashboard(main_layout)
        
        # Tab container per sezioni specializzate
        self.create_professional_sections(main_layout)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
    
    def create_header(self, layout):
        """Header con titolo"""
        header_layout = QHBoxLayout()
        
        # Titolo
        title = QLabel("Dashboard Fotografico")
        title.setStyleSheet(f"""
            color: {COLORS['grigio_chiaro']};
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 4px;
        """)
        
        subtitle = QLabel("Analisi database per workflow professionale • Auto-aggiornamento a ogni accesso")
        subtitle.setStyleSheet(f"""
            color: {COLORS['grigio_medio']};
            font-size: 13px;
            font-weight: 400;
        """)
        
        title_container = QVBoxLayout()
        title_container.addWidget(title)
        title_container.addWidget(subtitle)
        title_container.setContentsMargins(0, 0, 0, 0)
        title_container.setSpacing(2)
        
        header_layout.addLayout(title_container)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
    
    def create_kpi_dashboard(self, layout):
        """Dashboard KPI principali"""
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(16)
        
        # Cards principali (3 KPI)
        self.kpi_total = KPICard("Archivio Totale", "0", "", "📁", COLORS['blu_petrolio'])
        self.kpi_processing = KPICard("Processing AI", "0%", "", "🤖", COLORS['viola']) 
        self.kpi_coverage = KPICard("Metadata", "0%", "", "📋", COLORS['ambra'])
        
        kpi_layout.addWidget(self.kpi_total)
        kpi_layout.addWidget(self.kpi_processing)
        kpi_layout.addWidget(self.kpi_coverage)
        
        layout.addLayout(kpi_layout)
    
    def create_professional_sections(self, layout):
        """Crea sezioni professionali in tab"""
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
                padding: 12px 20px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 600;
                font-size: 11px;
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
        
        # Tab 1: Database Health
        self.tab_database = self.create_database_tab()
        self.tab_widget.addTab(self.tab_database, "🗄️ Database")
        
        # Tab 2: Gear Analysis
        self.tab_gear = self.create_gear_tab()
        self.tab_widget.addTab(self.tab_gear, "📸 Attrezzatura")
        
        # Tab 3: Shooting Analytics
        self.tab_shooting = self.create_shooting_tab()
        self.tab_widget.addTab(self.tab_shooting, "📊 Shooting")
        
        # Tab 4: Workflow Stats
        self.tab_workflow = self.create_workflow_tab()
        self.tab_widget.addTab(self.tab_workflow, "⚡ Workflow")
        
        layout.addWidget(self.tab_widget)
    
    def get_groupbox_style(self):
        """Stile consistente per i GroupBox con righe alternate"""
        return f"""
            QGroupBox {{
                font-weight: 600;
                font-size: 12px;
                color: {COLORS['grigio_chiaro']};
                border: 2px solid {COLORS['grafite_dark']};
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: {COLORS['grafite_light']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px 0 8px;
                color: {COLORS['grigio_chiaro']};
                background-color: {COLORS['grafite_light']};
            }}
            QLabel {{
                padding: 4px 8px;
                margin: 1px 0px;
            }}
        """
    
    def create_metric_row(self, label, key, stats_dict, even_row=True):
        """Crea una riga metrica con zebra striping"""
        row_widget = QWidget()
        bg_color = COLORS['grafite_light'] if even_row else COLORS['grafite']
        row_widget.setStyleSheet(f"""
            QWidget {{ 
                background-color: {bg_color}; 
                border-radius: 4px;
                margin: 1px 0px;
            }}
            QLabel {{ 
                background: transparent; 
                padding: 6px 8px;
            }}
        """)
        
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl = QLabel(f"{label}:")
        lbl.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-weight: 500;")
        
        val = QLabel("0")
        val.setStyleSheet(f"color: {COLORS['grigio_chiaro']}; font-weight: 600;")
        stats_dict[key] = val
        
        row_layout.addWidget(lbl)
        row_layout.addStretch()
        row_layout.addWidget(val)
        
        return row_widget
    
    def create_database_tab(self):
        """Tab Database Health & Sync Status"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Grid 2x2
        grid = QGridLayout()
        grid.setSpacing(16)
        
        # Database Summary
        db_group = QGroupBox("📊 Riepilogo Database")
        db_group.setStyleSheet(self.get_groupbox_style())
        db_layout = QVBoxLayout(db_group)
        
        self.db_stats = {}
        db_metrics = [
            ("Total Records", "db_total"),
            ("File Size", "db_size"),
            ("RAW Files", "raw_count"),
            ("Standard Files", "std_count"),
            ("Duplicati (hash)", "duplicates")
        ]
        
        for i, (label, key) in enumerate(db_metrics):
            row = self.create_metric_row(label, key, self.db_stats, i % 2 == 0)
            db_layout.addWidget(row)
        
        # Processing Status
        proc_group = QGroupBox("🤖 Processing AI")
        proc_group.setStyleSheet(self.get_groupbox_style())
        proc_layout = QVBoxLayout(proc_group)
        
        self.proc_stats = {}
        proc_metrics = [
            ("CLIP Embeddings", "clip_done"),
            ("LLM Descriptions", "llm_done"),
            ("Errori Processing", "error_count"),
            ("Avg Processing Time", "avg_time")
        ]
        
        for i, (label, key) in enumerate(proc_metrics):
            row = self.create_metric_row(label, key, self.proc_stats, i % 2 == 0)
            proc_layout.addWidget(row)
        
        # Timeline Distribution
        timeline_group = QGroupBox("📅 Distribuzione Temporale")
        timeline_group.setStyleSheet(self.get_groupbox_style())
        timeline_layout = QVBoxLayout(timeline_group)
        
        self.timeline_chart = ProBarChart({}, "Foto per Anno", COLORS['blu_petrolio'])
        timeline_layout.addWidget(self.timeline_chart)
        
        # Add to grid (2x2 senza sync)
        grid.addWidget(db_group, 0, 0)
        grid.addWidget(proc_group, 0, 1)
        grid.addWidget(timeline_group, 1, 0, 1, 2)  # Timeline spanning 2 columns
        
        layout.addLayout(grid)
        return widget
    
    def create_gear_tab(self):
        """Tab Gear Analysis"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Layout principale: Charts sopra, Summary sotto
        main_layout = QVBoxLayout()
        
        # Row superiore: Charts (3 colonne uguali)
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(16)
        
        # Camera Bodies
        cameras_group = QGroupBox("📷 Fotocamere")
        cameras_group.setStyleSheet(self.get_groupbox_style())
        cameras_layout = QVBoxLayout(cameras_group)
        self.cameras_chart = GearBarChart({}, "Uso per Fotocamera", COLORS['verde'], max_bars=8)
        cameras_layout.addWidget(self.cameras_chart)
        
        # Lenses
        lenses_group = QGroupBox("🔍 Obiettivi")
        lenses_group.setStyleSheet(self.get_groupbox_style())
        lenses_layout = QVBoxLayout(lenses_group)
        self.lenses_chart = GearBarChart({}, "Uso per Obiettivo", COLORS['ambra'], max_bars=8)
        lenses_layout.addWidget(self.lenses_chart)
        
        # Focal Lengths
        focal_group = QGroupBox("📏 Focali")
        focal_group.setStyleSheet(self.get_groupbox_style())
        focal_layout = QVBoxLayout(focal_group)
        self.focal_chart = GearBarChart({}, "Distribuzione Focali", COLORS['viola'], max_bars=8)
        focal_layout.addWidget(self.focal_chart)
        
        charts_layout.addWidget(cameras_group)
        charts_layout.addWidget(lenses_group)
        charts_layout.addWidget(focal_group)
        
        # Summary ultra-compatto orizzontale
        gear_summary_group = QGroupBox("📋 Summary")
        gear_summary_group.setStyleSheet(self.get_groupbox_style())
        gear_summary_group.setMaximumHeight(80)  # Più compatto
        gear_summary_layout = QHBoxLayout(gear_summary_group)
        gear_summary_layout.setSpacing(20)
        
        self.gear_summary = {}
        gear_metrics = [
            ("Fotocamere", "unique_cameras"),
            ("Obiettivi", "unique_lenses"), 
            ("Focale Top", "top_focal"),
            ("Range", "focal_range")
        ]
        
        for i, (label, key) in enumerate(gear_metrics):
            # Container per ogni metrica
            metric_widget = QWidget()
            metric_layout = QVBoxLayout(metric_widget)
            metric_layout.setContentsMargins(0, 0, 0, 0)
            metric_layout.setSpacing(2)
            
            lbl = QLabel(f"{label}")
            lbl.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 9px; font-weight: 500;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            val = QLabel("-")
            val.setStyleSheet(f"color: {COLORS['grigio_chiaro']}; font-weight: 700; font-size: 14px;")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.gear_summary[key] = val
            
            metric_layout.addWidget(lbl)
            metric_layout.addWidget(val)
            gear_summary_layout.addWidget(metric_widget)
        
        main_layout.addLayout(charts_layout)
        main_layout.addWidget(gear_summary_group)
        
        layout.addLayout(main_layout)
        return widget
    
    def create_shooting_tab(self):
        """Tab Shooting Analytics"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Grid 2x2
        grid = QGridLayout()
        grid.setSpacing(16)
        
        # Exposure Settings
        exposure_group = QGroupBox("🎯 Impostazioni Esposizione")
        exposure_group.setStyleSheet(self.get_groupbox_style())
        exposure_layout = QVBoxLayout(exposure_group)
        
        # Sub-charts per esposizione
        sub_grid = QGridLayout()
        
        # Aperture label e chart
        aperture_label = QLabel("Aperture più usate:")
        aperture_label.setStyleSheet(f"color: {COLORS['grigio_chiaro']}; font-weight: 600; margin: 4px;")
        sub_grid.addWidget(aperture_label, 0, 0)
        
        self.aperture_chart = ProBarChart({}, "Aperture", COLORS['verde'], max_bars=6)
        self.aperture_chart.setMinimumHeight(180)
        sub_grid.addWidget(self.aperture_chart, 1, 0)
        
        # Shutter label e chart  
        shutter_label = QLabel("Tempi di scatto:")
        shutter_label.setStyleSheet(f"color: {COLORS['grigio_chiaro']}; font-weight: 600; margin: 4px;")
        sub_grid.addWidget(shutter_label, 0, 1)
        
        self.shutter_chart = ProBarChart({}, "Tempi", COLORS['ambra'], max_bars=6)
        self.shutter_chart.setMinimumHeight(180)
        sub_grid.addWidget(self.shutter_chart, 1, 1)
        
        exposure_layout.addLayout(sub_grid)
        
        # ISO Analysis
        iso_group = QGroupBox("📊 Analisi ISO")
        iso_group.setStyleSheet(self.get_groupbox_style())
        iso_layout = QVBoxLayout(iso_group)
        self.iso_chart = ProBarChart({}, "Distribuzione ISO", COLORS['rosso'])
        iso_layout.addWidget(self.iso_chart)
        
        # Shooting Patterns (solo campi implementabili)
        patterns_group = QGroupBox("📈 Pattern di Scatto")
        patterns_group.setStyleSheet(self.get_groupbox_style())
        patterns_layout = QVBoxLayout(patterns_group)
        
        self.shooting_patterns = {}
        pattern_metrics = [
            ("ISO Range", "iso_range"),
            ("Apertura Preferita", "aperture_preferred"),
            ("Flash Detection", "flash_usage")
        ]
        
        for i, (label, key) in enumerate(pattern_metrics):
            row = self.create_metric_row(label, key, self.shooting_patterns, i % 2 == 0)
            patterns_layout.addWidget(row)
        
        # Quality Metrics (fix B&N)
        quality_group = QGroupBox("⭐ Metriche Qualità")
        quality_group.setStyleSheet(self.get_groupbox_style())
        quality_layout = QVBoxLayout(quality_group)
        
        self.quality_stats = {}
        quality_metrics = [
            ("Rating Medio LR", "avg_rating"),
            ("Foto 4-5 Stelle", "high_rated"),
            ("Con Color Label", "color_labeled"),
            ("Foto GPS", "gps_photos")
        ]
        
        for i, (label, key) in enumerate(quality_metrics):
            row = self.create_metric_row(label, key, self.quality_stats, i % 2 == 0)
            quality_layout.addWidget(row)
        
        grid.addWidget(exposure_group, 0, 0)
        grid.addWidget(iso_group, 0, 1)
        grid.addWidget(patterns_group, 1, 0)
        grid.addWidget(quality_group, 1, 1)
        
        layout.addLayout(grid)
        return widget
    
    def create_workflow_tab(self):
        """Tab Workflow & Metadata"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Grid 2x2
        grid = QGridLayout()
        grid.setSpacing(16)
        
        # Metadata Completeness
        metadata_group = QGroupBox("📝 Completezza Metadata")
        metadata_group.setStyleSheet(self.get_groupbox_style())
        metadata_layout = QVBoxLayout(metadata_group)
        
        self.metadata_completeness = {}
        metadata_metrics = [
            ("Con Titolo", "with_title"),
            ("Con Descrizione", "with_description"),
            ("Con Tags", "with_tags"),
            ("Con Rating LR", "with_rating"),
            ("Con GPS", "with_gps")
        ]
        
        for i, (label, key) in enumerate(metadata_metrics):
            row = self.create_metric_row(label, key, self.metadata_completeness, i % 2 == 0)
            metadata_layout.addWidget(row)
        
        # Tag Analysis
        tags_group = QGroupBox("🏷️ Analisi Tags")
        tags_group.setStyleSheet(self.get_groupbox_style())
        tags_layout = QVBoxLayout(tags_group)
        self.tags_chart = ProBarChart({}, "Tag più usati", COLORS['viola'], max_bars=10)
        self.tags_chart.setMinimumHeight(300)  # Più alto per text wrap sui tag
        tags_layout.addWidget(self.tags_chart)
        
        # Geographic Distribution (semplificato)
        geo_group = QGroupBox("🌍 Distribuzione Geografica")
        geo_group.setStyleSheet(self.get_groupbox_style())
        geo_layout = QVBoxLayout(geo_group)
        
        self.geo_stats = {}
        geo_metrics = [
            ("Paesi Visitati", "countries"),
            ("Città Fotografate", "cities"),
            ("GPS Coverage", "gps_coverage"),
            ("Location Principale", "top_location")
        ]
        
        for i, (label, key) in enumerate(geo_metrics):
            row = self.create_metric_row(label, key, self.geo_stats, i % 2 == 0)
            geo_layout.addWidget(row)
        
        # File Management (semplificato)
        files_group = QGroupBox("📁 Gestione File")
        files_group.setStyleSheet(self.get_groupbox_style())
        files_layout = QVBoxLayout(files_group)
        
        self.file_stats = {}
        file_metrics = [
            ("Dimensione Archivio", "total_size"),
            ("Dimensione Media", "avg_size"),
            ("File RAW", "raw_percentage"),
            ("Formati Unici", "unique_formats")
        ]
        
        for i, (label, key) in enumerate(file_metrics):
            row = self.create_metric_row(label, key, self.file_stats, i % 2 == 0)
            files_layout.addWidget(row)
        
        grid.addWidget(metadata_group, 0, 0)
        grid.addWidget(tags_group, 0, 1)
        grid.addWidget(geo_group, 1, 0)
        grid.addWidget(files_group, 1, 1)
        
        layout.addLayout(grid)
        return widget
    
    def set_database_manager(self, db_manager):
        """Imposta il database manager"""
        print(f"🔧 StatsTab.set_database_manager chiamato con: {db_manager}")
        self.db_manager = db_manager
        if db_manager:
            print("✅ Database manager impostato nella StatsTab")
        else:
            print("❌ Database manager è None")
    
    def refresh_stats(self):
        """Aggiorna tutte le statistiche"""
        try:
            if not self.db_manager:
                print("❌ Database manager non disponibile per refresh")
                return
            
            cursor = self.db_manager.cursor
            print("🔄 Inizio refresh statistiche...")
            
            # Aggiorna KPI principali
            self.update_main_kpis(cursor)
            
            # Aggiorna tab specifici
            self.update_database_stats(cursor)
            self.update_gear_stats(cursor)
            self.update_shooting_stats(cursor)
            self.update_workflow_stats(cursor)
            
            print("✅ Refresh statistiche completato")
            
        except Exception as e:
            print(f"❌ Errore refresh stats: {e}")
            import traceback
            traceback.print_exc()
    
    def update_main_kpis(self, cursor):
        """Aggiorna KPI principali"""
        try:
            # Total images
            cursor.execute("SELECT COUNT(*) FROM images")
            total = cursor.fetchone()[0]
            self.kpi_total.update_value(f"{total:,}")
            
            # AI Processing percentage
            cursor.execute("""
                SELECT COUNT(*) FROM images 
                WHERE embedding_generated = 1 OR llm_generated = 1
            """)
            processed = cursor.fetchone()[0] if total > 0 else 0
            proc_percent = (processed / total * 100) if total > 0 else 0
            self.kpi_processing.update_value(f"{proc_percent:.1f}%")

            
            # Metadata coverage (con almeno tags o descrizione o rating)
            cursor.execute("""
                SELECT COUNT(*) FROM images 
                WHERE (tags IS NOT NULL AND tags != '[]' AND tags != '') 
                   OR (description IS NOT NULL AND description != '') 
                   OR (lr_rating IS NOT NULL AND lr_rating > 0)
            """)
            with_metadata = cursor.fetchone()[0] if total > 0 else 0
            metadata_percent = (with_metadata / total * 100) if total > 0 else 0
            self.kpi_coverage.update_value(f"{metadata_percent:.1f}%")
            
        except Exception as e:
            print(f"❌ Errore update main KPIs: {e}")
    
    def update_database_stats(self, cursor):
        """Aggiorna statistiche database"""
        try:
            # Basic counts
            cursor.execute("SELECT COUNT(*) FROM images")
            total = cursor.fetchone()[0]
            self.db_stats["db_total"].setText(f"{total:,}")
            
            # RAW vs Standard
            cursor.execute("SELECT COUNT(*) FROM images WHERE is_raw = 1")
            raw_count = cursor.fetchone()[0]
            std_count = total - raw_count
            self.db_stats["raw_count"].setText(f"{raw_count:,}")
            self.db_stats["std_count"].setText(f"{std_count:,}")
            
            # File size (approssimativo)
            cursor.execute("SELECT SUM(file_size) FROM images WHERE file_size IS NOT NULL")
            total_size = cursor.fetchone()[0] or 0
            size_gb = total_size / (1024**3)
            self.db_stats["db_size"].setText(f"{size_gb:.1f} GB")
            
            # Fix duplicates: conta file duplicati totali, non gruppi
            cursor.execute("""
                SELECT COUNT(*) FROM images 
                WHERE file_hash IN (
                    SELECT file_hash FROM images 
                    WHERE file_hash IS NOT NULL 
                    GROUP BY file_hash 
                    HAVING COUNT(*) > 1
                )
            """)
            duplicates = cursor.fetchone()[0]
            self.db_stats["duplicates"].setText(str(duplicates))
            
            # Processing stats
            cursor.execute("SELECT COUNT(*) FROM images WHERE embedding_generated = 1")
            clip_done = cursor.fetchone()[0]
            self.proc_stats["clip_done"].setText(f"{clip_done:,}")

            
            cursor.execute("SELECT COUNT(*) FROM images WHERE llm_generated = 1")
            llm_done = cursor.fetchone()[0]
            self.proc_stats["llm_done"].setText(f"{llm_done:,}")
            
            # Fix processing time - debug per capire perché è N/A
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_rows,
                    COUNT(processing_time) as non_null,
                    COUNT(CASE WHEN processing_time > 0 THEN 1 END) as positive,
                    AVG(CASE WHEN processing_time > 0 THEN processing_time END) as avg_time,
                    MIN(CASE WHEN processing_time > 0 THEN processing_time END) as min_time,
                    MAX(CASE WHEN processing_time > 0 THEN processing_time END) as max_time
                FROM images
            """)
            time_stats = cursor.fetchone()
            
            if time_stats[3]:  # Se c'è avg_time
                avg_time = time_stats[3]
                self.proc_stats["avg_time"].setText(f"{avg_time:.1f}s")
                print(f"🕐 Processing: {time_stats[2]}/{time_stats[0]} con tempo, avg={avg_time:.1f}s")
            else:
                self.proc_stats["avg_time"].setText("N/A")
                print(f"🕐 Processing: {time_stats[1]} non-null, {time_stats[2]} positivi su {time_stats[0]} totali")
            
            # Error count
            cursor.execute("SELECT COUNT(*) FROM images WHERE success = 0 OR error_message IS NOT NULL")
            error_count = cursor.fetchone()[0]
            self.proc_stats["error_count"].setText(f"{error_count:,}")
            
            # Timeline con debug dettagliato per capire date mancanti
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(datetime_original) as has_original,
                    COUNT(datetime_modified) as has_modified,
                    COUNT(datetime_digitized) as has_digitized,
                    COUNT(processing_time) as has_processing
                FROM images
            """)
            date_breakdown = cursor.fetchone()
            print(f"🗓️ Date fields: orig={date_breakdown[1]}, mod={date_breakdown[2]}, dig={date_breakdown[3]}, proc={date_breakdown[4]} su {date_breakdown[0]} totali")
            
            # Timeline con più fallback possibili
            cursor.execute("""
                SELECT 
                    COALESCE(
                        strftime('%Y', datetime_original),
                        strftime('%Y', datetime_digitized),
                        strftime('%Y', datetime_modified),
                        strftime('%Y', processed_date),
                        '????'
                    ) as year,
                    COUNT(*) as count
                FROM images 
                GROUP BY year 
                ORDER BY year
            """)
            timeline_results = cursor.fetchall()
            timeline_data = {}
            
            missing_count = 0
            for row in timeline_results:
                year, count = row
                if year == '????':
                    missing_count = count
                    print(f"🗓️ {count} foto senza date valide")
                else:
                    timeline_data[str(year)] = count
                    print(f"🗓️ Anno {year}: {count} foto")
            
            if self.timeline_chart:
                self.timeline_chart.update_data(timeline_data)
            
        except Exception as e:
            print(f"❌ Errore update database stats: {e}")
    
    def update_gear_stats(self, cursor):
        """Aggiorna statistiche attrezzatura"""
        try:
            # Camera distribution
            cursor.execute("""
                SELECT camera_model, COUNT(*) as count
                FROM images 
                WHERE camera_model IS NOT NULL 
                GROUP BY camera_model 
                ORDER BY count DESC
            """)
            cameras_data = {row[0]: row[1] for row in cursor.fetchall()[:8]}
            if self.cameras_chart:
                self.cameras_chart.update_data(cameras_data)
            
            # Lens distribution
            cursor.execute("""
                SELECT lens_model, COUNT(*) as count
                FROM images 
                WHERE lens_model IS NOT NULL 
                GROUP BY lens_model 
                ORDER BY count DESC
            """)
            lenses_data = {row[0]: row[1] for row in cursor.fetchall()[:8]}
            if self.lenses_chart:
                self.lenses_chart.update_data(lenses_data)
            
            # Focal length distribution
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN focal_length < 20 THEN '<20mm'
                        WHEN focal_length < 35 THEN '20-35mm'
                        WHEN focal_length < 50 THEN '35-50mm'
                        WHEN focal_length < 85 THEN '50-85mm'
                        WHEN focal_length < 135 THEN '85-135mm'
                        WHEN focal_length < 200 THEN '135-200mm'
                        ELSE '>200mm'
                    END as focal_range,
                    COUNT(*) as count
                FROM images 
                WHERE focal_length IS NOT NULL 
                GROUP BY focal_range
                ORDER BY count DESC
            """)
            focal_data = {row[0]: row[1] for row in cursor.fetchall()}
            if self.focal_chart:
                self.focal_chart.update_data(focal_data)
            
            # Gear summary
            cursor.execute("SELECT COUNT(DISTINCT camera_model) FROM images WHERE camera_model IS NOT NULL")
            unique_cameras = cursor.fetchone()[0]
            self.gear_summary["unique_cameras"].setText(str(unique_cameras))
            
            cursor.execute("SELECT COUNT(DISTINCT lens_model) FROM images WHERE lens_model IS NOT NULL")
            unique_lenses = cursor.fetchone()[0]
            self.gear_summary["unique_lenses"].setText(str(unique_lenses))
            
            cursor.execute("""
                SELECT focal_length, COUNT(*) as count 
                FROM images 
                WHERE focal_length IS NOT NULL 
                GROUP BY focal_length 
                ORDER BY count DESC 
                LIMIT 1
            """)
            top_focal_data = cursor.fetchone()
            if top_focal_data:
                self.gear_summary["top_focal"].setText(f"{int(top_focal_data[0])}mm")
            
            # Range focali con debug
            cursor.execute("SELECT MIN(focal_length), MAX(focal_length), COUNT(*) FROM images WHERE focal_length IS NOT NULL")
            focal_range_result = cursor.fetchone()
            if focal_range_result[2] > 0 and focal_range_result[0]:
                min_focal = int(focal_range_result[0])
                max_focal = int(focal_range_result[1])
                if min_focal == max_focal:
                    self.gear_summary["focal_range"].setText(f"{min_focal}mm")
                else:
                    self.gear_summary["focal_range"].setText(f"{min_focal}-{max_focal}mm")
                print(f"📏 Range focali: {min_focal}-{max_focal}mm ({focal_range_result[2]} foto)")
            else:
                self.gear_summary["focal_range"].setText("N/A")
                print(f"📏 Nessuna focale trovata")

            
        except Exception as e:
            print(f"❌ Errore update gear stats: {e}")
    
    def update_shooting_stats(self, cursor):
        """Aggiorna statistiche di scatto"""
        try:
            # Aperture distribution
            cursor.execute("""
                SELECT aperture, COUNT(*) as count
                FROM images 
                WHERE aperture IS NOT NULL 
                GROUP BY aperture 
                ORDER BY count DESC
                LIMIT 8
            """)
            aperture_data = {f"f/{row[0]}": row[1] for row in cursor.fetchall()}
            if self.aperture_chart:
                self.aperture_chart.update_data(aperture_data)
            
            # Shutter speed distribution (grouped)
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN shutter_speed_decimal >= 1 THEN '≥1s'
                        WHEN shutter_speed_decimal >= 0.5 THEN '1/2s'
                        WHEN shutter_speed_decimal >= 0.1 THEN '1/10s'
                        WHEN shutter_speed_decimal >= 0.02 THEN '1/50s'
                        WHEN shutter_speed_decimal >= 0.008 THEN '1/125s'
                        WHEN shutter_speed_decimal >= 0.004 THEN '1/250s'
                        WHEN shutter_speed_decimal >= 0.002 THEN '1/500s'
                        ELSE '≥1/1000s'
                    END as speed_range,
                    COUNT(*) as count
                FROM images 
                WHERE shutter_speed_decimal IS NOT NULL 
                GROUP BY speed_range
                ORDER BY count DESC
            """)
            shutter_data = {row[0]: row[1] for row in cursor.fetchall()}
            if self.shutter_chart:
                self.shutter_chart.update_data(shutter_data)
            
            # ISO distribution
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN iso <= 100 THEN '≤100'
                        WHEN iso <= 200 THEN '101-200'
                        WHEN iso <= 400 THEN '201-400'
                        WHEN iso <= 800 THEN '401-800'
                        WHEN iso <= 1600 THEN '801-1600'
                        WHEN iso <= 3200 THEN '1601-3200'
                        WHEN iso <= 6400 THEN '3201-6400'
                        ELSE '>6400'
                    END as iso_range,
                    COUNT(*) as count
                FROM images 
                WHERE iso IS NOT NULL 
                GROUP BY iso_range
                ORDER BY count DESC
            """)
            iso_data = {row[0]: row[1] for row in cursor.fetchall()}
            if self.iso_chart:
                self.iso_chart.update_data(iso_data)
            
            # Shooting patterns con debug esteso
            cursor.execute("SELECT MIN(iso), MAX(iso), COUNT(*) FROM images WHERE iso IS NOT NULL")
            iso_range_result = cursor.fetchone()
            if iso_range_result[2] > 0 and iso_range_result[0]:
                self.shooting_patterns["iso_range"].setText(f"{iso_range_result[0]}-{iso_range_result[1]}")
                print(f"📊 ISO range: {iso_range_result[0]}-{iso_range_result[1]} ({iso_range_result[2]} foto)")
            else:
                self.shooting_patterns["iso_range"].setText("N/A")
                print(f"📊 Nessun dato ISO")
            
            cursor.execute("""
                SELECT aperture, COUNT(*) as count 
                FROM images 
                WHERE aperture IS NOT NULL 
                GROUP BY aperture 
                ORDER BY count DESC 
                LIMIT 1
            """)
            pref_aperture = cursor.fetchone()
            if pref_aperture:
                self.shooting_patterns["aperture_preferred"].setText(f"f/{pref_aperture[0]}")
                print(f"📊 Apertura preferita: f/{pref_aperture[0]} ({pref_aperture[1]} foto)")
            else:
                self.shooting_patterns["aperture_preferred"].setText("N/A")
                print(f"📊 Nessun dato apertura")
            
            # Flash detection migliorata
            cursor.execute("PRAGMA table_info(images)")
            columns = [col[1] for col in cursor.fetchall()]
            flash_fields = [col for col in columns if 'flash' in col.lower()]
            
            if 'flash_used' in columns:
                cursor.execute("SELECT COUNT(*) FROM images WHERE flash_used = 1")
                flash_used = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM images WHERE flash_used IS NOT NULL")
                flash_total = cursor.fetchone()[0]
                if flash_total > 0:
                    flash_percent = (flash_used / flash_total * 100)
                    self.shooting_patterns["flash_usage"].setText(f"{flash_percent:.0f}%")
                    print(f"📸 Flash: {flash_used}/{flash_total} = {flash_percent:.0f}%")
                else:
                    self.shooting_patterns["flash_usage"].setText("0%")
            elif any('flash' in col for col in columns):
                # Prova altri campi flash
                flash_col = next((col for col in columns if 'flash' in col.lower()), None)
                cursor.execute(f"SELECT COUNT(DISTINCT {flash_col}) FROM images WHERE {flash_col} IS NOT NULL")
                flash_variants = cursor.fetchone()[0]
                self.shooting_patterns["flash_usage"].setText(f"{flash_variants} tipi")
                print(f"📸 Flash variants in {flash_col}: {flash_variants}")
            else:
                self.shooting_patterns["flash_usage"].setText("N/A")
                print(f"📸 Nessun campo flash trovato. Campi: {flash_fields}")

            
            # Quality stats
            cursor.execute("SELECT AVG(lr_rating) FROM images WHERE lr_rating IS NOT NULL AND lr_rating > 0")
            avg_rating = cursor.fetchone()[0]
            if avg_rating:
                self.quality_stats["avg_rating"].setText(f"{avg_rating:.1f}⭐")
            
            cursor.execute("SELECT COUNT(*) FROM images WHERE lr_rating >= 4")
            high_rated = cursor.fetchone()[0]
            self.quality_stats["high_rated"].setText(f"{high_rated:,}")
            
            cursor.execute("SELECT COUNT(*) FROM images WHERE color_label IS NOT NULL AND color_label != ''")
            color_labeled = cursor.fetchone()[0]
            self.quality_stats["color_labeled"].setText(f"{color_labeled:,}")
            
            cursor.execute("SELECT COUNT(*) FROM images WHERE gps_latitude IS NOT NULL")
            gps_photos = cursor.fetchone()[0]
            self.quality_stats["gps_photos"].setText(f"{gps_photos:,}")
            
        except Exception as e:
            print(f"❌ Errore update shooting stats: {e}")
    
    def update_workflow_stats(self, cursor):
        """Aggiorna statistiche workflow"""
        try:
            # Total for percentage calculations
            cursor.execute("SELECT COUNT(*) FROM images")
            total = cursor.fetchone()[0]
            
            if total == 0:
                return
            
            # Metadata completeness
            cursor.execute("SELECT COUNT(*) FROM images WHERE title IS NOT NULL AND title != ''")
            with_title = cursor.fetchone()[0]
            self.metadata_completeness["with_title"].setText(f"{with_title/total*100:.1f}%")
            
            cursor.execute("SELECT COUNT(*) FROM images WHERE description IS NOT NULL AND description != ''")
            with_desc = cursor.fetchone()[0]
            self.metadata_completeness["with_description"].setText(f"{with_desc/total*100:.1f}%")
            
            cursor.execute("""
                SELECT COUNT(*) FROM images 
                WHERE tags IS NOT NULL AND tags != '[]' AND tags != ''
            """)
            with_tags = cursor.fetchone()[0]
            self.metadata_completeness["with_tags"].setText(f"{with_tags/total*100:.1f}%")
            
            cursor.execute("SELECT COUNT(*) FROM images WHERE lr_rating IS NOT NULL AND lr_rating > 0")
            with_rating = cursor.fetchone()[0]
            self.metadata_completeness["with_rating"].setText(f"{with_rating/total*100:.1f}%")
            
            # GPS consistency fix
            cursor.execute("SELECT COUNT(*) FROM images WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL")
            with_gps = cursor.fetchone()[0]
            self.metadata_completeness["with_gps"].setText(f"{with_gps/total*100:.1f}%")
            
            # Debug per capire il bug 7.1%
            print(f"📝 Metadata debug:")
            print(f"  Titolo: {with_title}/{total} = {with_title/total*100:.1f}%")
            print(f"  Descrizione: {with_desc}/{total} = {with_desc/total*100:.1f}%") 
            print(f"  Tags: {with_tags}/{total} = {with_tags/total*100:.1f}%")
            print(f"  Rating: {with_rating}/{total} = {with_rating/total*100:.1f}%")
            print(f"  GPS: {with_gps}/{total} = {with_gps/total*100:.1f}%")

            
            # Tag analysis (extract from unified tags field)
            cursor.execute("SELECT tags FROM images WHERE tags IS NOT NULL AND tags != '[]' AND tags != ''")
            all_tags = []
            for row in cursor.fetchall():
                try:
                    tags_data = json.loads(row[0])
                    if isinstance(tags_data, list):
                        all_tags.extend(tags_data)
                except:
                    continue
            
            tag_counter = Counter(all_tags)
            top_tags = dict(tag_counter.most_common(10))
            if self.tags_chart:
                self.tags_chart.update_data(top_tags)
            
            # Geographic stats con debug
            cursor.execute("SELECT COUNT(DISTINCT gps_country) FROM images WHERE gps_country IS NOT NULL AND gps_country != ''")
            countries = cursor.fetchone()[0]
            self.geo_stats["countries"].setText(str(countries))
            
            cursor.execute("SELECT COUNT(DISTINCT gps_city) FROM images WHERE gps_city IS NOT NULL AND gps_city != ''")
            cities = cursor.fetchone()[0]
            self.geo_stats["cities"].setText(str(cities))
            
            # GPS coverage (stesso calcolo per consistency)
            gps_coverage = (with_gps / total * 100) if total > 0 else 0
            self.geo_stats["gps_coverage"].setText(f"{gps_coverage:.1f}%")
            
            # Debug GPS
            cursor.execute("SELECT COUNT(*) FROM images WHERE gps_latitude IS NOT NULL")
            gps_coords = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM images WHERE gps_country IS NOT NULL AND gps_country != ''")
            gps_countries = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM images WHERE gps_city IS NOT NULL AND gps_city != ''")
            gps_cities = cursor.fetchone()[0]
            
            print(f"🌍 GPS debug: {gps_coords} coordinate, {gps_countries} paesi, {gps_cities} città")
            
            # Top location
            cursor.execute("""
                SELECT gps_city, COUNT(*) as count 
                FROM images 
                WHERE gps_city IS NOT NULL AND gps_city != ''
                GROUP BY gps_city 
                ORDER BY count DESC 
                LIMIT 1
            """)
            top_location = cursor.fetchone()
            if top_location:
                self.geo_stats["top_location"].setText(f"{top_location[0]} ({top_location[1]})")
            else:
                # Se non c'è città, mostra almeno le coordinate
                cursor.execute("""
                    SELECT gps_latitude, gps_longitude 
                    FROM images 
                    WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL 
                    LIMIT 1
                """)
                coords = cursor.fetchone()
                if coords:
                    self.geo_stats["top_location"].setText(f"Coordinate: {coords[0]:.3f}, {coords[1]:.3f}")
                else:
                    self.geo_stats["top_location"].setText("N/A")
            
            # File management
            cursor.execute("SELECT SUM(file_size) FROM images WHERE file_size IS NOT NULL")
            total_size = cursor.fetchone()[0] or 0
            size_gb = total_size / (1024**3)
            self.file_stats["total_size"].setText(f"{size_gb:.1f} GB")
            
            if total > 0:
                avg_size_mb = (total_size / total) / (1024**2)
                self.file_stats["avg_size"].setText(f"{avg_size_mb:.1f} MB")
            
            # RAW percentage
            cursor.execute("SELECT COUNT(*) FROM images WHERE is_raw = 1")
            raw_count = cursor.fetchone()[0]
            raw_percent = (raw_count / total * 100) if total > 0 else 0
            self.file_stats["raw_percentage"].setText(f"{raw_percent:.1f}%")
            
            # Unique formats
            cursor.execute("SELECT COUNT(DISTINCT file_format) FROM images WHERE file_format IS NOT NULL")
            unique_formats = cursor.fetchone()[0]
            self.file_stats["unique_formats"].setText(str(unique_formats))
            
        except Exception as e:
            print(f"❌ Errore update workflow stats: {e}")
    
    def on_activated(self):
        """Metodo chiamato quando la tab diventa attiva - RICHIESTO DAL MAIN"""
        print("🎯 StatsTab.on_activated chiamato dal main_window")
        try:
            if self.db_manager:
                self.refresh_stats()
            else:
                print("⚠️ Database manager non disponibile in on_activated")
            print("✅ on_activated completato")
        except Exception as e:
            print(f"❌ Errore in on_activated: {e}")
            import traceback
            traceback.print_exc()
