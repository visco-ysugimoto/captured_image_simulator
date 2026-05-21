"""Common machine-vision-friendly material presets."""

from __future__ import annotations

from ..domain import Material, MaterialKind

MATERIAL_PRESETS: dict[str, Material] = {
    "white_paper": Material(
        name="white_paper",
        kind=MaterialKind.diffuse,
        base_color=(0.85, 0.85, 0.85),
    ),
    "black_paper": Material(
        name="black_paper",
        kind=MaterialKind.diffuse,
        base_color=(0.04, 0.04, 0.04),
    ),
    "aluminum_polished": Material(
        name="aluminum_polished",
        kind=MaterialKind.metal,
        base_color=(0.91, 0.92, 0.92),
        roughness=0.02,
    ),
    "aluminum_brushed": Material(
        name="aluminum_brushed",
        kind=MaterialKind.anisotropic,
        base_color=(0.86, 0.87, 0.88),
        roughness=0.35,
        anisotropy=0.7,
        anisotropy_rotation_deg=0.0,
    ),
    "steel": Material(
        name="steel",
        kind=MaterialKind.metal,
        base_color=(0.74, 0.75, 0.78),
        roughness=0.18,
    ),
    "copper": Material(
        name="copper",
        kind=MaterialKind.metal,
        base_color=(0.95, 0.64, 0.54),
        roughness=0.1,
    ),
    "rubber_black": Material(
        name="rubber_black",
        kind=MaterialKind.rough_plastic,
        base_color=(0.04, 0.04, 0.04),
        roughness=0.55,
        ior=1.5,
    ),
    "plastic_white": Material(
        name="plastic_white",
        kind=MaterialKind.rough_plastic,
        base_color=(0.78, 0.78, 0.8),
        roughness=0.35,
        ior=1.45,
    ),
    "ceramic": Material(
        name="ceramic",
        kind=MaterialKind.rough_plastic,
        base_color=(0.94, 0.94, 0.94),
        roughness=0.18,
        ior=1.6,
    ),
    "glass": Material(
        name="glass",
        kind=MaterialKind.dielectric,
        base_color=(0.95, 0.97, 1.0),
        roughness=0.0,
        ior=1.5,
    ),
    "pcb_green": Material(
        name="pcb_green",
        kind=MaterialKind.rough_plastic,
        base_color=(0.05, 0.32, 0.18),
        roughness=0.4,
        ior=1.45,
    ),
    # --- Widget (workpiece) surfaces ---
    "widget_aluminum_machined": Material(
        name="widget_aluminum_machined",
        kind=MaterialKind.anisotropic,
        base_color=(0.84, 0.85, 0.87),
        roughness=0.32,
        anisotropy=0.65,
        anisotropy_rotation_deg=0.0,
    ),
    "widget_aluminum_polished": Material(
        name="widget_aluminum_polished",
        kind=MaterialKind.metal,
        base_color=(0.90, 0.91, 0.93),
        roughness=0.04,
    ),
    "widget_diecast": Material(
        name="widget_diecast",
        kind=MaterialKind.metal,
        base_color=(0.72, 0.73, 0.75),
        roughness=0.22,
    ),
    "widget_painted_white": Material(
        name="widget_painted_white",
        kind=MaterialKind.rough_plastic,
        base_color=(0.88, 0.88, 0.90),
        roughness=0.28,
        ior=1.45,
    ),
    "widget_painted_black": Material(
        name="widget_painted_black",
        kind=MaterialKind.rough_plastic,
        base_color=(0.06, 0.06, 0.07),
        roughness=0.35,
        ior=1.45,
    ),
    # --- Stage / carrier surfaces ---
    "stage_matte_white": Material(
        name="stage_matte_white",
        kind=MaterialKind.rough_plastic,
        base_color=(0.82, 0.82, 0.84),
        roughness=0.42,
        ior=1.45,
    ),
    "stage_anodized_black": Material(
        name="stage_anodized_black",
        kind=MaterialKind.metal,
        base_color=(0.08, 0.08, 0.09),
        roughness=0.25,
    ),
    "stage_stainless": Material(
        name="stage_stainless",
        kind=MaterialKind.metal,
        base_color=(0.78, 0.79, 0.81),
        roughness=0.15,
    ),
    "stage_antiglare_green": Material(
        name="stage_antiglare_green",
        kind=MaterialKind.rough_plastic,
        base_color=(0.12, 0.38, 0.22),
        roughness=0.55,
        ior=1.45,
    ),
    "stage_glass_bk7": Material(
        name="stage_glass_bk7",
        kind=MaterialKind.dielectric,
        # Near-neutral transmission; slight blue tint can be added if needed.
        base_color=(0.99, 0.99, 0.99),
        roughness=0.0,
        # BK7 refractive index around visible center wavelength.
        ior=1.5168,
    ),
}


def material_preset_names() -> list[str]:
    return sorted(MATERIAL_PRESETS.keys())


def get_material_preset(name: str) -> Material:
    if name not in MATERIAL_PRESETS:
        raise KeyError(f"Unknown material preset: {name}")
    return MATERIAL_PRESETS[name].model_copy(deep=True)
