"""Render result viewer with ROI selection, histogram and edge profile.

The image is rendered into a :class:`QGraphicsView` so the user can drag a
rectangular ROI directly on the picture and the side panels (metrics,
histogram, edge profile) recompute on the fly.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFormLayout,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    import matplotlib

    matplotlib.use("QtAgg", force=False)
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    _HAS_MPL = True
except Exception:  # pragma: no cover - matplotlib optional but required for plots
    _HAS_MPL = False

from ..analysis import compute_metrics, edge_profile, histogram
from ..render import RenderResult


class ImageView(QGraphicsView):
    """Graphics view that supports rubber-band ROI selection and line picking."""

    roiChanged = pyqtSignal(QRectF)  # in image (pixel) coordinates
    lineChanged = pyqtSignal(QPointF, QPointF)  # in image coordinates

    MODE_ROI = "roi"
    MODE_LINE = "line"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(self.renderHints())
        self.setBackgroundBrush(QBrush(QColor("#101010")))
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._roi_item: Optional[QGraphicsRectItem] = None
        self._line_p0: Optional[QPointF] = None
        self._line_p1: Optional[QPointF] = None
        self._line_visual = None  # QGraphicsLineItem
        self._mode = self.MODE_ROI

        self._dragging = False
        self._drag_origin = QPointF()
        self._image_size = (0, 0)

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def set_image(self, qimg: QImage) -> None:
        pix = QPixmap.fromImage(qimg)
        if self._pixmap_item is None:
            self._pixmap_item = self._scene.addPixmap(pix)
        else:
            self._pixmap_item.setPixmap(pix)
        self._scene.setSceneRect(QRectF(pix.rect()))
        self._image_size = (pix.width(), pix.height())
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._pixmap_item is not None:
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._pixmap_item is None:
            return super().mousePressEvent(event)
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._mode == self.MODE_ROI:
            self._dragging = True
            self._drag_origin = scene_pos
            if self._roi_item is None:
                self._roi_item = QGraphicsRectItem()
                pen = QPen(QColor(255, 230, 80), 2)
                pen.setCosmetic(True)
                self._roi_item.setPen(pen)
                self._roi_item.setBrush(QBrush(QColor(255, 230, 80, 40)))
                self._scene.addItem(self._roi_item)
            self._roi_item.setRect(QRectF(scene_pos, scene_pos))
        elif self._mode == self.MODE_LINE:
            if self._line_p0 is None:
                self._line_p0 = scene_pos
                self._line_p1 = None
                if self._line_visual is not None:
                    self._scene.removeItem(self._line_visual)
                    self._line_visual = None
            else:
                self._line_p1 = scene_pos
                self._update_line_visual()
                self.lineChanged.emit(self._line_p0, self._line_p1)
                self._line_p0 = None  # reset for next pick

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self._roi_item is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            rect = QRectF(self._drag_origin, scene_pos).normalized()
            rect = rect.intersected(self._scene.sceneRect())
            self._roi_item.setRect(rect)
        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and self._mode == self.MODE_ROI and self._roi_item is not None:
            self._dragging = False
            rect = self._roi_item.rect()
            if rect.width() > 2 and rect.height() > 2:
                self.roiChanged.emit(rect)
        return super().mouseReleaseEvent(event)

    def clear_roi(self) -> None:
        if self._roi_item is not None:
            self._scene.removeItem(self._roi_item)
            self._roi_item = None
        self.roiChanged.emit(QRectF())

    def _update_line_visual(self) -> None:
        if self._line_visual is not None:
            self._scene.removeItem(self._line_visual)
            self._line_visual = None
        if self._line_p0 is None or self._line_p1 is None:
            return
        from PyQt6.QtWidgets import QGraphicsLineItem
        from PyQt6.QtCore import QLineF
        pen = QPen(QColor(80, 200, 255), 2)
        pen.setCosmetic(True)
        self._line_visual = QGraphicsLineItem(QLineF(self._line_p0, self._line_p1))
        self._line_visual.setPen(pen)
        self._scene.addItem(self._line_visual)


class ResultView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_result: Optional[RenderResult] = None
        self._roi_pixels: Optional[tuple[int, int, int, int]] = None
        self._line_pts: Optional[tuple[tuple[int, int], tuple[int, int]]] = None

        layout = QHBoxLayout(self)
        self.image_view = ImageView()
        self.image_view.setMinimumSize(560, 420)
        self.image_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.image_view, 3)

        side = QWidget()
        side_layout = QVBoxLayout(side)

        toolbar = QHBoxLayout()
        self.btn_roi = QPushButton("ROIモード")
        self.btn_roi.setCheckable(True)
        self.btn_roi.setChecked(True)
        self.btn_line = QPushButton("ラインモード")
        self.btn_line.setCheckable(True)
        self.btn_clear = QPushButton("クリア")
        toolbar.addWidget(self.btn_roi)
        toolbar.addWidget(self.btn_line)
        toolbar.addWidget(self.btn_clear)
        side_layout.addLayout(toolbar)

        self.btn_roi.clicked.connect(lambda: self._set_mode(ImageView.MODE_ROI))
        self.btn_line.clicked.connect(lambda: self._set_mode(ImageView.MODE_LINE))
        self.btn_clear.clicked.connect(self._on_clear)

        self.tabs = QTabWidget()
        side_layout.addWidget(self.tabs, 1)

        # Metrics tab
        self.metrics_tab = QWidget()
        ml = QVBoxLayout(self.metrics_tab)
        self.metrics_box_full = QGroupBox("画像全体")
        self.metrics_full_form = QFormLayout(self.metrics_box_full)
        self.metrics_box_roi = QGroupBox("ROI内")
        self.metrics_roi_form = QFormLayout(self.metrics_box_roi)
        self.roi_label = QLabel("ROIを画像上でドラッグして指定してください")
        ml.addWidget(self.roi_label)
        ml.addWidget(self.metrics_box_full)
        ml.addWidget(self.metrics_box_roi)
        ml.addStretch(1)
        self.tabs.addTab(self.metrics_tab, "メトリクス")

        # Histogram tab
        self.hist_tab = QWidget()
        hl = QVBoxLayout(self.hist_tab)
        if _HAS_MPL:
            self.hist_fig = Figure(figsize=(4, 3))
            self.hist_canvas = FigureCanvas(self.hist_fig)
            hl.addWidget(self.hist_canvas, 1)
        else:
            hl.addWidget(QLabel("matplotlib が見つかりません"))
        self.tabs.addTab(self.hist_tab, "ヒストグラム")

        # Edge profile tab
        self.edge_tab = QWidget()
        el = QVBoxLayout(self.edge_tab)
        if _HAS_MPL:
            self.edge_fig = Figure(figsize=(4, 3))
            self.edge_canvas = FigureCanvas(self.edge_fig)
            el.addWidget(self.edge_canvas, 1)
            el.addWidget(QLabel(
                "「ラインモード」に切り替えて画像上を2回クリックすると、\n"
                "その線分上の輝度プロファイルを表示します。"
            ))
        else:
            el.addWidget(QLabel("matplotlib が見つかりません"))
        self.tabs.addTab(self.edge_tab, "エッジプロファイル")

        side.setMaximumWidth(420)
        layout.addWidget(side, 1)

        self.image_view.roiChanged.connect(self._on_roi)
        self.image_view.lineChanged.connect(self._on_line)

    # ---- public API ----
    def show_result(self, result: RenderResult) -> None:
        self._last_result = result
        qimg = self._numpy_to_qimage(result.digital)
        if qimg is None:
            return
        self.image_view.set_image(qimg)
        self._refresh_metrics()
        self._refresh_histogram()
        self._refresh_edge()

    # ---- internals ----
    def _set_mode(self, mode: str) -> None:
        self.image_view.set_mode(mode)
        self.btn_roi.setChecked(mode == ImageView.MODE_ROI)
        self.btn_line.setChecked(mode == ImageView.MODE_LINE)

    def _on_clear(self) -> None:
        self.image_view.clear_roi()
        self._roi_pixels = None
        self._line_pts = None
        self._refresh_metrics()
        self._refresh_histogram()
        self._refresh_edge()

    def _on_roi(self, rect: QRectF) -> None:
        if rect.isEmpty() or self._last_result is None:
            self._roi_pixels = None
        else:
            x = int(max(0, rect.left()))
            y = int(max(0, rect.top()))
            w = int(min(self._last_result.width - x, rect.width()))
            h = int(min(self._last_result.height - y, rect.height()))
            self._roi_pixels = (x, y, w, h)
        self._refresh_metrics()
        self._refresh_histogram()

    def _on_line(self, p0: QPointF, p1: QPointF) -> None:
        if self._last_result is None:
            return
        x0 = int(round(p0.x()))
        y0 = int(round(p0.y()))
        x1 = int(round(p1.x()))
        y1 = int(round(p1.y()))
        self._line_pts = ((x0, y0), (x1, y1))
        self._refresh_edge()

    def _refresh_metrics(self) -> None:
        if self._last_result is None:
            return
        digital = self._last_result.digital
        m_full = compute_metrics(digital)
        self._fill_form(self.metrics_full_form, asdict(m_full))
        if self._roi_pixels is not None:
            x, y, w, h = self._roi_pixels
            self.roi_label.setText(f"ROI: x={x}, y={y}, w={w}, h={h}")
            m_roi = compute_metrics(digital, roi=(x, y, w, h))
            self._fill_form(self.metrics_roi_form, asdict(m_roi))
        else:
            self.roi_label.setText("ROIを画像上でドラッグして指定してください")
            self._fill_form(self.metrics_roi_form, {})

    def _refresh_histogram(self) -> None:
        if not _HAS_MPL or self._last_result is None:
            return
        digital = self._last_result.digital
        if self._roi_pixels is not None:
            x, y, w, h = self._roi_pixels
            data = digital[y:y + h, x:x + w]
        else:
            data = digital
        bins, edges = histogram(data, bins=64)
        self.hist_fig.clear()
        ax = self.hist_fig.add_subplot(111)
        centers = 0.5 * (edges[1:] + edges[:-1])
        ax.bar(centers, bins, width=(edges[1] - edges[0]), align="center",
               color="#5ac8fa", edgecolor="#001020", linewidth=0.3)
        ax.set_xlabel("DN")
        ax.set_ylabel("count")
        ax.set_title("Histogram (ROI)" if self._roi_pixels else "Histogram (full)")
        self.hist_fig.tight_layout()
        self.hist_canvas.draw_idle()

    def _refresh_edge(self) -> None:
        if not _HAS_MPL or self._last_result is None:
            return
        self.edge_fig.clear()
        ax = self.edge_fig.add_subplot(111)
        if self._line_pts is None:
            ax.text(0.5, 0.5, "Pick two points in line mode", ha="center", va="center",
                    transform=ax.transAxes)
        else:
            (x0, y0), (x1, y1) = self._line_pts
            try:
                ep = edge_profile(self._last_result.digital, (x0, y0), (x1, y1))
                ax.plot(ep.distance, ep.intensity, color="#ffb86c", linewidth=1.4)
                ax.set_xlabel("distance (px)")
                ax.set_ylabel("DN")
                title = (
                    f"({x0},{y0})→({x1},{y1})  "
                    f"10-90 width={ep.edge_width_10_90:.2f} px"
                )
                ax.set_title(title)
            except Exception as exc:
                ax.text(0.5, 0.5, f"failed: {exc}", ha="center", va="center",
                        transform=ax.transAxes)
        self.edge_fig.tight_layout()
        self.edge_canvas.draw_idle()

    @staticmethod
    def _fill_form(form: QFormLayout, payload: dict) -> None:
        while form.rowCount():
            form.removeRow(0)
        for k, v in payload.items():
            if isinstance(v, (int, float)):
                form.addRow(k, QLabel(f"{v:.4f}"))
            else:
                form.addRow(k, QLabel(str(v)))

    @staticmethod
    def _numpy_to_qimage(arr: np.ndarray) -> QImage | None:
        if arr.size == 0:
            return None
        if arr.ndim == 2:
            shown = ResultView._stretch_to_uint8(arr)
            h, w = shown.shape
            return QImage(shown.tobytes(), w, h, w, QImage.Format.Format_Grayscale8).copy()
        if arr.ndim == 3 and arr.shape[2] == 3:
            shown = ResultView._stretch_to_uint8(arr)
            h, w, _ = shown.shape
            return QImage(shown.tobytes(), w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        return None

    @staticmethod
    def _stretch_to_uint8(arr: np.ndarray) -> np.ndarray:
        if arr.dtype == np.uint8:
            return arr
        if arr.dtype == np.uint16:
            # Detect effective bit depth via max value.
            mx = int(arr.max()) if arr.size else 1
            full = 255
            for cand in (255, 1023, 4095, 16383, 65535):
                if mx <= cand:
                    full = cand
                    break
            scale = 255.0 / max(full, 1)
            return np.clip(arr.astype(np.float32) * scale, 0, 255).astype(np.uint8)
        return np.clip(arr, 0, 255).astype(np.uint8)
