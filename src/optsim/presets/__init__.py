"""Curated BRDF and illumination presets used by the GUI and examples."""

from .lights import LIGHT_PRESETS, build_light_preset, light_preset_names
from .materials import MATERIAL_PRESETS, get_material_preset, material_preset_names
from .target_roles import (
    TARGET_ROLE_DEFAULTS,
    TARGET_ROLE_PRESET_GROUPS,
    all_role_preset_choices,
    get_material_for_role,
    target_role_names,
)

__all__ = [
    "MATERIAL_PRESETS",
    "get_material_preset",
    "material_preset_names",
    "LIGHT_PRESETS",
    "build_light_preset",
    "light_preset_names",
    "TARGET_ROLE_DEFAULTS",
    "TARGET_ROLE_PRESET_GROUPS",
    "all_role_preset_choices",
    "get_material_for_role",
    "target_role_names",
]
