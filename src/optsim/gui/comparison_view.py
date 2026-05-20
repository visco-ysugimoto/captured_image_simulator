"""Comparison view: show multiple render snapshots side-by-side."""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..analysis import compute_metrics
from ..render import RenderResult


class Snapshot:
    __slots__ = ("label", "result")

    def __init__(self, label: str, result: RenderResult) -> None:
        self.label = label
        self.result = result


class ComparisonView(QWidget):
    """Grid of snapshots with thumbnails and key metrics."""

    KEY_METRICS = ("mean", "std", "michelson", "snr_db", "dynamic_range_used")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshots: list[Snapshot] = []

        v = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("<b>レンダリング結果の比較</b>"))
        header.addStretch(1)
        self.btn_clear = QPushButton("すべて消去")
        self.btn_clear.clicked.connect(self.clear)
        header.addWidget(self.btn_clear)
        v.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        v.addWidget(self.scroll, 1)

        self._row_widget = QWidget()
        self._row_layout = QHBoxLayout(self._row_widget)
        self._row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self._row_widget)

        self._empty_label = QLabel(
            "ツールバーの「📸 スナップショット」を押すと、現在のレンダリング結果を\n"
            "ここに追加して並べて比較できます。"
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._row_layout.addWidget(self._empty_label)

    def add_snapshot(self, label: str, result: RenderResult) -> None:
        if self._empty_label is not None:
            self._row_layout.removeWidget(self._empty_label)
            self._empty_label.deleteLater()
            self._empty_label = None
        snap = Snapshot(label, result)
        self._snapshots.append(snap)
        self._row_layout.addWidget(self._build_snapshot_widget(snap))

    def clear(self) -> None:
        while self._row_layout.count():
            item = self._row_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._snapshots.clear()
        self._empty_label = QLabel("（スナップショットはまだありません）")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._row_layout.addWidget(self._empty_label)

    def _build_snapshot_widget(self, snap: Snapshot) -> QWidget:
        box = QGroupBox(snap.label)
        col = QVBoxLayout(box)
        thumb = QLabel()
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qimg = self._to_qimage(snap.result.digital)
        if qimg is not None:
            pix = QPixmap.fromImage(qimg).scaled(
                280, 220,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb.setPixmap(pix)
        col.addWidget(thumb)

        metrics = compute_metrics(snap.result.digital)
        form = QFormLayout()
        payload = asdict(metrics)
        for k in self.KEY_METRICS:
            if k in payload:
                form.addRow(k, QLabel(f"{payload[k]:.3f}"))
        col.addLayout(form)
        return box

    @staticmethod
    def _to_qimage(arr: np.ndarray) -> Optional[QImage]:
        if arr.size == 0:
            return None
        if arr.ndim == 2:
            shown = _stretch_to_uint8(arr)
            h, w = shown.shape
            return QImage(shown.tobytes(), w, h, w, QImage.Format.Format_Grayscale8).copy()
        if arr.ndim == 3 and arr.shape[2] == 3:
            shown = _stretch_to_uint8(arr)
            h, w, _ = shown.shape
            return QImage(shown.tobytes(), w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        return None


def _stretch_to_uint8(arr: np.ndarray) -> np.ndarray:
    if arr.dtype == np.uint8:
        return arr
    if arr.dtype == np.uint16:
        mx = int(arr.max()) if arr.size else 1
        full = 255
        for cand in (255, 1023, 4095, 16383, 65535):
            if mx <= cand:
                full = cand
                break
        scale = 255.0 / max(full, 1)
        return np.clip(arr.astype(np.float32) * scale, 0, 255).astype(np.uint8)
    return np.clip(arr, 0, 255).astype(np.uint8)
