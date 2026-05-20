"""High-level renderer that orchestrates Mitsuba and the sensor model.

The renderer is split into:

- ``Renderer.render(scene)`` -> a high-fidelity render using Mitsuba 3.
- ``Renderer.render_fallback(scene)`` -> a lightweight ray-marching preview
  used when Mitsuba is not installed, the GPU variant is unavailable, or the
  user requests a quick preview. The fallback is intentionally simple but
  preserves the same input/output contract so the GUI can use the same code
  paths.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..domain import Scene
from .cancellation import RenderCancellation, RenderCancelled
from .sensor_response import SensorResponseResult, apply_sensor_response
from .translator import build_mitsuba_dict

_log = logging.getLogger(__name__)


@dataclass
class RenderSettings:
    spp: int = 64
    max_depth: int = 6
    integrator: str = "path"
    variant: str = "scalar_rgb"
    radiance_scale: float = 1.0e3
    seed: int | None = None
    use_fallback: bool = False
    light_samples: int = 16
    """Number of point samples per area light in the fallback raycaster.
    Higher values give a smoother integration of the emitting surface, at the
    cost of render time. Point lights ignore this setting.
    """
    shadow_samples: int = 0
    """If > 0, cast shadow rays from each surface point to ``shadow_samples``
    light samples (subset of ``light_samples``). 0 disables shadowing for
    speed. Has no effect when Mitsuba is used.
    """
    depth_of_field: bool = False
    """If True, apply a depth-of-field blur in post based on per-pixel depth
    using the lens NA and magnification. Only affects the fallback path."""
    focus_z_world: float | None = None
    """Override in-focus distance in millimetres from the sensor plane.

    Historically this field represented a world-space Z plane; it is now
    interpreted as an axial focus depth (camera-forward distance) so it works
    for arbitrary camera orientation and both Mitsuba/fallback render paths.
    If ``None``, ``lens.working_distance_mm`` is used.
    """
    max_blur_px: int = 64
    """Maximum CoC in pixels considered when applying DoF blur."""
    preview_scale: float = 1.0
    """Render-resolution scale factor in ``(0, 1]``. Setting this below 1
    renders the fallback raycaster at a smaller resolution and upscales
    the radiance image to the sensor's native pixel count before sensor-
    response is applied. Used by the GUI to keep Preview/Live-preview
    fast even on multi-megapixel sensors. Mitsuba ignores this setting.
    """
    cancellation: RenderCancellation | None = None
    """When set, the renderer checks :meth:`RenderCancellation.is_requested`
    between coarse steps and raises :class:`RenderCancelled` if the user
    pressed Cancel in the GUI."""
    progress_callback: Callable[[int, int, str], None] | None = None
    """Optional ``(current, total, message)`` hook for progress UIs."""
    prefer_gpu_variant: bool = True
    """When choosing a Mitsuba variant, try CUDA before LLVM if available."""
    sensor_noise: bool = True
    """If False, skip shot/read/dark noise (deterministic DN for calibration)."""


@dataclass
class RenderResult:
    """Container for everything the renderer produces."""

    radiance: np.ndarray
    digital: np.ndarray
    electrons: np.ndarray
    saturated_mask: np.ndarray
    settings: RenderSettings
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def height(self) -> int:
        return self.digital.shape[0]

    @property
    def width(self) -> int:
        return self.digital.shape[1]


class Renderer:
    """Render an :class:`optsim.domain.Scene` to a digital image.

    Parameters mirror :class:`RenderSettings`; you can pass them directly or
    pass a pre-built settings object.
    """

    def __init__(
        self,
        settings: RenderSettings | None = None,
        **overrides: Any,
    ) -> None:
        if settings is None:
            settings = RenderSettings()
        if overrides:
            settings = RenderSettings(**{**settings.__dict__, **overrides})
        self.settings = settings

    def _report_progress(self, current: int, total: int, message: str) -> None:
        cb = self.settings.progress_callback
        if cb is not None:
            cb(current, total, message)

    def _check_cancelled(self) -> None:
        if self.settings.cancellation is not None:
            self.settings.cancellation.check()

    def render(self, scene: Scene) -> RenderResult:
        engine = "mitsuba"
        try:
            if self.settings.use_fallback:
                engine = "fallback"
                radiance = self._render_fallback(scene)
            else:
                try:
                    radiance, engine = self._render_mitsuba(scene)
                except ImportError as exc:
                    _log.warning(
                        "Mitsuba 3 is not installed; falling back to the "
                        "lightweight ray-caster. Install with "
                        "`pip install mitsuba`. (%s)",
                        exc,
                    )
                    engine = "fallback (mitsuba ImportError)"
                    radiance = self._render_fallback(scene, exc=exc)
                except RuntimeError as exc:
                    _log.warning(
                        "Mitsuba 3 render failed; falling back to the "
                        "lightweight ray-caster. Common cause: LLVM-C.dll "
                        "is missing. Install LLVM from "
                        "https://github.com/llvm/llvm-project/releases or "
                        "set DRJIT_LIBLLVM_PATH. (%s)",
                        exc,
                    )
                    engine = "fallback (mitsuba RuntimeError)"
                    radiance = self._render_fallback(scene, exc=exc)
        except RenderCancelled:
            raise

        response = apply_sensor_response(
            radiance,
            scene.camera.sensor,
            radiance_scale=scene.radiance_scale,
            seed=self.settings.seed,
            add_noise=self.settings.sensor_noise,
        )
        result = _wrap(radiance, response, self.settings)
        result.extras["engine"] = engine
        return result

    def _render_mitsuba(self, scene: Scene) -> tuple[np.ndarray, str]:
        mi = importlib.import_module("mitsuba")
        self._check_cancelled()
        # Variant names changed between Mitsuba versions. In 3.8 the LLVM
        # and CUDA variants are exposed with an `_ad_` infix (e.g.
        # `llvm_ad_rgb`). Try the requested variant first, then map
        # canonical short names onto whatever the install offers.
        available = set(mi.variants())
        candidates = self._candidate_mitsuba_variants(available)
        if not candidates:
            raise RuntimeError(f"No usable Mitsuba variant. Available: {sorted(available)}")

        failures: list[str] = []
        for chosen in candidates:
            self._report_progress(0, 4, f"Selecting Mitsuba variant... ({chosen})")
            self._check_cancelled()
            try:
                mi.set_variant(chosen)
                arr = self._render_mitsuba_with_variant(mi, scene)
                return arr, f"mitsuba ({chosen})"
            except RenderCancelled:
                raise
            except (ImportError, RuntimeError) as exc:
                failures.append(f"{chosen}: {exc}")
                _log.warning("Mitsuba variant '%s' failed. Trying next variant. (%s)", chosen, exc)
                continue
        detail = "; ".join(failures) if failures else "no details"
        raise RuntimeError(f"All Mitsuba variants failed. Tried: {candidates}. Errors: {detail}")

    def _candidate_mitsuba_variants(self, available: set[str]) -> list[str]:
        requested = self.settings.variant
        order = [requested]
        alias_map = {
            "llvm_rgb": "llvm_ad_rgb",
            "cuda_rgb": "cuda_ad_rgb",
            "llvm_spectral": "llvm_ad_spectral",
            "cuda_spectral": "cuda_ad_spectral",
        }
        if requested in alias_map:
            order.append(alias_map[requested])
        if self.settings.prefer_gpu_variant:
            order.extend(["cuda_ad_rgb", "cuda_rgb", "llvm_ad_rgb", "llvm_rgb"])
        else:
            order.extend(["llvm_ad_rgb", "llvm_rgb", "cuda_ad_rgb", "cuda_rgb"])
        order.extend(["scalar_rgb"])
        deduped: list[str] = []
        seen: set[str] = set()
        for v in order:
            if v in available and v not in seen:
                deduped.append(v)
                seen.add(v)
        return deduped

    def _render_mitsuba_with_variant(self, mi, scene: Scene) -> np.ndarray:
        self._report_progress(1, 4, "Building Mitsuba scene...")
        self._check_cancelled()
        scene_dict = build_mitsuba_dict(
            scene,
            spp=self.settings.spp,
            max_depth=self.settings.max_depth,
            integrator=self.settings.integrator,
        )
        scene_dict.pop("__background", None)
        mscene = mi.load_dict(scene_dict)

        self._report_progress(2, 4, f"Path tracing (spp={self.settings.spp})...")
        self._check_cancelled()
        image = mi.render(mscene, spp=self.settings.spp)
        self._report_progress(4, 4, "Mitsuba render complete")
        arr = np.array(image, copy=False, dtype=np.float32)
        if self.settings.depth_of_field and float(scene.lens.effective_na) > 0.0:
            try:
                depth = self._render_mitsuba_depth(mi, scene)
                hit_mask = np.isfinite(depth) & (depth > 0.0)
                arr = _apply_dof(
                    arr,
                    depth,
                    hit_mask,
                    scene.camera.sensor,
                    scene.lens,
                    focus_depth_mm=float(scene.lens.working_distance_mm),
                    max_blur_px=int(self.settings.max_blur_px),
                    pixel_scale=1.0,
                )
            except Exception as exc:
                _log.warning("Mitsuba DoF post-process skipped: %s", exc)
        return arr

    def _render_mitsuba_depth(self, mi, scene: Scene) -> np.ndarray:
        """Render a depth AOV map aligned with the beauty render."""
        self._check_cancelled()
        self._report_progress(2, 4, "Rendering depth AOV for DoF...")
        depth_dict = build_mitsuba_dict(
            scene,
            spp=1,
            max_depth=1,
            integrator="path",
        )
        depth_dict.pop("__background", None)
        depth_dict["integrator"] = {
            "type": "aov",
            "aovs": "dd.y:depth",
            "nested": {"type": "path", "max_depth": 1},
        }
        depth_scene = mi.load_dict(depth_dict)
        depth_img = mi.render(depth_scene, spp=1)
        depth_arr = np.array(depth_img, copy=False, dtype=np.float32)
        if depth_arr.ndim != 3 or depth_arr.shape[2] < 4:
            raise RuntimeError(
                f"Unexpected depth AOV shape: {depth_arr.shape}; expected (..., >=4)"
            )
        depth = depth_arr[..., -1]
        depth = np.nan_to_num(depth, nan=np.inf, posinf=np.inf, neginf=np.inf)
        return depth

    def _render_fallback(self, scene: Scene, *, exc: Exception | None = None) -> np.ndarray:
        """Lightweight orthographic raycaster used when Mitsuba is unavailable.

        It produces a Lambertian shaded depth-coded image good enough to wire
        up the GUI, validate the scene topology and exercise the analysis
        pipeline. Texture/reflectance is approximated by the material base
        color modulated by N.L. Multiple lights are accumulated.
        """
        import trimesh

        cam = scene.camera
        lens = scene.lens

        scale = float(self.settings.preview_scale or 1.0)
        scale = max(0.05, min(1.0, scale))
        native_w = cam.sensor.width_px
        native_h = cam.sensor.height_px
        w_px = max(8, int(round(native_w * scale)))
        h_px = max(8, int(round(native_h * scale)))
        w_mm = cam.sensor.width_mm / lens.magnification
        h_mm = cam.sensor.height_mm / lens.magnification

        cam_mat = cam.transform.to_matrix()
        cam_origin = cam_mat[:3, 3]
        cam_right = cam_mat[:3, 0]
        cam_up = cam_mat[:3, 1]
        cam_fwd = -cam_mat[:3, 2]

        ys = (np.linspace(0.5, h_px - 0.5, h_px) / h_px - 0.5) * h_mm
        xs = (np.linspace(0.5, w_px - 0.5, w_px) / w_px - 0.5) * w_mm
        gx, gy = np.meshgrid(xs, ys)
        origins = (
            cam_origin[None, None, :]
            + gx[..., None] * cam_right[None, None, :]
            + gy[..., None] * cam_up[None, None, :]
        )
        directions = np.broadcast_to(cam_fwd[None, None, :], origins.shape).copy()

        flat_origins = origins.reshape(-1, 3)
        flat_dirs = directions.reshape(-1, 3)

        accum_color = np.zeros((flat_origins.shape[0], 3), dtype=np.float64)
        hit_mask = np.zeros(flat_origins.shape[0], dtype=bool)
        hit_depth = np.full(flat_origins.shape[0], np.inf)
        hit_normal = np.zeros_like(flat_origins)
        hit_color = np.zeros_like(flat_origins)
        # Per-pixel material parameter vector:
        # [metallic, roughness, F0_dielectric, diffuse_weight, transmission]
        hit_material = np.zeros((flat_origins.shape[0], 5), dtype=np.float64)

        visible_targets = [t for t in scene.targets if t.visible]
        from .mesh_assembly import MergedMeshTarget, coalesce_mesh_targets_for_render

        render_targets = coalesce_mesh_targets_for_render(visible_targets)
        n_targets = max(len(render_targets), 1)
        for ti, target in enumerate(render_targets):
            self._check_cancelled()
            self._report_progress(
                ti, n_targets * 2,
                f"Ray cast: {target.name} ({ti + 1}/{len(render_targets)})",
            )
            try:
                t_target, normals, valid = _intersect_target(
                    target, flat_origins, flat_dirs
                )
            except ModuleNotFoundError as exc:
                _log.error(
                    "Ray intersection for mesh targets requires the 'rtree' "
                    "or 'pyembree' module. Install one with `pip install "
                    "rtree`. (%s)",
                    exc,
                )
                raise
            except Exception as exc:
                _log.warning("Ray cast against target %s failed: %s", target.name, exc)
                continue
            if valid is None or not valid.any():
                continue
            closer = valid & (t_target < hit_depth)
            if not closer.any():
                continue
            sel = np.where(closer)[0]
            hit_depth[sel] = t_target[sel]
            hit_mask[sel] = True
            hit_normal[sel] = normals[sel]
            base = np.array(target.material.base_color, dtype=np.float64)
            hit_color[sel] = base
            hit_material[sel] = _material_vector(target.material)

        if hit_mask.any():
            p_hit = flat_origins[hit_mask] + flat_dirs[hit_mask] * hit_depth[hit_mask, None]
            n_hit = hit_normal[hit_mask]
            base_hit = hit_color[hit_mask]
            material_props = hit_material[hit_mask]
            transmission = material_props[:, 4:5]
            view_dir_world = -cam_fwd  # orthographic: same v for all pixels
            ref_dist2 = 50.0 ** 2

            # Hoist all material-/view-dependent BRDF constants out of the
            # inner light-sample loop: they don't change with l.
            brdf_ctx = _build_brdf_context(
                n_hit, view_dir_world, base_hit, material_props
            )

            enabled_lights = [l for l in scene.lights if l.enabled]
            n_lights = max(len(enabled_lights), 1)
            from ..domain.light import Backlight
            for li, light in enumerate(enabled_lights):
                self._check_cancelled()
                self._report_progress(
                    n_targets + li,
                    n_targets + n_lights,
                    f"Shading: {light.name} ({li + 1}/{len(enabled_lights)})",
                )
                l_color = (
                    np.asarray(light.color, dtype=np.float64)
                    * float(light.intensity)
                )
                samples = _light_samples(light, self.settings.light_samples)
                exp_n = float(getattr(light, "directional_exponent", 0.0) or 0.0)
                accum_light = np.zeros_like(p_hit)
                for p_light, emit_dir, weight in samples:
                    to_light = p_light[None, :] - p_hit
                    dist2 = np.sum(to_light * to_light, axis=1) + 1e-6
                    inv_d = 1.0 / np.sqrt(dist2)
                    to_light_n = to_light * inv_d[:, None]
                    dot_nl = np.sum(n_hit * to_light_n, axis=1)
                    ndotl = np.clip(dot_nl, 0.0, 1.0)
                    falloff = ref_dist2 / dist2
                    if emit_dir is not None:
                        cos_emit = np.clip(
                            -np.sum(emit_dir[None, :] * to_light_n, axis=1),
                            0.0,
                            1.0,
                        )
                        if exp_n > 0.0:
                            cos_emit = cos_emit ** exp_n
                    else:
                        cos_emit = np.ones_like(ndotl)

                    brdf_rgb = _evaluate_brdf_cached(brdf_ctx, to_light_n)
                    geo = (ndotl * falloff * cos_emit * weight)[:, None]
                    accum_light += brdf_rgb * l_color[None, :] * geo

                    # Fast transmissive approximation for fallback:
                    # a backlight shining through dielectric targets contributes
                    # even when the front-face N.L is negative.
                    if isinstance(light, Backlight):
                        back_dot = np.clip(-dot_nl, 0.0, 1.0)[:, None]
                        trans_geo = transmission * back_dot * falloff[:, None] * (
                            cos_emit[:, None] * weight
                        )
                        accum_light += base_hit * l_color[None, :] * trans_geo

                accum_color[hit_mask] += accum_light

            self._report_progress(n_targets + n_lights, n_targets + n_lights, "Compositing...")

            # Simple environment ambient. For metals this acts as a base
            # reflectance (Fresnel * white env); for dielectrics it is the
            # diffuse environment term. Both reduce to base_color * env.
            ambient = 0.08
            accum_color[hit_mask] += base_hit * ambient

        bg = np.asarray(scene.background_color, dtype=np.float64)
        accum_color[~hit_mask] = bg

        radiance = accum_color.reshape(h_px, w_px, 3).astype(np.float32)
        radiance = np.flipud(radiance)

        if self.settings.depth_of_field:
            hit_depth_2d = hit_depth.reshape(h_px, w_px)
            hit_depth_2d = np.flipud(hit_depth_2d)
            hit_mask_2d = np.flipud(hit_mask.reshape(h_px, w_px))
            focus_depth = (
                float(self.settings.focus_z_world)
                if self.settings.focus_z_world is not None
                else float(lens.working_distance_mm)
            )
            # Scale the per-pixel CoC by ``scale`` so the blur radius
            # measured in pixels of the downscaled render matches the
            # full-resolution CoC after upscaling.
            radiance = _apply_dof(
                radiance,
                hit_depth_2d,
                hit_mask_2d,
                cam.sensor,
                lens,
                focus_depth_mm=focus_depth,
                max_blur_px=int(self.settings.max_blur_px),
                pixel_scale=scale,
            )

        if (w_px, h_px) != (native_w, native_h):
            try:
                import cv2

                radiance = cv2.resize(
                    radiance,
                    (native_w, native_h),
                    interpolation=cv2.INTER_LINEAR,
                ).astype(np.float32)
            except ImportError:
                # Fall back to a numpy nearest-neighbour upscale.
                ys = (np.arange(native_h) * h_px / native_h).astype(np.int64)
                xs = (np.arange(native_w) * w_px / native_w).astype(np.int64)
                radiance = radiance[ys[:, None], xs[None, :]].astype(np.float32)

        return radiance


def _apply_dof(
    radiance: np.ndarray,
    hit_depth_mm: np.ndarray,
    hit_mask: np.ndarray,
    sensor,
    lens,
    *,
    focus_depth_mm: float,
    max_blur_px: int = 64,
    pixel_scale: float = 1.0,
) -> np.ndarray:
    """Apply spatially-variant depth-of-field blur via a Gaussian pyramid.

    For a telecentric lens the (image-side) circle of confusion is
    ``CoC = 2 * |Δz| * NA * magnification`` where ``Δz`` is the object-space
    distance from the focus plane.

    The implementation generates a small Gaussian pyramid at fixed sigma
    levels and linearly interpolates between adjacent levels per pixel based
    on the desired blur radius. This is cheap (a handful of full-image
    Gaussian blurs) but smooth.
    """
    try:
        import cv2
    except ImportError:
        _log.warning("OpenCV not available; skipping DoF blur.")
        return radiance

    pixel_size_mm = float(sensor.pixel_pitch_um) * 1e-3
    coc_mm = (
        2.0
        * np.abs(hit_depth_mm - focus_depth_mm)
        * float(lens.effective_na)
        * float(lens.magnification)
    )
    # The CoC measured in the *rendered* image plane shrinks by the
    # downscale ratio (a 4 px CoC at native res becomes 1 px at scale=0.25).
    coc_px = (coc_mm / max(pixel_size_mm, 1e-6)) * float(pixel_scale)
    coc_px = np.where(hit_mask, coc_px, 0.0)
    coc_px = np.clip(coc_px, 0.0, float(max_blur_px))

    sigmas = [0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
    sigmas = [s for s in sigmas if s <= max_blur_px * 1.5]
    if sigmas[-1] < max_blur_px:
        sigmas.append(float(max_blur_px))

    pyramid = [radiance.astype(np.float32)]
    for s in sigmas[1:]:
        ksize = max(3, int(s * 6) | 1)  # odd kernel >= 3
        pyramid.append(cv2.GaussianBlur(radiance.astype(np.float32), (ksize, ksize), s))

    output = np.zeros_like(radiance, dtype=np.float32)
    sig_arr = np.array(sigmas, dtype=np.float32)
    for i in range(len(sig_arr) - 1):
        lo, hi = sig_arr[i], sig_arr[i + 1]
        denom = max(hi - lo, 1e-6)
        t = np.clip((coc_px - lo) / denom, 0.0, 1.0)
        in_range = (coc_px >= lo) & (coc_px <= hi)
        blend = (1.0 - t)[..., None] * pyramid[i] + t[..., None] * pyramid[i + 1]
        output = np.where(in_range[..., None], blend, output)
    # Pixels exceeding the last sigma fall back to the max blur level.
    over = coc_px > sig_arr[-1]
    output = np.where(over[..., None], pyramid[-1], output)
    return output


def _material_vector(material) -> np.ndarray:
    """Pack BRDF parameters into a (4,) float vector used by the fallback.

    Layout: ``[metallic, roughness, F0_dielectric, diffuse_weight, transmission]``.

    - ``metallic``: 0 = dielectric/diffuse, 1 = pure metal.
    - ``roughness``: clamped to [0.02, 1.0] to keep the Blinn-Phong shininess
      bounded.
    - ``F0_dielectric``: Schlick base reflectance for non-metals derived
      from the IOR (~0.04 for glass, ~0.05 for plastic).
    - ``diffuse_weight``: 0..1 mixing factor between diffuse and specular
      lobes for non-metallic materials.
    - ``transmission``: 0..1 heuristic pass-through amount used by fallback
      for backlight-through-dielectric approximation.
    """
    from ..domain.material import MaterialKind

    metallic = float(material.metallic)
    # Coerce category to numeric metallic for pure metal/diffuse if user
    # only set `kind` and not `metallic`.
    if material.kind is MaterialKind.metal or material.kind is MaterialKind.anisotropic:
        metallic = max(metallic, 1.0)
    elif material.kind is MaterialKind.diffuse:
        metallic = 0.0

    roughness = float(np.clip(material.roughness, 0.02, 1.0))

    ior = float(material.ior)
    f0_d = ((ior - 1.0) / (ior + 1.0)) ** 2

    diffuse_weight = float(material.diffuse_weight)
    transmission = 0.0
    if material.kind is MaterialKind.diffuse:
        diffuse_weight = 1.0
    elif material.kind is MaterialKind.metal or material.kind is MaterialKind.anisotropic:
        diffuse_weight = 0.0
    elif material.kind is MaterialKind.dielectric:
        # Transparent materials should not be treated as diffuse in fallback.
        diffuse_weight = 0.0
        transmission = float(np.clip(np.mean(material.base_color), 0.0, 1.0))

    return np.array(
        [metallic, roughness, f0_d, diffuse_weight, transmission],
        dtype=np.float64,
    )


def _build_brdf_context(
    n: np.ndarray,
    v_world: np.ndarray,
    base_color: np.ndarray,
    material_props: np.ndarray,
) -> dict[str, np.ndarray]:
    """Precompute BRDF terms that don't depend on the light direction.

    Hoisting these out of the per-sample loop avoids redoing the same
    ~M-pixel array math 16-32 times per render.
    """
    v = np.broadcast_to(v_world[None, :].astype(np.float64), n.shape)
    metallic = material_props[:, 0:1]
    roughness = material_props[:, 1:2]
    f0_d = material_props[:, 2:3]
    diffuse_weight = material_props[:, 3:4]

    one_minus_metallic = 1.0 - metallic
    alpha = roughness * roughness
    shininess = np.maximum(2.0 / np.maximum(alpha, 1e-4) - 2.0, 1.0)
    spec_norm = (shininess + 2.0) / (2.0 * np.pi)

    f0 = metallic * base_color + one_minus_metallic * f0_d
    one_minus_f0 = 1.0 - f0
    diffuse_base = one_minus_metallic * diffuse_weight * base_color / np.pi

    n_dot_v = np.clip(np.sum(n * v, axis=1, keepdims=True), 0.0, 1.0)
    inv_g_atten = 1.0 / np.clip(n_dot_v + 0.1, 0.1, 1.0)
    return {
        "n": n,
        "v": v,
        "f0": f0,
        "one_minus_f0": one_minus_f0,
        "diffuse_base": diffuse_base,
        "shininess": shininess,
        "spec_norm": spec_norm,
        "inv_g_atten": inv_g_atten,
    }


def _evaluate_brdf_cached(ctx: dict[str, np.ndarray], l: np.ndarray) -> np.ndarray:
    """Per-light-sample BRDF using values pre-computed in ``ctx``."""
    n = ctx["n"]
    v = ctx["v"]
    h = l + v
    # ``np.linalg.norm`` is much slower than an explicit sqrt(sum) for
    # this small-axis case (axis=1 of an (M, 3) array).
    h_norm = np.sqrt(np.sum(h * h, axis=1, keepdims=True)) + 1e-8
    h = h * (1.0 / h_norm)

    n_dot_h = np.clip(np.sum(n * h, axis=1, keepdims=True), 0.0, 1.0)
    v_dot_h = np.clip(np.sum(v * h, axis=1, keepdims=True), 0.0, 1.0)

    one_minus = 1.0 - v_dot_h
    one_minus2 = one_minus * one_minus
    one_minus5 = one_minus2 * one_minus2 * one_minus
    fresnel = ctx["f0"] + ctx["one_minus_f0"] * one_minus5

    spec_lobe = ctx["spec_norm"] * (n_dot_h ** ctx["shininess"])
    specular = fresnel * spec_lobe
    diffuse = (1.0 - fresnel) * ctx["diffuse_base"]
    return diffuse + specular * ctx["inv_g_atten"]


def _evaluate_brdf(
    n: np.ndarray,
    l: np.ndarray,
    v_world: np.ndarray,
    base_color: np.ndarray,
    material_props: np.ndarray,
) -> np.ndarray:
    """Standalone BRDF evaluator kept for tests / external callers.

    The hot path uses :func:`_build_brdf_context` + :func:`_evaluate_brdf_cached`
    to hoist material-only terms outside the light-sample loop.
    """
    ctx = _build_brdf_context(n, v_world, base_color, material_props)
    return _evaluate_brdf_cached(ctx, l)


def _light_samples(light, n_hint: int) -> list[tuple[np.ndarray, np.ndarray | None, float]]:
    """Generate point samples on (or representing) a light source.

    Returns a list of ``(world_position, emission_direction_world, weight)``
    tuples. ``weight`` sums to ~1 across the samples so the total light power
    matches ``light.intensity`` regardless of the sampling density.
    ``emission_direction_world`` is ``None`` for isotropic (point) emitters.

    The local light frame uses ``-Z`` as the canonical emission direction
    for ring / rect / bar / coaxial / dome lights (i.e. with the light at
    its default rotation (0, 0, 0), it emits "downward" toward the work
    plane). :class:`Backlight` is the exception: it emits along ``+Z`` so
    that a backlight placed below the work shines upward without requiring
    the user to flip its rotation.
    """
    from ..domain.light import (
        Backlight,
        BarLight,
        CoaxialLight,
        DomeLight,
        PointLight,
        RectAreaLight,
        RingLight,
    )

    mat = light.transform.to_matrix()
    R = mat[:3, :3]
    t = mat[:3, 3]
    minus_z_world = -R[:, 2]
    plus_z_world = R[:, 2]

    samples: list[tuple[np.ndarray, np.ndarray | None, float]] = []

    if isinstance(light, PointLight):
        samples.append((t.astype(np.float64), None, 1.0))
        return samples

    if isinstance(light, RectAreaLight):
        n_side = max(2, int(round(np.sqrt(max(n_hint, 4)))))
        w = 1.0 / (n_side * n_side)
        for i in range(n_side):
            for j in range(n_side):
                u = (i + 0.5) / n_side - 0.5
                v = (j + 0.5) / n_side - 0.5
                p_local = np.array(
                    [u * light.width_mm, v * light.height_mm, 0.0]
                )
                p_world = R @ p_local + t
                samples.append((p_world, minus_z_world, w))
        return samples

    if isinstance(light, RingLight):
        n_seg = max(8, int(light.segments))
        r = 0.5 * (light.inner_radius_mm + light.outer_radius_mm)
        tilt = np.deg2rad(light.tilt_deg)
        sin_t = np.sin(tilt)
        cos_t = np.cos(tilt)
        w = 1.0 / n_seg
        for i in range(n_seg):
            theta = 2.0 * np.pi * (i + 0.5) / n_seg
            ct, st = np.cos(theta), np.sin(theta)
            p_local = np.array([r * ct, r * st, 0.0])
            emit_local = np.array(
                [-sin_t * ct, -sin_t * st, -cos_t]
            )
            samples.append((R @ p_local + t, R @ emit_local, w))
        return samples

    if isinstance(light, BarLight):
        # Sample more densely along the long axis.
        n_long = max(4, int(round(n_hint ** 0.7)))
        n_short = max(2, int(round(n_hint / max(n_long, 1))))
        w = 1.0 / (n_long * n_short)
        for i in range(n_long):
            for j in range(n_short):
                u = (i + 0.5) / n_long - 0.5
                v = (j + 0.5) / n_short - 0.5
                p_local = np.array(
                    [u * light.length_mm, v * light.width_mm, 0.0]
                )
                samples.append((R @ p_local + t, minus_z_world, w))
        return samples

    if isinstance(light, CoaxialLight):
        # The 50/50 beam splitter halves the effective intensity.
        n_side = max(2, int(round(np.sqrt(max(n_hint, 4)))))
        w = 0.5 / (n_side * n_side)
        for i in range(n_side):
            for j in range(n_side):
                u = (i + 0.5) / n_side - 0.5
                v = (j + 0.5) / n_side - 0.5
                p_local = np.array(
                    [u * light.size_mm, v * light.size_mm, 0.0]
                )
                samples.append((R @ p_local + t, minus_z_world, w))
        return samples

    if isinstance(light, DomeLight):
        # Fibonacci hemisphere over the (local) +Z hemisphere; each facet
        # emits inward toward the dome centre.
        n_dome = max(16, int(n_hint * 2))
        w = 1.0 / n_dome
        golden = np.pi * (3.0 - np.sqrt(5.0))
        for i in range(n_dome):
            # z spans (0, 1] -> facets on the upper hemisphere.
            z = (i + 0.5) / n_dome
            phi = golden * i
            r = np.sqrt(max(0.0, 1.0 - z * z))
            x = r * np.cos(phi)
            y = r * np.sin(phi)
            local_dir = np.array([x, y, z])
            p_local = light.radius_mm * local_dir
            emit_local = -local_dir
            samples.append((R @ p_local + t, R @ emit_local, w))
        return samples

    if isinstance(light, Backlight):
        n_side = max(2, int(round(np.sqrt(max(n_hint, 4)))))
        w = 1.0 / (n_side * n_side)
        for i in range(n_side):
            for j in range(n_side):
                u = (i + 0.5) / n_side - 0.5
                v = (j + 0.5) / n_side - 0.5
                p_local = np.array(
                    [u * light.width_mm, v * light.height_mm, 0.0]
                )
                samples.append((R @ p_local + t, plus_z_world, w))
        return samples

    # Unknown light kind: treat as point at its transform.
    samples.append((t.astype(np.float64), None, 1.0))
    return samples


def _intersect_target(
    target,
    flat_origins: np.ndarray,
    flat_dirs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Dispatch ray-target intersection.

    Primitives use closed-form analytic intersection (vectorised, ~100x
    faster than the trimesh + rtree path for full-sensor ray casts).
    External meshes fall back to :func:`trimesh.ray.intersects_location`.

    Returns
    -------
    t : (N,) float ndarray
        Ray parameter along the unit direction where the ray hits the
        target. ``+inf`` for misses.
    normal_world : (N, 3) float ndarray
        Surface normal in world coordinates at the hit point. Undefined
        for missed rays.
    valid : (N,) bool ndarray
        True where the ray hit the target with positive ``t``.
    """
    from ..domain.target import PrimitiveKind, TargetMesh, TargetPrimitive

    if isinstance(target.geometry, TargetPrimitive):
        prim = target.geometry.primitive
        T = target.transform.to_matrix()
        R = T[:3, :3]
        t_vec = T[:3, 3]
        if prim.kind is PrimitiveKind.cube:
            half = 0.5 * np.asarray(prim.size_mm, dtype=np.float64)
            return _intersect_box(half, R, t_vec, flat_origins, flat_dirs)
        if prim.kind is PrimitiveKind.plane:
            sx, sy, sz = prim.size_mm
            half = np.array(
                [0.5 * sx, 0.5 * sy, max(0.5 * float(sz), 0.025)],
                dtype=np.float64,
            )
            return _intersect_box(half, R, t_vec, flat_origins, flat_dirs)
        if prim.kind is PrimitiveKind.sphere:
            return _intersect_sphere(
                float(prim.radius_mm), t_vec, flat_origins, flat_dirs
            )
        if prim.kind is PrimitiveKind.cylinder:
            return _intersect_cylinder(
                float(prim.radius_mm),
                float(prim.size_mm[2]),
                R,
                t_vec,
                flat_origins,
                flat_dirs,
            )

    from .mesh_assembly import MergedMeshTarget

    if isinstance(target, MergedMeshTarget) or isinstance(
        target.geometry, TargetMesh
    ):
        return _intersect_mesh(target, flat_origins, flat_dirs)

    n = flat_origins.shape[0]
    return (
        np.full(n, np.inf),
        np.zeros_like(flat_origins),
        np.zeros(n, dtype=bool),
    )


def _intersect_box(
    half: np.ndarray,
    R: np.ndarray,
    t_vec: np.ndarray,
    flat_origins: np.ndarray,
    flat_dirs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Slab-method box intersection in the box-local frame.

    ``R`` is the local-to-world rotation (rigid) and ``t_vec`` the
    world-space centre. The box extends from ``-half`` to ``+half`` in
    its local frame.
    """
    o_local = (flat_origins - t_vec[None, :]) @ R
    d_local = flat_dirs @ R

    eps = 1e-12
    d_safe = np.where(np.abs(d_local) > eps, d_local, eps)
    t1 = (-half[None, :] - o_local) / d_safe
    t2 = (+half[None, :] - o_local) / d_safe
    t_near_ax = np.minimum(t1, t2)
    t_far_ax = np.maximum(t1, t2)
    t_entry = np.max(t_near_ax, axis=1)
    t_exit = np.min(t_far_ax, axis=1)

    valid = (t_entry < t_exit) & (t_exit > 0)
    t = np.where(t_entry > 0, t_entry, t_exit)
    t = np.where(valid, t, np.inf)

    # Entry face = axis where t_near_ax was maximum.
    axis = np.argmax(t_near_ax, axis=1)
    rows = np.arange(d_local.shape[0])
    d_entry = d_local[rows, axis]
    sign = -np.sign(d_entry)
    sign = np.where(sign == 0, 1.0, sign)
    # Inside the box ``t_entry`` is negative; flip normal to point inward
    # so the shading still uses the closest face.
    inside = (t_entry <= 0) & (t_exit > 0)
    sign = np.where(inside, -sign, sign)
    normal_local = np.zeros_like(d_local)
    normal_local[rows, axis] = sign
    normal_world = normal_local @ R.T
    return t, normal_world, valid


def _intersect_sphere(
    radius: float,
    t_vec: np.ndarray,
    flat_origins: np.ndarray,
    flat_dirs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Closed-form ray-sphere intersection.

    Assumes unit-length ray directions.
    """
    oc = flat_origins - t_vec[None, :]
    b = 2.0 * np.sum(oc * flat_dirs, axis=1)
    c_val = np.sum(oc * oc, axis=1) - radius * radius
    disc = b * b - 4.0 * c_val
    has_root = disc >= 0
    sqrt_disc = np.sqrt(np.maximum(disc, 0.0))
    t_near = 0.5 * (-b - sqrt_disc)
    t_far = 0.5 * (-b + sqrt_disc)
    t = np.where(t_near > 0, t_near, t_far)
    valid = has_root & (t > 0)
    t = np.where(valid, t, np.inf)

    p_hit = flat_origins + np.where(valid, t, 0.0)[:, None] * flat_dirs
    n = p_hit - t_vec[None, :]
    n_len = np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    normal_world = n / n_len
    return t, normal_world, valid


def _intersect_cylinder(
    radius: float,
    height: float,
    R: np.ndarray,
    t_vec: np.ndarray,
    flat_origins: np.ndarray,
    flat_dirs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Closed cylinder (with caps) aligned with the local Z-axis.

    ``height`` is the full extent along Z; the cylinder spans ``z ∈
    [-height/2, +height/2]``.
    """
    o_local = (flat_origins - t_vec[None, :]) @ R
    d_local = flat_dirs @ R
    half_h = 0.5 * height
    ox, oy, oz = o_local[:, 0], o_local[:, 1], o_local[:, 2]
    dx, dy, dz = d_local[:, 0], d_local[:, 1], d_local[:, 2]

    a = dx * dx + dy * dy
    b = 2.0 * (ox * dx + oy * dy)
    c_val = ox * ox + oy * oy - radius * radius
    disc = b * b - 4.0 * a * c_val
    a_safe = np.where(np.abs(a) > 1e-12, a, 1e-12)
    sqrt_disc = np.sqrt(np.maximum(disc, 0.0))
    t_side_near = (-b - sqrt_disc) / (2.0 * a_safe)
    t_side_far = (-b + sqrt_disc) / (2.0 * a_safe)
    z_near = oz + t_side_near * dz
    z_far = oz + t_side_far * dz
    has_side_root = (disc >= 0) & (np.abs(a) > 1e-12)
    side_near_ok = has_side_root & (np.abs(z_near) <= half_h) & (t_side_near > 0)
    side_far_ok = has_side_root & (np.abs(z_far) <= half_h) & (t_side_far > 0)

    dz_safe = np.where(np.abs(dz) > 1e-12, dz, 1e-12)
    t_cap_top = (half_h - oz) / dz_safe
    t_cap_bot = (-half_h - oz) / dz_safe
    x_top = ox + t_cap_top * dx
    y_top = oy + t_cap_top * dy
    x_bot = ox + t_cap_bot * dx
    y_bot = oy + t_cap_bot * dy
    cap_top_ok = (
        (np.abs(dz) > 1e-12)
        & (x_top * x_top + y_top * y_top <= radius * radius)
        & (t_cap_top > 0)
    )
    cap_bot_ok = (
        (np.abs(dz) > 1e-12)
        & (x_bot * x_bot + y_bot * y_bot <= radius * radius)
        & (t_cap_bot > 0)
    )

    inf = np.inf
    cand = np.stack(
        [
            np.where(side_near_ok, t_side_near, inf),
            np.where(side_far_ok, t_side_far, inf),
            np.where(cap_top_ok, t_cap_top, inf),
            np.where(cap_bot_ok, t_cap_bot, inf),
        ],
        axis=1,
    )
    best = np.argmin(cand, axis=1)
    rows = np.arange(cand.shape[0])
    t = cand[rows, best]
    valid = np.isfinite(t)

    p_local = o_local + np.where(valid, t, 0.0)[:, None] * d_local
    normal_local = np.zeros_like(p_local)
    side_hit = (best == 0) | (best == 1)
    radial_len = np.sqrt(p_local[:, 0] ** 2 + p_local[:, 1] ** 2) + 1e-12
    nx = p_local[:, 0] / radial_len
    ny = p_local[:, 1] / radial_len
    normal_local[side_hit, 0] = nx[side_hit]
    normal_local[side_hit, 1] = ny[side_hit]
    normal_local[best == 2, 2] = 1.0
    normal_local[best == 3, 2] = -1.0
    # Flip if the ray hit the far surface from the inside.
    inside_far = best == 1
    normal_local[inside_far] = -normal_local[inside_far]
    normal_world = normal_local @ R.T
    return t, normal_world, valid


def _intersect_mesh(
    target,
    flat_origins: np.ndarray,
    flat_dirs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Trimesh-backed intersection for arbitrary triangle meshes."""
    from .mesh_assembly import MergedMeshTarget, world_mesh_for_target

    try:
        mesh = (
            target.world_mesh()
            if isinstance(target, MergedMeshTarget)
            else world_mesh_for_target(target)
        )
    except Exception:  # pragma: no cover - depends on user assets
        n = flat_origins.shape[0]
        return (
            np.full(n, np.inf),
            np.zeros_like(flat_origins),
            np.zeros(n, dtype=bool),
        )

    locations, ray_idx, tri_idx = mesh.ray.intersects_location(
        ray_origins=flat_origins,
        ray_directions=flat_dirs,
        multiple_hits=False,
    )
    n = flat_origins.shape[0]
    t = np.full(n, np.inf)
    normals = np.zeros_like(flat_origins)
    valid = np.zeros(n, dtype=bool)
    if len(ray_idx) == 0:
        return t, normals, valid
    distances = np.linalg.norm(locations - flat_origins[ray_idx], axis=1)
    order = np.argsort(distances)
    ray_idx_sorted = ray_idx[order]
    dist_sorted = distances[order]
    tri_sorted = tri_idx[order]
    seen = np.zeros(n, dtype=bool)
    for i in range(len(ray_idx_sorted)):
        r = int(ray_idx_sorted[i])
        if not seen[r]:
            seen[r] = True
            t[r] = dist_sorted[i]
            normals[r] = mesh.face_normals[int(tri_sorted[i])]
    valid = seen
    return t, normals, valid


def _wrap(radiance: np.ndarray, response: SensorResponseResult, settings: RenderSettings) -> RenderResult:
    return RenderResult(
        radiance=radiance,
        digital=response.digital,
        electrons=response.electrons,
        saturated_mask=response.saturated_mask,
        settings=settings,
    )
