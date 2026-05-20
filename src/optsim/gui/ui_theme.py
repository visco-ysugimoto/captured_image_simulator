"""Shared Qt stylesheet and layout constants for a modern desktop UI."""

from __future__ import annotations

import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QDockWidget, QMainWindow

# Layout defaults (pixels)
DOCK_LEFT_MIN_WIDTH = 260
DOCK_LEFT_DEFAULT_WIDTH = 280
DOCK_RIGHT_MIN_WIDTH = 400
DOCK_RIGHT_DEFAULT_WIDTH = 440
DOCK_RIGHT_DEFAULT_WIDTH_EN = 520
PROPERTY_PANEL_MIN_WIDTH = 380
PROPERTY_PANEL_MIN_WIDTH_EN = 440
FORM_FIELD_MIN_WIDTH = 120
SPIN_MIN_WIDTH = 112

# Palette — dark slate with teal accent
_BG = "#12151c"
_SURFACE = "#1c212b"
_SURFACE_ALT = "#252b36"
_BORDER = "#343b48"
_BORDER_FOCUS = "#4cc9b0"
_TEXT = "#e8ecf1"
_TEXT_MUTED = "#9aa3b2"
_ACCENT = "#3dd6b5"
_ACCENT_HOVER = "#5ce0c4"
_ACCENT_PRESSED = "#2bb89a"
_DANGER = "#f07178"
_INPUT_BG = "#161a22"
_SELECTION = "#2a3647"


def app_font() -> QFont:
    if sys.platform == "win32":
        return QFont("Segoe UI", 10)
    if sys.platform == "darwin":
        return QFont(".AppleSystemUIFont", 10)
    return QFont("Inter", 10)


def stylesheet() -> str:
    return f"""
    QWidget {{
        background-color: {_BG};
        color: {_TEXT};
        font-size: 13px;
    }}
    QMainWindow {{
        background-color: {_BG};
    }}
    QDockWidget {{
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
        color: {_TEXT_MUTED};
        font-weight: 600;
        font-size: 12px;
    }}
    QDockWidget::title {{
        background: {_SURFACE};
        padding: 10px 14px;
        border-bottom: 1px solid {_BORDER};
        text-align: left;
    }}
    QDockWidget > QWidget {{
        background: {_SURFACE};
    }}
    QTabWidget::pane {{
        border: 1px solid {_BORDER};
        border-radius: 8px;
        background: {_SURFACE};
        top: -1px;
    }}
    QTabBar::tab {{
        background: {_SURFACE_ALT};
        color: {_TEXT_MUTED};
        padding: 10px 20px;
        margin-right: 4px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        min-width: 88px;
    }}
    QTabBar::tab:selected {{
        background: {_SURFACE};
        color: {_TEXT};
        border-bottom: 2px solid {_ACCENT};
    }}
    QTabBar::tab:hover:!selected {{
        color: {_TEXT};
        background: {_SURFACE};
    }}
    QTreeWidget {{
        background: {_SURFACE};
        border: none;
        outline: none;
        padding: 6px;
    }}
    QTreeWidget::item {{
        padding: 6px 4px;
        border-radius: 6px;
    }}
    QTreeWidget::item:selected {{
        background: {_SELECTION};
        color: {_TEXT};
    }}
    QTreeWidget::item:hover:!selected {{
        background: {_SURFACE_ALT};
    }}
    QHeaderView::section {{
        background: {_SURFACE_ALT};
        color: {_TEXT_MUTED};
        padding: 8px;
        border: none;
        font-weight: 600;
    }}
    QGroupBox {{
        font-weight: 600;
        color: {_TEXT_MUTED};
        border: 1px solid {_BORDER};
        border-radius: 10px;
        margin-top: 14px;
        padding: 16px 14px 12px 14px;
        background: {_SURFACE_ALT};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 8px;
        color: {_TEXT};
    }}
    QLabel#propertyTitle {{
        font-size: 15px;
        font-weight: 700;
        color: {_TEXT};
        padding: 4px 0 8px 0;
    }}
    QLabel#propertyHint {{
        color: {_TEXT_MUTED};
        padding: 12px 4px;
        line-height: 1.4;
    }}
    QLabel#fieldAxis {{
        color: {_TEXT_MUTED};
        min-width: 18px;
        max-width: 18px;
        font-weight: 600;
        font-size: 11px;
    }}
    QScrollArea {{
        border: none;
        background: {_SURFACE};
    }}
    QScrollArea > QWidget > QWidget {{
        background: {_SURFACE};
    }}
    QScrollBar:vertical {{
        background: {_SURFACE};
        width: 10px;
        margin: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {_BORDER};
        border-radius: 5px;
        min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {_TEXT_MUTED};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {_INPUT_BG};
        border: 1px solid {_BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        min-height: 28px;
        selection-background-color: {_SELECTION};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border-color: {_BORDER_FOCUS};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: {_SURFACE_ALT};
        border: 1px solid {_BORDER};
        selection-background-color: {_SELECTION};
        padding: 4px;
    }}
    QPushButton {{
        background: {_SURFACE};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 6px;
        padding: 8px 16px;
        min-height: 28px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background: {_SURFACE_ALT};
        border-color: {_TEXT_MUTED};
    }}
    QPushButton:pressed {{
        background: {_INPUT_BG};
    }}
    QPushButton#primaryButton {{
        background: {_ACCENT};
        color: #0d1117;
        border: none;
        font-weight: 600;
    }}
    QPushButton#primaryButton:hover {{
        background: {_ACCENT_HOVER};
    }}
    QPushButton#primaryButton:pressed {{
        background: {_ACCENT_PRESSED};
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: {_INPUT_BG};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        width: 16px;
        height: 16px;
        margin: -5px 0;
        background: {_ACCENT};
        border-radius: 8px;
    }}
    QSlider::sub-page:horizontal {{
        background: {_ACCENT_PRESSED};
        border-radius: 3px;
    }}
    QCheckBox {{
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid {_BORDER};
        background: {_INPUT_BG};
    }}
    QCheckBox::indicator:checked {{
        background: {_ACCENT};
        border-color: {_ACCENT};
    }}
    QMenuBar {{
        background: {_SURFACE};
        border-bottom: 1px solid {_BORDER};
        padding: 4px 0;
    }}
    QMenuBar::item {{
        padding: 6px 12px;
        border-radius: 4px;
    }}
    QMenuBar::item:selected {{
        background: {_SURFACE_ALT};
    }}
    QMenu {{
        background: {_SURFACE_ALT};
        border: 1px solid {_BORDER};
        padding: 6px;
    }}
    QMenu::item {{
        padding: 8px 28px 8px 16px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background: {_SELECTION};
    }}
    QToolBar {{
        background: {_SURFACE};
        border-bottom: 1px solid {_BORDER};
        spacing: 8px;
        padding: 6px 10px;
    }}
    QToolBar QToolButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 6px 12px;
    }}
    QToolBar QToolButton:hover {{
        background: {_SURFACE_ALT};
        border-color: {_BORDER};
    }}
    QStatusBar {{
        background: {_SURFACE};
        color: {_TEXT_MUTED};
        border-top: 1px solid {_BORDER};
    }}
    QProgressBar {{
        border: 1px solid {_BORDER};
        border-radius: 6px;
        text-align: center;
        background: {_INPUT_BG};
        min-height: 20px;
    }}
    QProgressBar::chunk {{
        background: {_ACCENT};
        border-radius: 5px;
    }}
    QTableWidget {{
        background: {_SURFACE};
        gridline-color: {_BORDER};
        border: 1px solid {_BORDER};
        border-radius: 8px;
    }}
    QTableWidget::item:selected {{
        background: {_SELECTION};
    }}
    QDialog {{
        background: {_BG};
    }}
    QTextEdit, QPlainTextEdit {{
        background: {_INPUT_BG};
        border: 1px solid {_BORDER};
        border-radius: 8px;
        padding: 8px;
    }}
    """


def apply_app_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(app_font())
    app.setStyleSheet(stylesheet())


def configure_main_window_docks(window: QMainWindow, *, language: str = "ja") -> None:
    """Set minimum widths; call :func:`resize_main_window_docks` after show."""
    for dock in window.findChildren(QDockWidget):
        name = dock.objectName()
        title = dock.windowTitle().lower()
        if name == "dockProperties" or "propert" in title or "プロパティ" in title:
            dock.setMinimumWidth(DOCK_RIGHT_MIN_WIDTH)
            if dock.widget() is not None:
                min_panel = (
                    PROPERTY_PANEL_MIN_WIDTH_EN
                    if language == "en"
                    else PROPERTY_PANEL_MIN_WIDTH
                )
                dock.widget().setMinimumWidth(min_panel)
        elif name == "dockScene" or "scene" in title or "シーン" in title or "outline" in title:
            dock.setMinimumWidth(DOCK_LEFT_MIN_WIDTH)


def resize_main_window_docks(window: QMainWindow, *, language: str = "ja") -> None:
    from PyQt6.QtCore import Qt

    left = right = None
    for dock in window.findChildren(QDockWidget):
        area = window.dockWidgetArea(dock)
        if area == Qt.DockWidgetArea.LeftDockWidgetArea:
            left = dock
        elif area == Qt.DockWidgetArea.RightDockWidgetArea:
            if dock.objectName() == "dockProperties":
                right = dock
    docks = []
    sizes = []
    if left is not None:
        docks.append(left)
        sizes.append(DOCK_LEFT_DEFAULT_WIDTH)
    if right is not None:
        docks.append(right)
        sizes.append(
            DOCK_RIGHT_DEFAULT_WIDTH_EN
            if language == "en"
            else DOCK_RIGHT_DEFAULT_WIDTH
        )
    if docks:
        window.resizeDocks(docks, sizes, Qt.Orientation.Horizontal)
