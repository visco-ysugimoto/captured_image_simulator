"""Mesh loader multi-part tests."""

from __future__ import annotations

import trimesh

from optsim.io.mesh_loader import (
    clear_mesh_cache,
    list_mesh_parts,
    load_all_part_bounds,
    load_mesh,
    load_mesh_bounds,
    step_backend_available,
    suggest_mesh_scale_to_mm,
)


def test_step_backend_after_cascadio_install() -> None:
    """Document that cascadio enables STEP; skip if not installed."""
    backend = step_backend_available()
    if backend is None:
        import pytest

        pytest.skip("cascadio/cadquery not installed")
    assert backend in ("cascadio", "cadquery")


def test_list_mesh_parts_single_stl(tmp_path) -> None:
    path = tmp_path / "box.stl"
    trimesh.creation.box().export(path)
    assert list_mesh_parts(path) == ["default"]


def test_list_mesh_parts_multi_glb(tmp_path) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), geom_name="body")
    scene.add_geometry(trimesh.creation.icosphere(radius=5.0), geom_name="boss")
    path = tmp_path / "assembly.glb"
    scene.export(path)
    parts = list_mesh_parts(path)
    assert "body" in parts
    assert "boss" in parts

    body = load_mesh(path, part_name="body")
    assert len(body.vertices) > 0
    boss = load_mesh(path, part_name="boss")
    assert len(boss.vertices) > 0


def test_load_mesh_reuses_cached_file_load(tmp_path, monkeypatch) -> None:
    clear_mesh_cache()
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), geom_name="body")
    scene.add_geometry(trimesh.creation.icosphere(radius=5.0), geom_name="boss")
    path = tmp_path / "assembly.glb"
    scene.export(path)

    calls = {"n": 0}
    real_load = trimesh.load

    def counting_load(*args, **kwargs):
        calls["n"] += 1
        return real_load(*args, **kwargs)

    monkeypatch.setattr(trimesh, "load", counting_load)

    list_mesh_parts(path)
    load_mesh(path, part_name="body")
    load_mesh(path, part_name="boss")
    assert calls["n"] == 1


def test_load_all_part_bounds_multi_glb(tmp_path) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), geom_name="body")
    scene.add_geometry(trimesh.creation.icosphere(radius=5.0), geom_name="boss")
    path = tmp_path / "assembly.glb"
    scene.export(path)
    bounds = load_all_part_bounds(path)
    assert "body" in bounds
    assert "boss" in bounds
    bmin, bmax = load_mesh_bounds(path, part_name="body")
    import numpy as np

    np.testing.assert_allclose(bounds["body"][0], bmin, rtol=1e-5)
    np.testing.assert_allclose(bounds["body"][1], bmax, rtol=1e-5)


def test_suggest_mesh_scale_for_metre_step_like_extent() -> None:
    from pathlib import Path

    p = Path("test.stp")
    if not p.exists():
        import pytest

        pytest.skip("test.stp not in workspace")
    assert suggest_mesh_scale_to_mm(p) == 1000.0


def test_load_mesh_bounds_matches_mesh(tmp_path) -> None:
    path = tmp_path / "box.stl"
    mesh = trimesh.creation.box(extents=(30.0, 20.0, 10.0))
    mesh.export(path)
    bmin, bmax = load_mesh_bounds(path)
    assert bmax[0] - bmin[0] > 25.0
    assert bmax[2] - bmin[2] > 5.0
