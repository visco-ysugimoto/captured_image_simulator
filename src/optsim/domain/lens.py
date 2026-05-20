"""Telecentric lens model.

Object-space telecentric: all chief rays in object space are parallel to the
optical axis. The effective sensor projection is therefore an orthographic
projection of a region of dimensions ``sensor_size / magnification`` placed at
the working distance from the lens.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TelecentricLens(BaseModel):
    """Object-space telecentric lens parameters.

    Either ``na`` (numerical aperture) or ``f_number`` may be specified to
    describe the aperture. ``f_number`` is converted to NA internally.
    """

    model_config = ConfigDict(extra="forbid")

    magnification: float = Field(default=0.5, gt=0.0, le=20.0)
    working_distance_mm: float = Field(default=80.0, gt=0.0)

    na: float | None = Field(default=0.05, ge=0.0, le=0.95)
    f_number: float | None = Field(default=None, gt=0.0)

    distortion_pct: float = Field(default=0.0, ge=-5.0, le=5.0)

    @model_validator(mode="after")
    def _resolve_aperture(self) -> "TelecentricLens":
        if self.na is None and self.f_number is None:
            object.__setattr__(self, "na", 0.05)
        if self.na is None and self.f_number is not None:
            object.__setattr__(self, "na", 1.0 / (2.0 * self.f_number))
        return self

    @property
    def effective_na(self) -> float:
        return self.na if self.na is not None else 0.05

    @property
    def aperture_radius_object_mm(self) -> float:
        """Approximate radius of the aperture seen from the object side.

        Treats the entrance pupil as a thin disk at the working distance and
        relates its radius to the numerical aperture by NA = sin(theta_max),
        with theta_max approximated by aperture_radius / working_distance for
        the small angles typical of telecentric lenses.
        """
        theta = math.asin(min(0.99, self.effective_na))
        return self.working_distance_mm * math.tan(theta)

    @property
    def depth_of_field_mm(self) -> float:
        """Total DoF using the simple geometric formula.

        DoF = 2 * c / (NA * M), where c is the circle of confusion (one pixel)
        and M is the magnification. This is computed at request time by the
        renderer because c depends on the sensor pixel pitch.
        """
        circle_of_confusion_mm = 0.0055
        return 2.0 * circle_of_confusion_mm / (self.effective_na * self.magnification + 1e-9)
