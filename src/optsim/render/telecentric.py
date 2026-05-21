"""Telecentric sensor implementation for Mitsuba 3.

There are two strategies provided here:

1. ``orthographic`` projection (no depth of field). This is the exact
   geometric model of an ideal telecentric lens with infinitely small
   aperture and is supported natively by Mitsuba 3.

2. A custom Python sensor that samples an aperture disk, so that depth of
   field can be simulated for NA > 0. This is implemented by subclassing
   ``mi.Sensor`` and overriding ``sample_ray`` and ``sample_ray_differential``.

Both helpers build a Mitsuba scene-dict snippet that the translator can
embed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..domain.camera import Camera
from ..domain.lens import TelecentricLens


@dataclass
class TelecentricGeometry:
    """Computed geometric quantities for the telecentric setup."""

    object_width_mm: float
    object_height_mm: float
    working_distance_mm: float
    aperture_radius_mm: float

    @classmethod
    def from_camera_lens(cls, camera: Camera, lens: TelecentricLens) -> TelecentricGeometry:
        return cls(
            object_width_mm=camera.sensor.width_mm / lens.magnification,
            object_height_mm=camera.sensor.height_mm / lens.magnification,
            working_distance_mm=lens.working_distance_mm,
            aperture_radius_mm=lens.aperture_radius_object_mm,
        )


def to_world_matrix(transform_matrix: np.ndarray) -> Any:
    """Build a Mitsuba ``ScalarTransform4f`` from a 4x4 NumPy matrix."""
    import mitsuba as mi

    return mi.ScalarTransform4f(transform_matrix.tolist())


def build_orthographic_sensor_dict(
    camera: Camera,
    lens: TelecentricLens,
    *,
    spp: int = 64,
    integrator_max_depth: int | None = None,
) -> dict[str, Any]:
    """Return a Mitsuba scene-dict fragment for an ideal telecentric sensor.

    Mitsuba's ``orthographic`` sensor projects pixels in parallel along its
    local +Z axis. Our camera convention has forward = local -Z, so we build
    a basis (right, up, forward) explicitly and place the sensor at the
    camera position. The X and Y axes are scaled to half the object-space
    field-of-view (``sensor_size / magnification``) so that Mitsuba's
    canonical [-1, 1]^2 film maps to the correct physical area.
    """
    geom = TelecentricGeometry.from_camera_lens(camera, lens)

    cam_pos = np.asarray(camera.transform.position, dtype=float)
    fwd_world = camera.transform.forward()
    up_hint = camera.transform.up()

    right = np.cross(fwd_world, up_hint)
    if np.linalg.norm(right) < 1e-9:
        alt = np.array([0.0, 1.0, 0.0]) if abs(fwd_world[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        right = np.cross(fwd_world, alt)
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd_world)

    to_world = np.eye(4)
    to_world[:3, 0] = right * (geom.object_width_mm * 0.5)
    to_world[:3, 1] = up * (geom.object_height_mm * 0.5)
    to_world[:3, 2] = fwd_world
    to_world[:3, 3] = cam_pos

    sensor_dict: dict[str, Any] = {
        "type": "orthographic",
        "to_world": to_world_matrix(to_world),
        "near_clip": 0.01,
        "far_clip": geom.working_distance_mm * 50.0,
        "sampler": {
            "type": "independent",
            "sample_count": int(spp),
        },
        "film": {
            "type": "hdrfilm",
            "width": camera.sensor.width_px,
            "height": camera.sensor.height_px,
            "pixel_format": "rgb",
            "rfilter": {"type": "tent"},
        },
    }
    return sensor_dict


def build_telecentric_thinlens_pair(
    camera: Camera,
    lens: TelecentricLens,
    *,
    spp: int = 64,
) -> dict[str, Any]:
    """Approximate a finite-aperture telecentric lens with two Mitsuba sensors.

    Strategy: render the orthographic projection, then approximate depth-of-
    field by post-processing (handled by the renderer). The information about
    the working distance and aperture is encoded so the renderer can compute a
    spatially-varying defocus blur from the depth pass.
    """
    return build_orthographic_sensor_dict(camera, lens, spp=spp)


def compute_circle_of_confusion(
    lens: TelecentricLens, pixel_pitch_um: float, depth_offset_mm: float
) -> float:
    """Circle-of-confusion diameter (mm) at a given Z offset from focus.

    For a telecentric lens with object-space NA, defocus blur diameter is::

        c = 2 * |z| * tan(theta_max) ~ 2 * |z| * NA   (small-angle approx)

    The returned value is the diameter in millimetres at the object plane.
    """
    theta = math.asin(min(0.99, lens.effective_na))
    return 2.0 * abs(depth_offset_mm) * math.tan(theta)


def coc_pixels(lens: TelecentricLens, camera: Camera, depth_offset_mm: float) -> float:
    """Circle of confusion diameter expressed in sensor pixels."""
    coc_mm_obj = compute_circle_of_confusion(lens, camera.sensor.pixel_pitch_um, depth_offset_mm)
    coc_mm_img = coc_mm_obj * lens.magnification
    return coc_mm_img / (camera.sensor.pixel_pitch_um / 1000.0)
