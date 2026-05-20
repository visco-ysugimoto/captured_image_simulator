"""Limits for stable interactive 3D preview with large CAD imports."""

from __future__ import annotations

# Per-part surface actors in the 3D view (simplified meshes).
VIEWPORT_MAX_MESH_ACTORS = 64

# Simplified triangles per part (50 parts × ~5k ≈ 250k faces — heavier but readable).
VIEWPORT_SURFACE_MAX_FACES = 5_000

# For a single merged target, allow denser preview so it does not look wire-like.
VIEWPORT_SURFACE_MAX_FACES_SINGLE = 35_000

# Safety cap when the scene has very many mesh targets (full STEP assemblies).
VIEWPORT_SURFACE_HARD_CAP = 100

# Populating the import table / scene tree with thousands of rows freezes Qt.
IMPORT_WARN_PART_COUNT = 100
IMPORT_DEFAULT_CHECKED_PARTS = 50
SCENE_TREE_MAX_TARGET_ROWS = 120
