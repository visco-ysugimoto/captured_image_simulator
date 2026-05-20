"""Mesh loading helpers.

For inspection-grade simulation, STL/OBJ/PLY are the most common inputs.
STEP files are converted to triangle meshes via **cascadio** (recommended on
Windows: ``pip install cascadio``) or optionally **cadquery**.

Multi-part files (OBJ groups, GLTF, STEP with ``merge_primitives=False``)
expose named parts via :func:`list_mesh_parts`. Each part can become its own
:class:`~optsim.domain.Target` with an independent material.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from ..domain.target import TargetMesh

STEP_EXTENSIONS = {".step", ".stp"}

STEP_INSTALL_HINT = (
    "STEP の読み込みには追加パッケージが必要です。\n\n"
    "  推奨 (Windows / pip):\n"
    "    pip install cascadio\n\n"
    "  または:\n"
    "    pip install cadquery\n\n"
    "  インストール後、GUI を再起動してください。\n"
    "  代替: CAD から STL/OBJ にエクスポートして読み込む。"
)


def supported_mesh_extensions() -> set[str]:
    return {".stl", ".obj", ".ply", ".glb", ".gltf", ".step", ".stp"}


def step_backend_available() -> str | None:
    """Return the name of an available STEP backend, or ``None``."""
    if _has_cascadio():
        return "cascadio"
    try:
        import cadquery  # noqa: F401

        return "cadquery"
    except ImportError:
        return None


def _has_cascadio() -> bool:
    try:
        import cascadio  # noqa: F401

        return True
    except ImportError:
        return False


def _is_step(path: Path) -> bool:
    return path.suffix.lower() in STEP_EXTENSIONS


# (resolved path, merge_primitives) -> (mtime, loaded scene/mesh)
_RAW_FILE_CACHE: dict[tuple[str, bool], tuple[float, trimesh.Trimesh | trimesh.Scene]] = {}


def clear_mesh_cache() -> None:
    """Clear the in-memory mesh file cache (mainly for tests)."""
    _RAW_FILE_CACHE.clear()


def _load_file_raw(
    path: Path,
    *,
    merge_primitives: bool | None = None,
) -> trimesh.Trimesh | trimesh.Scene:
    suffix = path.suffix.lower()
    if suffix in STEP_EXTENSIONS:
        if merge_primitives is None:
            merge_primitives = True
        merge_key = bool(merge_primitives)
    else:
        merge_key = True

    resolved = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0

    cache_key = (resolved, merge_key)
    cached = _RAW_FILE_CACHE.get(cache_key)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    if suffix in {".stl", ".obj", ".ply", ".glb", ".gltf"}:
        raw = trimesh.load(path)
    elif suffix in STEP_EXTENSIONS:
        raw = _load_step(path, merge_primitives=merge_key)
    else:
        raise ValueError(f"Unsupported mesh extension: {suffix}")

    _RAW_FILE_CACHE[cache_key] = (mtime, raw)
    return raw


def list_mesh_parts(path: str | Path) -> list[str]:
    """Return geometry names in a mesh file.

    Single-body STL/PLY returns ``["default"]``. Multi-body OBJ/GLTF/STEP
    returns one entry per geometry when STEP is loaded with
    ``merge_primitives=False``.
    """
    path = Path(path)
    merge = False if _is_step(path) else True
    raw = _load_file_raw(path, merge_primitives=merge)
    if isinstance(raw, trimesh.Scene):
        names = [str(k) for k in raw.geometry.keys()]
        return names if names else ["default"]
    return ["default"]


def load_mesh(
    path: str | Path,
    *,
    part_name: str | None = None,
    scale: float = 1.0,
) -> trimesh.Trimesh:
    """Load a triangle mesh, optionally selecting one part by name."""
    path = Path(path)
    merge = True
    if _is_step(path) and part_name not in (None, "default"):
        merge = False
    raw = _load_file_raw(path, merge_primitives=merge)

    if isinstance(raw, trimesh.Trimesh):
        mesh = raw.copy()
    else:
        assert isinstance(raw, trimesh.Scene)
        if part_name is None or part_name == "default":
            if len(raw.geometry) == 1:
                mesh = next(iter(raw.geometry.values())).copy()
            else:
                mesh = trimesh.util.concatenate(tuple(raw.geometry.values()))
        else:
            if part_name not in raw.geometry:
                available = ", ".join(str(k) for k in raw.geometry.keys())
                raise KeyError(
                    f"Part '{part_name}' not found in {path.name}. "
                    f"Available: {available}"
                )
            mesh = raw.geometry[part_name].copy()

    if scale != 1.0:
        mesh.apply_scale(scale)
    if not isinstance(mesh, trimesh.Trimesh):
        raise RuntimeError(f"Failed to load mesh as triangles: {path}")
    return mesh


def simplify_trimesh(mesh: trimesh.Trimesh, *, max_faces: int = 80_000) -> trimesh.Trimesh:
    """Reduce triangle count for interactive preview ray casting."""
    if len(mesh.faces) <= max_faces:
        return mesh
    try:
        simplified = mesh.simplify_quadric_decimation(max_faces)
        if len(simplified.faces) > 0:
            return simplified
    except Exception:
        pass
    step = max(1, len(mesh.faces) // max_faces)
    faces = mesh.faces[::step][:max_faces]
    return trimesh.Trimesh(vertices=mesh.vertices, faces=faces, process=False)


def _bounds_from_geom(
    geom: trimesh.Trimesh, scale: float
) -> tuple[np.ndarray, np.ndarray]:
    g = geom
    if scale != 1.0:
        g = geom.copy()
        g.apply_scale(scale)
    return (
        np.asarray(g.bounds[0], dtype=np.float64),
        np.asarray(g.bounds[1], dtype=np.float64),
    )


def suggest_mesh_scale_to_mm(path: str | Path) -> float:
    """Guess a uniform scale to express CAD geometry in millimetres.

    Many STEP files arrive in metres (≈0.01–2 unit extent) while this simulator
    uses millimetres for primitives, lights, and the camera model.
    """
    try:
        all_bounds = load_all_part_bounds(path, scale=1.0)
    except Exception:
        return 1.0
    if not all_bounds:
        return 1.0
    max_extent = 0.0
    for lo, hi in all_bounds.values():
        max_extent = max(max_extent, float(np.max(hi - lo)))
    if max_extent <= 0.0:
        return 1.0
    if max_extent < 5.0:
        return 1000.0
    if max_extent < 50.0:
        return 10.0
    return 1.0


def union_bounds_for_parts(
    path: str | Path,
    part_names: list[str | None],
    *,
    scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Axis-aligned union of bounds for the listed parts."""
    all_bounds = load_all_part_bounds(path, scale=scale)
    bmin = np.array([np.inf, np.inf, np.inf], dtype=np.float64)
    bmax = np.array([-np.inf, -np.inf, -np.inf], dtype=np.float64)
    for part_name in part_names:
        key = part_name if part_name not in (None, "default") else "default"
        if key not in all_bounds and len(all_bounds) == 1:
            key = next(iter(all_bounds))
        if key not in all_bounds:
            lo, hi = load_mesh_bounds(path, part_name=part_name, scale=scale)
        else:
            lo, hi = all_bounds[key]
        bmin = np.minimum(bmin, lo)
        bmax = np.maximum(bmax, hi)
    return bmin, bmax


def workspace_placement_offset(
    bmin: np.ndarray,
    bmax: np.ndarray,
    *,
    center_mm: tuple[float, float, float] = (0.0, 0.0, 5.0),
) -> tuple[float, float, float]:
    """Translation that moves the assembly centre to ``center_mm``."""
    mid = 0.5 * (np.asarray(bmin) + np.asarray(bmax))
    return (
        center_mm[0] - float(mid[0]),
        center_mm[1] - float(mid[1]),
        center_mm[2] - float(mid[2]),
    )


def load_all_part_bounds(
    path: str | Path,
    *,
    scale: float = 1.0,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Return bounds for every named body in one cached file read."""
    path = Path(path)
    merge = False if _is_step(path) else True
    raw = _load_file_raw(path, merge_primitives=merge)
    if isinstance(raw, trimesh.Trimesh):
        return {"default": _bounds_from_geom(raw, scale)}
    return {str(name): _bounds_from_geom(geom, scale) for name, geom in raw.geometry.items()}


def load_mesh_bounds(
    path: str | Path,
    *,
    part_name: str | None = None,
    scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return axis-aligned bounds (min, max) without building a PyVista mesh.

  Uses the same file cache as :func:`load_mesh` but avoids concatenating
  multi-body scenes when only bounds are needed for the 3D viewport.
    """
    path = Path(path)
    merge = True
    if _is_step(path) and part_name not in (None, "default"):
        merge = False
    all_bounds = load_all_part_bounds(path, scale=scale)
    key = part_name if part_name not in (None, "default") else "default"
    if key in all_bounds:
        return all_bounds[key]
    if len(all_bounds) == 1:
        return next(iter(all_bounds.values()))
    if part_name is None or part_name == "default":
        bmin = np.array([np.inf, np.inf, np.inf], dtype=np.float64)
        bmax = np.array([-np.inf, -np.inf, -np.inf], dtype=np.float64)
        for lo, hi in all_bounds.values():
            bmin = np.minimum(bmin, lo)
            bmax = np.maximum(bmax, hi)
        return bmin, bmax
    available = ", ".join(all_bounds.keys())
    raise KeyError(
        f"Part '{part_name}' not found in {path.name}. Available: {available}"
    )


def _safe_part_filename(part_name: str) -> str:
    safe = re.sub(r"[^\w\-.]+", "_", part_name, flags=re.UNICODE)
    return safe[:80] or "part"


def mesh_cache_path(geom: TargetMesh) -> Path:
    """Path for a cached single-part export used by Mitsuba."""
    stem = Path(geom.path).stem
    digest = hashlib.sha1(str(Path(geom.path).resolve()).encode()).hexdigest()[:10]
    part = _safe_part_filename(geom.part_name or "merged")
    cache_dir = Path(geom.path).resolve().parent / ".optsim_cache" / f"{stem}_{digest}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{part}.ply"


def resolve_mesh_path_for_render(geom: TargetMesh) -> str:
    """Return a filesystem path suitable for Mitsuba ``filename`` loading."""
    if geom.part_name is None and not _is_step(Path(geom.path)):
        return geom.path
    cache = mesh_cache_path(geom)
    src_mtime = Path(geom.path).stat().st_mtime
    if cache.exists() and cache.stat().st_mtime >= src_mtime:
        return str(cache)
    mesh = load_mesh(geom.path, part_name=geom.part_name, scale=1.0)
    mesh.export(cache)
    return str(cache)


def _load_step(path: Path, *, merge_primitives: bool = True) -> Any:
    """Load STEP via cascadio (through trimesh) or cadquery fallback."""
    errors: list[str] = []

    if _has_cascadio():
        try:
            return trimesh.load(str(path), merge_primitives=merge_primitives)
        except Exception as exc:
            errors.append(f"cascadio: {exc}")

    try:
        return _load_step_cadquery(path)
    except ImportError:
        errors.append("cadquery is not installed")
    except Exception as exc:
        errors.append(f"cadquery: {exc}")

    detail = "\n".join(f"  • {e}" for e in errors) if errors else "  (no backend)"
    raise RuntimeError(f"{STEP_INSTALL_HINT}\n\nDetails:\n{detail}")


def _load_step_cadquery(path: Path) -> trimesh.Trimesh:
    """Legacy STEP path: cadquery tessellation to STL in a temp directory."""
    try:
        import cadquery as cq
    except ImportError as exc:
        raise ImportError("cadquery") from exc

    shape = cq.importers.importStep(str(path))
    with tempfile.TemporaryDirectory(prefix="optsim_step_") as tmp:
        stl_path = Path(tmp) / f"{path.stem}.stl"
        cq.exporters.export(shape, str(stl_path), tolerance=0.05)
        loaded = trimesh.load(stl_path)
    if isinstance(loaded, trimesh.Scene):
        loaded = trimesh.util.concatenate(tuple(loaded.geometry.values()))
    return loaded
