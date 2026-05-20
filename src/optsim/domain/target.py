"""Target (workpiece) descriptions: meshes or parametric primitives."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import Transform
from .material import Material


class PrimitiveKind(str, Enum):
    plane = "plane"
    cube = "cube"
    sphere = "sphere"
    cylinder = "cylinder"


class Primitive(BaseModel):
    """A parametric primitive used when no external mesh is available."""

    model_config = ConfigDict(extra="forbid")

    kind: PrimitiveKind = PrimitiveKind.cube
    size_mm: tuple[float, float, float] = (20.0, 20.0, 10.0)
    radius_mm: float = Field(default=10.0, gt=0.0)


class TargetMesh(BaseModel):
    """External mesh loaded from a file.

    When ``part_name`` is set, only that sub-mesh from a multi-body file
    (OBJ/GLTF/STEP assembly) is used. ``None`` merges all parts into one
    triangle soup (legacy behaviour).
    """

    model_config = ConfigDict(extra="forbid")

    geometry_kind: Literal["mesh"] = "mesh"
    path: str
    scale: float = Field(default=1.0, gt=0.0)
    part_name: str | None = Field(
        default=None,
        description="Name of a geometry inside a multi-part mesh file. "
        "Leave empty to merge all parts.",
    )


class TargetPrimitive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry_kind: Literal["primitive"] = "primitive"
    primitive: Primitive = Field(default_factory=Primitive)


TargetGeometry = TargetMesh | TargetPrimitive


class Target(BaseModel):
    """A placed workpiece with geometry, transform and material."""

    model_config = ConfigDict(extra="forbid")

    name: str = "target"
    transform: Transform = Field(default_factory=Transform)
    geometry: TargetGeometry = Field(default_factory=TargetPrimitive)
    material: Material = Field(default_factory=Material)
    visible: bool = True
