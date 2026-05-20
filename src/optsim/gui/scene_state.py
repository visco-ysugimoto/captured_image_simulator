"""Shared scene state for the GUI, with Qt signals on mutation."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from ..domain import Scene


class SceneState(QObject):
    """Owns the editable scene and emits a signal whenever it changes."""

    sceneChanged = pyqtSignal()
    selectionChanged = pyqtSignal(str, str)

    def __init__(self, scene: Scene | None = None) -> None:
        super().__init__()
        self._scene = scene or Scene()
        self._selected_kind: str = ""
        self._selected_name: str = ""

    @property
    def scene(self) -> Scene:
        return self._scene

    def replace_scene(self, scene: Scene) -> None:
        self._scene = scene
        self._selected_kind = ""
        self._selected_name = ""
        self.sceneChanged.emit()
        self.selectionChanged.emit("", "")

    def notify_changed(self) -> None:
        self.sceneChanged.emit()

    def select(self, kind: str, name: str) -> None:
        self._selected_kind = kind
        self._selected_name = name
        self.selectionChanged.emit(kind, name)

    @property
    def selection(self) -> tuple[str, str]:
        return self._selected_kind, self._selected_name

    def remove(self, kind: str, name: str) -> bool:
        """Remove a light or target by name. Returns True on success."""
        if kind == "light":
            for i, item in enumerate(self._scene.lights):
                if item.name == name:
                    del self._scene.lights[i]
                    if self._selected_kind == kind and self._selected_name == name:
                        self.select("", "")
                    self.sceneChanged.emit()
                    return True
            return False
        if kind == "target":
            for i, item in enumerate(self._scene.targets):
                if item.name == name:
                    del self._scene.targets[i]
                    if self._selected_kind == kind and self._selected_name == name:
                        self.select("", "")
                    self.sceneChanged.emit()
                    return True
            return False
        return False

    def rename(self, kind: str, old: str, new: str) -> bool:
        """Rename a light or target. Returns True on success."""
        if not new or new == old:
            return False
        coll = self._scene.lights if kind == "light" else (
            self._scene.targets if kind == "target" else None
        )
        if coll is None:
            return False
        if any(getattr(x, "name", "") == new for x in coll):
            return False
        for item in coll:
            if item.name == old:
                item.name = new
                if self._selected_kind == kind and self._selected_name == old:
                    self.select(kind, new)
                self.sceneChanged.emit()
                return True
        return False
