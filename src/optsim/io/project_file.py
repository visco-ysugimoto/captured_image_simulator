"""Serialise and deserialise :class:`optsim.domain.Scene` to YAML or JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ..domain import (
    BarLight,
    Camera,
    CoaxialLight,
    DomeLight,
    LightKind,
    PointLight,
    RectAreaLight,
    RingLight,
    Scene,
    Target,
    TelecentricLens,
)
from ..domain.light import Backlight
from ..domain.target import TargetMesh, TargetPrimitive

_LIGHT_BY_KIND: dict[str, type] = {
    LightKind.point.value: PointLight,
    LightKind.rect_area.value: RectAreaLight,
    LightKind.ring.value: RingLight,
    LightKind.bar.value: BarLight,
    LightKind.coaxial.value: CoaxialLight,
    LightKind.dome.value: DomeLight,
    LightKind.backlight.value: Backlight,
}


def _light_from_dict(data: dict[str, Any]):
    kind = data.get("kind", LightKind.point.value)
    cls = _LIGHT_BY_KIND.get(kind, PointLight)
    return cls.model_validate(data)


def _target_from_dict(data: dict[str, Any]) -> Target:
    geom = data.get("geometry", {})
    geom_kind = geom.get("geometry_kind", "primitive")
    if geom_kind == "mesh":
        data = {**data, "geometry": TargetMesh.model_validate(geom).model_dump()}
    else:
        data = {**data, "geometry": TargetPrimitive.model_validate(geom).model_dump()}
    return Target.model_validate(data)


def _scene_from_dict(data: dict[str, Any]) -> Scene:
    camera = Camera.model_validate(data.get("camera", {}))
    lens = TelecentricLens.model_validate(data.get("lens", {}))
    lights = [_light_from_dict(d) for d in data.get("lights", [])]
    targets = [_target_from_dict(d) for d in data.get("targets", [])]
    return Scene(
        name=data.get("name", "untitled"),
        camera=camera,
        lens=lens,
        lights=lights,
        targets=targets,
        background_color=tuple(data.get("background_color", (0.0, 0.0, 0.0))),
    )


def save_project(scene: Scene, path: str | Path) -> None:
    path = Path(path)
    data = scene.model_dump(mode="json")
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    elif suffix == ".json":
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported project file extension: {suffix}")


def load_project(path: str | Path) -> Scene:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text) or {}
    elif suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"Unsupported project file extension: {suffix}")
    if not isinstance(data, dict):
        raise ValueError("Project file is not a mapping")
    return _scene_from_dict(data)
