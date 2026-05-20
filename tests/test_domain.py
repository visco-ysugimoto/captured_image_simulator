"""Smoke tests for the domain layer."""

from __future__ import annotations

import numpy as np

from optsim.domain import (
    Camera,
    PointLight,
    RingLight,
    Scene,
    Target,
    TelecentricLens,
)
from optsim.domain.common import Transform, look_at_rotation_deg
from optsim.domain.target import Primitive, PrimitiveKind, TargetPrimitive
from optsim.presets import get_material_preset


def test_default_scene_validates() -> None:
    scene = Scene(
        camera=Camera(),
        lens=TelecentricLens(),
        lights=[PointLight(name="p1")],
        targets=[
            Target(
                name="cube",
                geometry=TargetPrimitive(primitive=Primitive(kind=PrimitiveKind.cube)),
            )
        ],
    )
    assert scene.camera.sensor.width_px > 0
    assert scene.find_target("cube") is not None
    assert scene.find_light("p1") is not None


def test_lens_aperture_derivation() -> None:
    lens = TelecentricLens(magnification=0.5, working_distance_mm=80.0, na=0.1, f_number=None)
    assert 0.0 < lens.aperture_radius_object_mm < 80.0


def test_transform_forward_default() -> None:
    t = Transform()
    fwd = t.forward()
    np.testing.assert_allclose(fwd, np.array([0.0, 0.0, -1.0]), atol=1e-6)


def test_look_at_rotation_resolves_180() -> None:
    rx, ry, rz = look_at_rotation_deg((0, 0, 100), (0, 0, 0))
    t = Transform(position=(0, 0, 100), rotation_deg=(rx, ry, rz))
    fwd = t.forward()
    np.testing.assert_allclose(fwd, np.array([0.0, 0.0, -1.0]), atol=1e-5)


def test_ring_light_segments() -> None:
    rl = RingLight(name="r", segments=8)
    assert rl.kind.value == "ring"
    assert rl.segments == 8


def test_stage_glass_bk7_preset() -> None:
    mat = get_material_preset("stage_glass_bk7")
    assert mat.kind.value == "dielectric"
    assert abs(mat.ior - 1.5168) < 1e-4
