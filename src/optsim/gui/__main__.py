"""Allow running the GUI as ``python -m optsim.gui`` (and PyInstaller entry)."""

from __future__ import annotations

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
