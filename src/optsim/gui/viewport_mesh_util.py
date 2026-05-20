"""Lightweight mesh preparation for the interactive 3D viewport."""

from __future__ import annotations

import numpy as np

# Keep the UI responsive; full detail is for the renderer only.
VIEWPORT_MAX_FACES = 20_000


def simplify_for_viewport(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    max_faces: int = VIEWPORT_MAX_FACES,
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce triangle count for PyVista preview (runs off the UI thread)."""
    import trimesh

    verts = np.asarray(vertices, dtype=np.float64)
    tris = np.asarray(faces, dtype=np.int64)
    if tris.size == 0:
        return verts, tris
    if tris.ndim != 2 or tris.shape[1] != 3:
        mesh = trimesh.Trimesh(vertices=verts, faces=tris, process=True)
        verts, tris = mesh.vertices, mesh.faces

    mesh = trimesh.Trimesh(vertices=verts, faces=tris, process=False)
    if len(mesh.faces) <= max_faces:
        return mesh.vertices, mesh.faces

    try:
        simplified = mesh.simplify_quadric_decimation(max_faces)
        if len(simplified.faces) > 0:
            return simplified.vertices, simplified.faces
    except Exception:
        pass

    # Fast fallback: face subsampling (coarse but avoids UI freeze).
    step = max(1, len(mesh.faces) // max_faces)
    sampled = mesh.faces[::step][:max_faces]
    return mesh.vertices, sampled


def faces_to_vtk_cells(faces: np.ndarray) -> np.ndarray:
    """Build PyVista/VTK cell array from triangle indices."""
    tris = np.asarray(faces, dtype=np.int64)
    return np.hstack([np.full((len(tris), 1), 3), tris]).astype(np.int64)
