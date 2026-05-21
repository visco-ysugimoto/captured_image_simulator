"""Dialog that runs environment diagnostics (like ``optsim doctor``)."""

from __future__ import annotations

import importlib
import platform

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QTextEdit, QVBoxLayout

from .i18n import LanguageManager


def _run_doctor_report() -> str:
    lines: list[str] = []
    lines.append(f"Python: {platform.python_version()} on {platform.platform()}\n")

    def check(name: str, attr: str = "__version__") -> None:
        try:
            mod = importlib.import_module(name)
            version = getattr(mod, attr, "?")
            lines.append(f"  {name:12s} OK    ({version})")
        except Exception as exc:
            lines.append(f"  {name:12s} MISSING ({exc})")

    for pkg in [
        "numpy", "pydantic", "yaml", "trimesh", "rtree", "cv2",
        "PyQt6", "pyvista", "pyvistaqt", "mitsuba", "drjit",
    ]:
        check(pkg)

    lines.append("\n-- Mitsuba variants --")
    try:
        import mitsuba as mi

        available = list(mi.variants())
        lines.append(f"  available: {available}")
        candidates = [
            v for v in (
                "scalar_rgb", "llvm_ad_rgb", "llvm_rgb",
                "cuda_ad_rgb", "cuda_rgb",
            )
            if v in available
        ]
        for variant in candidates:
            try:
                mi.set_variant(variant)
                scene_dict = {
                    "type": "scene",
                    "integrator": {"type": "path"},
                    "sensor": {
                        "type": "perspective",
                        "to_world": mi.ScalarTransform4f().look_at(
                            origin=[0, 0, 3], target=[0, 0, 0], up=[0, 1, 0]
                        ),
                        "film": {"type": "hdrfilm", "width": 16, "height": 16},
                        "sampler": {"type": "independent", "sample_count": 1},
                    },
                    "sphere": {"type": "sphere", "bsdf": {"type": "diffuse"}},
                    "emitter": {"type": "constant"},
                }
                msc = mi.load_dict(scene_dict)
                mi.render(msc, spp=1)
                lines.append(f"  {variant:14s} OK")
            except Exception as exc:
                lines.append(f"  {variant:14s} FAIL ({type(exc).__name__}: {exc})")
    except ImportError:
        lines.append("  Mitsuba is not installed.")

    lines.append("\n-- Fallback dry run --")
    try:
        from ..domain import Camera, Scene, Target, TelecentricLens
        from ..domain.light import RingLight
        from ..domain.target import Primitive, PrimitiveKind, TargetPrimitive
        from ..render import Renderer, RenderSettings

        scene = Scene(
            camera=Camera(),
            lens=TelecentricLens(),
            lights=[RingLight(name="r")],
            targets=[
                Target(
                    name="t",
                    geometry=TargetPrimitive(
                        primitive=Primitive(kind=PrimitiveKind.cube)
                    ),
                )
            ],
        )
        res = Renderer(RenderSettings(spp=1, use_fallback=True)).render(scene)
        lines.append(
            f"  fallback raycaster: OK ({res.width}x{res.height}, "
            f"max DN {int(res.digital.max())})"
        )
    except Exception as exc:
        lines.append(f"  fallback raycaster: FAIL ({type(exc).__name__}: {exc})")

    lines.append(
        "\nTip: Full render (F6) uses Mitsuba when available. "
        "Install LLVM or use a CUDA variant if llvm_ad_rgb fails."
    )
    return "\n".join(lines)


class EnvironmentDialog(QDialog):
    def __init__(
        self,
        i18n: LanguageManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._i18n = i18n
        self.setWindowTitle(self._t("env.title"))
        self.resize(620, 480)

        layout = QVBoxLayout(self)
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setPlainText(self._t("env.running"))
        layout.addWidget(self._text)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setText(self._t("dialog.close"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._text.setPlainText(_run_doctor_report())

    def _t(self, key: str, **kwargs: object) -> str:
        return self._i18n.text(key, **kwargs)
