"""Merge multi-part mesh targets for faster fallback ray casting."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..domain import Target
from ..domain.target import TargetMesh
from ..io.mesh_loader import load_mesh, simplify_trimesh

# Cap triangles for fallback Preview / Live (full detail: export or Mitsuba path).
RENDER_RAYCAST_MAX_FACES = 80_000

# (path, scale, position, rotation) -> transformed trimesh
_WORLD_MESH_CACHE: dict[tuple[Any, ...], Any] = {}


def clear_render_mesh_cache() -> None:
    _WORLD_MESH_CACHE.clear()


class MergedMeshTarget:
    """Ray-cast several mesh bodies that share placement as one triangle soup."""

    __slots__ = (
        "name",
        "visible",
        "material",
        "geometry",
        "transform",
        "_parts",
        "_cache_key",
    )

    def __init__(self, parts: list[Target]) -> None:
        if not parts:
            raise ValueError("MergedMeshTarget requires at least one part")
        first = parts[0]
        self._parts = parts
        self.name = f"{first.name} (+{len(parts) - 1} parts)"
        self.visible = all(p.visible for p in parts)
        self.material = first.material
        self.geometry = first.geometry
        self.transform = first.transform
        part_ids = tuple(
            sorted(
                p.geometry.part_name or "default"
                for p in parts
                if isinstance(p.geometry, TargetMesh)
            )
        )
        g = first.geometry
        assert isinstance(g, TargetMesh)
        self._cache_key = (
            "merged",
            g.path,
            float(g.scale),
            tuple(first.transform.position),
            tuple(first.transform.rotation_deg),
            part_ids,
        )

    def world_mesh(self):
        import trimesh

        if self._cache_key in _WORLD_MESH_CACHE:
            return _WORLD_MESH_CACHE[self._cache_key]

        transform = self.transform.to_matrix()
        meshes = []
        for part in self._parts:
            geom = part.geometry
            assert isinstance(geom, TargetMesh)
            try:
                mesh = load_mesh(
                    geom.path,
                    part_name=geom.part_name,
                    scale=float(geom.scale),
                )
            except Exception:
                continue
            mesh = mesh.copy()
            mesh.apply_transform(transform)
            meshes.append(mesh)

        if not meshes:
            empty = trimesh.Trimesh()
            _WORLD_MESH_CACHE[self._cache_key] = empty
            return empty
        combined = (
            trimesh.util.concatenate(meshes)
            if len(meshes) > 1
            else meshes[0]
        )
        combined = simplify_trimesh(combined, max_faces=RENDER_RAYCAST_MAX_FACES)
        _WORLD_MESH_CACHE[self._cache_key] = combined
        return combined


def _placement_key(target: Target) -> tuple[Any, ...] | None:
    if not isinstance(target.geometry, TargetMesh):
        return None
    g = target.geometry
    return (
        g.path,
        float(g.scale),
        tuple(target.transform.position),
        tuple(target.transform.rotation_deg),
    )


def coalesce_mesh_targets_for_render(targets: list[Target]) -> list[Target | MergedMeshTarget]:
    """Group mesh targets that share file + transform into one ray-cast pass."""
    out: list[Target | MergedMeshTarget] = []
    mesh_groups: dict[tuple[Any, ...], list[Target]] = defaultdict(list)

    for target in targets:
        key = _placement_key(target)
        if key is None:
            out.append(target)
        else:
            mesh_groups[key].append(target)

    for group in mesh_groups.values():
        if len(group) == 1:
            out.append(group[0])
        else:
            out.append(MergedMeshTarget(group))
    return out


def world_mesh_for_target(target: Target):
    """Return a world-space triangle mesh for a single mesh target (cached)."""
    import trimesh

    if isinstance(target, MergedMeshTarget):
        return target.world_mesh()

    if not isinstance(target.geometry, TargetMesh):
        raise TypeError("Not a mesh target")

    geom = target.geometry
    key = (
        "single",
        geom.path,
        geom.part_name,
        float(geom.scale),
        tuple(target.transform.position),
        tuple(target.transform.rotation_deg),
    )
    if key in _WORLD_MESH_CACHE:
        return _WORLD_MESH_CACHE[key]

    mesh = load_mesh(geom.path, part_name=geom.part_name, scale=float(geom.scale))
    mesh = mesh.copy()
    mesh.apply_transform(target.transform.to_matrix())
    mesh = simplify_trimesh(mesh, max_faces=RENDER_RAYCAST_MAX_FACES)
    _WORLD_MESH_CACHE[key] = mesh
    return mesh
