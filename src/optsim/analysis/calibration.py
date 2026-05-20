"""Calibrate simulator parameters against a reference camera image."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..domain import Scene
from ..io.image_io import load_image
from ..render import RenderResult, Renderer, RenderSettings
from .metrics import _slice_roi, _to_luma


@dataclass
class CalibrationFit:
    """Fitted parameter values to apply to a :class:`~optsim.domain.Scene`."""

    radiance_scale: float | None = None
    black_level_dn: float | None = None
    quantum_efficiency: float | None = None


@dataclass
class CalibrationMetrics:
    """Agreement between reference and simulated images in the ROI."""

    mean_reference: float
    mean_simulated: float
    mean_error: float
    rmse: float
    correlation: float
    n_pixels: int


@dataclass
class CalibrationResult:
    reference_path: str
    roi: tuple[int, int, int, int] | None
    dark_roi: tuple[int, int, int, int] | None
    fit: CalibrationFit
    before: CalibrationMetrics
    after: CalibrationMetrics
    reference_shape: tuple[int, ...]
    simulated_shape: tuple[int, ...]
    render_engine: str = ""
    notes: list[str] = field(default_factory=list)


def parse_roi(text: str) -> tuple[int, int, int, int] | None:
    """Parse ``x,y,w,h`` or return ``None`` for full image."""
    text = text.strip()
    if not text:
        return None
    parts = [int(p.strip()) for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError("ROI must be four comma-separated integers: x,y,w,h")
    return (parts[0], parts[1], parts[2], parts[3])


def reference_to_dn(
    image: np.ndarray,
    *,
    bit_depth: int | None = None,
) -> np.ndarray:
    """Convert a loaded reference image to float DN (luminance)."""
    del bit_depth  # reserved for future bit-depth normalisation
    return _to_luma(np.asarray(image)).astype(np.float64)


def align_reference_to_simulation(
    reference: np.ndarray,
    target_shape: tuple[int, int],
) -> tuple[np.ndarray, list[str]]:
    """Crop or pad notes when reference and simulation sizes differ."""
    notes: list[str] = []
    ref = reference
    th, tw = target_shape
    rh, rw = ref.shape[:2]
    if (rh, rw) == (th, tw):
        return ref, notes
    if rh >= th and rw >= tw:
        y0 = (rh - th) // 2
        x0 = (rw - tw) // 2
        notes.append(f"Reference centre-cropped ({rw}x{rh}) -> ({tw}x{th}).")
        return ref[y0 : y0 + th, x0 : x0 + tw], notes
    notes.append(
        f"Size mismatch ref ({rw}x{rh}) vs sim ({tw}x{th}); "
        "using top-left overlap."
    )
    out = np.zeros((th, tw), dtype=np.float64)
    h, w = min(rh, th), min(rw, tw)
    out[:h, :w] = ref[:h, :w]
    return out, notes


def _roi_pixels(image: np.ndarray, roi: tuple[int, int, int, int] | None) -> np.ndarray:
    return _slice_roi(image, roi).reshape(-1)


def compute_calibration_metrics(
    reference: np.ndarray,
    simulated: np.ndarray,
    roi: tuple[int, int, int, int] | None,
) -> CalibrationMetrics:
    ref = _roi_pixels(reference, roi)
    sim = _roi_pixels(simulated, roi)
    n = min(ref.size, sim.size)
    ref, sim = ref[:n], sim[:n]
    err = sim - ref
    mean_ref = float(ref.mean())
    mean_sim = float(sim.mean())
    rmse = float(np.sqrt(np.mean(err * err)))
    if ref.std() < 1e-9 or sim.std() < 1e-9:
        corr = 1.0 if np.allclose(ref, sim) else 0.0
    else:
        corr = float(np.corrcoef(ref, sim)[0, 1])
    return CalibrationMetrics(
        mean_reference=mean_ref,
        mean_simulated=mean_sim,
        mean_error=mean_sim - mean_ref,
        rmse=rmse,
        correlation=corr,
        n_pixels=int(n),
    )


def fit_radiance_scale_mean(
    reference: np.ndarray,
    simulated_at_unit_scale: np.ndarray,
    roi: tuple[int, int, int, int] | None,
    *,
    black_level_dn: float = 0.0,
) -> float:
    """Return ``radiance_scale`` so ROI mean DN matches the reference."""
    ref_m = float(_roi_pixels(reference, roi).mean())
    sim_m = float(_roi_pixels(simulated_at_unit_scale, roi).mean())
    if abs(sim_m) < 1e-9:
        raise ValueError("Simulated ROI mean is near zero; cannot fit radiance_scale.")
    return max(1e-12, (ref_m + black_level_dn) / sim_m)


def fit_black_level_mean(
    reference: np.ndarray,
    simulated: np.ndarray,
    dark_roi: tuple[int, int, int, int],
) -> float:
    """Estimate ``black_level_dn`` from a dark ROI after scale is set."""
    ref_m = float(_roi_pixels(reference, dark_roi).mean())
    sim_m = float(_roi_pixels(simulated, dark_roi).mean())
    return max(0.0, sim_m - ref_m)


def fit_scale_and_offset_lstsq(
    reference: np.ndarray,
    simulated: np.ndarray,
    roi: tuple[int, int, int, int] | None,
) -> tuple[float, float]:
    """Least-squares ``ref ≈ scale * sim + offset`` in the ROI."""
    ref = _roi_pixels(reference, roi)
    sim = _roi_pixels(simulated, roi)
    design = np.column_stack([sim, np.ones_like(sim)])
    scale, offset = np.linalg.lstsq(design, ref, rcond=None)[0]
    return float(max(scale, 1e-12)), float(offset)


def apply_calibration(scene: Scene, fit: CalibrationFit) -> Scene:
    """Return a new scene with fitted parameters applied."""
    data = scene.model_dump(mode="python")
    if fit.radiance_scale is not None:
        data["radiance_scale"] = float(fit.radiance_scale)
    if fit.black_level_dn is not None:
        data["camera"]["sensor"]["black_level_dn"] = float(fit.black_level_dn)
    if fit.quantum_efficiency is not None:
        data["camera"]["sensor"]["quantum_efficiency"] = float(fit.quantum_efficiency)
    return Scene.model_validate(data)


def _default_calib_render_settings() -> RenderSettings:
    return RenderSettings(
        use_fallback=True,
        preview_scale=0.5,
        spp=4,
        light_samples=8,
        sensor_noise=False,
        seed=0,
    )


def run_calibration(
    scene: Scene,
    reference_path: str | Path,
    *,
    roi: tuple[int, int, int, int] | None = None,
    dark_roi: tuple[int, int, int, int] | None = None,
    fit_radiance_scale: bool = True,
    fit_black_level: bool = False,
    fit_quantum_efficiency: bool = False,
    use_lstsq_offset: bool = False,
    render_settings: RenderSettings | None = None,
) -> CalibrationResult:
    """Render, fit parameters, re-render, and return before/after metrics."""
    path = Path(reference_path)
    ref_dn = reference_to_dn(load_image(path))

    settings = render_settings or _default_calib_render_settings()
    settings = RenderSettings(
        **{**settings.__dict__, "sensor_noise": False, "seed": 0}
    )
    renderer = Renderer(settings)

    before_result: RenderResult = renderer.render(scene)
    sim_before = _to_luma(before_result.digital.astype(np.float64))

    scene_unit = apply_calibration(scene, CalibrationFit(radiance_scale=1.0))
    unit_result: RenderResult = renderer.render(scene_unit)
    sim_unit = _to_luma(unit_result.digital.astype(np.float64))

    ref_aligned, align_notes = align_reference_to_simulation(
        ref_dn, (sim_unit.shape[0], sim_unit.shape[1])
    )
    sim_before, _ = align_reference_to_simulation(
        sim_before, ref_aligned.shape[:2]
    )

    before = compute_calibration_metrics(ref_aligned, sim_before, roi)

    fit = CalibrationFit()
    notes = list(align_notes)
    working = scene

    if fit_radiance_scale:
        bl_hint = 0.0 if (fit_black_level and dark_roi) else float(
            scene.camera.sensor.black_level_dn
        )
        if use_lstsq_offset and not dark_roi:
            scale, offset = fit_scale_and_offset_lstsq(ref_aligned, sim_unit, roi)
            fit.radiance_scale = scale
            notes.append(f"LSTSQ radiance_scale={scale:.4g}, offset={offset:.2g}")
            if fit_black_level:
                fit.black_level_dn = max(0.0, -offset)
        else:
            fit.radiance_scale = fit_radiance_scale_mean(
                ref_aligned, sim_unit, roi, black_level_dn=bl_hint
            )
            notes.append(f"Mean-matched radiance_scale={fit.radiance_scale:.4g}")
        working = apply_calibration(
            working, CalibrationFit(radiance_scale=fit.radiance_scale)
        )

    if fit_black_level and dark_roi is not None:
        sim_mid = _to_luma(renderer.render(working).digital.astype(np.float64))
        sim_mid, _ = align_reference_to_simulation(sim_mid, ref_aligned.shape[:2])
        fit.black_level_dn = fit_black_level_mean(ref_aligned, sim_mid, dark_roi)
        notes.append(f"Dark ROI black_level_dn={fit.black_level_dn:.2f}")
        working = apply_calibration(working, CalibrationFit(black_level_dn=fit.black_level_dn))

    if fit_quantum_efficiency:
        ratio = before.mean_reference / max(before.mean_simulated, 1e-9)
        new_qe = float(np.clip(scene.camera.sensor.quantum_efficiency * ratio, 0.01, 1.0))
        fit.quantum_efficiency = new_qe
        notes.append(f"quantum_efficiency={new_qe:.4f}")
        working = apply_calibration(working, CalibrationFit(quantum_efficiency=new_qe))

    after_result: RenderResult = renderer.render(working)
    sim_after = _to_luma(after_result.digital.astype(np.float64))
    sim_after, _ = align_reference_to_simulation(sim_after, ref_aligned.shape[:2])
    after = compute_calibration_metrics(ref_aligned, sim_after, roi)

    engine = after_result.extras.get("engine", "?") if after_result.extras else "?"

    return CalibrationResult(
        reference_path=str(path),
        roi=roi,
        dark_roi=dark_roi,
        fit=fit,
        before=before,
        after=after,
        reference_shape=tuple(ref_dn.shape),
        simulated_shape=tuple(sim_after.shape),
        render_engine=str(engine),
        notes=notes,
    )
