# Agent guide (Cursor / parallel agents)

このファイルは AI エージェント向けの作業指針です。人間向けの詳細は `CONTRIBUTING.md` と `README.md` を参照してください。

## リポジトリ

- URL: https://github.com/visco-ysugimoto/captured_image_simulator
- デフォルトブランチ: `main`
- CI: `.github/workflows/ci.yml`（`ruff` + `pytest`）

## 作業前チェック

1. 仮想環境: `.venv312` または `.venv`
2. `pytest -q` が通ること
3. 変更範囲を Issue / ユーザー指示に限定（無関係なリファクタ禁止）

## 重要なコード領域

| 領域 | パス | 注意 |
|------|------|------|
| Mitsuba 翻訳 | `src/optsim/render/translator.py` | 照明の `flip_normals`, `null` BSDF, 材質 BSDF |
| レンダラ | `src/optsim/render/renderer.py` | fallback vs Mitsuba, variant フォールバック |
| GUI | `src/optsim/gui/` | PyQt6, i18n (`i18n.py`) |
| プリセット | `src/optsim/presets/` | 照明・材質の既定値 |

## Preview vs Render

- **Preview (F5)**: `renderer._render_fallback` — 近似、高速
- **Render (F6)**: Mitsuba — 物理ベース、`scalar_rgb` 等

両者の見え方が違う場合、まず `translator.py` のエミッター向きと BSDF を疑うこと。

## 並列タスクの分け方（推奨）

```
Issue #N
├── Agent A: feat/render-lighting-fix   (translator + tests)
├── Agent B: feat/gui-preset-ux         (property_panel only)
└── Agent C: docs/readme-calibration    (README only)
```

同一ファイルを複数エージェントで編集しない。

## 完了条件（DoD）

- [ ] `pytest -q` 成功
- [ ] `ruff check src tests` 成功（CI と同様）
- [ ] ユーザー向け変更なら README または CONTRIBUTING を更新
- [ ] PR テンプレートの Test plan を埋める

## コミット

ユーザーが明示的に依頼したときのみ `git commit` / `git push` する。
