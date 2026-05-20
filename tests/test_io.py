"""Round-trip tests for the project file format."""

from __future__ import annotations

from pathlib import Path

from optsim.domain import Camera, Scene, TelecentricLens
from optsim.io import load_project, save_project
from optsim.presets import build_light_preset, get_material_preset


def test_yaml_round_trip(tmp_path: Path) -> None:
    scene = Scene(
        name="rt",
        camera=Camera(),
        lens=TelecentricLens(),
        lights=[build_light_preset("ring_above")],
    )
    path = tmp_path / "scene.yaml"
    save_project(scene, path)
    loaded = load_project(path)
    assert loaded.name == "rt"
    assert len(loaded.lights) == 1
    assert loaded.lights[0].kind.value == "ring"


def test_json_round_trip(tmp_path: Path) -> None:
    scene = Scene(name="rt2", camera=Camera(), lens=TelecentricLens())
    path = tmp_path / "scene.json"
    save_project(scene, path)
    loaded = load_project(path)
    assert loaded.name == "rt2"


def test_sample_yaml_loads() -> None:
    p = Path(__file__).resolve().parent.parent / "examples" / "sample_scene.yaml"
    assert p.exists()
    scene = load_project(p)
    assert scene.camera.sensor.width_px == 800
    assert len(scene.lights) >= 1


def test_material_presets() -> None:
    mat = get_material_preset("aluminum_brushed")
    assert mat.kind.value == "anisotropic"
