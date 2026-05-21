"""3D scene preview widget using PyVista embedded in PyQt6.

Imported CAD targets are drawn as simplified shaded surfaces (one per
part, up to a safety cap). Primitives, lights, and the camera use simple
wireframe glyphs. Full-detail shading is via Preview (F5).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ..domain import (
    BarLight,
    CoaxialLight,
    DomeLight,
    PointLight,
    RectAreaLight,
    RingLight,
)
from ..domain.light import Backlight
from ..domain.target import TargetMesh, TargetPrimitive
from .scene_state import SceneState
from .viewport_limits import VIEWPORT_MAX_MESH_ACTORS
from .viewport_mesh_util import faces_to_vtk_cells
from .viewport_refresh_worker import PreloadedTargetMesh, run_viewport_refresh_in_thread


class Viewport3D(QWidget):
    def __init__(self, state: SceneState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        try:
            import pyvista as pv
            from pyvistaqt import QtInteractor
        except ImportError as exc:
            raise RuntimeError(
                "pyvista / pyvistaqt are required for the 3D viewport. "
                "Install GUI extras with `pip install -e .[gui]`."
            ) from exc

        self._pv = pv
        self.plotter = QtInteractor(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plotter.interactor)

        self.plotter.set_background("white")
        self.plotter.show_axes()
        self.plotter.show_grid()

        self.state.sceneChanged.connect(self.refresh)
        self.state.selectionChanged.connect(lambda *_: self.refresh())

        self._actors: dict[str, object] = {}
        self._mesh_display_cache: dict[str, PreloadedTargetMesh] = {}
        self._refresh_thread: QThread | None = None
        self._incr_mesh_queue: list = []
        self.refresh()

    def refresh(self) -> None:
        if self._has_mesh_targets():
            specs = self._mesh_target_specs()
            missing = [
                name for name, *_ in specs if name not in self._mesh_display_cache
            ]
            if missing and (
                self._refresh_thread is None or not self._refresh_thread.isRunning()
            ):
                self.refresh_async()
                return
        self._refresh_immediate()

    def _refresh_immediate(self) -> None:
        try:
            self.plotter.clear_actors()
            self._actors.clear()
            mesh_targets = [
                t
                for t in self.state.scene.targets
                if t.visible and isinstance(t.geometry, TargetMesh)
            ]
            if len(mesh_targets) > 12:
                self._incr_mesh_queue = list(mesh_targets)
                self._add_lights()
                self._add_camera()
                for t in self.state.scene.targets:
                    if t.visible and not isinstance(t.geometry, TargetMesh):
                        self._add_one_target(t)
                QTimer.singleShot(0, self._add_next_mesh_surface)
                return
            self._add_targets()
            self._add_lights()
            self._add_camera()
            self.plotter.reset_camera()
            if hasattr(self.plotter, "render"):
                self.plotter.render()
        except Exception:
            pass
        QApplication.processEvents()

    def _add_next_mesh_surface(self) -> None:
        if not self._incr_mesh_queue:
            try:
                self.plotter.reset_camera()
                if hasattr(self.plotter, "render"):
                    self.plotter.render()
            except Exception:
                pass
            QApplication.processEvents()
            return
        target = self._incr_mesh_queue.pop(0)
        cached = self._cached_bounds(target.name)
        if cached is not None and cached.vertices is not None:
            self._add_one_target(target, surface_style=True)
        QApplication.processEvents()
        QTimer.singleShot(0, self._add_next_mesh_surface)

    def _mesh_target_specs(self) -> list[tuple[str, str, str | None, float]]:
        specs: list[tuple[str, str, str | None, float]] = []
        for target in self.state.scene.targets:
            if not target.visible:
                continue
            if isinstance(target.geometry, TargetMesh):
                specs.append(
                    (
                        target.name,
                        target.geometry.path,
                        target.geometry.part_name,
                        float(target.geometry.scale),
                    )
                )
        return specs

    def _has_mesh_targets(self) -> bool:
        return bool(self._mesh_target_specs())

    def refresh_async(
        self,
        on_complete: Callable[[], None] | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> None:
        """Load mesh bounds in a worker thread, then refresh on the UI thread."""
        specs = self._mesh_target_specs()
        if not specs:
            self._refresh_immediate()
            if on_complete is not None:
                on_complete()
            return

        if self._refresh_thread is not None and self._refresh_thread.isRunning():
            if on_complete is not None:
                prev = getattr(self, "_pending_on_complete", None)
                if prev is None:

                    def chained() -> None:
                        on_complete()

                    self._pending_on_complete = chained
                else:

                    def chained() -> None:
                        prev()
                        on_complete()

                    self._pending_on_complete = chained
            return

        def on_finished(preloaded: object) -> None:
            self._refresh_thread = None
            self._mesh_display_cache.update(preloaded)  # type: ignore[arg-type]
            self._refresh_immediate()
            pending = getattr(self, "_pending_on_complete", None)
            self._pending_on_complete = None
            if on_complete is not None:
                on_complete()
            if pending is not None:
                pending()

        def on_failed(_msg: str) -> None:
            self._refresh_thread = None
            self._refresh_immediate()
            pending = getattr(self, "_pending_on_complete", None)
            self._pending_on_complete = None
            if on_complete is not None:
                on_complete()
            if pending is not None:
                pending()

        self._refresh_thread, _worker = run_viewport_refresh_in_thread(
            self,
            specs,
            on_finished,
            on_failed,
            on_progress=on_progress,
        )

    def _selected(self, kind: str, name: str) -> bool:
        return self.state.selection == (kind, name)

    def _cached_bounds(self, target_name: str) -> PreloadedTargetMesh | None:
        return self._mesh_display_cache.get(target_name)

    def _world_bounds_from_cache(
        self, target, cached: PreloadedTargetMesh
    ) -> tuple[np.ndarray, np.ndarray]:
        lo = np.asarray(cached.bounds_min, dtype=np.float64)
        hi = np.asarray(cached.bounds_max, dtype=np.float64)
        corners = np.array(
            [
                [lo[0], lo[1], lo[2], 1.0],
                [hi[0], lo[1], lo[2], 1.0],
                [lo[0], hi[1], lo[2], 1.0],
                [hi[0], hi[1], lo[2], 1.0],
                [lo[0], lo[1], hi[2], 1.0],
                [hi[0], lo[1], hi[2], 1.0],
                [lo[0], hi[1], hi[2], 1.0],
                [hi[0], hi[1], hi[2], 1.0],
            ]
        )
        world = (target.transform.to_matrix() @ corners.T).T[:, :3]
        return world.min(axis=0), world.max(axis=0)

    def _bbox_mesh(self, bmin: np.ndarray, bmax: np.ndarray):
        pv = self._pv
        lo = np.asarray(bmin, dtype=np.float64)
        hi = np.asarray(bmax, dtype=np.float64)
        if np.any(hi <= lo):
            return pv.Cube(x_length=10.0, y_length=10.0, z_length=10.0)
        return pv.Box(
            bounds=(float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1]), float(lo[2]), float(hi[2]))
        )

    def _add_targets(self) -> None:
        mesh_targets = [
            t
            for t in self.state.scene.targets
            if t.visible and isinstance(t.geometry, TargetMesh)
        ]
        other_targets = [
            t
            for t in self.state.scene.targets
            if t.visible and not isinstance(t.geometry, TargetMesh)
        ]

        for target in mesh_targets:
            cached = self._cached_bounds(target.name)
            if cached is not None and cached.vertices is not None:
                self._add_one_target(target, surface_style=True)
            elif len(mesh_targets) <= VIEWPORT_MAX_MESH_ACTORS:
                self._add_one_target(target, surface_style=True)

        for target in other_targets:
            self._add_one_target(target)

    def _add_one_target(self, target, *, surface_style: bool = False) -> None:
        try:
            mesh = self._target_to_pv(target)
        except Exception:
            return
        if mesh is None:
            return
        transform = target.transform.to_matrix()
        mesh.transform(transform, inplace=True)
        color = tuple(min(1.0, c) for c in target.material.base_color)
        highlight = self._selected("target", target.name)
        is_mesh = isinstance(target.geometry, TargetMesh)
        if surface_style and is_mesh:
            actor = self.plotter.add_mesh(
                mesh,
                color=color,
                opacity=0.72,
                style="surface",
                show_edges=False,
                smooth_shading=True,
                name=f"target:{target.name}",
            )
        else:
            actor = self.plotter.add_mesh(
                mesh,
                color=color,
                opacity=1.0,
                style="surface",
                show_edges=highlight,
                edge_color=(1.0, 0.5, 0.0) if highlight else None,
                name=f"target:{target.name}",
            )
        self._actors[f"target:{target.name}"] = actor

    def _target_to_pv(self, target):
        pv = self._pv
        if isinstance(target.geometry, TargetPrimitive):
            prim = target.geometry.primitive
            if prim.kind.value == "cube":
                return pv.Cube(
                    x_length=prim.size_mm[0],
                    y_length=prim.size_mm[1],
                    z_length=prim.size_mm[2],
                )
            if prim.kind.value == "sphere":
                return pv.Sphere(radius=prim.radius_mm)
            if prim.kind.value == "cylinder":
                return pv.Cylinder(
                    radius=prim.radius_mm,
                    height=prim.size_mm[2],
                    direction=(0, 0, 1),
                )
            if prim.kind.value == "plane":
                thickness = max(float(prim.size_mm[2]), 0.05)
                return pv.Cube(
                    x_length=prim.size_mm[0],
                    y_length=prim.size_mm[1],
                    z_length=thickness,
                )
        if isinstance(target.geometry, TargetMesh):
            cached = self._cached_bounds(target.name)
            if cached is not None and cached.vertices is not None:
                return pv.PolyData(
                    cached.vertices, faces_to_vtk_cells(cached.faces)
                )
            return None
        return None

    def _add_lights(self) -> None:
        pv = self._pv
        for light in self.state.scene.lights:
            if not light.enabled:
                continue
            highlight = self._selected("light", light.name)
            color = (1.0, 0.9, 0.3) if not highlight else (1.0, 0.4, 0.0)
            pos = light.transform.position
            fwd = light.transform.forward()

            if isinstance(light, PointLight):
                glyph = pv.Sphere(radius=2.0)
            elif isinstance(light, (RectAreaLight, CoaxialLight, Backlight)):
                if isinstance(light, RectAreaLight):
                    w, h = light.width_mm, light.height_mm
                elif isinstance(light, CoaxialLight):
                    w = h = light.size_mm
                else:
                    w, h = light.width_mm, light.height_mm
                glyph = pv.Plane(i_size=w, j_size=h)
            elif isinstance(light, BarLight):
                glyph = pv.Plane(i_size=light.length_mm, j_size=light.width_mm)
            elif isinstance(light, RingLight):
                glyph = pv.Disc(
                    inner=light.inner_radius_mm,
                    outer=light.outer_radius_mm,
                    r_res=24,
                    c_res=4,
                )
            elif isinstance(light, DomeLight):
                glyph = pv.Sphere(
                    radius=light.radius_mm,
                    theta_resolution=24,
                    phi_resolution=12,
                    start_phi=0,
                    end_phi=90,
                )
            else:
                glyph = pv.Sphere(radius=2.0)

            transform = light.transform.to_matrix()
            try:
                glyph.transform(transform, inplace=True)
            except Exception:
                pass

            actor = self.plotter.add_mesh(
                glyph,
                color=color,
                opacity=0.45,
                style="wireframe" if not highlight else "surface",
                show_edges=True,
                name=f"light:{light.name}",
            )
            self._actors[f"light:{light.name}"] = actor

            arrow_end = np.array(pos) + fwd * 15.0
            arrow_pts = np.vstack([pos, arrow_end])
            arrow_line = pv.lines_from_points(arrow_pts)
            self.plotter.add_mesh(arrow_line, color=color, line_width=2)

    def _add_camera(self) -> None:
        pv = self._pv
        cam = self.state.scene.camera
        lens = self.state.scene.lens
        sensor_w = cam.sensor.width_mm
        sensor_h = cam.sensor.height_mm
        wd = lens.working_distance_mm

        body = pv.Cube(x_length=25, y_length=25, z_length=18)
        body.transform(cam.transform.to_matrix(), inplace=True)
        highlight = self._selected("camera", "camera")
        self.plotter.add_mesh(
            body,
            color=(0.4, 0.4, 0.8) if not highlight else (1.0, 0.4, 0.0),
            opacity=0.8,
            show_edges=True,
            name="camera",
        )

        mag = max(float(lens.magnification), 1e-6)
        obj_w = sensor_w / mag
        obj_h = sensor_h / mag
        local = np.array(
            [
                [-obj_w * 0.5, -obj_h * 0.5, -wd, 1.0],
                [obj_w * 0.5, -obj_h * 0.5, -wd, 1.0],
                [obj_w * 0.5, obj_h * 0.5, -wd, 1.0],
                [-obj_w * 0.5, obj_h * 0.5, -wd, 1.0],
            ]
        )
        m = cam.transform.to_matrix()
        world = (m @ local.T).T[:, :3]
        cam_origin = m[:3, 3]
        for i in range(4):
            line = pv.lines_from_points(np.vstack([cam_origin, world[i]]))
            self.plotter.add_mesh(line, color=(0.2, 0.6, 1.0), line_width=1)
        rect = pv.lines_from_points(np.vstack([world, world[0]]))
        self.plotter.add_mesh(rect, color=(0.2, 0.6, 1.0), line_width=2)
