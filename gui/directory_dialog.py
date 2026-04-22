"""
DirectoryTreeWidget — Widget riutilizzabile con albero directory, checkbox tristate e conteggi.
DirectoryTreeDialog  — Dialog modale che wrappa DirectoryTreeWidget.

Usato da: plugins_tab.py (dialog), gui/search_tab.py (widget embedded)
"""

from collections import defaultdict
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTreeWidget, QTreeWidgetItem,
)
from PyQt6.QtCore import Qt, pyqtSignal

from i18n import t


class DirectoryTreeWidget(QWidget):
    """Widget riutilizzabile con albero directory multi-root, checkbox tristate e conteggi.

    Può essere usato sia embedded in un layout sia wrappato da DirectoryTreeDialog.
    Emette selection_changed(list) ad ogni variazione di selezione.
    """

    selection_changed = pyqtSignal(list)

    # Palette consolidata del progetto
    _GRAFITE       = '#2A2A2A'
    _GRAFITE_LIGHT = '#3A3A3A'
    _GRAFITE_DARK  = '#1E1E1E'
    _GRIGIO_CHIARO = '#E3E3E3'
    _GRIGIO_MEDIO  = '#B0B0B0'
    _BLU_PETROLIO  = '#1C4F63'
    _BLU_PETROLIO_LIGHT = '#2A6A82'
    _AMBRA         = '#C88B2E'
    _AMBRA_LIGHT   = '#E0A84A'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dir_counts   = {}
        self.pre_selected = set()
        self._leaf_items       = {}
        self._updating_checks  = False
        self._build_ui()

    def refresh(self, dir_counts: dict, pre_selected: list = None):
        """Ricostruisce l'albero con i dati forniti (tipicamente estratti dal DB)."""
        self.dir_counts   = dir_counts
        self.pre_selected = set(pre_selected or [])
        self._leaf_items  = {}
        self.tree.clear()
        self._populate_tree()
        self._update_counter()

    def get_selected_dirs(self) -> list:
        """Restituisce la lista delle directory selezionate (checked)."""
        return self._get_selected_dirs()

    # ------------------------------------------------------------------
    # Costruzione UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self._GRAFITE};
                color: {self._GRIGIO_CHIARO};
            }}
            QLabel {{
                color: {self._GRIGIO_CHIARO};
            }}
        """)

        # --- Toolbar ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        btn_style = f"""
            QPushButton {{
                background-color: {self._BLU_PETROLIO};
                color: {self._GRIGIO_CHIARO};
                border: none;
                padding: 5px 12px;
                border-radius: 3px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {self._BLU_PETROLIO_LIGHT};
            }}
        """

        self.btn_all = QPushButton(t("export.dialog.dir_btn_all"))
        self.btn_all.setStyleSheet(btn_style)
        self.btn_all.clicked.connect(self._select_all)
        toolbar.addWidget(self.btn_all)

        self.btn_none = QPushButton(t("export.dialog.dir_btn_none"))
        self.btn_none.setStyleSheet(btn_style)
        self.btn_none.clicked.connect(self._deselect_all)
        toolbar.addWidget(self.btn_none)

        toolbar.addSpacing(12)

        self.btn_expand = QPushButton(t("export.dialog.dir_btn_expand"))
        self.btn_expand.setStyleSheet(btn_style)
        self.btn_expand.clicked.connect(lambda: self.tree.expandAll())
        toolbar.addWidget(self.btn_expand)

        self.btn_collapse = QPushButton(t("export.dialog.dir_btn_collapse"))
        self.btn_collapse.setStyleSheet(btn_style)
        self.btn_collapse.clicked.connect(lambda: self.tree.collapseAll())
        toolbar.addWidget(self.btn_collapse)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # --- Tree ---
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(20)
        self.tree.itemChanged.connect(self._on_item_changed)

        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {self._GRAFITE_DARK};
                color: {self._GRIGIO_CHIARO};
                border: 1px solid {self._GRAFITE_LIGHT};
                border-radius: 4px;
                font-size: 12px;
                padding: 4px;
            }}
            QTreeWidget::item {{
                padding: 3px 2px;
                border: none;
            }}
            QTreeWidget::item:hover {{
                background-color: {self._GRAFITE_LIGHT};
            }}
            QTreeWidget::item:selected {{
                background-color: {self._BLU_PETROLIO};
                color: {self._GRIGIO_CHIARO};
            }}
            QTreeWidget::branch {{
                background: transparent;
            }}
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {{
                image: none;
                border-image: none;
            }}
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {{
                image: none;
                border-image: none;
            }}
            QTreeWidget::indicator {{
                width: 14px;
                height: 14px;
            }}
            QTreeWidget::indicator:unchecked {{
                background-color: {self._GRAFITE};
                border: 1px solid {self._GRIGIO_MEDIO};
                border-radius: 2px;
            }}
            QTreeWidget::indicator:checked {{
                background-color: {self._BLU_PETROLIO_LIGHT};
                border: 1px solid {self._BLU_PETROLIO};
                border-radius: 2px;
            }}
            QTreeWidget::indicator:indeterminate {{
                background-color: {self._GRAFITE};
                border: 1px solid {self._AMBRA};
                border-radius: 2px;
            }}
        """)

        layout.addWidget(self.tree)

        # --- Contatore ---
        self.counter_label = QLabel()
        self.counter_label.setStyleSheet(f"""
            color: {self._AMBRA_LIGHT};
            font-size: 12px;
            font-weight: bold;
            padding: 2px 0px;
        """)
        layout.addWidget(self.counter_label)

    # ------------------------------------------------------------------
    # Costruzione albero da dir_counts
    # ------------------------------------------------------------------

    def _populate_tree(self):
        """Costruisce l'albero gerarchico dalle directory del DB."""
        self.tree.blockSignals(True)

        if not self.dir_counts:
            self.tree.blockSignals(False)
            return

        tree_data  = defaultdict(dict)
        root_paths = {}

        for dir_path, count in sorted(self.dir_counts.items()):
            p     = Path(dir_path)
            parts = p.parts

            if not parts:
                continue

            if len(parts) >= 1 and (len(parts[0]) <= 3 and ':' in parts[0]):
                # Windows: D:\
                root_label     = parts[0]
                relative_parts = parts[1:]
            elif len(parts) >= 3 and parts[1] in ('mnt', 'Volumes', 'media'):
                # Unix mount: /mnt/X, /Volumes/X, /media/user/X
                if parts[1] == 'media' and len(parts) >= 4:
                    root_label     = f"/{parts[1]}/{parts[2]}/{parts[3]}"
                    relative_parts = parts[4:]
                else:
                    root_label     = f"/{parts[1]}/{parts[2]}"
                    relative_parts = parts[3:]
            else:
                root_label     = str(Path(*parts[:2])) if len(parts) >= 2 else str(p)
                relative_parts = parts[2:] if len(parts) > 2 else ()

            tree_data[root_label][relative_parts] = count
            if root_label not in root_paths:
                root_paths[root_label] = root_label

        for root_label in sorted(tree_data.keys()):
            sub_dirs = tree_data[root_label]

            root_item = QTreeWidgetItem(self.tree)
            root_item.setText(0, root_label)
            root_item.setFlags(
                root_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )
            root_item.setCheckState(0, Qt.CheckState.Unchecked)

            font = root_item.font(0)
            font.setBold(True)
            root_item.setFont(0, font)

            self._build_subtree(root_item, sub_dirs, root_label)
            root_item.setExpanded(True)

        self._update_aggregate_counts()
        self.tree.blockSignals(False)

    def _build_subtree(self, parent_item, sub_dirs, root_label):
        """Costruisce ricorsivamente i nodi sotto un parent."""
        groups = defaultdict(dict)

        for parts, count in sub_dirs.items():
            if not parts:
                full_path = root_label
                parent_item.setData(0, Qt.ItemDataRole.UserRole, full_path)
                parent_item.setData(0, Qt.ItemDataRole.UserRole + 1, count)
                self._leaf_items[full_path] = parent_item
                parent_item.setText(0, f"{parent_item.text(0).split('  (')[0]}  ({count})")
                if full_path in self.pre_selected:
                    parent_item.setCheckState(0, Qt.CheckState.Checked)
                continue

            first     = parts[0]
            remaining = parts[1:]
            groups[first][remaining] = count

        for name in sorted(groups.keys()):
            children = groups[name]

            child_item = QTreeWidgetItem(parent_item)
            child_item.setText(0, name)
            child_item.setFlags(
                child_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )
            child_item.setCheckState(0, Qt.CheckState.Unchecked)

            if len(children) == 1 and () in children:
                full_path = str(Path(root_label) / name)
                child_item.setData(0, Qt.ItemDataRole.UserRole, full_path)
                child_item.setData(0, Qt.ItemDataRole.UserRole + 1, children[()])
                self._leaf_items[full_path] = child_item
                child_item.setText(0, f"{name}  ({children[()]})")
                if full_path in self.pre_selected:
                    child_item.setCheckState(0, Qt.CheckState.Checked)
            else:
                if len(children) == 1 and () not in children:
                    only_key = list(children.keys())[0]
                    only_val = children[only_key]
                    if isinstance(only_val, int):
                        compact_name = name + '/' + '/'.join(only_key)
                        full_path    = str(Path(root_label) / name / '/'.join(only_key))
                        child_item.setText(0, f"{compact_name}  ({only_val})")
                        child_item.setData(0, Qt.ItemDataRole.UserRole, full_path)
                        child_item.setData(0, Qt.ItemDataRole.UserRole + 1, only_val)
                        self._leaf_items[full_path] = child_item
                        if full_path in self.pre_selected:
                            child_item.setCheckState(0, Qt.CheckState.Checked)
                        continue

                sub_root = str(Path(root_label) / name)
                self._build_subtree(child_item, children, sub_root)

    def _update_aggregate_counts(self):
        """Aggiorna testo di tutti i nodi con conteggio aggregato dei discendenti."""
        for i in range(self.tree.topLevelItemCount()):
            self._update_node_count_recursive(self.tree.topLevelItem(i))

    def _update_node_count_recursive(self, item):
        """Aggiorna ricorsivamente il conteggio di un nodo e di tutti i suoi figli."""
        for i in range(item.childCount()):
            self._update_node_count_recursive(item.child(i))
        total = self._count_descendants(item)
        if total > 0:
            label = item.text(0).split('  (')[0]
            item.setText(0, f"{label}  ({total})")

    def _count_descendants(self, item):
        """Conta ricorsivamente le immagini nei discendenti foglia."""
        count = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if count is not None and item.childCount() == 0:
            return count

        total = 0
        if count is not None:
            total += count
        for i in range(item.childCount()):
            total += self._count_descendants(item.child(i))
        return total

    # ------------------------------------------------------------------
    # Gestione checkbox
    # ------------------------------------------------------------------

    def _on_item_changed(self, item, column):
        """Aggiorna contatore e segnala cambio selezione."""
        if self._updating_checks:
            return
        self._update_counter()
        self.selection_changed.emit(self._get_selected_dirs())

    def _select_all(self):
        self._set_all_checks(Qt.CheckState.Checked)

    def _deselect_all(self):
        self._set_all_checks(Qt.CheckState.Unchecked)

    def _set_all_checks(self, state):
        self._updating_checks = True
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, state)
        self.tree.blockSignals(False)
        self._updating_checks = False
        self._update_counter()
        self.selection_changed.emit(self._get_selected_dirs())

    def _update_counter(self):
        """Conta immagini nelle directory checked."""
        total = 0
        for dir_path, item in self._leaf_items.items():
            if item.checkState(0) == Qt.CheckState.Checked:
                count = item.data(0, Qt.ItemDataRole.UserRole + 1) or 0
                total += count
        self.counter_label.setText(t("export.dialog.dir_count", count=total))

    def _get_selected_dirs(self) -> list:
        """Restituisce lista directory selezionate (checked)."""
        selected = []
        for dir_path, item in self._leaf_items.items():
            if item.checkState(0) == Qt.CheckState.Checked:
                selected.append(dir_path)
        return selected


class DirectoryTreeDialog(QDialog):
    """Dialog modale con albero directory multi-root. Wrapper di DirectoryTreeWidget."""

    _GRAFITE            = '#2A2A2A'
    _GRAFITE_LIGHT      = '#3A3A3A'
    _GRIGIO_CHIARO      = '#E3E3E3'
    _GRIGIO_MEDIO       = '#B0B0B0'
    _BLU_PETROLIO       = '#1C4F63'
    _BLU_PETROLIO_LIGHT = '#2A6A82'

    def __init__(self, dir_counts: dict, pre_selected: list = None, parent=None):
        """
        Args:
            dir_counts:   {directory_path: image_count} dal DB
            pre_selected: lista directory già selezionate (per riapertura)
        """
        super().__init__(parent)
        self.selected_directories = []

        self.setWindowTitle(t("export.dialog.dir_title"))
        self.setMinimumSize(620, 480)
        self.resize(700, 540)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {self._GRAFITE};
                color: {self._GRIGIO_CHIARO};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        self._tree_widget = DirectoryTreeWidget(self)
        self._tree_widget.refresh(dir_counts, pre_selected)
        layout.addWidget(self._tree_widget)

        # --- OK / Cancel ---
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addStretch()

        ok_cancel_style = f"""
            QPushButton {{
                padding: 7px 20px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                min-width: 80px;
            }}
        """

        btn_cancel = QPushButton(t("export.dialog.dir_cancel"))
        btn_cancel.setStyleSheet(ok_cancel_style + f"""
            QPushButton {{
                background-color: {self._GRAFITE_LIGHT};
                color: {self._GRIGIO_CHIARO};
                border: 1px solid {self._GRIGIO_MEDIO};
            }}
            QPushButton:hover {{
                background-color: #4A4A4A;
            }}
        """)
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)

        btn_ok = QPushButton(t("export.dialog.dir_ok"))
        btn_ok.setStyleSheet(ok_cancel_style + f"""
            QPushButton {{
                background-color: {self._BLU_PETROLIO};
                color: {self._GRIGIO_CHIARO};
                border: none;
            }}
            QPushButton:hover {{
                background-color: {self._BLU_PETROLIO_LIGHT};
            }}
        """)
        btn_ok.clicked.connect(self._on_accept)
        bottom.addWidget(btn_ok)

        layout.addLayout(bottom)

    def _on_accept(self):
        self.selected_directories = self._tree_widget.get_selected_dirs()
        self.accept()
