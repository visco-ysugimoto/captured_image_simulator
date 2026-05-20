"""Surface material (BSDF) descriptions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MaterialKind(str, Enum):
    """High-level surface category mapped to a Mitsuba 3 BSDF.

    Mapping (see ``optsim.render.translator``):
    - ``diffuse``        -> ``diffuse``
    - ``metal``          -> ``conductor`` (rough variant when roughness > 0)
    - ``dielectric``     -> ``plastic`` (rough variant when roughness > 0)
    - ``rough_plastic``  -> ``roughplastic``
    - ``anisotropic``    -> ``roughconductor`` with anisotropic alpha
    """

    diffuse = "diffuse"
    metal = "metal"
    dielectric = "dielectric"
    rough_plastic = "rough_plastic"
    anisotropic = "anisotropic"


class Material(BaseModel):
    """BSDF parameters for a surface.

    Colour values are normalised reflectance (0-1) in linear sRGB. For more
    accurate spectral rendering, swap this for a per-wavelength array in the
    future.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = "default"
    kind: MaterialKind = MaterialKind.diffuse

    base_color: tuple[float, float, float] = (0.8, 0.8, 0.8)

    roughness: float = Field(default=0.3, ge=0.0, le=1.0)
    anisotropy: float = Field(default=0.0, ge=-1.0, le=1.0)
    anisotropy_rotation_deg: float = Field(default=0.0, ge=-180.0, le=180.0)

    ior: float = Field(default=1.5, ge=1.0, le=3.0)
    metallic: float = Field(default=0.0, ge=0.0, le=1.0)

    specular_tint: float = Field(default=1.0, ge=0.0, le=1.0)
    diffuse_weight: float = Field(default=0.5, ge=0.0, le=1.0)

    normal_map_path: str | None = None
    normal_strength: float = Field(default=1.0, ge=0.0, le=4.0)
