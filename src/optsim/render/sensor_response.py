"""Sensor response model: convert physical radiance into a quantised image.

This module turns the HDR radiance image emitted by Mitsuba into a digital
image with the requested bit depth, including:

- spectral integration into a monochrome / RGB response,
- linear exposure scaling (exposure time, gain in dB),
- shot noise (Poisson on collected electrons),
- read noise (Gaussian, in electrons),
- dark current noise (Poisson, scaled by exposure),
- well capacity clipping,
- quantisation to the requested bit depth.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..domain.camera import Sensor


@dataclass
class SensorResponseResult:
    """Per-pixel intermediate quantities, mostly useful for diagnostics."""

    digital: np.ndarray
    electrons: np.ndarray
    saturated_mask: np.ndarray


def _radiance_to_electrons(
    radiance: np.ndarray,
    sensor: Sensor,
    *,
    radiance_scale: float,
) -> np.ndarray:
    """Approximate conversion from incident radiance to collected electrons.

    The conversion is intentionally simple: a single coefficient
    ``radiance_scale`` lets the user calibrate the simulator against a real
    measurement when needed. Quantum efficiency, exposure time, and gain are
    folded in here so the rest of the pipeline only deals with electrons.
    """
    exposure_s = sensor.exposure_time_ms * 1e-3
    gain = 10.0 ** (sensor.gain_db / 20.0)
    if radiance.ndim == 3 and sensor.monochrome:
        r = radiance[..., 0] * 0.2126
        g = radiance[..., 1] * 0.7152
        b = radiance[..., 2] * 0.0722
        mono = r + g + b
        scalar = mono
    else:
        scalar = radiance
    return scalar * radiance_scale * exposure_s * sensor.quantum_efficiency * gain


def apply_sensor_response(
    radiance: np.ndarray,
    sensor: Sensor,
    *,
    radiance_scale: float = 1.0e3,
    seed: int | None = None,
    add_noise: bool = True,
) -> SensorResponseResult:
    """Apply the sensor response chain to an HDR radiance image.

    Parameters
    ----------
    radiance:
        Float radiance image either as ``HxW`` or ``HxWxC``.
    sensor:
        Sensor parameters.
    radiance_scale:
        Calibration factor that maps the renderer's energy units onto
        electrons. The default value gives sensible exposure ranges for the
        scene units defined in this project.
    seed:
        Optional RNG seed for deterministic noise.
    """
    rng = np.random.default_rng(seed)
    radiance = np.asarray(radiance, dtype=np.float64)
    radiance = np.clip(radiance, 0.0, None)

    signal_e = _radiance_to_electrons(radiance, sensor, radiance_scale=radiance_scale)

    if add_noise:
        dark_e = sensor.dark_current_e_per_s * (sensor.exposure_time_ms * 1e-3)
        total_e_mean = signal_e + dark_e
        shot = rng.poisson(np.clip(total_e_mean, 0, None)).astype(np.float64)
        read = rng.normal(0.0, sensor.read_noise_e, size=signal_e.shape)
        electrons = shot + read
    else:
        electrons = signal_e.copy()

    saturated = electrons >= sensor.full_well_e
    electrons = np.clip(electrons, 0.0, sensor.full_well_e)

    max_dn = (1 << sensor.bit_depth) - 1
    digital = electrons / sensor.full_well_e * max_dn
    digital = np.round(digital).astype(np.float64)
    if sensor.black_level_dn > 0.0:
        digital = np.clip(digital - sensor.black_level_dn, 0.0, max_dn)
    dtype = np.uint16 if sensor.bit_depth > 8 else np.uint8
    digital = digital.astype(dtype)

    return SensorResponseResult(digital=digital, electrons=electrons, saturated_mask=saturated)
