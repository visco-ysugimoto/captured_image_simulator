"""Property editor panel.

Renders a form for the currently selected scene object, dynamically
introspecting the pydantic model fields:

- bounded floats / ints use a slider + spinbox so the user can drag for
  exploration but type for precision
- unbounded floats / ints use a plain spinbox
- tuples expand into N spinboxes (positions, colours, sizes)
- enums use a combo box, booleans a checkbox
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..presets import (
    TARGET_ROLE_PRESET_GROUPS,
    build_light_preset,
    get_material_for_role,
    get_material_preset,
    light_preset_names,
    material_preset_names,
)
from ..domain.light import (
    Backlight,
    BarLight,
    CoaxialLight,
    DomeLight,
    PointLight,
    RectAreaLight,
    RingLight,
)
from .i18n import LanguageManager
from .scene_state import SceneState
from .ui_theme import FORM_FIELD_MIN_WIDTH, PROPERTY_PANEL_MIN_WIDTH, SPIN_MIN_WIDTH

_FIELD_LABELS_JA: dict[str, str] = {
    "name": "名前",
    "enabled": "有効",
    "intensity": "強度",
    "color": "色 (RGB)",
    "transform": "変換",
    "position": "位置 (mm)",
    "rotation_deg": "回転 (deg)",
    "width_mm": "幅 (mm)",
    "height_mm": "高さ (mm)",
    "length_mm": "長さ (mm)",
    "inner_radius_mm": "内径 (mm)",
    "outer_radius_mm": "外径 (mm)",
    "radius_mm": "半径 (mm)",
    "size_mm": "サイズ (mm)",
    "tilt_deg": "チルト (deg)",
    "segments": "分割数",
    "directional_exponent": "指向性 (cos^n)",
    "magnification": "倍率",
    "working_distance_mm": "作動距離 (mm)",
    "na": "NA",
    "distortion_pct": "歪曲 (%)",
    "width_px": "幅 (px)",
    "height_px": "高さ (px)",
    "pixel_pitch_um": "ピクセルピッチ (µm)",
    "bit_depth": "ビット深度",
    "exposure_time_ms": "露光時間 (ms)",
    "gain_db": "ゲイン (dB)",
    "quantum_efficiency": "量子効率",
    "roughness": "粗さ",
    "metallic": "金属度",
    "base_color": "ベースカラー",
    "kind": "種別",
    "visible": "表示",
    "scale": "スケール",
}

_FIELD_LABELS_EN: dict[str, str] = {
    "name": "Name",
    "enabled": "Enabled",
    "intensity": "Intensity",
    "color": "Color (RGB)",
    "transform": "Transform",
    "position": "Position (mm)",
    "rotation_deg": "Rotation (deg)",
    "width_mm": "Width (mm)",
    "height_mm": "Height (mm)",
    "length_mm": "Length (mm)",
    "inner_radius_mm": "Inner radius (mm)",
    "outer_radius_mm": "Outer radius (mm)",
    "radius_mm": "Radius (mm)",
    "size_mm": "Size (mm)",
    "tilt_deg": "Tilt (deg)",
    "segments": "Segments",
    "directional_exponent": "Directionality (cos^n)",
    "magnification": "Magnification",
    "working_distance_mm": "Working distance (mm)",
    "na": "NA",
    "distortion_pct": "Distortion (%)",
    "width_px": "Width (px)",
    "height_px": "Height (px)",
    "pixel_pitch_um": "Pixel pitch (um)",
    "bit_depth": "Bit depth",
    "exposure_time_ms": "Exposure time (ms)",
    "gain_db": "Gain (dB)",
    "quantum_efficiency": "Quantum efficiency",
    "roughness": "Roughness",
    "metallic": "Metallic",
    "base_color": "Base color",
    "kind": "Kind",
    "visible": "Visible",
    "scale": "Scale",
}


def _field_label(field_name: str, *, language: str) -> str:
    table = _FIELD_LABELS_EN if language == "en" else _FIELD_LABELS_JA
    if field_name in table:
        return table[field_name]
    return field_name.replace("_", " ")


def _configure_form(form: QFormLayout) -> None:
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setLabelAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
    )
    form.setFormAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
    )
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(10)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)


def _configure_spin(widget: QSpinBox | QDoubleSpinBox) -> None:
    widget.setMinimumWidth(SPIN_MIN_WIDTH)
    widget.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )


def _configure_line_edit(widget: QLineEdit) -> None:
    widget.setMinimumWidth(FORM_FIELD_MIN_WIDTH)
    widget.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )


def _configure_combo(widget: QComboBox) -> None:
    widget.setMinimumWidth(FORM_FIELD_MIN_WIDTH)
    widget.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )


@dataclass
class _Bounds:
    ge: float | None = None
    le: float | None = None
    gt: float | None = None
    lt: float | None = None

    @property
    def lower(self) -> float | None:
        if self.ge is not None:
            return self.ge
        if self.gt is not None:
            return self.gt
        return None

    @property
    def upper(self) -> float | None:
        if self.le is not None:
            return self.le
        if self.lt is not None:
            return self.lt
        return None

    @property
    def is_bounded(self) -> bool:
        return self.lower is not None and self.upper is not None


def _extract_bounds(model: BaseModel, field_name: str) -> _Bounds:
    """Pull ge/le/gt/lt constraints from a pydantic ``Field`` declaration."""
    bounds = _Bounds()
    try:
        info = model.__class__.model_fields[field_name]
    except (KeyError, AttributeError):
        return bounds
    for meta in getattr(info, "metadata", []) or []:
        for key in ("ge", "le", "gt", "lt"):
            v = getattr(meta, key, None)
            if v is not None:
                setattr(bounds, key, float(v))
    return bounds


class SliderSpin(QWidget):
    """Horizontal slider tied to a QDoubleSpinBox for bounded floats.

    The slider integer position maps to ``[lower, upper]`` via 1000 steps so
    fine-grained dragging is possible.
    """

    valueChanged = pyqtSignal(float)
    STEPS = 1000

    def __init__(
        self,
        value: float,
        lower: float,
        upper: float,
        *,
        decimals: int = 3,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._lower = float(lower)
        self._upper = float(upper)
        self._decimals = decimals
        self._suppress = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(self.STEPS)
        self.slider.setTracking(True)

        self.spin = QDoubleSpinBox()
        self.spin.setRange(self._lower, self._upper)
        self.spin.setDecimals(decimals)
        step = max((self._upper - self._lower) / 200.0, 10 ** -decimals)
        self.spin.setSingleStep(step)
        _configure_spin(self.spin)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        row.addWidget(self.slider, 1)
        row.addWidget(self.spin, 0)

        self.set_value(float(value))

        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)

    def _val_to_pos(self, v: float) -> int:
        if self._upper == self._lower:
            return 0
        return int(round((v - self._lower) / (self._upper - self._lower) * self.STEPS))

    def _pos_to_val(self, pos: int) -> float:
        return self._lower + (pos / self.STEPS) * (self._upper - self._lower)

    def set_value(self, v: float) -> None:
        self._suppress = True
        v = max(self._lower, min(self._upper, float(v)))
        self.spin.setValue(v)
        self.slider.setValue(self._val_to_pos(v))
        self._suppress = False

    def _on_slider(self, pos: int) -> None:
        if self._suppress:
            return
        v = self._pos_to_val(pos)
        self._suppress = True
        self.spin.setValue(v)
        self._suppress = False
        self.valueChanged.emit(v)

    def _on_spin(self, v: float) -> None:
        if self._suppress:
            return
        self._suppress = True
        self.slider.setValue(self._val_to_pos(v))
        self._suppress = False
        self.valueChanged.emit(float(v))


class PropertyPanel(QScrollArea):
    def __init__(
        self,
        state: SceneState,
        i18n: LanguageManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.i18n = i18n
        self.setObjectName("propertyPanel")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self._container = QWidget()
        self._container.setMinimumWidth(PROPERTY_PANEL_MIN_WIDTH)
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(14, 14, 14, 14)
        self._layout.setSpacing(12)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self._container)

        self._suppress = False

        self.state.selectionChanged.connect(self._on_selection_changed)
        self.state.sceneChanged.connect(self._refresh)
        self.i18n.languageChanged.connect(self._refresh)

        self._refresh()

    def _on_selection_changed(self, _kind: str, _name: str) -> None:
        self._refresh()

    def _refresh(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        kind, name = self.state.selection
        if not kind:
            hint = QLabel(self.i18n.text("prop.hint.select"))
            hint.setObjectName("propertyHint")
            hint.setWordWrap(True)
            self._layout.addWidget(hint)
            self._layout.addStretch(1)
            return

        target_obj = self._resolve(kind, name)
        if target_obj is None:
            hint = QLabel(self.i18n.text("prop.hint.not_found", kind=kind, name=name))
            hint.setObjectName("propertyHint")
            self._layout.addWidget(hint)
            self._layout.addStretch(1)
            return

        title = QLabel(self.i18n.text("prop.title.format", kind=kind, name=name))
        title.setObjectName("propertyTitle")
        self._layout.addWidget(title)

        if kind == "light":
            self._build_light_preset_bar(name)
        elif kind == "target":
            self._build_material_preset_bar(name)

        self._build_form_for(target_obj)
        self._layout.addStretch(1)

    def _resolve(self, kind: str, name: str) -> BaseModel | None:
        scene = self.state.scene
        if kind == "camera":
            return scene.camera
        if kind == "lens":
            return scene.lens
        if kind == "target":
            return scene.find_target(name)
        if kind == "light":
            return scene.find_light(name)
        return None

    def _build_form_for(self, model: BaseModel) -> None:
        group = QGroupBox(model.__class__.__name__)
        form = QFormLayout(group)
        _configure_form(form)

        for field_name in model.__class__.model_fields:
            value = getattr(model, field_name)
            if isinstance(value, BaseModel):
                continue
            widget = self._editor_for(model, field_name, value)
            if widget is None:
                continue
            form.addRow(_field_label(field_name, language=self.i18n.code), widget)

        self._layout.addWidget(group)

        for field_name in model.__class__.model_fields:
            value = getattr(model, field_name)
            if isinstance(value, BaseModel):
                child_group = QGroupBox(
                    _field_label(field_name, language=self.i18n.code)
                )
                child_layout = QFormLayout(child_group)
                _configure_form(child_layout)
                for nf in value.__class__.model_fields:
                    nv = getattr(value, nf)
                    if isinstance(nv, BaseModel):
                        continue
                    editor = self._editor_for(value, nf, nv)
                    if editor is None:
                        continue
                    child_layout.addRow(
                        _field_label(nf, language=self.i18n.code), editor
                    )
                self._layout.addWidget(child_group)

    def _editor_for(
        self,
        model: BaseModel,
        field_name: str,
        value: Any,
    ) -> QWidget | None:
        bounds = _extract_bounds(model, field_name)

        if isinstance(value, bool):
            cb = QCheckBox()
            cb.setChecked(value)
            cb.toggled.connect(
                lambda v, m=model, n=field_name: self._set_attr(m, n, bool(v))
            )
            return cb
        if isinstance(value, int) and not isinstance(value, bool):
            if bounds.is_bounded and (bounds.upper - bounds.lower) <= 256:
                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setMinimum(int(bounds.lower))
                slider.setMaximum(int(bounds.upper))
                slider.setValue(int(value))
                sp = QSpinBox()
                sp.setRange(int(bounds.lower), int(bounds.upper))
                sp.setValue(int(value))
                _configure_spin(sp)
                row.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed,
                )
                rl.addWidget(slider, 1)
                rl.addWidget(sp, 0)
                suppress = {"v": False}

                def _on_sl(v, sp=sp, suppress=suppress, m=model, n=field_name):
                    if suppress["v"]:
                        return
                    suppress["v"] = True
                    sp.setValue(int(v))
                    suppress["v"] = False
                    self._set_attr(m, n, int(v))

                def _on_sp(v, slider=slider, suppress=suppress, m=model, n=field_name):
                    if suppress["v"]:
                        return
                    suppress["v"] = True
                    slider.setValue(int(v))
                    suppress["v"] = False
                    self._set_attr(m, n, int(v))

                slider.valueChanged.connect(_on_sl)
                sp.valueChanged.connect(_on_sp)
                return row
            sp = QSpinBox()
            lo = int(bounds.lower) if bounds.lower is not None else -10_000_000
            hi = int(bounds.upper) if bounds.upper is not None else 10_000_000
            sp.setRange(lo, hi)
            sp.setValue(int(value))
            _configure_spin(sp)
            sp.valueChanged.connect(
                lambda v, m=model, n=field_name: self._set_attr(m, n, int(v))
            )
            return sp
        if isinstance(value, float):
            if bounds.is_bounded:
                slider_spin = SliderSpin(
                    float(value), bounds.lower, bounds.upper, decimals=4
                )
                slider_spin.valueChanged.connect(
                    lambda v, m=model, n=field_name: self._set_attr(m, n, float(v))
                )
                return slider_spin
            sp = QDoubleSpinBox()
            sp.setRange(-1e6, 1e6)
            sp.setDecimals(4)
            sp.setSingleStep(0.1)
            sp.setValue(float(value))
            _configure_spin(sp)
            sp.valueChanged.connect(
                lambda v, m=model, n=field_name: self._set_attr(m, n, float(v))
            )
            return sp
        if isinstance(value, str):
            le = QLineEdit(value)
            _configure_line_edit(le)
            le.editingFinished.connect(
                lambda m=model, n=field_name, w=le: self._set_attr(m, n, w.text())
            )
            return le
        if isinstance(value, tuple) and all(isinstance(v, (int, float)) for v in value):
            return self._tuple_editor(model, field_name, value)
        if hasattr(value, "value") and hasattr(type(value), "__members__"):
            combo = QComboBox()
            for member_name in type(value).__members__:
                combo.addItem(member_name)
            combo.setCurrentText(value.name)
            _configure_combo(combo)
            combo.currentTextChanged.connect(
                lambda text, m=model, n=field_name, et=type(value):
                self._set_attr(m, n, et[text])
            )
            return combo
        return None

    def _tuple_editor(
        self,
        model: BaseModel,
        field_name: str,
        value: tuple[float | int, ...],
    ) -> QWidget:
        """Stack X/Y/Z (and W) on separate rows for easier editing."""
        axes = ("X", "Y", "Z", "W")
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        spinboxes: list[QDoubleSpinBox] = []
        for i, item in enumerate(value):
            row = QHBoxLayout()
            row.setSpacing(8)
            axis = QLabel(axes[i] if i < len(axes) else str(i))
            axis.setObjectName("fieldAxis")
            box = QDoubleSpinBox()
            box.setRange(-1e6, 1e6)
            box.setDecimals(4)
            box.setSingleStep(0.1)
            box.setValue(float(item))
            _configure_spin(box)
            box.valueChanged.connect(
                lambda _v, m=model, n=field_name, lst=spinboxes: self._set_tuple(
                    m, n, lst
                )
            )
            spinboxes.append(box)
            row.addWidget(axis)
            row.addWidget(box, 1)
            layout.addLayout(row)
        container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        return container

    def _set_tuple(self, model: BaseModel, field_name: str, spinboxes: list[QDoubleSpinBox]) -> None:
        values = tuple(b.value() for b in spinboxes)
        self._set_attr(model, field_name, values)

    def _set_attr(self, model: BaseModel, field_name: str, value: Any) -> None:
        if self._suppress:
            return
        try:
            setattr(model, field_name, value)
        except Exception:
            return
        self.state.notify_changed()

    # ----- Preset application UI -----

    def _guess_light_preset_name(self, light: BaseModel) -> str:
        """Map current light kind to the closest preset name.

        This keeps the combo selection stable after UI refresh so it does not
        jump back to the first item ("backlight").
        """
        if isinstance(light, Backlight):
            return "backlight"
        if isinstance(light, RingLight):
            return "ring_above"
        if isinstance(light, CoaxialLight):
            return "coaxial"
        if isinstance(light, DomeLight):
            return "dome"
        if isinstance(light, RectAreaLight):
            return "rect_overhead"
        if isinstance(light, PointLight):
            return "point_oblique_45"
        if isinstance(light, BarLight):
            x = float(light.transform.position[0])
            return "bar_left" if x <= 0.0 else "bar_right"
        return "ring_above"

    def _build_light_preset_bar(self, light_name: str) -> None:
        light = self.state.scene.find_light(light_name)
        if light is None:
            return
        bar = QGroupBox(self.i18n.text("prop.light_preset"))
        row = QHBoxLayout(bar)
        row.setSpacing(10)
        combo = QComboBox()
        names = light_preset_names()
        combo.addItems(names)
        guessed = self._guess_light_preset_name(light)
        if guessed in names:
            combo.setCurrentText(guessed)
        _configure_combo(combo)
        btn = QPushButton(self.i18n.text("prop.apply"))
        btn.setObjectName("primaryButton")
        btn.clicked.connect(
            lambda: self._apply_light_preset(light_name, combo.currentText())
        )
        row.addWidget(combo, 1)
        row.addWidget(btn, 0)
        self._layout.addWidget(bar)

    def _apply_light_preset(self, light_name: str, preset_name: str) -> None:
        scene = self.state.scene
        for i, light in enumerate(scene.lights):
            if light.name != light_name:
                continue
            new_light = build_light_preset(preset_name)
            # Preserve identity and enabled state; the preset supplies light
            # kind / geometry / default orientation.
            new_light.name = light_name
            new_light.enabled = bool(light.enabled)
            scene.lights[i] = new_light
            self.state.notify_changed()
            return

    def _build_material_preset_bar(self, target_name: str) -> None:
        bar = QGroupBox(self.i18n.text("prop.material_preset"))
        col = QVBoxLayout(bar)
        col.setSpacing(10)

        role_row = QHBoxLayout()
        role_row.setSpacing(10)
        role_combo = QComboBox()
        role_combo.addItem(self.i18n.text("prop.role_placeholder"), "")
        for group_name, items in TARGET_ROLE_PRESET_GROUPS.items():
            for label, preset_key in items:
                role_combo.addItem(f"{group_name} — {label}", preset_key)
        _configure_combo(role_combo)
        role_row.addWidget(role_combo, 1)
        btn_role = QPushButton(self.i18n.text("prop.apply"))
        btn_role.setObjectName("primaryButton")
        btn_role.clicked.connect(
            lambda: self._apply_material_preset_key(
                target_name, role_combo.currentData()
            )
        )
        role_row.addWidget(btn_role)
        col.addLayout(role_row)

        quick = QHBoxLayout()
        quick.setSpacing(8)
        for role, label in [
            ("widget", self.i18n.text("prop.widget_default")),
            ("stage", self.i18n.text("prop.stage_default")),
        ]:
            b = QPushButton(label)
            b.clicked.connect(
                lambda _c=False, r=role: self._apply_target_role(target_name, r)
            )
            quick.addWidget(b)
        col.addLayout(quick)

        all_row = QHBoxLayout()
        all_row.setSpacing(10)
        all_combo = QComboBox()
        all_combo.addItems(material_preset_names())
        _configure_combo(all_combo)
        all_row.addWidget(all_combo, 1)
        btn_all = QPushButton(self.i18n.text("prop.apply_from_list"))
        btn_all.setObjectName("primaryButton")
        btn_all.clicked.connect(
            lambda: self._apply_material_preset(target_name, all_combo.currentText())
        )
        all_row.addWidget(btn_all)
        col.addLayout(all_row)

        self._layout.addWidget(bar)

    def _apply_material_preset_key(self, target_name: str, preset_key: object) -> None:
        if not preset_key:
            return
        self._apply_material_preset(target_name, str(preset_key))

    def _apply_target_role(self, target_name: str, role: str) -> None:
        target = self.state.scene.find_target(target_name)
        if target is None:
            return
        target.material = get_material_for_role(role)
        self.state.notify_changed()

    def _apply_material_preset(self, target_name: str, preset_name: str) -> None:
        target = self.state.scene.find_target(target_name)
        if target is None:
            return
        target.material = get_material_preset(preset_name)
        self.state.notify_changed()
