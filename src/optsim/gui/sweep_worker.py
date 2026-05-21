"""Background worker for parameter sweeps."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Sequence
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ..analysis.sweep import run_sweep
from ..domain import Scene
from ..render import RenderSettings
from ..render.cancellation import RenderCancellation, RenderCancelled

_log = logging.getLogger(__name__)


class SweepWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(int, int, str)

    def __init__(
        self,
        scene: Scene,
        parameter: str,
        values: Sequence[Any],
        settings: RenderSettings,
        cancellation: RenderCancellation | None = None,
    ) -> None:
        super().__init__()
        self._scene = scene
        self._parameter = parameter
        self._values = list(values)
        self._settings = settings
        self._cancellation = cancellation or RenderCancellation()

    @property
    def cancellation(self) -> RenderCancellation:
        return self._cancellation

    def run(self) -> None:
        total = len(self._values)
        _log.info("SweepWorker starting: %s across %d values", self._parameter, total)

        def on_step(index: int, _total: int, value: Any, _render) -> bool:
            self.progress.emit(
                index + 1,
                total,
                f"Sweep {index + 1}/{total}: {self._parameter}={value}",
            )
            return not self._cancellation.is_requested()

        try:
            result = run_sweep(
                self._scene,
                self._parameter,
                self._values,
                settings=self._settings,
                cancellation=self._cancellation,
                on_step=on_step,
            )
        except RenderCancelled:
            _log.info("SweepWorker cancelled")
            self.cancelled.emit()
            return
        except Exception as exc:
            _log.exception("SweepWorker failed")
            self.failed.emit(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            return

        if result.cancelled:
            self.cancelled.emit()
            return
        self.finished.emit(result)


def run_sweep_in_thread(
    parent: QObject,
    scene: Scene,
    parameter: str,
    values: Sequence[Any],
    settings: RenderSettings,
    on_finished,
    on_failed,
    *,
    on_cancelled=None,
    on_progress=None,
    cancellation: RenderCancellation | None = None,
) -> tuple[QThread, SweepWorker]:
    thread = QThread(parent)
    worker = SweepWorker(scene, parameter, values, settings, cancellation=cancellation)
    worker.moveToThread(thread)
    thread._optsim_worker = worker  # type: ignore[attr-defined]

    thread.started.connect(worker.run)
    worker.finished.connect(on_finished)
    worker.failed.connect(on_failed)
    if on_cancelled is not None:
        worker.cancelled.connect(on_cancelled)
    if on_progress is not None:
        worker.progress.connect(on_progress)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.cancelled.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker
