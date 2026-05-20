"""Rendering layer.

Bridges the domain model to Mitsuba 3 and applies a post-renderer sensor
response model (quantum efficiency, noise, quantisation) to obtain the final
8/16-bit imager output.
"""

from .cancellation import RenderCancellation, RenderCancelled
from .renderer import RenderResult, Renderer, RenderSettings
from .sensor_response import apply_sensor_response

__all__ = [
    "Renderer",
    "RenderSettings",
    "RenderResult",
    "RenderCancellation",
    "RenderCancelled",
    "apply_sensor_response",
]
