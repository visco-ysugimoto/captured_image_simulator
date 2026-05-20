# PyInstaller spec for the Optical Simulator GUI.
#
# Usage (from the project root):
#     pyinstaller packaging/optsim.spec
#
# Output: ./dist/optsim/optsim.exe with all DLLs/resources.

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent

datas = []
datas += [(str(PROJECT_ROOT / "examples"), "examples")]
datas += [(str(PROJECT_ROOT / "resources"), "resources")]
datas += collect_data_files("pyvista")
datas += collect_data_files("vtkmodules", include_py_files=False)
datas += collect_data_files("trimesh")

hiddenimports = []
hiddenimports += collect_submodules("pyvista")
hiddenimports += collect_submodules("pyvistaqt")
hiddenimports += collect_submodules("vtkmodules")
hiddenimports += collect_submodules("imageio")
hiddenimports += collect_submodules("mitsuba")
hiddenimports += [
    "scipy._lib.array_api_compat.numpy.fft",
    "scipy.special.cython_special",
    "PyQt6.sip",
]

a = Analysis(
    [str(PROJECT_ROOT / "src" / "optsim" / "gui" / "__main__.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="optsim",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="optsim",
)
