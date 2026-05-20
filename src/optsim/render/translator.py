"""Translate the domain scene into a Mitsuba 3 scene dictionary.

The translator is intentionally pure data: it never imports Mitsuba so that
the rest of the code can be inspected even when Mitsuba is not installed.
The only Mitsuba-specific call is the ``ScalarTransform4f`` builder used in
:mod:`optsim.render.telecentric`, which is invoked lazily.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..domain import (
    BarLight,
    Camera,
    CoaxialLight,
    DomeLight,
    Light,
    Material,
    MaterialKind,
    PointLight,
    RectAreaLight,
    RingLight,
    Scene,
    Target,
    TelecentricLens,
)
from ..domain.light import Backlight
from ..domain.target import PrimitiveKind, TargetMesh, TargetPrimitive
from .telecentric import build_orthographic_sensor_dict, to_world_matrix


def _material_to_bsdf(material: Material) -> dict[str, Any]:
    """Convert our ``Material`` description into a Mitsuba BSDF dict."""
    r, g, b = material.base_color

    if material.kind is MaterialKind.diffuse:
        return {
            "type": "diffuse",
            "reflectance": {"type": "rgb", "value": [r, g, b]},
        }

    if material.kind is MaterialKind.metal:
        if material.roughness <= 1e-3:
            return {
                "type": "conductor",
                "specular_reflectance": {"type": "rgb", "value": [r, g, b]},
            }
        return {
            "type": "roughconductor",
            "alpha": max(material.roughness**2, 1e-3),
            "distribution": "ggx",
            "specular_reflectance": {"type": "rgb", "value": [r, g, b]},
        }

    if material.kind is MaterialKind.dielectric:
        if material.roughness <= 1e-3:
            return {
                "type": "dielectric",
                "int_ior": material.ior,
                "ext_ior": 1.0,
                "specular_reflectance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
                "specular_transmittance": {"type": "rgb", "value": [r, g, b]},
            }
        return {
            "type": "roughdielectric",
            "alpha": max(material.roughness**2, 1e-3),
            "distribution": "ggx",
            "int_ior": material.ior,
            "ext_ior": 1.0,
            "specular_reflectance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
            "specular_transmittance": {"type": "rgb", "value": [r, g, b]},
        }

    if material.kind is MaterialKind.rough_plastic:
        return {
            "type": "roughplastic",
            "alpha": max(material.roughness**2, 1e-3),
            "distribution": "ggx",
            "int_ior": material.ior,
            "ext_ior": 1.0,
            "diffuse_reflectance": {"type": "rgb", "value": [r, g, b]},
        }

    if material.kind is MaterialKind.anisotropic:
        base_alpha = max(material.roughness**2, 1e-3)
        aniso = float(np.clip(material.anisotropy, 0.0, 0.95))
        alpha_u = base_alpha * (1.0 + aniso)
        alpha_v = base_alpha * (1.0 - aniso)
        conductor = {
            "type": "roughconductor",
            "alpha_u": max(alpha_u, 1e-3),
            "alpha_v": max(alpha_v, 1e-3),
            "distribution": "ggx",
            "specular_reflectance": {"type": "rgb", "value": [r, g, b]},
        }
        # Real machined / brushed metal has a meaningful diffuse component
        # coming from oxide layers and sub-resolution scratches. Without it,
        # an anisotropic conductor only reflects light along a narrow
        # specular lobe and oblique front lights (rings, bars, etc.) vanish
        # from the rendered image -- which is the discrepancy users see
        # between the fallback preview and the Mitsuba render. Blending in
        # a Lambertian diffuse term keeps the part visible under any
        # lighting direction while preserving the anisotropic highlight.
        diffuse_color = tuple(0.55 * c for c in (r, g, b))
        diffuse = {
            "type": "diffuse",
            "reflectance": {"type": "rgb", "value": list(diffuse_color)},
        }
        return {
            "type": "blendbsdf",
            "weight": 0.55,
            "bsdf_0": conductor,
            "bsdf_1": diffuse,
        }

    return {"type": "diffuse", "reflectance": {"type": "rgb", "value": [r, g, b]}}


def _make_emitter(color: tuple[float, float, float], intensity: float) -> dict[str, Any]:
    r, g, b = (max(0.0, c) * intensity for c in color)
    return {"type": "area", "radiance": {"type": "rgb", "value": [r, g, b]}}


# Area emitters in Mitsuba are attached to opaque shapes which would block
# the camera ray if the emitter happens to sit between the lens and the work.
# Using a ``null`` BSDF makes the shape transparent for BSDF interactions
# while still acting as a light source -- the renderer can see straight
# through the emitter, exactly like a real machine-vision setup where the
# illumination optics don't occlude the imaging path.
_NULL_BSDF: dict[str, Any] = {"type": "null"}


def _make_point(light: PointLight) -> dict[str, Any]:
    pos = light.transform.position
    r, g, b = (max(0.0, c) * light.intensity for c in light.color)
    return {
        light.name: {
            "type": "point",
            "position": list(pos),
            "intensity": {"type": "rgb", "value": [r, g, b]},
        }
    }


def _make_rect_area(light: RectAreaLight) -> dict[str, Any]:
    mat = light.transform.to_matrix().copy()
    mat[:3, 0] *= light.width_mm * 0.5
    mat[:3, 1] *= light.height_mm * 0.5
    return {
        light.name: {
            "type": "rectangle",
            "to_world": to_world_matrix(mat),
            # Emit along the transform's local -Z (the convention used by
            # the rest of the codebase: ``Transform.forward()`` returns
            # local -Z).
            "flip_normals": True,
            "bsdf": _NULL_BSDF,
            "emitter": _make_emitter(light.color, light.intensity),
        }
    }


def _make_ring(light: RingLight) -> dict[str, Any]:
    out: dict[str, Any] = {}
    radius = (light.inner_radius_mm + light.outer_radius_mm) * 0.5
    facet_w = (light.outer_radius_mm - light.inner_radius_mm)
    facet_h = 2 * math.pi * radius / max(light.segments, 1)
    base = light.transform.to_matrix()
    for i in range(light.segments):
        phi = 2.0 * math.pi * i / light.segments
        local = np.eye(4)
        rot = np.array(
            [
                [math.cos(phi), -math.sin(phi), 0.0, 0.0],
                [math.sin(phi), math.cos(phi), 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        offset = np.eye(4)
        offset[:3, 3] = [radius, 0.0, 0.0]
        tilt = math.radians(light.tilt_deg)
        # Tilt around the facet's local +Y axis so its -Z hemisphere points
        # inward (toward the ring centre) and downward by ``tilt_deg``. This
        # matches the fallback raycaster's convention.
        tilt_rot = np.array(
            [
                [math.cos(tilt), 0.0, math.sin(tilt), 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [-math.sin(tilt), 0.0, math.cos(tilt), 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        local = rot @ offset @ tilt_rot
        world = base @ local
        world[:3, 0] *= facet_w * 0.5
        world[:3, 1] *= facet_h * 0.5
        out[f"{light.name}_seg{i:03d}"] = {
            "type": "rectangle",
            "to_world": to_world_matrix(world),
            # See note on ``_make_rect_area``: ``flip_normals`` aligns the
            # area emitter with the transform's local -Z so each facet
            # shines inward and downward toward the work.
            "flip_normals": True,
            "bsdf": _NULL_BSDF,
            # In Mitsuba's ``area`` emitter the parameter is radiance
            # W/(sr*m^2), so the total emitted power scales with facet
            # area. Each facet gets the full ``intensity`` (rather than
            # the fallback's per-sample 1/segments normalization) so
            # changing the segment count does not change the total ring
            # power.
            "emitter": _make_emitter(light.color, light.intensity),
        }
    return out


def _make_bar(light: BarLight) -> dict[str, Any]:
    mat = light.transform.to_matrix().copy()
    mat[:3, 0] *= light.length_mm * 0.5
    mat[:3, 1] *= light.width_mm * 0.5
    return {
        light.name: {
            "type": "rectangle",
            "to_world": to_world_matrix(mat),
            "flip_normals": True,
            "bsdf": _NULL_BSDF,
            "emitter": _make_emitter(light.color, light.intensity),
        }
    }


def _make_coaxial(light: CoaxialLight) -> dict[str, Any]:
    mat = light.transform.to_matrix().copy()
    mat[:3, 0] *= light.size_mm * 0.5
    mat[:3, 1] *= light.size_mm * 0.5
    return {
        light.name: {
            "type": "rectangle",
            "to_world": to_world_matrix(mat),
            # Coaxial light: emit toward the work via the (virtual) beam
            # splitter. ``flip_normals`` aligns the emission with the
            # transform's local -Z, and a ``null`` BSDF lets the camera
            # ray pass through the imaginary beam splitter without being
            # blocked.
            "flip_normals": True,
            "bsdf": _NULL_BSDF,
            "emitter": _make_emitter(light.color, light.intensity * 0.5),
        }
    }


def _make_backlight(light: Backlight) -> dict[str, Any]:
    mat = light.transform.to_matrix().copy()
    mat[:3, 0] *= light.width_mm * 0.5
    mat[:3, 1] *= light.height_mm * 0.5
    return {
        light.name: {
            "type": "rectangle",
            "to_world": to_world_matrix(mat),
            "emitter": _make_emitter(light.color, light.intensity),
        }
    }


def _make_dome(light: DomeLight) -> dict[str, Any]:
    mat = light.transform.to_matrix().copy()
    mat[:3, :3] *= light.radius_mm
    return {
        light.name: {
            "type": "sphere",
            "to_world": to_world_matrix(mat),
            # Dome lights illuminate the work from the inner surface of the
            # sphere -- flip the surface normal inward so the area emitter
            # radiates toward the work at the centre. The ``null`` BSDF lets
            # the camera ray pass through the (otherwise opaque) dome shell
            # without being blocked.
            "flip_normals": True,
            "bsdf": _NULL_BSDF,
            "emitter": _make_emitter(light.color, light.intensity),
        }
    }


def _light_to_shapes(light: Light) -> dict[str, Any]:
    if isinstance(light, PointLight):
        return _make_point(light)
    if isinstance(light, RectAreaLight):
        return _make_rect_area(light)
    if isinstance(light, RingLight):
        return _make_ring(light)
    if isinstance(light, BarLight):
        return _make_bar(light)
    if isinstance(light, CoaxialLight):
        return _make_coaxial(light)
    if isinstance(light, Backlight):
        return _make_backlight(light)
    if isinstance(light, DomeLight):
        return _make_dome(light)
    raise TypeError(f"Unsupported light type: {type(light).__name__}")


def _primitive_shape(target: Target) -> dict[str, Any]:
    geom = target.geometry
    assert isinstance(geom, TargetPrimitive)
    prim = geom.primitive
    base = target.transform.to_matrix().copy()
    if prim.kind is PrimitiveKind.cube:
        sx, sy, sz = (s * 0.5 for s in prim.size_mm)
        base[:3, 0] *= sx
        base[:3, 1] *= sy
        base[:3, 2] *= sz
        return {"type": "cube", "to_world": to_world_matrix(base)}
    if prim.kind is PrimitiveKind.sphere:
        base[:3, :3] *= prim.radius_mm
        return {"type": "sphere", "to_world": to_world_matrix(base)}
    if prim.kind is PrimitiveKind.plane:
        sx, sy, sz = prim.size_mm
        # Model stage planes as thin slabs so dielectric materials (e.g. BK7)
        # have physical thickness for refraction and attenuation.
        thickness = max(float(sz), 0.05)
        base[:3, 0] *= sx * 0.5
        base[:3, 1] *= sy * 0.5
        base[:3, 2] *= thickness * 0.5
        return {"type": "cube", "to_world": to_world_matrix(base)}
    if prim.kind is PrimitiveKind.cylinder:
        h = prim.size_mm[2]
        return {
            "type": "cylinder",
            "to_world": to_world_matrix(base),
            "p0": [0.0, 0.0, -h * 0.5],
            "p1": [0.0, 0.0, h * 0.5],
            "radius": prim.radius_mm,
        }
    raise TypeError(f"Unsupported primitive kind: {prim.kind}")


def _mesh_shape(target: Target) -> dict[str, Any]:
    from ..io.mesh_loader import resolve_mesh_path_for_render

    geom = target.geometry
    assert isinstance(geom, TargetMesh)
    mat = target.transform.to_matrix().copy()
    if geom.scale != 1.0:
        mat[:3, :3] *= geom.scale
    mesh_path = resolve_mesh_path_for_render(geom)
    path_lower = mesh_path.lower()
    if path_lower.endswith(".ply"):
        shape_type = "ply"
    elif path_lower.endswith(".obj"):
        shape_type = "obj"
    elif path_lower.endswith(".stl"):
        shape_type = "obj"
    else:
        shape_type = "ply"
    return {
        "type": shape_type,
        "filename": mesh_path,
        "to_world": to_world_matrix(mat),
    }


def _target_to_shape(target: Target) -> dict[str, Any]:
    if isinstance(target.geometry, TargetMesh):
        shape = _mesh_shape(target)
    else:
        shape = _primitive_shape(target)
    shape["bsdf"] = _material_to_bsdf(target.material)
    return {target.name: shape}


def build_mitsuba_dict(
    scene: Scene,
    *,
    spp: int = 64,
    max_depth: int = 8,
    integrator: str = "path",
) -> dict[str, Any]:
    """Translate an :class:`optsim.domain.Scene` into a Mitsuba 3 scene dict."""

    sensor_dict = build_orthographic_sensor_dict(scene.camera, scene.lens, spp=spp)

    scene_dict: dict[str, Any] = {
        "type": "scene",
        "integrator": {
            "type": integrator,
            "max_depth": max_depth,
        },
        "sensor": sensor_dict,
    }

    for target in scene.targets:
        if not target.visible:
            continue
        scene_dict.update(_target_to_shape(target))

    for light in scene.lights:
        if not light.enabled:
            continue
        scene_dict.update(_light_to_shapes(light))

    bg = scene.background_color
    if max(bg) > 1e-4:
        scene_dict["__background"] = {
            "type": "constant",
            "radiance": {"type": "rgb", "value": list(bg)},
        }

    return scene_dict
