"""Project file persistence and mesh loading helpers.

Sub-modules are imported lazily so that consumers that only need project
file I/O do not pay the cost (and dependency) of trimesh / imageio.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "load_project",
    "save_project",
    "load_mesh",
    "supported_mesh_extensions",
    "load_image",
    "save_image",
]


def __getattr__(name: str) -> Any:
    if name in {"load_project", "save_project"}:
        from .project_file import load_project, save_project

        return {"load_project": load_project, "save_project": save_project}[name]
    if name in {"load_mesh", "supported_mesh_extensions"}:
        from .mesh_loader import load_mesh, supported_mesh_extensions

        return {"load_mesh": load_mesh, "supported_mesh_extensions": supported_mesh_extensions}[name]
    if name in {"load_image", "save_image"}:
        from .image_io import load_image, save_image

        return {"load_image": load_image, "save_image": save_image}[name]
    raise AttributeError(f"module 'optsim.io' has no attribute {name!r}")


if TYPE_CHECKING:
    from .image_io import load_image, save_image
    from .mesh_loader import load_mesh, supported_mesh_extensions
    from .project_file import load_project, save_project
