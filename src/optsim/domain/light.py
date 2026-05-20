"""Light source descriptions.

Several typical machine-vision illuminations are modelled as parametric
shapes that can be expanded into Mitsuba primitive emitters by the
translator. All emit Lambertian radiance unless ``directional`` is set,
which adds a cosine-power directivity term.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import Transform


class LightKind(str, Enum):
    point = "point"
    rect_area = "rect_area"
    ring = "ring"
    bar = "bar"
    coaxial = "coaxial"
    dome = "dome"
    backlight = "backlight"


class _LightBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "light"
    transform: Transform = Field(default_factory=Transform)
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    intensity: float = Field(
        default=500.0,
        gt=0.0,
        description="Radiant flux equivalent in arbitrary units. Higher = brighter.",
    )
    enabled: bool = True
    directional_exponent: float = Field(
        default=0.0,
        ge=0.0,
        le=64.0,
        description="0 = Lambertian, higher = more directional (cos^n) emission.",
    )


class PointLight(_LightBase):
    kind: Literal[LightKind.point] = LightKind.point


class RectAreaLight(_LightBase):
    kind: Literal[LightKind.rect_area] = LightKind.rect_area
    width_mm: float = Field(default=40.0, gt=0.0)
    height_mm: float = Field(default=40.0, gt=0.0)


class RingLight(_LightBase):
    kind: Literal[LightKind.ring] = LightKind.ring
    inner_radius_mm: float = Field(default=25.0, gt=0.0)
    outer_radius_mm: float = Field(default=40.0, gt=0.0)
    segments: int = Field(default=24, ge=4, le=256)
    tilt_deg: float = Field(
        default=30.0,
        ge=0.0,
        le=89.0,
        description="Tilt of each emitter facet toward the optical axis.",
    )


class BarLight(_LightBase):
    kind: Literal[LightKind.bar] = LightKind.bar
    length_mm: float = Field(default=100.0, gt=0.0)
    width_mm: float = Field(default=15.0, gt=0.0)


class CoaxialLight(_LightBase):
    """Coaxial / on-axis illumination via a beam splitter.

    Implemented as a rectangular emitter placed in front of the lens and
    pointing along the optical axis (the beam splitter is not modelled
    explicitly; light is assumed to be folded onto the axis by an ideal
    50/50 splitter, which halves the effective intensity).
    """

    kind: Literal[LightKind.coaxial] = LightKind.coaxial
    size_mm: float = Field(default=40.0, gt=0.0)


class DomeLight(_LightBase):
    """Hemispherical diffuse illumination.

    Approximated as a hemisphere mesh emitter centred over the workpiece.
    """

    kind: Literal[LightKind.dome] = LightKind.dome
    radius_mm: float = Field(default=80.0, gt=0.0)


class Backlight(_LightBase):
    kind: Literal[LightKind.backlight] = LightKind.backlight
    width_mm: float = Field(default=100.0, gt=0.0)
    height_mm: float = Field(default=100.0, gt=0.0)


Light = (
    PointLight | RectAreaLight | RingLight | BarLight | CoaxialLight | DomeLight | Backlight
)
"""Discriminated union over all supported light kinds.

Pydantic resolves the right subclass via the ``kind`` literal field.
"""
