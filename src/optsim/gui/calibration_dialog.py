"""Dialog to calibrate scene parameters against a reference photograph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..analysis.calibration import (
    CalibrationResult,
    apply_calibration,
    parse_roi,
)
from ..render import RenderSettings
from ..render.cancellation import RenderCancellation
from .calibration_worker import run_calibration_in_thread
from .i18n import LanguageManager
from .progress_dialog import RenderProgressDialog

if TYPE_CHECKING:
    from .scene_state import SceneState


class CalibrationDialog(QDialog):
    def __init__(
        self,
        state: SceneState,
        i18n: LanguageManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._i18n = i18n
        self._thread: QThread | None = None
        self._last_result: CalibrationResult | None = None
        self.setWindowTitle(self._t("calib.title"))
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        row = QHBoxLayout()
        self.ref_edit = QLineEdit()
        row.addWidget(self.ref_edit, 1)
        browse = QPushButton(self._t("mesh.browse"))
        browse.clicked.connect(self._browse_reference)
        row.addWidget(browse)
        form.addRow(self._t("calib.reference_image"), row)

        self.roi_edit = QLineEdit()
        self.roi_edit.setPlaceholderText(self._t("calib.roi_placeholder"))
        form.addRow(self._t("calib.signal_roi"), self.roi_edit)

        self.dark_roi_edit = QLineEdit()
        self.dark_roi_edit.setPlaceholderText(self._t("calib.dark_roi_placeholder"))
        form.addRow(self._t("calib.dark_roi"), self.dark_roi_edit)

        self.fit_scale = QCheckBox(self._t("calib.fit_scale"))
        self.fit_scale.setChecked(True)
        form.addRow("", self.fit_scale)

        self.fit_black = QCheckBox(self._t("calib.fit_black"))
        form.addRow("", self.fit_black)

        self.fit_qe = QCheckBox(self._t("calib.fit_qe"))
        form.addRow("", self.fit_qe)

        self.lstsq_check = QCheckBox(self._t("calib.use_lstsq"))
        form.addRow("", self.lstsq_check)

        hint = QLabel(self._t("calib.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.report = QTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report, 1)

        buttons = QDialogButtonBox()
        self.run_btn = QPushButton(self._t("calib.run"))
        self.run_btn.clicked.connect(self._run)
        buttons.addButton(self.run_btn, QDialogButtonBox.ButtonRole.ActionRole)
        self.apply_btn = QPushButton(self._t("calib.apply_scene"))
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply)
        buttons.addButton(self.apply_btn, QDialogButtonBox.ButtonRole.ApplyRole)
        close_btn = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        close_btn.setText(self._t("dialog.close"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_reference(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("calib.reference_image"),
            self.ref_edit.text() or "",
            "Images (*.png *.tif *.tiff *.jpg *.jpeg *.bmp)",
        )
        if path:
            self.ref_edit.setText(path)

    def _run(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        ref = self.ref_edit.text().strip()
        if not ref:
            QMessageBox.warning(
                self,
                self._t("calib.reference_missing_title"),
                self._t("calib.reference_missing_msg"),
            )
            return
        try:
            roi = parse_roi(self.roi_edit.text())
            dark = parse_roi(self.dark_roi_edit.text()) if self.dark_roi_edit.text().strip() else None
        except ValueError as exc:
            QMessageBox.warning(self, self._t("calib.roi_error_title"), str(exc))
            return

        settings = RenderSettings(
            use_fallback=True,
            preview_scale=0.5,
            spp=4,
            light_samples=8,
            sensor_noise=False,
            seed=0,
        )
        cancellation = RenderCancellation()
        progress = RenderProgressDialog(
            self._t("calib.title"),
            cancellation,
            self,
            indeterminate=False,
            start_label=self._t("dialog.starting"),
            cancel_label=self._t("dialog.cancel"),
            cancelling_label=self._t("dialog.cancelling"),
        )
        progress.show()
        self.run_btn.setEnabled(False)
        self.report.setPlainText(self._t("calib.running"))

        def on_progress(cur: int, tot: int, msg: str) -> None:
            progress.update_progress(cur, tot, msg)

        def cleanup() -> None:
            progress.mark_finished()
            progress.close()
            self.run_btn.setEnabled(True)
            self._thread = None

        def on_finished(result: CalibrationResult) -> None:
            cleanup()
            self._last_result = result
            self.apply_btn.setEnabled(True)
            self._show_report(result)

        def on_failed(msg: str) -> None:
            cleanup()
            QMessageBox.critical(self, self._t("calib.failed"), msg)

        def on_cancelled() -> None:
            cleanup()
            self.report.setPlainText(self._t("calib.cancelled"))

        self._thread, _ = run_calibration_in_thread(
            self,
            self._state.scene,
            ref,
            roi=roi,
            dark_roi=dark,
            fit_radiance_scale=self.fit_scale.isChecked(),
            fit_black_level=self.fit_black.isChecked(),
            fit_quantum_efficiency=self.fit_qe.isChecked(),
            use_lstsq=self.lstsq_check.isChecked(),
            settings=settings,
            on_finished=on_finished,
            on_failed=on_failed,
            on_cancelled=on_cancelled,
            on_progress=on_progress,
            cancellation=cancellation,
        )

    def _show_report(self, result: CalibrationResult) -> None:
        b, a = result.before, result.after
        f = result.fit
        lines = [
            f"Reference: {result.reference_path}",
            f"Engine: {result.render_engine}",
            "",
            self._t("calib.report.before"),
            f"  mean ref={b.mean_reference:.2f}  sim={b.mean_simulated:.2f}  "
            f"err={b.mean_error:+.2f}",
            f"  RMSE={b.rmse:.2f}  r={b.correlation:.4f}  n={b.n_pixels}",
            "",
            self._t("calib.report.after"),
            f"  mean ref={a.mean_reference:.2f}  sim={a.mean_simulated:.2f}  "
            f"err={a.mean_error:+.2f}",
            f"  RMSE={a.rmse:.2f}  r={a.correlation:.4f}",
            "",
            self._t("calib.report.fit"),
        ]
        if f.radiance_scale is not None:
            lines.append(f"  radiance_scale = {f.radiance_scale:.6g}")
        if f.black_level_dn is not None:
            lines.append(f"  black_level_dn = {f.black_level_dn:.2f}")
        if f.quantum_efficiency is not None:
            lines.append(f"  quantum_efficiency = {f.quantum_efficiency:.4f}")
        for note in result.notes:
            lines.append(self._t("calib.report.note", note=note))
        lines.append("")
        lines.append(self._t("calib.report.apply_hint"))
        self.report.setPlainText("\n".join(lines))

    def _apply(self) -> None:
        if self._last_result is None:
            return
        new_scene = apply_calibration(self._state.scene, self._last_result.fit)
        self._state.replace_scene(new_scene)
        QMessageBox.information(
            self,
            self._t("calib.applied_title"),
            self._t("calib.applied_msg"),
        )

    def _t(self, key: str, **kwargs: object) -> str:
        return self._i18n.text(key, **kwargs)
