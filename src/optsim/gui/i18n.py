"""Lightweight runtime i18n for the GUI (Japanese / English)."""

from __future__ import annotations

from typing import Literal

from PyQt6.QtCore import QObject, pyqtSignal

LanguageCode = Literal["ja", "en"]


_TEXTS: dict[str, dict[LanguageCode, str]] = {
    "app.title": {"ja": "Optical Simulator", "en": "Optical Simulator"},
    "tab.scene": {"ja": "3D シーン", "en": "3D Scene"},
    "tab.render": {"ja": "レンダ結果", "en": "Render Result"},
    "tab.compare": {"ja": "比較", "en": "Comparison"},
    "dock.scene": {"ja": "シーン", "en": "Scene"},
    "dock.properties": {"ja": "プロパティ", "en": "Properties"},
    "status.ready": {"ja": "Ready", "en": "Ready"},
    "menu.file": {"ja": "ファイル", "en": "File"},
    "menu.add": {"ja": "追加", "en": "Add"},
    "menu.render": {"ja": "レンダー", "en": "Render"},
    "menu.analysis": {"ja": "解析", "en": "Analysis"},
    "menu.language": {"ja": "言語", "en": "Language"},
    "menu.help": {"ja": "ヘルプ", "en": "Help"},
    "action.new_scene": {"ja": "新規シーン", "en": "New scene"},
    "action.open_project": {"ja": "プロジェクトを開く...", "en": "Open project..."},
    "action.save_project": {"ja": "プロジェクトを保存...", "en": "Save project..."},
    "action.save_last_render": {"ja": "最新レンダを保存...", "en": "Save last render..."},
    "action.quit": {"ja": "終了", "en": "Quit"},
    "action.import_mesh_multi": {"ja": "メッシュ読込 (複数パーツ)...", "en": "Import mesh (multi-part)..."},
    "action.import_mesh_single": {"ja": "メッシュターゲット (単一統合)...", "en": "Mesh target (single merged)..."},
    "action.quick_preview": {"ja": "プレビュー (高速/fallback)", "en": "Quick preview (fallback)"},
    "action.full_render": {"ja": "高品質レンダ (Mitsuba)", "en": "Full render (Mitsuba)"},
    "action.parameter_sweep": {"ja": "パラメータスイープ...", "en": "Parameter sweep..."},
    "action.calibration": {"ja": "参照画像でキャリブレーション...", "en": "Calibrate from reference image..."},
    "action.environment_check": {"ja": "環境チェック...", "en": "Environment check..."},
    "action.about": {"ja": "このアプリについて", "en": "About"},
    "action.live_preview": {"ja": "ライブプレビュー", "en": "Live preview"},
    "action.snapshot": {"ja": "スナップショット", "en": "Snapshot"},
    "action.language.ja": {"ja": "日本語", "en": "Japanese"},
    "action.language.en": {"ja": "英語", "en": "English"},
    "add.light_preset": {"ja": "照明プリセット: {name}", "en": "Light preset: {name}"},
    "add.primitive_target": {"ja": "プリミティブ: {name}", "en": "Primitive target: {name}"},
    "primitive.cube": {"ja": "キューブ", "en": "Cube"},
    "primitive.sphere": {"ja": "球", "en": "Sphere"},
    "primitive.cylinder": {"ja": "円柱", "en": "Cylinder"},
    "primitive.plane": {"ja": "平面", "en": "Plane"},
    "scene_tree.header": {"ja": "オブジェクト", "en": "Objects"},
    "scene_tree.camera": {"ja": "カメラ", "en": "camera"},
    "scene_tree.lens": {"ja": "レンズ (テレセントリック)", "en": "lens (telecentric)"},
    "scene_tree.lights": {"ja": "照明", "en": "lights"},
    "scene_tree.targets": {"ja": "ターゲット", "en": "targets"},
    "scene_tree.more_targets": {
        "ja": "... さらに {count} 個のターゲット (全体確認はPreview)",
        "en": "... and {count} more targets (use Preview for full scene)",
    },
    "scene_tree.rename": {"ja": "名前変更...", "en": "Rename..."},
    "scene_tree.delete": {"ja": "削除", "en": "Delete"},
    "scene_tree.rename_title": {"ja": "名前変更", "en": "Rename"},
    "scene_tree.rename_label": {"ja": "新しい名前:", "en": "New name:"},
    "scene_tree.rename_failed": {"ja": "名前変更に失敗", "en": "Rename failed"},
    "scene_tree.rename_failed_msg": {
        "ja": "同名オブジェクトが存在するか、名前が空です。",
        "en": "An object with that name already exists, or the name is empty.",
    },
    "scene_tree.delete_title": {"ja": "削除しますか？", "en": "Delete?"},
    "scene_tree.delete_msg": {"ja": "{kind} '{name}' を削除しますか？", "en": "Delete {kind} '{name}'?"},
    "scene_tree.delete_failed": {"ja": "削除に失敗", "en": "Delete failed"},
    "scene_tree.not_found": {"ja": "{kind} '{name}' が見つかりません", "en": "{kind} '{name}' was not found"},
    "prop.hint.select": {"ja": "シーン内のオブジェクトを選択してください", "en": "Select an object in the scene."},
    "prop.hint.not_found": {"ja": "{kind} '{name}' が見つかりません", "en": "{kind} '{name}' was not found."},
    "prop.title.format": {"ja": "{kind} · {name}", "en": "{kind} · {name}"},
    "prop.light_preset": {"ja": "照明プリセット", "en": "Light preset"},
    "prop.material_preset": {"ja": "材質プリセット", "en": "Material preset"},
    "prop.apply": {"ja": "適用", "en": "Apply"},
    "prop.role_placeholder": {"ja": "(ロールを選択)", "en": "(choose role preset)"},
    "prop.widget_default": {"ja": "ワーク標準", "en": "Widget default"},
    "prop.stage_default": {"ja": "ステージ標準", "en": "Stage default"},
    "prop.apply_from_list": {"ja": "一覧から適用", "en": "Apply (full list)"},
    "status.new_scene": {"ja": "新しいシーンを作成しました。", "en": "New scene created."},
    "status.live_on": {
        "ja": "ライブプレビュー ON - パラメータ変更で自動再レンダ (低spp/fallback)",
        "en": "Live preview ON - auto re-render on parameter changes (low spp/fallback)",
    },
    "status.live_off": {"ja": "ライブプレビュー OFF", "en": "Live preview OFF"},
    "dialog.close": {"ja": "閉じる", "en": "Close"},
    "dialog.cancel": {"ja": "キャンセル", "en": "Cancel"},
    "dialog.starting": {"ja": "開始中...", "en": "Starting..."},
    "dialog.cancelling": {"ja": "キャンセル中...", "en": "Cancelling..."},
    "mesh.title": {"ja": "メッシュをインポート", "en": "Import mesh"},
    "mesh.browse": {"ja": "参照...", "en": "Browse..."},
    "mesh.uniform_scale": {"ja": "一様スケール", "en": "Uniform scale"},
    "mesh.name_prefix": {"ja": "名前プレフィックス", "en": "Name prefix"},
    "mesh.name_prefix_placeholder": {
        "ja": "ターゲット名の接頭辞（任意）",
        "en": "Optional name prefix for targets",
    },
    "mesh.step_missing": {"ja": "STEP: cascadio 未導入 - pip install cascadio", "en": "STEP: cascadio missing - pip install cascadio"},
    "mesh.hint": {
        "ja": "OBJ/GLB/STEP の各パーツに材質を指定してインポートできます。",
        "en": "You can import OBJ/GLB/STEP parts and assign materials per part.",
    },
    "mesh.parts_label": {
        "ja": "パーツ一覧（チェックした行をインポート、材質を指定）:",
        "en": "Parts (check rows to import; set material per part):",
    },
    "mesh.header.import": {"ja": "取込", "en": "Import"},
    "mesh.header.part": {"ja": "パーツ / ボディ", "en": "Part / body"},
    "mesh.header.target": {"ja": "ターゲット名", "en": "Target name"},
    "mesh.header.material": {"ja": "材質プリセット", "en": "Material preset"},
    "mesh.quick_assign": {"ja": "チェック行に一括適用:", "en": "Quick assign checked:"},
    "mesh.quick.widget_aluminum": {"ja": "ワーク: 切削アルミ", "en": "Widget: machined aluminum"},
    "mesh.quick.widget_white": {"ja": "ワーク: 白塗装", "en": "Widget: painted white"},
    "mesh.quick.stage_white": {"ja": "ステージ: マット白", "en": "Stage: matte white"},
    "mesh.quick.stage_black": {"ja": "ステージ: 黒アルマイト", "en": "Stage: anodized black"},
    "mesh.quick.general_plastic": {"ja": "汎用: 白プラ", "en": "General: plastic white"},
    "mesh.quick.general_aluminum": {"ja": "汎用: ヘアラインアルミ", "en": "General: aluminum brushed"},
    "mesh.apply_checked": {"ja": "チェック行へ適用", "en": "Apply to checked"},
    "mesh.check_first": {"ja": "先頭 {count} 件をチェック", "en": "Check first {count}"},
    "mesh.uncheck_all": {"ja": "全解除", "en": "Uncheck all"},
    "mesh.loading_title": {"ja": "読込中", "en": "Loading"},
    "mesh.loading_wait": {"ja": "メッシュの読み込み完了までお待ちください。", "en": "Please wait until mesh loading completes."},
    "mesh.open_mesh": {"ja": "メッシュを開く", "en": "Open mesh"},
    "mesh.file_filter": {"ja": "メッシュ", "en": "Meshes"},
    "mesh.step_loading": {"ja": "STEP を読み込み中です。初回は数十秒かかることがあります。", "en": "Loading STEP. The first conversion may take tens of seconds."},
    "mesh.loading": {"ja": "メッシュを読み込み中...", "en": "Loading mesh..."},
    "mesh.step_failed": {"ja": "STEP 読込失敗", "en": "STEP load failed"},
    "mesh.load_failed": {"ja": "読込失敗", "en": "Load failed"},
    "mesh.many_parts_title": {"ja": "パーツ数が多いです", "en": "Many parts"},
    "mesh.many_parts_msg": {
        "ja": "このファイルには {count} 個のボディがあります。\n一度に全部インポートすると GUI / Preview が重くなるため、\n既定では先頭 {default_count} 件のみ選択しています。\n\n3D ビュー: インポートした各パーツを面表示（簡略メッシュ）。\nPreview (F5): 同一ファイル・同一配置のパーツはまとめてレンダします。",
        "en": "This file contains {count} bodies.\nImporting all of them at once can slow down GUI/Preview,\nso only the first {default_count} are selected by default.\n\n3D view: imported parts are shown as simplified surfaces.\nPreview (F5): parts with same file/placement are merged for rendering.",
    },
    "mesh.unit_scale_title": {"ja": "単位スケール", "en": "Unit scale"},
    "mesh.unit_scale_msg": {
        "ja": "モデルサイズから単位スケールを {scale:g}（m->mm 相当）に設定しました。\nプレビューが小さすぎる/見えない場合はこの値を調整してください。",
        "en": "Based on model size, unit scale was set to {scale:g} (roughly m->mm).\nIf preview is too small or invisible, adjust this value.",
    },
    "mesh.no_file_title": {"ja": "ファイル未選択", "en": "No file"},
    "mesh.no_file_msg": {"ja": "先にメッシュファイルを選択してください。", "en": "Select a mesh file first."},
    "mesh.no_parts_title": {"ja": "パーツ未選択", "en": "No parts"},
    "mesh.no_parts_msg": {"ja": "インポートするパーツを1件以上チェックしてください。", "en": "Check at least one part to import."},
    "mesh.import_many_title": {"ja": "多数パーツをインポートしますか？", "en": "Import many parts?"},
    "mesh.import_many_msg": {
        "ja": "{count} 件をインポートします。続行しますか？\n（多数の場合、処理時間が長くなります）",
        "en": "Import {count} parts. Continue?\n(This can take longer for many parts.)",
    },
    "calib.title": {"ja": "参照画像でキャリブレーション", "en": "Calibrate against reference image"},
    "calib.reference_image": {"ja": "参照画像", "en": "Reference image"},
    "calib.signal_roi": {"ja": "信号 ROI", "en": "Signal ROI"},
    "calib.dark_roi": {"ja": "暗部 ROI", "en": "Dark ROI"},
    "calib.roi_placeholder": {"ja": "x,y,w,h（空欄=全体）", "en": "x,y,w,h (empty = full image)"},
    "calib.dark_roi_placeholder": {"ja": "黒レベル推定用の暗部ROI（任意）", "en": "optional dark ROI for black level"},
    "calib.fit_scale": {"ja": "radiance_scale をフィット", "en": "Fit radiance_scale"},
    "calib.fit_black": {"ja": "black_level_dn をフィット（暗部ROI or LSTSQ）", "en": "Fit black_level_dn (dark ROI or LSTSQ offset)"},
    "calib.fit_qe": {"ja": "quantum_efficiency をフィット（平均一致）", "en": "Fit quantum_efficiency (mean match)"},
    "calib.use_lstsq": {"ja": "画素ごと LSTSQ を使用（scale + offset）", "en": "Use per-pixel LSTSQ (scale + offset)"},
    "calib.hint": {
        "ja": "ノイズなし fallback レンダ（preview scale 0.5）で評価します。信号ROIには均一領域（例: グレーカード）を置いてください。",
        "en": "Uses a noise-free fallback render (preview scale 0.5). Place a uniform region (e.g. grey card) in the signal ROI.",
    },
    "calib.run": {"ja": "キャリブ実行", "en": "Run calibration"},
    "calib.apply_scene": {"ja": "シーンへ適用", "en": "Apply to scene"},
    "calib.reference_missing_title": {"ja": "参照画像", "en": "Reference"},
    "calib.reference_missing_msg": {"ja": "参照画像を選択してください。", "en": "Select a reference image."},
    "calib.roi_error_title": {"ja": "ROI", "en": "ROI"},
    "calib.running": {"ja": "キャリブレーション中...", "en": "Calibrating..."},
    "calib.failed": {"ja": "キャリブ失敗", "en": "Calibration failed"},
    "calib.cancelled": {"ja": "キャンセルしました。", "en": "Cancelled."},
    "calib.applied_title": {"ja": "適用完了", "en": "Applied"},
    "calib.applied_msg": {
        "ja": "キャリブレーション結果をシーンへ反映しました。\nPreview または Render で確認してください。",
        "en": "Calibration values were written to the scene.\nRun Preview or Render to verify.",
    },
    "calib.report.before": {"ja": "--- 調整前 ---", "en": "--- Before ---"},
    "calib.report.after": {"ja": "--- 調整後 ---", "en": "--- After ---"},
    "calib.report.fit": {"ja": "--- フィット結果 ---", "en": "--- Fit ---"},
    "calib.report.note": {"ja": "  備考: {note}", "en": "  note: {note}"},
    "calib.report.apply_hint": {"ja": "「シーンへ適用」を押すと推定値をプロジェクトへ反映します。", "en": "Click 'Apply to scene' to write fitted values into the project."},
    "sweep.title": {"ja": "パラメータスイープ", "en": "Parameter sweep"},
    "sweep.preset": {"ja": "パラメータプリセット", "en": "Parameter preset"},
    "sweep.custom": {"ja": "(カスタム)", "en": "(custom)"},
    "sweep.param_path": {"ja": "パラメータ（ドット区切り）", "en": "Parameter (dotted path)"},
    "sweep.values": {"ja": "値（カンマ区切り）", "en": "Values (comma separated)"},
    "sweep.spp": {"ja": "サンプル/ピクセル", "en": "Samples / pixel"},
    "sweep.preview_scale": {"ja": "プレビュー縮尺", "en": "Preview scale"},
    "sweep.preview_scale_tip": {"ja": "fallback プレビュー解像度倍率（1.0=センサー等倍）", "en": "Fallback preview resolution scale (1.0 = full sensor)."},
    "sweep.use_fallback": {"ja": "fallback レイキャスタを使用（高速）", "en": "Use fallback raycaster (fast)"},
    "sweep.add_compare": {"ja": "結果を Comparison タブに追加", "en": "Add results to Comparison tab"},
    "sweep.hint": {"ja": "結果は下表に表示され、必要に応じて Comparison タブへスナップショット追加されます。", "en": "Results appear in the table below and optionally in the Comparison tab as labelled snapshots."},
    "sweep.run": {"ja": "スイープ実行", "en": "Run sweep"},
    "sweep.busy_title": {"ja": "実行中", "en": "Busy"},
    "sweep.busy_msg": {"ja": "スイープは既に実行中です。", "en": "Sweep is already running."},
    "sweep.param_title": {"ja": "パラメータ", "en": "Parameter"},
    "sweep.param_msg": {"ja": "ドット区切りのパラメータパスを入力してください。", "en": "Enter a dotted parameter path."},
    "sweep.values_title": {"ja": "値", "en": "Values"},
    "sweep.no_values": {"ja": "値が入力されていません。", "en": "No values provided."},
    "sweep.progress_title": {"ja": "パラメータスイープ", "en": "Parameter sweep"},
    "sweep.complete_title": {"ja": "スイープ完了", "en": "Sweep complete"},
    "sweep.complete_msg": {"ja": "{done} / {total} レンダリング完了。", "en": "Finished {done} / {total} renders."},
    "sweep.failed": {"ja": "スイープ失敗", "en": "Sweep failed"},
    "sweep.cancelled_title": {"ja": "キャンセル", "en": "Cancelled"},
    "sweep.cancelled_msg": {"ja": "スイープをキャンセルしました。", "en": "Sweep was cancelled."},
    "env.title": {"ja": "環境チェック", "en": "Environment check"},
    "env.running": {"ja": "診断を実行中...", "en": "Running diagnostics..."},
    "render.progress.title": {"ja": "レンダリング", "en": "Rendering"},
    "mesh.refreshing_3d": {"ja": "3Dビューを更新しています...", "en": "Updating 3D view..."},
    "mesh.rendering_locked": {"ja": "レンダリング中はメッシュをインポートできません。完了後に再度お試しください。", "en": "Mesh import is unavailable while rendering. Please try again after it finishes."},
    "mesh.rendering_title": {"ja": "レンダリング中", "en": "Rendering"},
}


class LanguageManager(QObject):
    """Holds the current language and broadcasts updates to widgets."""

    languageChanged = pyqtSignal(str)

    def __init__(self, default: LanguageCode = "ja") -> None:
        super().__init__()
        self._lang: LanguageCode = default

    @property
    def code(self) -> LanguageCode:
        return self._lang

    def set_language(self, language: LanguageCode) -> None:
        if language == self._lang:
            return
        self._lang = language
        self.languageChanged.emit(language)

    def text(self, key: str, **kwargs: object) -> str:
        entry = _TEXTS.get(key)
        if entry is None:
            return key.format(**kwargs) if kwargs else key
        raw = entry.get(self._lang, entry.get("en", key))
        return raw.format(**kwargs) if kwargs else raw
