"""Tests for fallback mesh target coalescing."""

from __future__ import annotations

from optsim.domain import Target
from optsim.domain.common import Transform
from optsim.domain.target import TargetMesh
from optsim.render.mesh_assembly import MergedMeshTarget, coalesce_mesh_targets_for_render


def test_coalesce_same_placement_merges() -> None:
    path = "model.stp"
    targets = [
        Target(
            name=f"p{i}",
            transform=Transform(position=(1.0, 2.0, 3.0)),
            geometry=TargetMesh(path=path, scale=1000.0, part_name=f"part{i}"),
        )
        for i in range(5)
    ]
    out = coalesce_mesh_targets_for_render(targets)
    assert len(out) == 1
    assert isinstance(out[0], MergedMeshTarget)


def test_coalesce_different_placement_stays_separate() -> None:
    path = "model.stp"
    targets = [
        Target(
            name="a",
            transform=Transform(position=(0.0, 0.0, 0.0)),
            geometry=TargetMesh(path=path, scale=1.0, part_name="a"),
        ),
        Target(
            name="b",
            transform=Transform(position=(10.0, 0.0, 0.0)),
            geometry=TargetMesh(path=path, scale=1.0, part_name="b"),
        ),
    ]
    out = coalesce_mesh_targets_for_render(targets)
    assert len(out) == 2
