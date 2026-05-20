"""Target-role material presets (widget, stage, generic parts).

Roles map to named entries in :data:`optsim.presets.materials.MATERIAL_PRESETS`.
Use these when building default scenes or assigning materials after mesh import.
"""

from __future__ import annotations

from ..domain import Material
from .materials import get_material_preset

# Role -> default material preset key
TARGET_ROLE_DEFAULTS: dict[str, str] = {
    "widget": "widget_aluminum_machined",
    "stage": "stage_matte_white",
    "fixture": "steel",
    "cover": "plastic_white",
}

# Grouped quick-pick labels for the GUI (category -> list of (label, preset_key))
TARGET_ROLE_PRESET_GROUPS: dict[str, list[tuple[str, str]]] = {
    "Widget (workpiece)": [
        ("Machined aluminum (brushed)", "widget_aluminum_machined"),
        ("Polished aluminum", "widget_aluminum_polished"),
        ("Die-cast zinc", "widget_diecast"),
        ("Painted white", "widget_painted_white"),
        ("Painted black", "widget_painted_black"),
        ("Rubber / elastomer", "rubber_black"),
        ("PCB green", "pcb_green"),
    ],
    "Stage / carrier": [
        ("Matte white plate", "stage_matte_white"),
        ("Anodized black", "stage_anodized_black"),
        ("Stainless steel", "stage_stainless"),
        ("Anti-glare green", "stage_antiglare_green"),
        ("Glass window (BK7)", "stage_glass_bk7"),
    ],
    "General": [
        ("White diffuse", "white_paper"),
        ("Black diffuse", "black_paper"),
        ("Plastic white", "plastic_white"),
        ("Ceramic white", "ceramic"),
        ("Copper", "copper"),
    ],
}


def target_role_names() -> list[str]:
    return sorted(TARGET_ROLE_DEFAULTS.keys())


def get_material_for_role(role: str) -> Material:
    """Return a deep copy of the default material for a target role."""
    key = TARGET_ROLE_DEFAULTS.get(role)
    if key is None:
        raise KeyError(f"Unknown target role: {role}. Known: {target_role_names()}")
    return get_material_preset(key)


def all_role_preset_choices() -> list[tuple[str, str]]:
    """Flat list of ``(display_label, preset_key)`` for combo boxes."""
    out: list[tuple[str, str]] = []
    for _group, items in TARGET_ROLE_PRESET_GROUPS.items():
        out.extend(items)
    return out
