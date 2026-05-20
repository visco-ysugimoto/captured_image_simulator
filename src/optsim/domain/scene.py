"""Top-level scene container."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .camera import Camera
from .lens import TelecentricLens
from .light import Light
from .target import Target


class Scene(BaseModel):
    """All objects required to simulate one imaging configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = "untitled"

    camera: Camera = Field(default_factory=Camera)
    lens: TelecentricLens = Field(default_factory=TelecentricLens)
    lights: list[Light] = Field(default_factory=list)
    targets: list[Target] = Field(default_factory=list)

    background_color: tuple[float, float, float] = (0.0, 0.0, 0.0)

    radiance_scale: float = Field(
        default=1.0e3,
        gt=0.0,
        description=(
            "Calibration factor mapping renderer radiance units to sensor "
            "electrons. Adjust so that a known reference scene matches "
            "measured mean DN (together with exposure, QE, and gain)."
        ),
    )

    def find_target(self, name: str) -> Target | None:
        for t in self.targets:
            if t.name == name:
                return t
        return None

    def find_light(self, name: str) -> Light | None:
        for light in self.lights:
            if light.name == name:
                return light
        return None
