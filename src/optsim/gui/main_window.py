"""Main application window."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThread, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence, QShowEvent
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..domain import (
    Camera,
    Scene,
    Target,
    TelecentricLens,
)
from ..domain.common import Transform
from ..domain.target import Primitive, PrimitiveKind, TargetMesh, TargetPrimitive
from ..io import load_project, save_image, save_project
from ..io.mesh_loader import supported_mesh_extensions
from ..presets import (
    build_light_preset,
    get_material_for_role,
    light_preset_names,
)
from ..render import RenderSettings
from ..render.cancellation import RenderCancellation
from .calibration_dialog import CalibrationDialog
from .comparison_view import ComparisonView
from .environment_dialog import EnvironmentDialog
from .i18n import LanguageManager
from .progress_dialog import RenderProgressDialog, TaskProgressDialog
from .property_panel import PropertyPanel
from .render_worker import run_render_in_thread
from .result_view import ResultView
from .scene_state import SceneState
from .scene_tree import SceneTree
from .sweep_dialog import SweepDialog
from .ui_theme import configure_main_window_docks, resize_main_window_docks

_log = logging.getLogger(__name__)


def _make_default_scene() -> Scene:
    return Scene(
        name="new_scene",
        camera=Camera(
            name="cam",
            transform=Transform(position=(0.0, 0.0, 120.0), rotation_deg=(0.0, 0.0, 0.0)),
        ),
        lens=TelecentricLens(magnification=0.5, working_distance_mm=80.0, na=0.04),
        lights=[build_light_preset("ring_above")],
        targets=[
            Target(
                name="widget",
                transform=Transform(position=(0.0, 0.0, 5.0)),
                geometry=TargetPrimitive(primitive=Primitive(kind=PrimitiveKind.cube,
                                                             size_mm=(30.0, 20.0, 10.0))),
                material=get_material_for_role("widget"),
            ),
            Target(
                name="stage",
                transform=Transform(position=(0.0, 0.0, -1.0)),
                geometry=TargetPrimitive(primitive=Primitive(kind=PrimitiveKind.plane,
                                                             size_mm=(120.0, 120.0, 1.0))),
                material=get_material_for_role("stage"),
            ),
        ],
    )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.i18n = LanguageManager(default="ja")
        self.setWindowTitle(self.i18n.text("app.title"))
        self.resize(1680, 960)
        self._docks_sized = False

        self.state = SceneState(_make_default_scene())
        self._render_thread: QThread | None = None
        self._ui_locked = False
        self._lockable_actions: list[QAction] = []
        self._live_preview = False
        self._live_pending = False
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(350)  # ms debounce
        self._live_timer.timeout.connect(self._fire_live_preview)
        self.state.sceneChanged.connect(self._on_scene_changed)

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self.i18n.languageChanged.connect(self._on_language_changed)
        self.statusBar().showMessage(self.i18n.text("status.ready"))

    def _build_ui(self) -> None:
        try:
            from .viewport import Viewport3D
            self.viewport = Viewport3D(self.state)
        except Exception as exc:
            self.viewport = QWidget()
            layout = QVBoxLayout(self.viewport)
            from PyQt6.QtWidgets import QLabel
            layout.addWidget(QLabel(f"3D viewport を初期化できません:\n{exc}"))

        self.result_view = ResultView()
        self.comparison_view = ComparisonView()
        self.tabs = QTabWidget()
        self.tabs.addTab(self.viewport, self.i18n.text("tab.scene"))
        self.tabs.addTab(self.result_view, self.i18n.text("tab.render"))
        self.tabs.addTab(self.comparison_view, self.i18n.text("tab.compare"))
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)

        self.setCentralWidget(self.tabs)

        self.scene_tree = SceneTree(self.state, self.i18n)
        self._dock_left = QDockWidget(self.i18n.text("dock.scene"), self)
        self._dock_left.setObjectName("dockScene")
        self._dock_left.setWidget(self.scene_tree)
        self._dock_left.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock_left)

        self.property_panel = PropertyPanel(self.state, self.i18n)
        self._dock_right = QDockWidget(self.i18n.text("dock.properties"), self)
        self._dock_right.setObjectName("dockProperties")
        self._dock_right.setWidget(self.property_panel)
        self._dock_right.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock_right)
        configure_main_window_docks(self, language=self.i18n.code)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._docks_sized:
            self._docks_sized = True
            QTimer.singleShot(
                0, lambda: resize_main_window_docks(self, language=self.i18n.code)
            )

    def _t(self, key: str, **kwargs: object) -> str:
        return self.i18n.text(key, **kwargs)

    def _on_language_changed(self, _language: str) -> None:
        self._retranslate_ui()
        configure_main_window_docks(self, language=self.i18n.code)
        QTimer.singleShot(
            0, lambda: resize_main_window_docks(self, language=self.i18n.code)
        )

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self._t("app.title"))
        self.tabs.setTabText(0, self._t("tab.scene"))
        self.tabs.setTabText(1, self._t("tab.render"))
        self.tabs.setTabText(2, self._t("tab.compare"))
        self._dock_left.setWindowTitle(self._t("dock.scene"))
        self._dock_right.setWindowTitle(self._t("dock.properties"))
        self._menu_file.setTitle(self._t("menu.file"))
        self._menu_add.setTitle(self._t("menu.add"))
        self._menu_render.setTitle(self._t("menu.render"))
        self._menu_analysis.setTitle(self._t("menu.analysis"))
        self._menu_language.setTitle(self._t("menu.language"))
        self._menu_help.setTitle(self._t("menu.help"))
        self._act_new.setText(self._t("action.new_scene"))
        self._act_open.setText(self._t("action.open_project"))
        self._act_save.setText(self._t("action.save_project"))
        self._act_save_img.setText(self._t("action.save_last_render"))
        self._act_quit.setText(self._t("action.quit"))
        self._act_mesh.setText(self._t("action.import_mesh_multi"))
        self._act_mesh_quick.setText(self._t("action.import_mesh_single"))
        self._act_render_fast.setText(self._t("action.quick_preview"))
        self._act_render.setText(self._t("action.full_render"))
        self._act_sweep.setText(self._t("action.parameter_sweep"))
        self._act_calib.setText(self._t("action.calibration"))
        self._act_env.setText(self._t("action.environment_check"))
        self._act_about.setText(self._t("action.about"))
        self._act_tb_preview.setText("Preview (F5)" if self.i18n.code == "en" else "プレビュー (F5)")
        self._act_tb_render.setText("Render (F6)" if self.i18n.code == "en" else "レンダー (F6)")
        self._live_action.setText(self._t("action.live_preview"))
        self._act_tb_snapshot.setText(self._t("action.snapshot"))
        self._act_lang_ja.setText(self._t("action.language.ja"))
        self._act_lang_en.setText(self._t("action.language.en"))
        for action, preset_name in self._light_preset_actions:
            action.setText(self._t("add.light_preset", name=preset_name))
        for action, kind in self._primitive_actions:
            action.setText(
                self._t(
                    "add.primitive_target",
                    name=self._t(f"primitive.{kind.value}"),
                )
            )

    def _register_lockable(self, *actions: QAction) -> None:
        self._lockable_actions.extend(actions)

    def _set_operation_locked(self, locked: bool) -> None:
        """Disable scene editing and destructive actions during long tasks."""
        if self._ui_locked == locked:
            return
        self._ui_locked = locked
        self.tabs.setEnabled(not locked)
        self._dock_left.setEnabled(not locked)
        self._dock_right.setEnabled(not locked)
        for act in self._lockable_actions:
            act.setEnabled(not locked)

    def _build_menu(self) -> None:
        menubar: QMenuBar = self.menuBar()
        self._menu_file = menubar.addMenu(self._t("menu.file"))

        self._act_new = QAction(self._t("action.new_scene"), self)
        self._act_new.setShortcut(QKeySequence.StandardKey.New)
        self._act_new.triggered.connect(self._new_scene)
        self._menu_file.addAction(self._act_new)

        self._act_open = QAction(self._t("action.open_project"), self)
        self._act_open.setShortcut(QKeySequence.StandardKey.Open)
        self._act_open.triggered.connect(self._open_project)
        self._menu_file.addAction(self._act_open)

        self._act_save = QAction(self._t("action.save_project"), self)
        self._act_save.setShortcut(QKeySequence.StandardKey.Save)
        self._act_save.triggered.connect(self._save_project)
        self._menu_file.addAction(self._act_save)
        self._register_lockable(self._act_new, self._act_open, self._act_save)

        self._menu_file.addSeparator()
        self._act_save_img = QAction(self._t("action.save_last_render"), self)
        self._act_save_img.triggered.connect(self._save_last_image)
        self._menu_file.addAction(self._act_save_img)

        self._menu_file.addSeparator()
        self._act_quit = QAction(self._t("action.quit"), self)
        self._act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self._act_quit.triggered.connect(self.close)
        self._menu_file.addAction(self._act_quit)

        self._menu_add = menubar.addMenu(self._t("menu.add"))
        self._light_preset_actions: list[tuple[QAction, str]] = []
        for name in light_preset_names():
            act = QAction(self._t("add.light_preset", name=name), self)
            act.triggered.connect(lambda _checked=False, n=name: self._add_light_preset(n))
            self._menu_add.addAction(act)
            self._light_preset_actions.append((act, name))
        self._menu_add.addSeparator()
        self._primitive_actions: list[tuple[QAction, PrimitiveKind]] = []
        for kind, label in [
            (PrimitiveKind.cube, self._t("primitive.cube")),
            (PrimitiveKind.sphere, self._t("primitive.sphere")),
            (PrimitiveKind.cylinder, self._t("primitive.cylinder")),
            (PrimitiveKind.plane, self._t("primitive.plane")),
        ]:
            act = QAction(self._t("add.primitive_target", name=label), self)
            act.triggered.connect(lambda _c=False, k=kind: self._add_primitive_target(k))
            self._menu_add.addAction(act)
            self._primitive_actions.append((act, kind))
        self._menu_add.addSeparator()
        self._act_mesh = QAction(self._t("action.import_mesh_multi"), self)
        self._act_mesh.triggered.connect(self._import_mesh_dialog)
        self._menu_add.addAction(self._act_mesh)
        self._act_mesh_quick = QAction(self._t("action.import_mesh_single"), self)
        self._act_mesh_quick.triggered.connect(self._add_mesh_target_merged)
        self._menu_add.addAction(self._act_mesh_quick)
        self._register_lockable(self._act_mesh, self._act_mesh_quick)

        self._menu_render = menubar.addMenu(self._t("menu.render"))
        self._act_render_fast = QAction(self._t("action.quick_preview"), self)
        self._act_render_fast.setShortcut("F5")
        self._act_render_fast.triggered.connect(
            lambda: self._render(
                use_fallback=True,
                spp=4,
                light_samples=8,
                preview_scale=0.5,
                show_progress=True,
            )
        )
        self._menu_render.addAction(self._act_render_fast)
        self._act_render = QAction(self._t("action.full_render"), self)
        self._act_render.setShortcut("F6")
        self._act_render.triggered.connect(
            lambda: self._render(
                use_fallback=False,
                spp=64,
                preview_scale=1.0,
                show_progress=True,
            )
        )
        self._menu_render.addAction(self._act_render)
        self._register_lockable(self._act_render_fast, self._act_render)

        self._menu_analysis = menubar.addMenu(self._t("menu.analysis"))
        self._act_sweep = QAction(self._t("action.parameter_sweep"), self)
        self._act_sweep.triggered.connect(self._open_sweep_dialog)
        self._menu_analysis.addAction(self._act_sweep)
        self._act_calib = QAction(self._t("action.calibration"), self)
        self._act_calib.triggered.connect(self._open_calibration_dialog)
        self._menu_analysis.addAction(self._act_calib)

        self._menu_language = menubar.addMenu(self._t("menu.language"))
        self._lang_group = QActionGroup(self)
        self._lang_group.setExclusive(True)
        self._act_lang_ja = QAction(self._t("action.language.ja"), self)
        self._act_lang_ja.setCheckable(True)
        self._act_lang_en = QAction(self._t("action.language.en"), self)
        self._act_lang_en.setCheckable(True)
        self._lang_group.addAction(self._act_lang_ja)
        self._lang_group.addAction(self._act_lang_en)
        self._menu_language.addAction(self._act_lang_ja)
        self._menu_language.addAction(self._act_lang_en)
        self._act_lang_ja.setChecked(True)
        self._act_lang_ja.triggered.connect(lambda: self.i18n.set_language("ja"))
        self._act_lang_en.triggered.connect(lambda: self.i18n.set_language("en"))

        self._menu_help = menubar.addMenu(self._t("menu.help"))
        self._act_env = QAction(self._t("action.environment_check"), self)
        self._act_env.triggered.connect(self._show_environment_check)
        self._menu_help.addAction(self._act_env)
        self._act_about = QAction(self._t("action.about"), self)
        self._act_about.triggered.connect(self._show_about)
        self._menu_help.addAction(self._act_about)

    def _build_toolbar(self) -> None:
        self._toolbar = QToolBar("Main", self)
        self._toolbar.setMovable(False)
        self.addToolBar(self._toolbar)
        self._act_tb_preview = self._toolbar.addAction(
            "Preview (F5)",
            lambda: self._render(
                use_fallback=True,
                spp=4,
                light_samples=8,
                preview_scale=0.5,
                show_progress=True,
            ),
        )
        self._act_tb_render = self._toolbar.addAction(
            "Render (F6)",
            lambda: self._render(
                use_fallback=False,
                spp=64,
                preview_scale=1.0,
                show_progress=True,
            ),
        )
        self._register_lockable(self._act_tb_preview, self._act_tb_render)
        self._toolbar.addSeparator()
        self._live_action = QAction(self._t("action.live_preview"), self)
        self._live_action.setCheckable(True)
        self._live_action.toggled.connect(self._toggle_live_preview)
        self._toolbar.addAction(self._live_action)
        self._register_lockable(self._live_action)
        self._toolbar.addSeparator()
        self._act_tb_snapshot = self._toolbar.addAction(
            self._t("action.snapshot"),
            self._add_snapshot,
        )

    def _new_scene(self) -> None:
        self.state.replace_scene(_make_default_scene())
        self.statusBar().showMessage(self._t("status.new_scene"))

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open project",
                                              str(Path.cwd()),
                                              "Scene (*.yaml *.yml *.json)")
        if not path:
            return
        try:
            scene = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self.state.replace_scene(scene)
        self.statusBar().showMessage(f"Loaded {path}")

    def _save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save project",
                                              str(Path.cwd() / "scene.yaml"),
                                              "Scene (*.yaml *.yml *.json)")
        if not path:
            return
        try:
            save_project(self.state.scene, path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved {path}")

    def _save_last_image(self) -> None:
        if self.result_view._last_result is None:
            QMessageBox.information(self, "No image", "まずレンダリングを実行してください。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save image", str(Path.cwd() / "render.png"),
            "Image (*.png *.tiff *.exr)"
        )
        if not path:
            return
        try:
            save_image(self.result_view._last_result.digital, path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved {path}")

    def _add_light_preset(self, name: str) -> None:
        light = build_light_preset(name)
        base_name = light.name
        existing = {lg.name for lg in self.state.scene.lights}
        i = 1
        while light.name in existing:
            light.name = f"{base_name}_{i}"
            i += 1
        self.state.scene.lights.append(light)
        self.state.notify_changed()
        self.statusBar().showMessage(f"Added light preset '{name}'")

    def _add_primitive_target(self, kind: PrimitiveKind) -> None:
        existing = {t.name for t in self.state.scene.targets}
        base = kind.value
        name = base
        i = 1
        while name in existing:
            name = f"{base}_{i}"
            i += 1
        role = "stage" if kind is PrimitiveKind.plane else "widget"
        target = Target(
            name=name,
            transform=Transform(position=(0.0, 0.0, 5.0)),
            geometry=TargetPrimitive(primitive=Primitive(kind=kind)),
            material=get_material_for_role(role),
        )
        self.state.scene.targets.append(target)
        self.state.notify_changed()

    def _import_mesh_dialog(self) -> None:
        if self._render_thread is not None and self._render_thread.isRunning():
            QMessageBox.information(
                self,
                self._t("mesh.rendering_title"),
                self._t("mesh.rendering_locked"),
            )
            return
        from .mesh_import_dialog import MeshImportDialog

        dlg = MeshImportDialog(self.i18n, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        from collections import defaultdict

        from ..io.mesh_loader import union_bounds_for_parts, workspace_placement_offset

        existing = {t.name for t in self.state.scene.targets}
        added = 0
        by_file: dict[tuple[str, float], list[Target]] = defaultdict(list)
        for target in dlg.imported_targets:
            name = target.name
            i = 1
            while name in existing:
                name = f"{target.name}_{i}"
                i += 1
            target.name = name
            existing.add(name)
            if isinstance(target.geometry, TargetMesh):
                geom = target.geometry
                by_file[(geom.path, float(geom.scale))].append(target)
            self.state.scene.targets.append(target)
            added += 1

        for (path, scale), group in by_file.items():
            part_names = [t.geometry.part_name for t in group]
            try:
                bmin, bmax = union_bounds_for_parts(
                    path, part_names, scale=scale
                )
                offset = workspace_placement_offset(bmin, bmax)
            except Exception:
                offset = (0.0, 0.0, 5.0)
            for target in group:
                target.transform = Transform(
                    position=offset,
                    rotation_deg=target.transform.rotation_deg,
                )

        self._refresh_viewport_after_mesh_import(added)

    def _refresh_viewport_after_mesh_import(self, added: int) -> None:
        """Update the 3D view without blocking the UI (STEP can be slow)."""
        if added <= 0:
            return
        if not hasattr(self.viewport, "refresh_async"):
            self.state.notify_changed()
            self.statusBar().showMessage(f"Imported {added} mesh target(s).")
            return

        progress = TaskProgressDialog(
            self._t("mesh.title"),
            self._t("mesh.refreshing_3d"),
            self,
        )
        progress.show()
        self._set_operation_locked(True)
        was_live = self._live_preview
        self._live_timer.stop()

        try:
            self.state.sceneChanged.disconnect(self.viewport.refresh)
        except TypeError:
            pass

        def on_progress(current: int, total: int, message: str) -> None:
            progress.set_progress(current, total, message)
            QApplication.processEvents()

        def _done() -> None:
            progress.close()
            self._set_operation_locked(False)
            try:
                self.state.sceneChanged.connect(self.viewport.refresh)
            except TypeError:
                pass
            self.scene_tree.rebuild()
            self.property_panel._refresh()
            from .viewport_limits import VIEWPORT_MAX_MESH_ACTORS

            msg = f"Imported {added} mesh target(s)."
            if added > VIEWPORT_MAX_MESH_ACTORS:
                msg += (
                    f" 3D view: shaded surfaces for each part "
                    f"(up to {VIEWPORT_MAX_MESH_ACTORS} at once)."
                )
            self.statusBar().showMessage(msg)
            if was_live:
                self._live_timer.start()
            QApplication.processEvents()

        QApplication.processEvents()
        self.viewport.refresh_async(_done, on_progress=on_progress)

    def _add_mesh_target_merged(self) -> None:
        exts = " ".join(f"*{ext}" for ext in supported_mesh_extensions())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open mesh", str(Path.cwd()), f"Meshes ({exts})"
        )
        if not path:
            return
        from ..domain.target import TargetMesh

        name_default = Path(path).stem
        name, ok = QInputDialog.getText(
            self, "Target name", "Name:", text=name_default
        )
        if not ok:
            return
        from ..io.mesh_loader import (
            suggest_mesh_scale_to_mm,
            union_bounds_for_parts,
            workspace_placement_offset,
        )

        scale = float(suggest_mesh_scale_to_mm(path))
        offset = (0.0, 0.0, 5.0)
        try:
            bmin, bmax = union_bounds_for_parts(path, [None], scale=scale)
            offset = workspace_placement_offset(bmin, bmax)
        except Exception:
            pass

        target = Target(
            name=name,
            transform=Transform(position=offset),
            geometry=TargetMesh(path=path, scale=scale, part_name=None),
            material=get_material_for_role("widget"),
        )
        existing = {t.name for t in self.state.scene.targets}
        if target.name in existing:
            target.name = f"{target.name}_1"
        self.state.scene.targets.append(target)
        if scale != 1.0:
            QMessageBox.information(
                self,
                self._t("mesh.unit_scale_title"),
                self._t("mesh.unit_scale_msg", scale=scale),
            )
        self._refresh_viewport_after_mesh_import(1)

    def _render(self, *, use_fallback: bool, spp: int,
                light_samples: int = 16, switch_tab: bool = True,
                preview_scale: float = 1.0,
                show_progress: bool = False,
                lock_ui: bool = True) -> None:
        if self._render_thread is not None and self._render_thread.isRunning():
            self.statusBar().showMessage("Render already in progress.")
            return

        settings = RenderSettings(
            spp=spp,
            max_depth=10 if not use_fallback else 4,
            use_fallback=use_fallback,
            light_samples=light_samples,
            preview_scale=preview_scale,
            prefer_gpu_variant=True,
            depth_of_field=True,
            max_blur_px=96,
        )
        self.statusBar().showMessage(
            f"Rendering... (spp={spp}, "
            f"{'fallback' if use_fallback else 'mitsuba'}, "
            f"scale={preview_scale:.2f})"
        )
        QApplication.processEvents()

        if lock_ui:
            self._set_operation_locked(True)

        cancellation = RenderCancellation()
        progress_dlg: RenderProgressDialog | None = None
        if show_progress:
            progress_dlg = RenderProgressDialog(
                self._t("render.progress.title"),
                cancellation,
                self,
                indeterminate=use_fallback and preview_scale >= 0.99,
                start_label=self._t("dialog.starting"),
                cancel_label=self._t("dialog.cancel"),
                cancelling_label=self._t("dialog.cancelling"),
            )
            progress_dlg.show()
            QApplication.processEvents()

        def on_progress(current: int, total: int, message: str) -> None:
            if progress_dlg is not None:
                progress_dlg.update_progress(current, total, message)

        def _cleanup_render_ui() -> None:
            if progress_dlg is not None:
                progress_dlg.mark_finished()
                progress_dlg.close()
            if lock_ui:
                self._set_operation_locked(False)

        def on_finished(result: Any) -> None:
            _cleanup_render_ui()
            _log.info(
                "on_finished received result (shape=%s)",
                getattr(result.digital, "shape", "?"),
            )
            try:
                self.result_view.show_result(result)
                if switch_tab:
                    self.tabs.setCurrentWidget(self.result_view)
                engine = result.extras.get("engine", "?") if result.extras else "?"
                self.statusBar().showMessage(
                    f"Done: {result.width}x{result.height} ({engine})"
                )
            except Exception as exc:
                # Don't let a UI-rendering bug leave the user looking at a
                # stale "Rendering..." status with no image.
                _log.exception("on_finished: failed to display result")
                self.statusBar().showMessage(
                    f"Render done but display failed: {exc}"
                )
                QMessageBox.critical(
                    self,
                    "Display failed",
                    f"Render produced an image but it could not be "
                    f"displayed:\n{exc}\n\n{traceback.format_exc()}",
                )
            finally:
                self._render_thread = None
                if self._live_pending and self._live_preview:
                    self._live_pending = False
                    self._live_timer.start()

        def on_failed(msg: str) -> None:
            _cleanup_render_ui()
            _log.error("Render failed: %s", msg)
            self.statusBar().showMessage(f"Render failed: {msg[:80]}")
            self._render_thread = None
            if not self._live_preview:
                QMessageBox.critical(self, "Render failed", msg)

        def on_cancelled() -> None:
            _cleanup_render_ui()
            self.statusBar().showMessage("Render cancelled.")
            self._render_thread = None

        thread, _worker = run_render_in_thread(
            self,
            self.state.scene,
            settings,
            on_finished,
            on_failed,
            on_cancelled=on_cancelled,
            on_progress=on_progress,
            cancellation=cancellation,
        )
        self._render_thread = thread

    def _toggle_live_preview(self, on: bool) -> None:
        self._live_preview = on
        if on:
            self.statusBar().showMessage(self._t("status.live_on"))
            self._live_timer.start()
        else:
            self._live_timer.stop()
            self._live_pending = False
            self.statusBar().showMessage(self._t("status.live_off"))

    def _on_scene_changed(self) -> None:
        if not self._live_preview:
            return
        if self._render_thread is not None and self._render_thread.isRunning():
            # Coalesce: mark pending; will fire after the current render finishes.
            self._live_pending = True
            return
        self._live_timer.start()

    def _fire_live_preview(self) -> None:
        if not self._live_preview:
            return
        if self._render_thread is not None and self._render_thread.isRunning():
            self._live_pending = True
            return
        self._render(
            use_fallback=True,
            spp=2,
            light_samples=4,
            switch_tab=False,
            preview_scale=0.25,
            show_progress=False,
            lock_ui=True,
        )

    def _add_snapshot(self) -> None:
        result = self.result_view._last_result
        if result is None:
            QMessageBox.information(self, "No image", "まずレンダリングを実行してください。")
            return
        default_label = f"snap-{len(self.comparison_view._snapshots) + 1}"
        label, ok = QInputDialog.getText(
            self, "Snapshot label", "Label:", text=default_label
        )
        if not ok or not label:
            return
        self.comparison_view.add_snapshot(label, result)
        self.tabs.setCurrentWidget(self.comparison_view)
        self.statusBar().showMessage(f"Snapshot '{label}' added.")

    def _open_calibration_dialog(self) -> None:
        dlg = CalibrationDialog(self.state, self.i18n, self)
        dlg.exec()

    def _open_sweep_dialog(self) -> None:
        dlg = SweepDialog(
            self.state.scene,
            comparison_view=self.comparison_view,
            i18n=self.i18n,
            parent=self,
        )
        dlg.exec()
        if dlg._last_result and dlg.compare_check.isChecked():
            self.tabs.setCurrentWidget(self.comparison_view)

    def _show_environment_check(self) -> None:
        EnvironmentDialog(self.i18n, self).exec()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "Optical Simulator",
            "<b>Optical Simulator</b><br>"
            "Machine-vision imaging simulator with telecentric lens model.<br><br>"
            "Renderer: Mitsuba 3 / trimesh fallback<br>"
            "GUI: PyQt6 + PyVista",
        )
