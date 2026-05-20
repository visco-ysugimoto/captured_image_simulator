"""Parameter sweep runner.

A sweep replays the same scene with a single parameter varied across a list
of values. The parameter is referenced by a dotted path that mirrors the
pydantic model layout, e.g. ``lights.0.intensity`` or
``camera.sensor.exposure_time_ms``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from ..domain import Scene
from ..io.image_io import save_image
from ..render import RenderResult, Renderer, RenderSettings
from ..render.cancellation import RenderCancellation, RenderCancelled
from .metrics import ImageMetrics, compute_metrics

# Common sweep parameters exposed in the GUI preset picker.
SWEEP_PARAM_PRESETS: dict[str, str] = {
    "Ring light intensity": "lights.0.intensity",
    "Sensor exposure [ms]": "camera.sensor.exposure_time_ms",
    "Sensor gain [dB]": "camera.sensor.gain_db",
    "Sensor QE": "camera.sensor.quantum_efficiency",
    "Read noise [e-]": "camera.sensor.read_noise_e",
    "Black level [DN]": "camera.sensor.black_level_dn",
    "Radiance scale (cal.)": "radiance_scale",
    "Lens NA": "lens.na",
    "Lens magnification": "lens.magnification",
    "Camera Z [mm]": "camera.transform.position.2",
}


@dataclass
class SweepResult:
    parameter: str
    values: list[Any]
    images: list[np.ndarray] = field(default_factory=list)
    metrics: list[ImageMetrics] = field(default_factory=list)
    renders: list[RenderResult] = field(default_factory=list)
    cancelled: bool = False


def _set_dotted(obj: Any, path: str, value: Any) -> Any:
    """Return a deep-copied scene with ``path`` set to ``value``.

    The scene is rebuilt through pydantic so validation runs on every step.
    Supports list/tuple indices (e.g. ``camera.transform.position.2``).
    """
    data = obj.model_dump(mode="python")
    parts = _split_dotted(path)

    def _assign(container: Any, remaining: list[str | int]) -> None:
        key = remaining[0]
        if len(remaining) == 1:
            if isinstance(container, list):
                container[key] = value  # type: ignore[index]
            elif isinstance(container, dict):
                container[key] = value
            else:
                raise TypeError(f"Cannot assign into {type(container)!r}")
            return
        child = container[key]  # type: ignore[index]
        if isinstance(child, tuple):
            child = list(child)
            container[key] = child  # type: ignore[index]
        _assign(child, remaining[1:])

    _assign(data, parts)
    return type(obj).model_validate(data)


def _split_dotted(path: str) -> list[str | int]:
    out: list[str | int] = []
    for token in path.split("."):
        if token.isdigit():
            out.append(int(token))
        else:
            out.append(token)
    return out


def run_sweep(
    scene: Scene,
    parameter: str,
    values: Sequence[Any],
    *,
    settings: RenderSettings | None = None,
    output_dir: str | Path | None = None,
    roi: tuple[int, int, int, int] | None = None,
    cancellation: RenderCancellation | None = None,
    on_step: Callable[[int, int, Any, RenderResult], bool] | None = None,
) -> SweepResult:
    """Render the scene once per ``value`` and collect metrics.

    Files are saved to ``output_dir`` with the naming pattern
    ``sweep_<param>_<value>.png`` if ``output_dir`` is provided.

    Parameters
    ----------
    on_step:
        Called as ``(index, total, value, render_result)`` after each
        successful render. Return ``False`` to stop early (also triggered
        when ``cancellation`` is set).
    """
    base_settings = settings or RenderSettings()
    if cancellation is not None:
        base_settings = RenderSettings(
            **{**base_settings.__dict__, "cancellation": cancellation}
        )
    renderer = Renderer(base_settings)
    value_list = list(values)
    result = SweepResult(parameter=parameter, values=value_list)

    out_path: Path | None = None
    if output_dir is not None:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

    total = len(value_list)
    try:
        for index, value in enumerate(value_list):
            if cancellation is not None and cancellation.is_requested():
                result.cancelled = True
                break
            modified = _set_dotted(scene, parameter, value)
            render: RenderResult = renderer.render(modified)
            result.renders.append(render)
            result.images.append(render.digital)
            result.metrics.append(compute_metrics(render.digital, roi=roi))
            if out_path is not None:
                safe = str(value).replace("/", "_").replace(" ", "_")
                save_image(
                    render.digital,
                    out_path / f"sweep_{parameter}_{safe}.png",
                )
            if on_step is not None and not on_step(index, total, value, render):
                result.cancelled = True
                break
    except RenderCancelled:
        result.cancelled = True

    return result
