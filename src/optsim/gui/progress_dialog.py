"""Modal progress dialogs for long-running GUI operations."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..render.cancellation import RenderCancellation


def _apply_blocking_style(dlg: QDialog) -> None:
    """Block interaction with the rest of the application while visible."""
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setModal(True)
    dlg.setMinimumWidth(420)
    dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)


class TaskProgressDialog(QDialog):
    """Indeterminate progress for tasks without cancellation (e.g. mesh load)."""

    def __init__(self, title: str, message: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        _apply_blocking_style(self)

        layout = QVBoxLayout(self)
        self._label = QLabel(message)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        layout.addWidget(self._bar)

    def set_message(self, message: str) -> None:
        self._label.setText(message)

    def set_progress(self, current: int, total: int, message: str) -> None:
        self.set_message(message)
        if total > 0 and self._bar.maximum() == 0:
            self._bar.setRange(0, total)
        if total > 0:
            self._bar.setMaximum(total)
            self._bar.setValue(min(current, total))


class RenderProgressDialog(QDialog):
    """Shows progress and forwards Cancel to a :class:`RenderCancellation`."""

    def __init__(
        self,
        title: str,
        cancellation: RenderCancellation,
        parent=None,
        *,
        indeterminate: bool = False,
        start_label: str = "Starting...",
        cancel_label: str = "Cancel",
        cancelling_label: str = "Cancelling...",
    ) -> None:
        super().__init__(parent)
        self._cancellation = cancellation
        self.setWindowTitle(title)
        _apply_blocking_style(self)

        layout = QVBoxLayout(self)
        self._label = QLabel(start_label)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        if indeterminate:
            self._bar.setRange(0, 0)
        else:
            self._bar.setRange(0, 100)
            self._bar.setValue(0)
        layout.addWidget(self._bar)

        row = QHBoxLayout()
        row.addStretch(1)
        self._cancel_btn = QPushButton(cancel_label)
        self._cancel_btn.clicked.connect(self._on_cancel)
        row.addWidget(self._cancel_btn)
        layout.addLayout(row)
        self._cancelling_label = cancelling_label

    def _on_cancel(self) -> None:
        self._cancellation.request()
        self._cancel_btn.setEnabled(False)
        self._label.setText(self._cancelling_label)

    def update_progress(self, current: int, total: int, message: str) -> None:
        self._label.setText(message)
        if self._bar.maximum() == 0 and total > 0:
            self._bar.setRange(0, total)
        if total > 0:
            self._bar.setMaximum(total)
            self._bar.setValue(min(current, total))

    def mark_finished(self) -> None:
        self._cancel_btn.setEnabled(False)
