"""GUI entry point."""

from __future__ import annotations

import logging
import sys


def main() -> int:
    # Stream log records to stderr so users can diagnose render hangs by
    # running ``python -m optsim.gui`` from a console.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as exc:
        print(
            "PyQt6 is not installed. Install GUI extras with:\n"
            "    pip install -e .[gui]\n"
            f"(import error: {exc})",
            file=sys.stderr,
        )
        return 1

    from .main_window import MainWindow
    from .ui_theme import apply_app_theme

    app = QApplication.instance() or QApplication(sys.argv)
    apply_app_theme(app)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
