"""Background worker for reference-image calibration."""

from __future__ import annotations

import logging
import traceback

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ..analysis.calibration import run_calibration
from ..domain import Scene
from ..render import RenderSettings
from ..render.cancellation import RenderCancellation, RenderCancelled

_log = logging.getLogger(__name__)


class CalibrationWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(int, int, str)

    def __init__(
        self,
        scene: Scene,
        reference_path: str,
        *,
        roi,
        dark_roi,
        fit_radiance_scale: bool,
        fit_black_level: bool,
        fit_quantum_efficiency: bool,
        use_lstsq: bool,
        settings: RenderSettings,
        cancellation: RenderCancellation | None = None,
    ) -> None:
        super().__init__()
        self._scene = scene
        self._reference_path = reference_path
        self._roi = roi
        self._dark_roi = dark_roi
        self._fit_radiance_scale = fit_radiance_scale
        self._fit_black_level = fit_black_level
        self._fit_qe = fit_quantum_efficiency
        self._use_lstsq = use_lstsq
        self._settings = settings
        self._cancellation = cancellation or RenderCancellation()

    def run(self) -> None:
        if self._cancellation.is_requested():
            self.cancelled.emit()
            return
        self.progress.emit(0, 3, "Rendering baseline...")
        try:
            result = run_calibration(
                self._scene,
                self._reference_path,
                roi=self._roi,
                dark_roi=self._dark_roi,
                fit_radiance_scale=self._fit_radiance_scale,
                fit_black_level=self._fit_black_level,
                fit_quantum_efficiency=self._fit_qe,
                use_lstsq_offset=self._use_lstsq,
                render_settings=self._settings,
            )
        except RenderCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:
            _log.exception("Calibration failed")
            self.failed.emit(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            return
        self.progress.emit(3, 3, "Calibration complete")
        self.finished.emit(result)


def run_calibration_in_thread(
    parent: QObject,
    scene: Scene,
    reference_path: str,
    *,
    roi,
    dark_roi,
    fit_radiance_scale: bool,
    fit_black_level: bool,
    fit_quantum_efficiency: bool,
    use_lstsq: bool,
    settings: RenderSettings,
    on_finished,
    on_failed,
    on_cancelled=None,
    on_progress=None,
    cancellation: RenderCancellation | None = None,
) -> tuple[QThread, CalibrationWorker]:
    thread = QThread(parent)
    worker = CalibrationWorker(
        scene,
        reference_path,
        roi=roi,
        dark_roi=dark_roi,
        fit_radiance_scale=fit_radiance_scale,
        fit_black_level=fit_black_level,
        fit_quantum_efficiency=fit_quantum_efficiency,
        use_lstsq=use_lstsq,
        settings=settings,
        cancellation=cancellation,
    )
    worker.moveToThread(thread)
    thread._optsim_worker = worker  # type: ignore[attr-defined]

    thread.started.connect(worker.run)
    worker.finished.connect(on_finished)
    worker.failed.connect(on_failed)
    if on_cancelled:
        worker.cancelled.connect(on_cancelled)
    if on_progress:
        worker.progress.connect(on_progress)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.cancelled.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker
