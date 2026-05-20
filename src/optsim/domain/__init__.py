"""Domain models for the optical simulator scene description.

All geometric quantities are expressed in millimetres unless explicitly noted.
Coordinate convention: right-handed, Z is up (sensor looks toward -Z by default).
"""

from .camera import Camera, Sensor
from .lens import TelecentricLens
from .light import (
    BarLight,
    CoaxialLight,
    DomeLight,
    Light,
    LightKind,
    PointLight,
    RectAreaLight,
    RingLight,
)
from .material import Material, MaterialKind
from .scene import Scene
from .target import Primitive, PrimitiveKind, Target, TargetGeometry, TargetMesh

__all__ = [
    "Scene",
    "Camera",
    "Sensor",
    "TelecentricLens",
    "Light",
    "LightKind",
    "PointLight",
    "RectAreaLight",
    "RingLight",
    "BarLight",
    "DomeLight",
    "CoaxialLight",
    "Material",
    "MaterialKind",
    "Target",
    "TargetGeometry",
    "TargetMesh",
    "Primitive",
    "PrimitiveKind",
]
