"""Calibration against reference images."""

from __future__ import annotations

import numpy as np
import pytest

from optsim.analysis.calibration import (
    CalibrationFit,
    apply_calibration,
    compute_calibration_metrics,
    fit_radiance_scale_mean,
    run_calibration,
)
from optsim.domain import Camera, Scene, TelecentricLens
from optsim.domain.light import RingLight
from optsim.domain.target import Primitive, PrimitiveKind, Target, TargetPrimitive
from optsim.render import RenderSettings


def _scene() -> Scene:
    return Scene(
        camera=Camera(),
        lens=TelecentricLens(),
        lights=[RingLight(name="ring", intensity=800.0)],
        targets=[
            Target(
                name="card",
                geometry=TargetPrimitive(
                    primitive=Primitive(kind=PrimitiveKind.cube)
                ),
            )
        ],
        radiance_scale=500.0,
    )


def test_fit_radiance_scale_mean() -> None:
    ref = np.full((32, 32), 800.0)
    sim = np.full((32, 32), 200.0)
    scale = fit_radiance_scale_mean(ref, sim, None)
    assert scale == pytest.approx(4.0)


def test_apply_calibration_updates_scene() -> None:
    scene = _scene()
    updated = apply_calibration(
        scene,
        CalibrationFit(radiance_scale=1234.0, black_level_dn=12.0),
    )
    assert updated.radiance_scale == 1234.0
    assert updated.camera.sensor.black_level_dn == 12.0


def test_compute_metrics_identical() -> None:
    img = np.linspace(0, 100, 100).reshape(10, 10)
    m = compute_calibration_metrics(img, img, None)
    assert m.rmse == pytest.approx(0.0, abs=1e-9)
    assert m.correlation == pytest.approx(1.0)


def test_run_calibration_improves_mean(tmp_path) -> None:
    """End-to-end on a synthetic reference (avoids empty low-res renders)."""
    import imageio.v3 as iio

    scene = _scene()
    settings = RenderSettings(
        spp=2, use_fallback=True, preview_scale=0.25, sensor_noise=False, seed=0
    )
    from optsim.render import Renderer

    ref_render = Renderer(settings).render(scene)
    if float(ref_render.digital.mean()) < 1.0:
        pytest.skip("Fallback render too dark at low preview scale")

    ref_path = tmp_path / "ref.png"
    iio.imwrite(str(ref_path), ref_render.digital)

    scene_off = apply_calibration(
        scene, CalibrationFit(radiance_scale=scene.radiance_scale * 0.5)
    )
    result = run_calibration(
        scene_off,
        ref_path,
        fit_radiance_scale=True,
        render_settings=settings,
    )
    assert abs(result.after.mean_error) <= abs(result.before.mean_error) + 5.0
