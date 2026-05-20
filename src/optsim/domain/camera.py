"""Camera and sensor model.

The camera is split into two concepts:
- ``Sensor``  : Physical detector parameters (size, pixels, noise, QE, etc.)
- ``Camera``  : The placed camera object that owns a sensor + transform.

The lens (telecentric) is modeled separately so that the same sensor can be
swapped between different optical formulas.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .common import Transform


class Sensor(BaseModel):
    """Physical sensor description.

    Default values approximate a typical 1/1.8" monochrome industrial sensor
    (Sony IMX series, 2/3 inch class) with a 5.5 um pixel pitch.
    """

    model_config = ConfigDict(extra="forbid")

    width_px: int = Field(default=1280, ge=16, le=20000)
    height_px: int = Field(default=1024, ge=16, le=20000)
    pixel_pitch_um: float = Field(default=5.5, gt=0.0, le=50.0)

    bit_depth: int = Field(default=12, ge=8, le=16)

    quantum_efficiency: float = Field(default=0.6, ge=0.0, le=1.0)
    full_well_e: float = Field(
        default=20000.0,
        gt=0.0,
        description="Full-well capacity in electrons.",
    )
    read_noise_e: float = Field(default=2.0, ge=0.0)
    dark_current_e_per_s: float = Field(default=5.0, ge=0.0)

    exposure_time_ms: float = Field(default=10.0, gt=0.0)
    gain_db: float = Field(default=0.0, ge=0.0, le=48.0)

    black_level_dn: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "ADC offset in digital numbers (DN) subtracted after "
            "quantisation. Set from dark-frame measurement for absolute "
            "correlation with a real camera."
        ),
    )

    monochrome: bool = True

    @property
    def width_mm(self) -> float:
        return self.width_px * self.pixel_pitch_um / 1000.0

    @property
    def height_mm(self) -> float:
        return self.height_px * self.pixel_pitch_um / 1000.0


class Camera(BaseModel):
    """Camera object placed in the scene.

    The optical axis is along the local -Z direction.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = "camera"
    transform: Transform = Field(default_factory=Transform)
    sensor: Sensor = Field(default_factory=Sensor)
