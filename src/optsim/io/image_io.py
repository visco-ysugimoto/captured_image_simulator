"""Image read/write helpers that handle both 8/16-bit and HDR formats."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def save_image(
    image: np.ndarray,
    path: str | Path,
    *,
    stretch: bool | None = None,
    source_bit_depth: int | None = None,
) -> None:
    """Save an image, with smart bit-depth handling.

    Parameters
    ----------
    image:
        Either an integer image (DN values from the sensor model) or a float
        HDR image (radiance).
    path:
        Destination file. Extension chooses the format:

        - ``.png``                  : 8 or 16 bit PNG, visually stretched.
        - ``.tiff`` / ``.tif``      : raw DN values preserved (uint16).
        - ``.exr``                  : float32 HDR.
    stretch:
        If ``None`` (default), PNG output is stretched to fill the bit-depth
        of the file (so 12-bit DN values look normal in any image viewer),
        TIFF preserves the raw DN values. Pass ``True`` / ``False`` to force.
    source_bit_depth:
        Bit depth of the source data (e.g. ``12`` for a 12-bit sensor). Used
        when ``stretch=True`` so the linear mapping is exact rather than
        based on the observed maximum.
    """
    import imageio.v3 as iio

    path = Path(path)
    suffix = path.suffix.lower()
    arr = image

    if suffix == ".exr":
        iio.imwrite(str(path), arr.astype(np.float32, copy=False))
        return

    do_stretch = stretch if stretch is not None else suffix == ".png"

    if arr.dtype.kind == "f":
        max_val = max(1e-6, float(arr.max()))
        scaled = np.clip(arr / max_val * 65535.0, 0, 65535).astype(np.uint16)
        iio.imwrite(str(path), scaled)
        return

    if do_stretch and arr.dtype.kind in "iu":
        if source_bit_depth is not None:
            full_scale = (1 << source_bit_depth) - 1
        else:
            measured_max = int(arr.max()) if arr.size else 1
            full_scale = _detect_full_scale(measured_max)
        scaled = np.clip(arr.astype(np.float64) / max(full_scale, 1) * 65535.0,
                         0, 65535).astype(np.uint16)
        iio.imwrite(str(path), scaled)
        return

    iio.imwrite(str(path), arr)


def _detect_full_scale(measured_max: int) -> int:
    """Guess the original full-scale value from an observed maximum DN.

    Picks the smallest of 255, 1023, 4095, 16383, 65535 that is >= the
    observed maximum. This makes the auto-stretch work for 8/10/12/14/16 bit
    sensors without configuration.
    """
    for full in (255, 1023, 4095, 16383, 65535):
        if measured_max <= full:
            return full
    return 65535


def load_image(path: str | Path) -> np.ndarray:
    import imageio.v3 as iio

    return iio.imread(str(path))
