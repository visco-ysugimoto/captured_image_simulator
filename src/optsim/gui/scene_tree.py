"""Scene outline tree.

Lists camera / lens / lights / targets so the user can pick what to edit
and offers a context menu for renaming and removing scene objects.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import (
    QInputDialog,
    QMenu,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from .i18n import LanguageManager
from .scene_state import SceneState
from .viewport_limits import SCENE_TREE_MAX_TARGET_ROWS


class SceneTree(QTreeWidget):
    def __init__(
        self,
        state: SceneState,
        i18n: LanguageManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.i18n = i18n
        self.setHeaderLabels([self.i18n.text("scene_tree.header")])
        self.setMinimumWidth(220)
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.state.sceneChanged.connect(self.rebuild)
        self.i18n.languageChanged.connect(self.rebuild)
        self.itemSelectionChanged.connect(self._on_selection)
        self.rebuild()

    def rebuild(self) -> None:
        was_blocked = self.blockSignals(True)
        self.clear()
        root = QTreeWidgetItem([self.state.scene.name])
        self.addTopLevelItem(root)

        self.setHeaderLabels([self.i18n.text("scene_tree.header")])

        cam = QTreeWidgetItem([self.i18n.text("scene_tree.camera")])
        cam.setData(0, Qt.ItemDataRole.UserRole, ("camera", "camera"))
        root.addChild(cam)

        lens = QTreeWidgetItem([self.i18n.text("scene_tree.lens")])
        lens.setData(0, Qt.ItemDataRole.UserRole, ("lens", "lens"))
        root.addChild(lens)

        lights_node = QTreeWidgetItem([self.i18n.text("scene_tree.lights")])
        root.addChild(lights_node)
        for light in self.state.scene.lights:
            it = QTreeWidgetItem([f"{light.name} [{light.kind.value}]"])
            it.setData(0, Qt.ItemDataRole.UserRole, ("light", light.name))
            lights_node.addChild(it)

        targets_node = QTreeWidgetItem([self.i18n.text("scene_tree.targets")])
        root.addChild(targets_node)
        from ..domain.target import TargetMesh

        targets = self.state.scene.targets
        show_all = len(targets) <= SCENE_TREE_MAX_TARGET_ROWS
        shown = targets if show_all else targets[:SCENE_TREE_MAX_TARGET_ROWS]

        for tgt in shown:
            label = tgt.name
            if isinstance(tgt.geometry, TargetMesh):
                part = tgt.geometry.part_name
                fname = Path(tgt.geometry.path).name
                if part:
                    label = f"{tgt.name} [{part}]"
                else:
                    label = f"{tgt.name} ({fname})"
            it = QTreeWidgetItem([label])
            it.setData(0, Qt.ItemDataRole.UserRole, ("target", tgt.name))
            targets_node.addChild(it)

        if not show_all:
            rest = len(targets) - len(shown)
            summary = QTreeWidgetItem(
                [self.i18n.text("scene_tree.more_targets", count=rest)]
            )
            targets_node.addChild(summary)

        root.setExpanded(True)
        lights_node.setExpanded(True)
        targets_node.setExpanded(True)
        self.blockSignals(was_blocked)

    def _on_selection(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, name = data
        self.state.select(kind, name)

    def _show_context_menu(self, _pos) -> None:
        items = self.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, name = data
        if kind not in ("light", "target"):
            return

        menu = QMenu(self)
        act_rename = QAction(self.i18n.text("scene_tree.rename"), self)
        act_rename.triggered.connect(lambda: self._rename(kind, name))
        menu.addAction(act_rename)
        act_delete = QAction(self.i18n.text("scene_tree.delete"), self)
        act_delete.triggered.connect(lambda: self._delete(kind, name))
        menu.addAction(act_delete)
        menu.exec(QCursor.pos())

    def _rename(self, kind: str, old_name: str) -> None:
        text, ok = QInputDialog.getText(
            self,
            self.i18n.text("scene_tree.rename_title"),
            self.i18n.text("scene_tree.rename_label"),
            text=old_name,
        )
        if not ok or not text:
            return
        if not self.state.rename(kind, old_name, text):
            QMessageBox.warning(
                self,
                self.i18n.text("scene_tree.rename_failed"),
                self.i18n.text("scene_tree.rename_failed_msg"),
            )

    def _delete(self, kind: str, name: str) -> None:
        ret = QMessageBox.question(
            self,
            self.i18n.text("scene_tree.delete_title"),
            self.i18n.text("scene_tree.delete_msg", kind=kind, name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        if not self.state.remove(kind, name):
            QMessageBox.warning(
                self,
                self.i18n.text("scene_tree.delete_failed"),
                self.i18n.text("scene_tree.not_found", kind=kind, name=name),
            )
