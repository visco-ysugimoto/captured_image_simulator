"""Viewport mesh simplification tests."""

from __future__ import annotations

import numpy as np
import trimesh

from optsim.gui.viewport_mesh_util import VIEWPORT_MAX_FACES, simplify_for_viewport


def test_simplify_for_viewport_reduces_large_mesh() -> None:
    dense = trimesh.creation.icosphere(subdivisions=5)
    assert len(dense.faces) > VIEWPORT_MAX_FACES
    verts, faces = simplify_for_viewport(dense.vertices, dense.faces)
    assert len(faces) <= VIEWPORT_MAX_FACES
    assert verts.shape[1] == 3


def test_simplify_for_viewport_keeps_small_mesh() -> None:
    mesh = trimesh.creation.box()
    verts, faces = simplify_for_viewport(mesh.vertices, mesh.faces)
    np.testing.assert_array_equal(faces, mesh.faces)
