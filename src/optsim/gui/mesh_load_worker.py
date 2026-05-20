"""Background worker to list mesh parts without blocking the UI."""

from __future__ import annotations

import traceback

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ..io.mesh_loader import list_mesh_parts


class MeshPartsWorker(QObject):
    finished = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        try:
            parts = list_mesh_parts(self._path)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            return
        self.finished.emit(parts)


def run_list_parts_in_thread(
    parent: QObject,
    path: str,
    on_finished,
    on_failed,
) -> tuple[QThread, MeshPartsWorker]:
    thread = QThread(parent)
    worker = MeshPartsWorker(path)
    worker.moveToThread(thread)
    thread._optsim_worker = worker  # type: ignore[attr-defined]
    thread.started.connect(worker.run)
    worker.finished.connect(on_finished)
    worker.failed.connect(on_failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker
