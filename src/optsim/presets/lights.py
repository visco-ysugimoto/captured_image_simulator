"""Common illumination presets for machine-vision setups."""

from __future__ import annotations

from collections.abc import Callable

from ..domain import (
    BarLight,
    CoaxialLight,
    DomeLight,
    PointLight,
    RectAreaLight,
    RingLight,
)
from ..domain.common import Transform
from ..domain.light import Backlight, Light

LightFactory = Callable[[], Light]


def _ring_above() -> Light:
    return RingLight(
        name="ring_light",
        transform=Transform(position=(0.0, 0.0, 60.0), rotation_deg=(0.0, 0.0, 0.0)),
        inner_radius_mm=25.0,
        outer_radius_mm=45.0,
        intensity=600.0,
        tilt_deg=35.0,
        segments=32,
    )


def _coaxial() -> Light:
    return CoaxialLight(
        name="coaxial_light",
        transform=Transform(position=(0.0, 0.0, 70.0), rotation_deg=(0.0, 0.0, 0.0)),
        size_mm=40.0,
        intensity=800.0,
    )


def _dome() -> Light:
    return DomeLight(
        name="dome_light",
        transform=Transform(position=(0.0, 0.0, 0.0)),
        radius_mm=80.0,
        intensity=400.0,
    )


def _bar_side_left() -> Light:
    return BarLight(
        name="bar_left",
        transform=Transform(position=(-60.0, 0.0, 40.0), rotation_deg=(0.0, -60.0, 0.0)),
        length_mm=100.0,
        width_mm=15.0,
        intensity=700.0,
    )


def _bar_side_right() -> Light:
    return BarLight(
        name="bar_right",
        transform=Transform(position=(60.0, 0.0, 40.0), rotation_deg=(0.0, 60.0, 0.0)),
        length_mm=100.0,
        width_mm=15.0,
        intensity=700.0,
    )


def _backlight() -> Light:
    return Backlight(
        name="backlight",
        transform=Transform(position=(0.0, 0.0, -20.0)),
        width_mm=120.0,
        height_mm=120.0,
        intensity=1200.0,
    )


def _rect_overhead() -> Light:
    return RectAreaLight(
        name="overhead_rect",
        transform=Transform(position=(0.0, 0.0, 80.0), rotation_deg=(0.0, 0.0, 0.0)),
        width_mm=80.0,
        height_mm=80.0,
        intensity=500.0,
    )


def _point_45() -> Light:
    return PointLight(
        name="point_oblique",
        transform=Transform(position=(50.0, 50.0, 80.0)),
        intensity=800.0,
    )


LIGHT_PRESETS: dict[str, LightFactory] = {
    "ring_above": _ring_above,
    "coaxial": _coaxial,
    "dome": _dome,
    "bar_left": _bar_side_left,
    "bar_right": _bar_side_right,
    "backlight": _backlight,
    "rect_overhead": _rect_overhead,
    "point_oblique_45": _point_45,
}


def light_preset_names() -> list[str]:
    return sorted(LIGHT_PRESETS.keys())


def build_light_preset(name: str) -> Light:
    if name not in LIGHT_PRESETS:
        raise KeyError(f"Unknown light preset: {name}")
    return LIGHT_PRESETS[name]()
