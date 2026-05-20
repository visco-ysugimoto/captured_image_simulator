"""Parameter sweep dialog with background execution and comparison export."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..analysis.sweep import SWEEP_PARAM_PRESETS, SweepResult
from ..domain import Scene
from ..render import RenderSettings
from ..render.cancellation import RenderCancellation
from .i18n import LanguageManager
from .progress_dialog import RenderProgressDialog
from .sweep_worker import run_sweep_in_thread

if TYPE_CHECKING:
    from .comparison_view import ComparisonView


class SweepDialog(QDialog):
    def __init__(
        self,
        scene: Scene,
        comparison_view: ComparisonView | None = None,
        i18n: LanguageManager | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._i18n = i18n or LanguageManager(default="en")
        self.setWindowTitle(self._t("sweep.title"))
        self.scene = scene
        self._comparison = comparison_view
        self._thread: QThread | None = None
        self._last_result: SweepResult | None = None
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem(self._t("sweep.custom"), "")
        for label, path in SWEEP_PARAM_PRESETS.items():
            self.preset_combo.addItem(label, path)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow(self._t("sweep.preset"), self.preset_combo)

        self.param_edit = QLineEdit("lights.0.intensity")
        form.addRow(self._t("sweep.param_path"), self.param_edit)

        self.values_edit = QLineEdit("200, 500, 1000, 2000")
        form.addRow(self._t("sweep.values"), self.values_edit)

        self.spp_edit = QSpinBox()
        self.spp_edit.setRange(1, 4096)
        self.spp_edit.setValue(8)
        form.addRow(self._t("sweep.spp"), self.spp_edit)

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 1.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setValue(0.5)
        self.scale_spin.setToolTip(self._t("sweep.preview_scale_tip"))
        form.addRow(self._t("sweep.preview_scale"), self.scale_spin)

        self.fallback_check = QCheckBox(self._t("sweep.use_fallback"))
        self.fallback_check.setChecked(True)
        form.addRow("", self.fallback_check)

        self.compare_check = QCheckBox(self._t("sweep.add_compare"))
        self.compare_check.setChecked(True)
        form.addRow("", self.compare_check)

        hint = QLabel(self._t("sweep.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["value", "mean", "michelson", "snr_dB", "saturated"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table, 1)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        btns = QHBoxLayout()
        layout.addLayout(btns)
        self.run_btn = QPushButton(self._t("sweep.run"))
        self.run_btn.clicked.connect(self._run)
        btns.addWidget(self.run_btn)
        self.close_btn = QPushButton(self._t("dialog.close"))
        self.close_btn.clicked.connect(self.accept)
        btns.addWidget(self.close_btn)

    def _on_preset_changed(self, _index: int) -> None:
        path = self.preset_combo.currentData()
        if path:
            self.param_edit.setText(str(path))

    def _parse_values(self) -> list[Any]:
        raw = [v.strip() for v in self.values_edit.text().split(",") if v.strip()]
        if not raw:
            raise ValueError(self._t("sweep.no_values"))
        out: list[Any] = []
        for tok in raw:
            try:
                out.append(float(tok))
            except ValueError:
                out.append(tok)
        return out

    def _run(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(
                self,
                self._t("sweep.busy_title"),
                self._t("sweep.busy_msg"),
            )
            return

        param = self.param_edit.text().strip()
        if not param:
            QMessageBox.warning(
                self,
                self._t("sweep.param_title"),
                self._t("sweep.param_msg"),
            )
            return
        try:
            values = self._parse_values()
        except ValueError as exc:
            QMessageBox.warning(self, self._t("sweep.values_title"), str(exc))
            return

        settings = RenderSettings(
            spp=self.spp_edit.value(),
            use_fallback=self.fallback_check.isChecked(),
            preview_scale=float(self.scale_spin.value()),
            light_samples=8,
        )

        cancellation = RenderCancellation()
        progress = RenderProgressDialog(
            self._t("sweep.progress_title"),
            cancellation,
            self,
            indeterminate=False,
            start_label=self._t("dialog.starting"),
            cancel_label=self._t("dialog.cancel"),
            cancelling_label=self._t("dialog.cancelling"),
        )
        progress.show()

        self.run_btn.setEnabled(False)
        self.progress.setRange(0, len(values))
        self.progress.setValue(0)

        def on_progress(current: int, total: int, message: str) -> None:
            progress.update_progress(current, total, message)
            self.progress.setValue(current)

        def _cleanup() -> None:
            progress.mark_finished()
            progress.close()
            self.run_btn.setEnabled(True)
            self._thread = None

        def on_finished(result: SweepResult) -> None:
            _cleanup()
            self._last_result = result
            self._fill_table(result, values)
            if self.compare_check.isChecked() and self._comparison is not None:
                self._push_to_comparison(result)
            QMessageBox.information(
                self,
                self._t("sweep.complete_title"),
                self._t("sweep.complete_msg", done=len(result.metrics), total=len(values)),
            )

        def on_failed(msg: str) -> None:
            _cleanup()
            QMessageBox.critical(self, self._t("sweep.failed"), msg)

        def on_cancelled() -> None:
            _cleanup()
            QMessageBox.information(
                self,
                self._t("sweep.cancelled_title"),
                self._t("sweep.cancelled_msg"),
            )

        self._thread, _worker = run_sweep_in_thread(
            self,
            self.scene,
            param,
            values,
            settings,
            on_finished,
            on_failed,
            on_cancelled=on_cancelled,
            on_progress=on_progress,
            cancellation=cancellation,
        )

    def _fill_table(self, result: SweepResult, values: list[Any]) -> None:
        n = len(result.metrics)
        self.table.setRowCount(n)
        for r in range(n):
            v = result.values[r] if r < len(result.values) else values[r]
            m = result.metrics[r]
            self.table.setItem(r, 0, QTableWidgetItem(str(v)))
            self.table.setItem(r, 1, QTableWidgetItem(f"{m.mean:.2f}"))
            self.table.setItem(r, 2, QTableWidgetItem(f"{m.michelson:.3f}"))
            self.table.setItem(r, 3, QTableWidgetItem(f"{m.snr_db:.2f}"))
            self.table.setItem(r, 4, QTableWidgetItem(f"{m.saturated_fraction:.3f}"))

    def _push_to_comparison(self, result: SweepResult) -> None:
        assert self._comparison is not None
        short_param = result.parameter.split(".")[-1]
        for value, render in zip(result.values, result.renders):
            label = f"{short_param}={value}"
            self._comparison.add_snapshot(label, render)

    def _t(self, key: str, **kwargs: object) -> str:
        return self._i18n.text(key, **kwargs)
