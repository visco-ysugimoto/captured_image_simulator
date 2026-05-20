"""Background worker to load target mesh bounds for the 3D viewport."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ..io.mesh_loader import load_all_part_bounds, load_mesh, load_mesh_bounds
from .viewport_limits import (
    VIEWPORT_SURFACE_HARD_CAP,
    VIEWPORT_SURFACE_MAX_FACES,
    VIEWPORT_SURFACE_MAX_FACES_SINGLE,
)
from .viewport_mesh_util import simplify_for_viewport


@dataclass(frozen=True)
class PreloadedTargetMesh:
    """Viewport payload: bounds plus simplified surface (local coords)."""

    target_name: str
    bounds_min: np.ndarray
    bounds_max: np.ndarray
    vertices: np.ndarray | None = None
    faces: np.ndarray | None = None


class ViewportRefreshWorker(QObject):
    finished = pyqtSignal()
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)

    def __init__(self, specs: list[tuple[str, str, str | None, float]]) -> None:
        super().__init__()
        # (target_name, path, part_name, scale)
        self._specs = specs
        self.result: dict[str, PreloadedTargetMesh] = {}

    def run(self) -> None:
        self.result = {}
        total = len(self._specs)
        max_faces = (
            VIEWPORT_SURFACE_MAX_FACES_SINGLE
            if total <= 1
            else VIEWPORT_SURFACE_MAX_FACES
        )
        try:
            by_path_scale: dict[tuple[str, float], list[tuple[str, str | None]]] = {}
            for name, path, part_name, scale in self._specs:
                by_path_scale.setdefault((path, scale), []).append((name, part_name))

            done = 0
            for (path, scale), entries in by_path_scale.items():
                self.progress.emit(done, total, f"Reading {Path(path).name}...")
                all_bounds = load_all_part_bounds(path, scale=scale)

                for name, part_name in entries:
                    if done >= VIEWPORT_SURFACE_HARD_CAP:
                        break
                    done += 1
                    self.progress.emit(
                        done,
                        total,
                        f"Surface mesh {name} ({done}/{total})...",
                    )
                    verts: np.ndarray | None = None
                    faces: np.ndarray | None = None
                    try:
                        key = (
                            part_name
                            if part_name not in (None, "default")
                            else "default"
                        )
                        if key not in all_bounds:
                            if len(all_bounds) == 1:
                                key = next(iter(all_bounds))
                            else:
                                bmin, bmax = load_mesh_bounds(
                                    path, part_name=part_name, scale=scale
                                )
                                mesh = load_mesh(
                                    path, part_name=part_name, scale=scale
                                )
                                verts, faces = simplify_for_viewport(
                                    mesh.vertices,
                                    mesh.faces,
                                    max_faces=max_faces,
                                )
                                self.result[name] = PreloadedTargetMesh(
                                    name, bmin, bmax, verts, faces
                                )
                                continue
                        bmin, bmax = all_bounds[key]
                        mesh = load_mesh(path, part_name=part_name, scale=scale)
                        verts, faces = simplify_for_viewport(
                            mesh.vertices,
                            mesh.faces,
                            max_faces=max_faces,
                        )
                    except Exception:
                        continue
                    self.result[name] = PreloadedTargetMesh(
                        name, bmin, bmax, verts, faces
                    )
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            return
        self.finished.emit()


def run_viewport_refresh_in_thread(
    parent: QObject,
    specs: list[tuple[str, str, str | None, float]],
    on_finished,
    on_failed,
    *,
    on_progress=None,
) -> tuple[QThread, ViewportRefreshWorker]:
    thread = QThread(parent)
    worker = ViewportRefreshWorker(specs)
    worker.moveToThread(thread)
    thread._optsim_worker = worker  # type: ignore[attr-defined]

    def _emit_result() -> None:
        on_finished(worker.result)

    thread.started.connect(worker.run)
    worker.finished.connect(_emit_result)
    worker.failed.connect(on_failed)
    if on_progress is not None:
        worker.progress.connect(on_progress)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker
