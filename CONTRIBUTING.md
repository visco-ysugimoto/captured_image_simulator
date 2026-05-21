# Contributing

リポジトリ: https://github.com/visco-ysugimoto/captured_image_simulator

## 開発環境（ローカル）

```powershell
# Python 3.12 推奨
.\rebuild_py312.ps1

# または手動
.\.venv312\Scripts\python.exe -m pip install -U pip
.\.venv312\Scripts\python.exe -m pip install -e ".[all,dev]"

# 動作確認
.\.venv312\Scripts\python.exe -m pytest -q
.\.venv312\Scripts\python.exe -m ruff check src tests
.\.venv312\Scripts\python.exe -m optsim doctor
```

CI（GitHub Actions）では `pip install -e ".[dev,step]"` のみ（`pytest-qt` / PyQt6 は含めない。ウィジェットテストは未整備のため）。ローカルで GUI テストを書く場合は `pip install -e ".[all,dev,gui]"` を使ってください。

GUI 起動:

```powershell
.\.venv312\Scripts\python.exe -m optsim.gui
```

## ブランチ運用

| 種別 | 命名例 |
|------|--------|
| 機能 | `feat/short-description` |
| 修正 | `fix/short-description` |
| 雑務 | `chore/short-description` |

`main` への直接 push は行わず、Pull Request 経由でマージしてください。

## 標準フロー

1. Issue を作成（`.github/ISSUE_TEMPLATE/`）
2. `main` から作業ブランチを切る
3. 実装 + テスト + 必要なら README 更新
4. `pytest -q` と `ruff check src tests` をローカルで実行
5. PR 作成（`.github/pull_request_template.md`）
6. CI 通過後にマージ

## 並列エージェント運用のコツ

1つの Issue を複数エージェントで同時に触るとコンフリクトしやすいです。次のように分割してください。

| エージェント | 担当例 |
|-------------|--------|
| 実装 | `src/optsim/render/`, `src/optsim/gui/` の機能追加 |
| テスト | `tests/test_*.py` の追加・回帰 |
| ドキュメント | `README.md`, `CONTRIBUTING.md` |
| CI調査 | `.github/workflows/` の失敗ログ分析 |

**依存の少ないタスクを並列化**し、マージ前に 1 本の PR にまとめるか、小さな PR を順次マージします。

## コミットメッセージ

- 1 行目: 何をしたか（英語または日本語）
- 2 行目以降（任意）: なぜその変更が必要か

例:

```
Fix Mitsuba front-light emission for ring facets.

Align flip_normals and null BSDF with the fallback raycaster convention.
```

## レビュー観点

- Preview (fallback) と Render (Mitsuba) の差分が意図どおりか
- 照明・材質・キャリブレーションの回帰がないか
- 大きなメッシュ import で UI が固まらないか
