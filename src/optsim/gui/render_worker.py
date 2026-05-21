"""Background worker thread that runs the renderer without blocking the UI."""

from __future__ import annotations

import logging
import traceback

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ..domain import Scene
from ..render import Renderer, RenderResult, RenderSettings
from ..render.cancellation import RenderCancellation, RenderCancelled

_log = logging.getLogger(__name__)


class RenderWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(int, int, str)

    def __init__(
        self,
        scene: Scene,
        settings: RenderSettings,
        cancellation: RenderCancellation | None = None,
    ) -> None:
        super().__init__()
        self._scene = scene
        self._settings = settings
        self._cancellation = cancellation or RenderCancellation()

    @property
    def cancellation(self) -> RenderCancellation:
        return self._cancellation

    def run(self) -> None:
        _log.info(
            "RenderWorker.run starting (spp=%d, fallback=%s, scale=%.2f)",
            self._settings.spp,
            self._settings.use_fallback,
            self._settings.preview_scale,
        )

        def on_progress(current: int, total: int, message: str) -> None:
            self.progress.emit(current, total, message)

        settings = RenderSettings(
            **{
                **self._settings.__dict__,
                "cancellation": self._cancellation,
                "progress_callback": on_progress,
            }
        )
        try:
            renderer = Renderer(settings)
            result: RenderResult = renderer.render(self._scene)
        except RenderCancelled:
            _log.info("RenderWorker.run cancelled")
            self.cancelled.emit()
            return
        except Exception as exc:
            _log.exception("RenderWorker.run failed")
            self.failed.emit(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            return
        _log.info(
            "RenderWorker.run done: shape=%s, mean=%.1f",
            getattr(result.digital, "shape", "?"),
            float(getattr(result.digital, "mean", lambda: 0.0)()),
        )
        self.finished.emit(result)


def run_render_in_thread(
    parent: QObject,
    scene: Scene,
    settings: RenderSettings,
    on_finished,
    on_failed,
    *,
    on_cancelled=None,
    on_progress=None,
    cancellation: RenderCancellation | None = None,
) -> tuple[QThread, RenderWorker]:
    """Run a render on a worker QThread without blocking the UI.

    Returns ``(thread, worker)`` so the caller can wire a progress dialog
    to ``worker.cancellation`` and ``worker.progress``.
    """
    thread = QThread(parent)
    worker = RenderWorker(scene, settings, cancellation=cancellation)
    worker.moveToThread(thread)
    thread._optsim_worker = worker  # type: ignore[attr-defined]
    thread._optsim_on_finished = on_finished  # type: ignore[attr-defined]
    thread._optsim_on_failed = on_failed  # type: ignore[attr-defined]

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
    _log.debug("Render thread started (id=%s)", id(thread))
    return thread, worker
