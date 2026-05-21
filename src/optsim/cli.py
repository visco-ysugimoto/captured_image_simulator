"""Command-line interface for the optical simulator."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import click

from .analysis import apply_calibration, compute_metrics, run_calibration, run_sweep
from .io import load_image, load_project, save_image
from .io.project_file import save_project
from .render import Renderer, RenderSettings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@click.group(help="Optical / machine-vision imaging simulator.")
@click.version_option()
def main() -> None:
    """Entry point for the ``optsim`` command."""


@main.command(help="Render a scene file to an image.")
@click.argument("scene_path", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output", type=click.Path(dir_okay=False), default="render.png",
              show_default=True, help="Output image (.png, .tiff, .exr).")
@click.option("--spp", type=int, default=64, show_default=True, help="Samples per pixel.")
@click.option("--max-depth", type=int, default=6, show_default=True, help="Path tracer max depth.")
@click.option("--variant", default="scalar_rgb", show_default=True,
              help="Mitsuba variant, e.g. scalar_rgb, llvm_rgb, cuda_rgb.")
@click.option("--seed", type=int, default=None, help="Random seed for reproducible noise.")
@click.option("--fallback/--no-fallback", default=False,
              help="Force the trimesh raycaster fallback (no Mitsuba).")
@click.option("--light-samples", type=int, default=16, show_default=True,
              help="Number of point samples per area light (fallback only).")
@click.option("--dof/--no-dof", default=False,
              help="Apply depth-of-field blur using lens NA and depth map (fallback only).")
@click.option("--focus-z", type=float, default=None,
              help="World-Z of the in-focus plane. Defaults to camera.z - lens.WD.")
def render(scene_path: str, output: str, spp: int, max_depth: int, variant: str,
           seed: int | None, fallback: bool, light_samples: int,
           dof: bool, focus_z: float | None) -> None:
    scene = load_project(scene_path)
    settings = RenderSettings(
        spp=spp, max_depth=max_depth, variant=variant, seed=seed, use_fallback=fallback,
        light_samples=light_samples, depth_of_field=dof, focus_z_world=focus_z,
    )
    result = Renderer(settings).render(scene)
    save_image(result.digital, output, source_bit_depth=scene.camera.sensor.bit_depth)
    engine = result.extras.get("engine", "?")
    click.echo(f"Wrote {output} ({result.width} x {result.height}) using engine: {engine}")
    metrics = compute_metrics(result.digital)
    click.echo("Metrics:")
    for k, v in asdict(metrics).items():
        click.echo(f"  {k:24s} = {v:.4f}")


@main.command(help="Analyse an existing image and print metrics.")
@click.argument("image_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--roi", default=None,
              help="ROI as 'x,y,w,h' in pixels. If omitted, the whole image is used.")
@click.option("--json-out", "json_out", type=click.Path(dir_okay=False), default=None,
              help="If set, write the metrics as JSON to this path instead of printing.")
def analyze(image_path: str, roi: str | None, json_out: str | None) -> None:
    image = load_image(image_path)
    roi_t = None
    if roi:
        parts = [int(x) for x in roi.split(",")]
        if len(parts) != 4:
            raise click.BadOptionUsage("roi", "Expected 4 comma-separated integers.")
        roi_t = (parts[0], parts[1], parts[2], parts[3])
    metrics = compute_metrics(image, roi=roi_t)
    payload = asdict(metrics)
    if json_out:
        Path(json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        click.echo(f"Wrote {json_out}")
    else:
        for k, v in payload.items():
            click.echo(f"  {k:24s} = {v:.4f}")


@main.command(help="Sweep a scene parameter across a list of values.")
@click.argument("scene_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--param", required=True,
              help="Dotted path, e.g. 'lights.0.intensity' or 'camera.sensor.exposure_time_ms'.")
@click.option("--values", required=True,
              help="Comma-separated list of values (parsed as float when possible).")
@click.option("-o", "--output", type=click.Path(file_okay=False), default="sweep",
              show_default=True)
@click.option("--spp", type=int, default=32, show_default=True)
@click.option("--fallback/--no-fallback", default=False)
def sweep(scene_path: str, param: str, values: str, output: str, spp: int, fallback: bool) -> None:
    scene = load_project(scene_path)
    parsed: list = []
    for tok in values.split(","):
        tok = tok.strip()
        try:
            parsed.append(float(tok))
        except ValueError:
            parsed.append(tok)
    res = run_sweep(
        scene,
        param,
        parsed,
        settings=RenderSettings(spp=spp, use_fallback=fallback),
        output_dir=output,
    )
    click.echo(f"Sweep '{param}' completed across {len(parsed)} values; results in {output}/")
    for v, m in zip(res.values, res.metrics, strict=True):
        click.echo(f"  {v!r:>14}  mean={m.mean:8.2f}  michelson={m.michelson:.3f}  snr_dB={m.snr_db:6.2f}")


@main.command(help="Fit scene parameters to match a reference photograph.")
@click.argument("scene_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--reference", "-r", required=True, type=click.Path(exists=True, dir_okay=False),
    help="Measured image (PNG/TIFF) from the real camera.",
)
@click.option("--roi", default="", help="Signal ROI as x,y,w,h (default: full image).")
@click.option("--dark-roi", default="", help="Dark ROI for black_level_dn fit.")
@click.option("--fit-scale/--no-fit-scale", default=True, show_default=True)
@click.option("--fit-black/--no-fit-black", default=False, show_default=True)
@click.option("--fit-qe/--no-fit-qe", default=False, show_default=True)
@click.option("--lstsq/--no-lstsq", default=False, show_default=True,
              help="Per-pixel LSTSQ scale+offset instead of mean matching.")
@click.option("--apply/--no-apply", default=False,
              help="Write fitted parameters back to the scene file.")
@click.option("--output-scene", type=click.Path(dir_okay=False), default=None,
              help="Save calibrated scene to this path (implies --apply).")
@click.option("--spp", type=int, default=4, show_default=True)
@click.option("--preview-scale", type=float, default=0.5, show_default=True)
def calibrate(
    scene_path: str,
    reference: str,
    roi: str,
    dark_roi: str,
    fit_scale: bool,
    fit_black: bool,
    fit_qe: bool,
    lstsq: bool,
    apply: bool,
    output_scene: str | None,
    spp: int,
    preview_scale: float,
) -> None:
    from .analysis.calibration import parse_roi

    scene = load_project(scene_path)
    roi_t = parse_roi(roi) if roi.strip() else None
    dark_t = parse_roi(dark_roi) if dark_roi.strip() else None
    settings = RenderSettings(
        use_fallback=True,
        preview_scale=preview_scale,
        spp=spp,
        sensor_noise=False,
        seed=0,
    )
    result = run_calibration(
        scene,
        reference,
        roi=roi_t,
        dark_roi=dark_t,
        fit_radiance_scale=fit_scale,
        fit_black_level=fit_black,
        fit_quantum_efficiency=fit_qe,
        use_lstsq_offset=lstsq,
        render_settings=settings,
    )
    b, a = result.before, result.after
    click.echo(f"Reference: {result.reference_path}")
    click.echo(f"Engine: {result.render_engine}")
    click.echo("Before:")
    click.echo(
        f"  mean ref={b.mean_reference:.2f} sim={b.mean_simulated:.2f} "
        f"RMSE={b.rmse:.2f} r={b.correlation:.4f}"
    )
    click.echo("After:")
    click.echo(
        f"  mean ref={a.mean_reference:.2f} sim={a.mean_simulated:.2f} "
        f"RMSE={a.rmse:.2f} r={a.correlation:.4f}"
    )
    f = result.fit
    if f.radiance_scale is not None:
        click.echo(f"  radiance_scale = {f.radiance_scale:.6g}")
    if f.black_level_dn is not None:
        click.echo(f"  black_level_dn = {f.black_level_dn:.2f}")
    if f.quantum_efficiency is not None:
        click.echo(f"  quantum_efficiency = {f.quantum_efficiency:.4f}")
    for note in result.notes:
        click.echo(f"  note: {note}")

    do_apply = apply or output_scene is not None
    if do_apply:
        calibrated = apply_calibration(scene, f)
        out = output_scene or scene_path
        save_project(calibrated, out)
        click.echo(f"Wrote calibrated scene to {out}")


@main.command(help="Validate a scene file by loading it.")
@click.argument("scene_path", type=click.Path(exists=True, dir_okay=False))
def validate(scene_path: str) -> None:
    try:
        scene = load_project(scene_path)
    except Exception as exc:
        click.echo(f"INVALID: {exc}", err=True)
        sys.exit(1)
    click.echo(
        f"OK: {scene.name} ({len(scene.targets)} targets, {len(scene.lights)} lights)"
    )


@main.command(help="Check that runtime dependencies and the renderer are working.")
def doctor() -> None:
    """Diagnose the environment.

    Reports the versions of all critical dependencies and tries each Mitsuba
    variant in turn so the user can see exactly which path works.
    """
    import importlib
    import platform

    click.echo(f"Python      : {platform.python_version()} on {platform.platform()}")

    def check(name: str, attr: str = "__version__") -> None:
        try:
            mod = importlib.import_module(name)
            version = getattr(mod, attr, "?")
            click.echo(f"{name:12s}: OK    ({version})")
        except Exception as exc:
            click.echo(f"{name:12s}: MISSING ({exc})")

    for pkg in ["numpy", "pydantic", "yaml", "trimesh", "rtree", "cv2",
                "PyQt6", "pyvista", "pyvistaqt", "mitsuba", "drjit", "cascadio"]:
        check(pkg)

    from .io.mesh_loader import step_backend_available

    backend = step_backend_available()
    if backend:
        click.echo(f"\n-- STEP import --\n  backend: {backend}")
    else:
        click.echo(
            "\n-- STEP import --\n  NOT AVAILABLE — install: pip install cascadio"
        )

    click.echo("\n-- Mitsuba variants --")
    try:
        import mitsuba as mi
        available = list(mi.variants())
        click.echo(f"available   : {available}")
        # Probe a representative set of variants. Names changed between
        # Mitsuba versions; in 3.8 the LLVM/CUDA variants carry an `_ad_`
        # prefix because they're built with automatic-differentiation
        # support.
        candidates = [v for v in ("scalar_rgb", "scalar_spectral",
                                   "llvm_ad_rgb", "llvm_rgb",
                                   "cuda_ad_rgb", "cuda_rgb") if v in available]
        for variant in candidates:
            try:
                mi.set_variant(variant)
                scene_dict = {
                    "type": "scene",
                    "integrator": {"type": "path"},
                    "sensor": {
                        "type": "perspective",
                        "to_world": mi.ScalarTransform4f().look_at(
                            origin=[0, 0, 3], target=[0, 0, 0], up=[0, 1, 0]
                        ),
                        "film": {"type": "hdrfilm", "width": 16, "height": 16},
                        "sampler": {"type": "independent", "sample_count": 1},
                    },
                    "sphere": {"type": "sphere", "bsdf": {"type": "diffuse"}},
                    "emitter": {"type": "constant"},
                }
                msc = mi.load_dict(scene_dict)
                mi.render(msc, spp=1)
                click.echo(f"  {variant:14s}: OK")
            except Exception as exc:
                click.echo(f"  {variant:14s}: FAIL ({type(exc).__name__}: {exc})")
    except ImportError:
        click.echo("  Mitsuba is not installed.")

    click.echo("\n-- Render dry run --")
    try:
        from .domain import Camera, RingLight, Scene, Target, TelecentricLens
        from .domain.target import Primitive, PrimitiveKind, TargetPrimitive
        from .render import Renderer, RenderSettings
        scene = Scene(
            camera=Camera(),
            lens=TelecentricLens(),
            lights=[RingLight(name="r")],
            targets=[Target(name="t",
                            geometry=TargetPrimitive(primitive=Primitive(kind=PrimitiveKind.cube)))],
        )
        res = Renderer(RenderSettings(spp=1, use_fallback=True)).render(scene)
        click.echo(f"  fallback raycaster: OK ({res.width}x{res.height}, max DN {int(res.digital.max())})")
    except Exception as exc:
        click.echo(f"  fallback raycaster: FAIL ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    main()
