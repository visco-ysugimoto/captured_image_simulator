"""Shared primitives used across the domain models."""

from __future__ import annotations

import math
from typing import Annotated

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

Vec3 = Annotated[tuple[float, float, float], Field(min_length=3, max_length=3)]


class Transform(BaseModel):
    """6-DoF rigid transform expressed by position [mm] and Euler angles [deg].

    Rotation order is intrinsic ZYX (yaw-pitch-roll). All angles are in degrees
    so that the GUI can show physically meaningful values to the user.
    """

    model_config = ConfigDict(extra="forbid")

    position: Vec3 = (0.0, 0.0, 0.0)
    rotation_deg: Vec3 = (0.0, 0.0, 0.0)

    def to_matrix(self) -> np.ndarray:
        """Return a 4x4 homogeneous transform."""
        rx, ry, rz = (math.radians(a) for a in self.rotation_deg)
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)
        cz, sz = math.cos(rz), math.sin(rz)
        rot_x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
        rot_y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        rot_z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
        rot = rot_z @ rot_y @ rot_x
        mat = np.eye(4)
        mat[:3, :3] = rot
        mat[:3, 3] = self.position
        return mat

    def forward(self) -> np.ndarray:
        """Unit vector along the local -Z axis transformed into world space.

        Used as the optical axis direction for cameras and lights.
        """
        return self.to_matrix()[:3, :3] @ np.array([0.0, 0.0, -1.0])

    def up(self) -> np.ndarray:
        """Unit vector along the local +Y axis transformed into world space."""
        return self.to_matrix()[:3, :3] @ np.array([0.0, 1.0, 0.0])


def look_at_rotation_deg(
    position: Vec3, target: Vec3, up_hint: Vec3 = (0.0, 1.0, 0.0)
) -> tuple[float, float, float]:
    """Compute Euler angles (deg, ZYX intrinsic) that orient -Z toward ``target``.

    Useful for cameras/lights that the user wants to aim at a world point.
    """
    pos = np.asarray(position, dtype=float)
    tgt = np.asarray(target, dtype=float)
    fwd = tgt - pos
    norm = np.linalg.norm(fwd)
    if norm < 1e-9:
        return (0.0, 0.0, 0.0)
    fwd = fwd / norm
    up = np.asarray(up_hint, dtype=float)
    right = np.cross(fwd, up)
    if np.linalg.norm(right) < 1e-6:
        up = np.array([0.0, 0.0, 1.0]) if abs(up_hint[1]) > 0.9 else np.array([0.0, 1.0, 0.0])
        right = np.cross(fwd, up)
    right /= np.linalg.norm(right)
    new_up = np.cross(right, fwd)
    rot = np.column_stack([right, new_up, -fwd])
    sy = -rot[2, 0]
    cy = math.sqrt(max(0.0, 1.0 - sy * sy))
    if cy > 1e-6:
        rx = math.atan2(rot[2, 1], rot[2, 2])
        ry = math.atan2(sy, cy)
        rz = math.atan2(rot[1, 0], rot[0, 0])
    else:
        rx = math.atan2(-rot[1, 2], rot[1, 1])
        ry = math.atan2(sy, cy)
        rz = 0.0
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))
