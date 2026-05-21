"""Dialog to import external meshes with per-part materials."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..domain import Target
from ..domain.target import TargetMesh
from ..io.mesh_loader import (
    STEP_INSTALL_HINT,
    step_backend_available,
    suggest_mesh_scale_to_mm,
)
from ..presets import get_material_for_role, get_material_preset, material_preset_names
from .i18n import LanguageManager
from .mesh_load_worker import run_list_parts_in_thread
from .progress_dialog import TaskProgressDialog
from .viewport_limits import (
    IMPORT_DEFAULT_CHECKED_PARTS,
    IMPORT_WARN_PART_COUNT,
)


@dataclass
class PartImportRow:
    part_name: str | None
    target_name: str
    material_preset: str
    import_part: bool


class MeshImportDialog(QDialog):
    """Select mesh file, choose parts, assign materials, import as targets."""

    def __init__(
        self,
        i18n: LanguageManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._i18n = i18n
        self.setWindowTitle(self._t("mesh.title"))
        self.resize(720, 480)
        self._path: str = ""
        self._part_keys: list[str] = []
        self.imported_targets: list[Target] = []
        self._load_thread: QThread | None = None
        self._load_progress: TaskProgressDialog | None = None

        layout = QVBoxLayout(self)

        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        file_row.addWidget(self.path_edit, 1)
        browse = QPushButton(self._t("mesh.browse"))
        browse.clicked.connect(self._browse)
        file_row.addWidget(browse)
        layout.addLayout(file_row)

        opts = QFormLayout()
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.001, 1000.0)
        self.scale_spin.setValue(1.0)
        self.scale_spin.setDecimals(4)
        opts.addRow(self._t("mesh.uniform_scale"), self.scale_spin)
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText(self._t("mesh.name_prefix_placeholder"))
        opts.addRow(self._t("mesh.name_prefix"), self.prefix_edit)
        layout.addLayout(opts)

        backend = step_backend_available()
        step_note = (
            f"STEP backend: {backend}"
            if backend
            else self._t("mesh.step_missing")
        )
        hint = QLabel(
            f"{step_note}\n{self._t('mesh.hint')}"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(QLabel(self._t("mesh.parts_label")))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [
                self._t("mesh.header.import"),
                self._t("mesh.header.part"),
                self._t("mesh.header.target"),
                self._t("mesh.header.material"),
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table, 1)

        quick = QHBoxLayout()
        quick.addWidget(QLabel(self._t("mesh.quick_assign")))
        self.quick_role = QComboBox()
        self.quick_role.addItem(
            self._t("mesh.quick.widget_aluminum"),
            "widget_aluminum_machined",
        )
        self.quick_role.addItem(
            self._t("mesh.quick.widget_white"),
            "widget_painted_white",
        )
        self.quick_role.addItem(
            self._t("mesh.quick.stage_white"),
            "stage_matte_white",
        )
        self.quick_role.addItem(
            self._t("mesh.quick.stage_black"),
            "stage_anodized_black",
        )
        self.quick_role.addItem(
            self._t("mesh.quick.general_plastic"),
            "plastic_white",
        )
        self.quick_role.addItem(
            self._t("mesh.quick.general_aluminum"),
            "aluminum_brushed",
        )
        quick.addWidget(self.quick_role, 1)
        btn_apply_quick = QPushButton(self._t("mesh.apply_checked"))
        btn_apply_quick.clicked.connect(self._apply_quick_material)
        quick.addWidget(btn_apply_quick)
        layout.addLayout(quick)

        sel_row = QHBoxLayout()
        btn_check_first = QPushButton(
            self._t("mesh.check_first", count=IMPORT_DEFAULT_CHECKED_PARTS)
        )
        btn_check_first.clicked.connect(self._check_first_parts)
        sel_row.addWidget(btn_check_first)
        btn_uncheck = QPushButton(self._t("mesh.uncheck_all"))
        btn_uncheck.clicked.connect(self._uncheck_all_parts)
        sel_row.addWidget(btn_uncheck)
        sel_row.addStretch(1)
        layout.addLayout(sel_row)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._accept_import)
        self._buttons.rejected.connect(self._try_reject)
        layout.addWidget(self._buttons)
        self._browse_btn = browse

    def _try_reject(self) -> None:
        if self._is_loading():
            QMessageBox.information(
                self,
                self._t("mesh.loading_title"),
                self._t("mesh.loading_wait"),
            )
            return
        self.reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._is_loading():
            QMessageBox.information(
                self,
                self._t("mesh.loading_title"),
                self._t("mesh.loading_wait"),
            )
            event.ignore()
            return
        super().closeEvent(event)

    def _browse(self) -> None:
        from ..io.mesh_loader import supported_mesh_extensions

        exts = " ".join(f"*{e}" for e in sorted(supported_mesh_extensions()))
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("mesh.open_mesh"),
            str(Path.cwd()),
            f"{self._t('mesh.file_filter')} ({exts})",
        )
        if not path:
            return
        self._path = path
        self.path_edit.setText(path)
        self._load_parts(path)

    def _is_loading(self) -> bool:
        return self._load_thread is not None and self._load_thread.isRunning()

    def _set_loading(self, loading: bool) -> None:
        self._browse_btn.setEnabled(not loading)
        self.scale_spin.setEnabled(not loading)
        self.prefix_edit.setEnabled(not loading)
        self.table.setEnabled(not loading)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            not loading
        )

    def _load_parts(self, path: str) -> None:
        if self._is_loading():
            return

        suffix = Path(path).suffix.lower()
        if suffix in (".step", ".stp"):
            msg = self._t("mesh.step_loading")
        else:
            msg = self._t("mesh.loading")
        self._load_progress = TaskProgressDialog(self._t("mesh.title"), msg, self)
        self._load_progress.show()
        self._set_loading(True)

        def on_finished(parts: list) -> None:
            if self._load_progress is not None:
                self._load_progress.close()
                self._load_progress = None
            self._load_thread = None
            self._set_loading(False)
            self._populate_parts_table(path, parts)

        def on_failed(msg: str) -> None:
            if self._load_progress is not None:
                self._load_progress.close()
                self._load_progress = None
            self._load_thread = None
            self._set_loading(False)
            if path.lower().endswith((".step", ".stp")) and "cascadio" in msg.lower():
                QMessageBox.critical(self, self._t("mesh.step_failed"), STEP_INSTALL_HINT)
            else:
                QMessageBox.critical(self, self._t("mesh.load_failed"), msg)

        self._load_thread, _worker = run_list_parts_in_thread(
            self, path, on_finished, on_failed
        )

    def _check_first_parts(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            item.setCheckState(
                Qt.CheckState.Checked
                if row < IMPORT_DEFAULT_CHECKED_PARTS
                else Qt.CheckState.Unchecked
            )

    def _uncheck_all_parts(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Unchecked)

    def _populate_parts_table(self, path: str, parts: list[str]) -> None:
        stem = Path(path).stem
        prefix = self.prefix_edit.text().strip()
        self.table.setRowCount(len(parts))
        default_mat = "widget_aluminum_machined"
        many_parts = len(parts) > IMPORT_WARN_PART_COUNT
        if many_parts:
            QMessageBox.warning(
                self,
                self._t("mesh.many_parts_title"),
                self._t(
                    "mesh.many_parts_msg",
                    count=len(parts),
                    default_count=IMPORT_DEFAULT_CHECKED_PARTS,
                ),
            )

        for row, part in enumerate(parts):
            chk = QTableWidgetItem()
            chk.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            if many_parts:
                checked = row < IMPORT_DEFAULT_CHECKED_PARTS
            else:
                checked = True
            chk.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 0, chk)

            part_label = part if part != "default" else "(merged)"
            self.table.setItem(row, 1, QTableWidgetItem(part_label))

            if part == "default":
                tname = f"{prefix}_{stem}" if prefix else stem
            else:
                safe = part.replace(" ", "_")
                tname = f"{prefix}_{safe}" if prefix else safe
            self.table.setItem(row, 2, QTableWidgetItem(tname))

            combo = QComboBox()
            combo.addItems(material_preset_names())
            idx = combo.findText(default_mat)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            self.table.setCellWidget(row, 3, combo)

        self._part_keys = parts
        suggested = suggest_mesh_scale_to_mm(path)
        if suggested != 1.0:
            self.scale_spin.setValue(suggested)
            QMessageBox.information(
                self,
                self._t("mesh.unit_scale_title"),
                self._t("mesh.unit_scale_msg", scale=suggested),
            )

    def _apply_quick_material(self) -> None:
        preset = self.quick_role.currentData()
        if not preset:
            preset = self.quick_role.currentText()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                combo = self.table.cellWidget(row, 3)
                if isinstance(combo, QComboBox):
                    idx = combo.findText(str(preset))
                    if idx >= 0:
                        combo.setCurrentIndex(idx)

    def _collect_rows(self) -> list[PartImportRow]:
        rows: list[PartImportRow] = []
        for i in range(self.table.rowCount()):
            chk = self.table.item(i, 0)
            if chk is None or chk.checkState() != Qt.CheckState.Checked:
                continue
            part_key = self._part_keys[i]
            part_name = None if part_key == "default" else part_key
            name_item = self.table.item(i, 2)
            tname = name_item.text().strip() if name_item else f"part_{i}"
            combo = self.table.cellWidget(i, 3)
            preset = combo.currentText() if isinstance(combo, QComboBox) else "plastic_white"
            rows.append(
                PartImportRow(
                    part_name=part_name,
                    target_name=tname,
                    material_preset=preset,
                    import_part=True,
                )
            )
        return rows

    def _accept_import(self) -> None:
        if self._is_loading():
            QMessageBox.information(
                self,
                self._t("mesh.loading_title"),
                self._t("mesh.loading_wait"),
            )
            return
        if not self._path:
            QMessageBox.warning(
                self,
                self._t("mesh.no_file_title"),
                self._t("mesh.no_file_msg"),
            )
            return
        part_rows = self._collect_rows()
        if not part_rows:
            QMessageBox.warning(
                self,
                self._t("mesh.no_parts_title"),
                self._t("mesh.no_parts_msg"),
            )
            return
        if len(part_rows) > IMPORT_WARN_PART_COUNT:
            ret = QMessageBox.question(
                self,
                self._t("mesh.import_many_title"),
                self._t("mesh.import_many_msg", count=len(part_rows)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        scale = float(self.scale_spin.value())
        targets: list[Target] = []
        for row in part_rows:
            try:
                material = get_material_preset(row.material_preset)
            except KeyError:
                material = get_material_for_role("widget")
            geom = TargetMesh(
                path=self._path,
                scale=scale,
                part_name=row.part_name,
            )
            targets.append(
                Target(
                    name=row.target_name,
                    geometry=geom,
                    material=material,
                )
            )
        self.imported_targets = targets
        self.accept()

    def _t(self, key: str, **kwargs: object) -> str:
        return self._i18n.text(key, **kwargs)
