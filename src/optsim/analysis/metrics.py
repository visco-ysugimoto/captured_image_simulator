"""Inspection-fitness metrics for simulated images.

All functions accept either a 2D mono image or a 3D RGB image; RGB is
converted to luminance with Rec.709 weights before evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _to_luma(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image, dtype=np.float64)
    if arr.ndim == 2:
        return arr
    if arr.ndim == 3:
        return 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    raise ValueError(f"Unsupported image shape: {arr.shape}")


def _slice_roi(image: np.ndarray, roi: tuple[int, int, int, int] | None) -> np.ndarray:
    if roi is None:
        return image
    x, y, w, h = roi
    return image[y : y + h, x : x + w]


def michelson_contrast(
    image: np.ndarray,
    roi: tuple[int, int, int, int] | None = None,
) -> float:
    """Michelson contrast: (Imax - Imin) / (Imax + Imin)."""
    luma = _slice_roi(_to_luma(image), roi)
    imax = float(luma.max())
    imin = float(luma.min())
    denom = imax + imin
    if denom < 1e-9:
        return 0.0
    return (imax - imin) / denom


def weber_contrast(
    image: np.ndarray,
    foreground_roi: tuple[int, int, int, int],
    background_roi: tuple[int, int, int, int],
) -> float:
    """Weber contrast: (I_fg - I_bg) / I_bg."""
    luma = _to_luma(image)
    fg = float(_slice_roi(luma, foreground_roi).mean())
    bg = float(_slice_roi(luma, background_roi).mean())
    if bg < 1e-9:
        return float("inf") if fg > 0 else 0.0
    return (fg - bg) / bg


def snr_db(
    image: np.ndarray,
    roi: tuple[int, int, int, int] | None = None,
) -> float:
    """Signal-to-noise ratio in dB on a uniform ROI."""
    luma = _slice_roi(_to_luma(image), roi)
    mean = float(luma.mean())
    std = float(luma.std())
    if std < 1e-9:
        return float("inf")
    return 20.0 * float(np.log10(mean / std))


def histogram(
    image: np.ndarray,
    bins: int = 256,
    *,
    bit_depth: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (counts, bin_edges) of luminance values."""
    luma = _to_luma(image)
    if bit_depth is not None:
        hi = (1 << bit_depth) - 1
    elif luma.dtype.kind in "iu":
        hi = int(np.iinfo(luma.dtype).max)
    else:
        hi = float(max(1e-6, luma.max()))
    counts, edges = np.histogram(luma, bins=bins, range=(0, hi))
    return counts, edges


@dataclass
class EdgeProfile:
    distance: np.ndarray
    intensity: np.ndarray
    edge_position: float
    edge_width_10_90: float

    @property
    def slope(self) -> float:
        return float(np.gradient(self.intensity, self.distance).max())


def edge_profile(
    image: np.ndarray,
    p0: tuple[float, float],
    p1: tuple[float, float],
    *,
    samples: int = 200,
) -> EdgeProfile:
    """Sample an intensity profile along a line and analyse the edge response.

    The 10%-to-90% rise width is reported as an indicator of effective
    resolution. Sub-pixel sampling uses bilinear interpolation.
    """
    luma = _to_luma(image)
    x = np.linspace(p0[0], p1[0], samples)
    y = np.linspace(p0[1], p1[1], samples)
    x0 = np.clip(np.floor(x).astype(int), 0, luma.shape[1] - 2)
    y0 = np.clip(np.floor(y).astype(int), 0, luma.shape[0] - 2)
    fx = x - x0
    fy = y - y0
    v00 = luma[y0, x0]
    v10 = luma[y0, x0 + 1]
    v01 = luma[y0 + 1, x0]
    v11 = luma[y0 + 1, x0 + 1]
    intensity = (
        v00 * (1 - fx) * (1 - fy)
        + v10 * fx * (1 - fy)
        + v01 * (1 - fx) * fy
        + v11 * fx * fy
    )
    dist = np.hypot(x - x[0], y - y[0])

    lo, hi = float(intensity.min()), float(intensity.max())
    span = max(hi - lo, 1e-9)
    norm = (intensity - lo) / span
    i_10 = int(np.argmax(norm >= 0.1))
    i_90 = int(np.argmax(norm >= 0.9))
    if i_90 <= i_10:
        edge_w = float("nan")
    else:
        edge_w = float(dist[i_90] - dist[i_10])

    i_50 = int(np.argmax(norm >= 0.5))
    edge_pos = float(dist[i_50])
    return EdgeProfile(
        distance=dist,
        intensity=intensity,
        edge_position=edge_pos,
        edge_width_10_90=edge_w,
    )


@dataclass
class ImageMetrics:
    mean: float
    std: float
    minimum: float
    maximum: float
    michelson: float
    snr_db: float
    saturated_fraction: float
    dynamic_range_used: float


def compute_metrics(
    image: np.ndarray,
    *,
    roi: tuple[int, int, int, int] | None = None,
    saturation_threshold: float | None = None,
) -> ImageMetrics:
    """Compute the standard set of inspection-fitness metrics."""
    luma = _slice_roi(_to_luma(image), roi)
    if luma.dtype.kind in "iu":
        max_possible = float(np.iinfo(luma.dtype).max)
    else:
        max_possible = float(max(1.0, luma.max()))
    if saturation_threshold is None:
        saturation_threshold = max_possible * 0.99
    saturated_fraction = float((luma >= saturation_threshold).mean())
    return ImageMetrics(
        mean=float(luma.mean()),
        std=float(luma.std()),
        minimum=float(luma.min()),
        maximum=float(luma.max()),
        michelson=michelson_contrast(image, roi),
        snr_db=snr_db(image, roi),
        saturated_fraction=saturated_fraction,
        dynamic_range_used=float(luma.max() - luma.min()) / max_possible,
    )
