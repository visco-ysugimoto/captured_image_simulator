"""Tests for parameter sweep helpers."""

from __future__ import annotations

import pytest

from optsim.analysis.sweep import SweepResult, _set_dotted, run_sweep
from optsim.domain import Camera, Scene, TelecentricLens
from optsim.domain.light import RingLight
from optsim.domain.target import Primitive, PrimitiveKind, Target, TargetPrimitive
from optsim.render import RenderSettings
from optsim.render.cancellation import RenderCancellation


def _minimal_scene() -> Scene:
    return Scene(
        camera=Camera(),
        lens=TelecentricLens(),
        lights=[RingLight(name="ring", intensity=500.0)],
        targets=[
            Target(
                name="cube",
                geometry=TargetPrimitive(
                    primitive=Primitive(kind=PrimitiveKind.cube)
                ),
            )
        ],
    )


def test_set_dotted_light_intensity() -> None:
    scene = _minimal_scene()
    updated = _set_dotted(scene, "lights.0.intensity", 999.0)
    assert updated.lights[0].intensity == 999.0


def test_set_dotted_position_z() -> None:
    scene = _minimal_scene()
    updated = _set_dotted(scene, "camera.transform.position.2", 150.0)
    assert updated.camera.transform.position[2] == 150.0


def test_run_sweep_collects_metrics() -> None:
    scene = _minimal_scene()
    result = run_sweep(
        scene,
        "lights.0.intensity",
        [100.0, 200.0],
        settings=RenderSettings(spp=1, use_fallback=True, preview_scale=0.1),
    )
    assert isinstance(result, SweepResult)
    assert len(result.metrics) == 2
    assert len(result.renders) == 2
    assert result.metrics[0].mean >= 0.0


def test_run_sweep_cancellation() -> None:
    scene = _minimal_scene()
    cancel = RenderCancellation()
    cancel.request()
    result = run_sweep(
        scene,
        "lights.0.intensity",
        [100.0, 200.0, 300.0],
        settings=RenderSettings(spp=1, use_fallback=True, preview_scale=0.1),
        cancellation=cancel,
    )
    assert result.cancelled
    assert len(result.metrics) == 0
