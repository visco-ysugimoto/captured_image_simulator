"""Quickstart example: build a scene in code and render an image.

Run with::

    python examples/quickstart.py

If Mitsuba 3 is installed it will be used; otherwise the project falls back
to a lightweight trimesh raycaster that produces a good-enough preview.
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS.parent / "src"))

from optsim.domain import Camera, Scene, Target, TelecentricLens
from optsim.domain.common import Transform
from optsim.domain.target import Primitive, PrimitiveKind, TargetPrimitive
from optsim.io import save_image, save_project
from optsim.presets import build_light_preset, get_material_preset
from optsim.render import Renderer, RenderSettings


def main() -> None:
    scene = Scene(
        name="quickstart",
        camera=Camera(name="cam", transform=Transform(position=(0.0, 0.0, 120.0))),
        lens=TelecentricLens(magnification=0.5, working_distance_mm=80.0, na=0.04),
        lights=[build_light_preset("ring_above")],
        targets=[
            Target(
                name="widget",
                transform=Transform(position=(0.0, 0.0, 5.0)),
                geometry=TargetPrimitive(primitive=Primitive(kind=PrimitiveKind.cube,
                                                             size_mm=(30.0, 20.0, 10.0))),
                material=get_material_preset("aluminum_brushed"),
            ),
            Target(
                name="stage",
                transform=Transform(position=(0.0, 0.0, -1.0)),
                geometry=TargetPrimitive(primitive=Primitive(kind=PrimitiveKind.plane,
                                                             size_mm=(120.0, 120.0, 1.0))),
                material=get_material_preset("plastic_white"),
            ),
        ],
    )

    save_project(scene, THIS / "quickstart_scene.yaml")
    print(f"Saved scene to {THIS / 'quickstart_scene.yaml'}")

    renderer = Renderer(RenderSettings(spp=32, use_fallback=True))
    result = renderer.render(scene)

    out = THIS / "quickstart_render.png"
    save_image(result.digital, out)
    print(f"Rendered {result.width}x{result.height} -> {out}")
    print(f"  electrons mean = {result.electrons.mean():.1f}")
    print(f"  digital max    = {result.digital.max()}")


if __name__ == "__main__":
    main()
