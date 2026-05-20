# Optical Simulator (optsim)

マシンビジョン検査向けの光学シミュレータです。テレセントリックレンズ・任意形状のワーク・任意の照明配置を 3D 空間に置き、センサーに映る画像を物理ベースレンダリングで予測します。撮像画像のコントラストや SN 比など、検査適合性の定量評価まで一気通貫で行えます。

## 主な機能

- カメラ / レンズ / 照明 / ワークを任意座標に配置（pydantic ベースのシーン記述）
- テレセントリック投影（物体側テレセントリック、平行投影 + 開口モデル）
- 物理ベースレンダリング（[Mitsuba 3](https://www.mitsuba-renderer.org/)）
- センサー応答モデル（量子効率・露光・ダーク/ショットノイズ・ビット深度量子化）
- 検査評価関数（コントラスト、SN 比、ヒストグラム、エッジプロファイル、ROI 統計）
- パラメータスイープ（照明角度・露光・NA などを振ってバッチ撮影）
- PyQt6 + PyVista による 3D シーンエディタ / 結果ビューア
- プロジェクトファイル（YAML / JSON）保存・読み込み
- BRDF・照明プリセット同梱

## アーキテクチャ

```
GUI (PyQt6 + PyVista)
    -> Domain (pydantic)
        -> Render Translator
            -> Mitsuba 3 (Telecentric Sensor)
                -> Sensor Response Model
                    -> Result Viewer / Analysis (NumPy / OpenCV)
```

詳細は `.cursor/plans/` 内の設計ドキュメントを参照してください。

## インストール

### 1. Python 環境を準備（推奨: 3.12）

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

`py` ランチャーが無い環境では、`python3.12` の実体パスを直接使ってください。

```powershell
$py312 = "$env:LocalAppData\Programs\Python\Python312\python.exe"
& $py312 -m venv .venv312
.\.venv312\Scripts\Activate.ps1
python -m pip install -U pip
```

ワンコマンドで再構築する場合:

```powershell
.\rebuild_py312.ps1
```

### 2. 開発インストール

```powershell
# GUI とレンダラを含むフル構成
pip install -e .[all,dev]

# CLI のみ（レンダリングはモック）
pip install -e .

# レンダラのみ追加
pip install -e .[render]
```

Mitsuba 3 は Windows のホイールを公式配布しているので `pip install mitsuba` で導入できます。GPU バックエンド (`cuda_*`) を使う場合は NVIDIA RTX GPU と最新ドライバが必要です。

#### Windows でのインストール時の注意

1. **`Successfully installed optsim-0.1.0` で完了します**。最後に出る `WARNING: The scripts optsim-gui.exe and optsim.exe are installed in '...\\Python313\\Scripts' which is not on PATH.` は **エラーではなく PATH 設定の警告**です。次のいずれかで対応できます：

   - 警告に表示されるパスを環境変数 `PATH` に追加する
   - `python -m optsim.cli ...` と `python -m optsim.gui` を使う（Path 設定なしで直接呼べる）

2. **`rtree` パッケージは fallback レイキャスタの依存に必要**です。本プロジェクトの依存に含まれていますが、すでに trimesh 等が入っていた環境では明示的に `pip install rtree` が必要なことがあります。

3. **Mitsuba 3.8 は `LLVM-C.dll` を要求します**（dr.jit が path tracer 内で LLVM JIT を呼ぶため）。LLVM が見つからない場合は自動的に内蔵 raycaster にフォールバックします。Mitsuba を本番利用するには：

   - [LLVM Project Releases](https://github.com/llvm/llvm-project/releases) から Windows 用 LLVM をインストール
   - インストール先 (`C:\\Program Files\\LLVM\\bin` 等) を `PATH` に追加するか、`DRJIT_LIBLLVM_PATH` 環境変数で指定
   - NVIDIA GPU があれば `--variant cuda_rgb` で LLVM を回避できます

4. **GPU 未搭載PCでは `llvm_ad_rgb` が不安定なケースがあります**。本プロジェクトでは render 時に variant を順次リトライし、失敗時は `scalar_rgb` に自動降格します（Mitsuba 経由のCPUレンダは継続）。

## 各素子のパラメータと実物との対応

プロパティパネル（シーン内オブジェクト選択）または YAML で編集できます。  
**絶対 DN（輝度値）を実機と合わせる**ときは、下表の「キャリブ必須」項目を優先してください。

### カメラ / センサー (`camera.sensor`)

| パラメータ | 物理的意味 | 実物での決め方 | キャリブ |
|------------|------------|----------------|--------|
| `width_px`, `height_px` | 解像度 | カメラ仕様 | 仕様値 |
| `pixel_pitch_um` | ピクセルサイズ | カタログ | 仕様値 |
| `bit_depth` | ADC ビット数 | 8 / 10 / 12 bit 等 | 仕様値 |
| `exposure_time_ms` | 露光時間 | 撮像条件 | **必須** |
| `gain_db` | アナログ/デジタルゲイン | カメラ設定 | **必須** |
| `quantum_efficiency` | 量子効率（単色近似） | データシートまたは λ 依存表 | **推奨** |
| `full_well_e` | フルウェル [e⁻] | データシート | 推奨 |
| `read_noise_e` | 読出ノイズ [e⁻] | ダーク＋短露光のσ | **推奨** |
| `dark_current_e_per_s` | 暗電流 | 高温長露光 | 任意 |
| `black_level_dn` | 黒レベル [DN] | レンズキャップ撮影の平均 | **推奨** |
| `monochrome` | モノクロ統合 | カメラ種別 | 仕様値 |

### レンズ (`lens`) — テレセントリック

| パラメータ | 物理的意味 | 実物での決め方 | キャリブ |
|------------|------------|----------------|--------|
| `magnification` | 物体側倍率 | レンズ仕様（>0 必須） | 仕様値 |
| `working_distance_mm` | 作動距離 | レンズ仕様 | 仕様値 |
| `na` / `f_number` | 開口（DoF・ボケ） | 仕様 or 絞り | 推奨 |
| `distortion_pct` | 歪曲 | データシート | ※レンダ未使用 |

### 照明 (`lights[]`)

| パラメータ | 物理的意味 | 実物での決め方 | キャリブ |
|------------|------------|----------------|--------|
| `transform` | 位置・向き [mm, deg] | 治具・CAD | 必須（幾何） |
| `intensity` | 相対輝度（無次元） | 調光→**相対比較** | `radiance_scale` と併用 |
| `color` | RGB 比率 | LED 色・フィルタ | 任意 |
| `directional_exponent` | 指向性 cosⁿ | 拡散/集光 | 近似 |
| 形状 (`width_mm`, `ring` 半径等) | 発光面サイズ | 実機寸法 | 必須（幾何） |
| `tilt_deg` (ring) | リング傾き | 機種依存 | 推奨 |

※ `intensity` は絶対 [W/sr/m²] ではなく、**`radiance_scale` で実 DN にスケール**します。

### ワーク / 材質 (`targets[].material`)

| パラメータ | 物理的意味 | 実物での決め方 | キャリブ |
|------------|------------|----------------|--------|
| `kind` | BRDF モデル種別 | 金属/樹脂/拡散等 | プリセットから選択 |
| `base_color` | 線形 RGB 反射率 | グレーカード・分光 | **推奨** |
| `roughness` | 表面粗さ | 見た目合わせ | **推奨** |
| `ior`, `metallic` | 誘電体/金属 | 材質 | 推奨 |
| `anisotropy*` | 異方性（ブラシ目） | 加工方向 | 金属向け |
| `normal_map_path` | 微細凹凸 | テクスチャ | ※未接続 |

### シーン全体 (`scene`)

| パラメータ | 物理的意味 | 実物での決め方 | キャリブ |
|------------|------------|----------------|--------|
| `radiance_scale` | レンダ輝度→電子数の倍率 | 既知試料で平均 DN 一致 | **必須（絶対合わせ）** |
| `background_color` | 背景輝度 | 暗視野/明視野 | 任意 |

### フェーズ3: 実画像キャリブレーション（実装済み）

実機で撮った参照画像に対し、シミュレーション DN を自動で合わせます。

**GUI**

1. 実機と同じ露光・ゲイン・解像度をプロパティで設定  
2. **Analysis → Calibrate from reference image...**  
3. 参照画像（PNG/TIFF）と **Signal ROI**（均一なグレー領域の `x,y,w,h`）を指定  
4. **Run calibration** → Before/After の RMSE・相関・平均 DN を確認  
5. **Apply to scene** で `radiance_scale` 等をプロジェクトに反映  

**CLI**

```powershell
optsim calibrate examples/sample_scene.yaml -r measured.png --roi 400,300,200,200 --apply
optsim calibrate scene.yaml -r dark.png --dark-roi 10,10,50,50 --fit-black --apply
```

| オプション | 内容 |
|------------|------|
| `--fit-scale` / `--no-fit-scale` | `radiance_scale` を平均 DN 一致で推定（既定 ON） |
| `--fit-black` | `black_level_dn`（要 `--dark-roi` または `--lstsq`） |
| `--fit-qe` | `quantum_efficiency` を平均で補正 |
| `--lstsq` | ROI 内で scale+offset の最小二乗 |
| `--apply` | 推定値を YAML に書き戻し |

キャリブレーション中は **センサノイズ OFF**・**fallback・preview scale 0.5** で決定論的にフィットします。最終確認は **Render (F6)** を推奨します。

**手動での合わせ方（スイープ）**

1. 実機と同じ `exposure_time_ms`, `gain_db` を設定  
2. 参照試料を撮影し、**Parameter sweep** で `radiance_scale` を振る  
3. 必要なら `black_level_dn`・`quantum_efficiency` を追加調整  

相対比較のみなら **幾何 + 材質 + 相対 intensity** だけでも十分なことが多いです。

### 表面材質プリセット（widget / stage）

| カテゴリ | プリセット例 | 用途 |
|----------|--------------|------|
| **Widget** | `widget_aluminum_machined`, `widget_painted_white`, … | ワーク（加工品） |
| **Stage** | `stage_matte_white`, `stage_anodized_black`, … | ステージ・治具面 |
| **General** | `plastic_white`, `aluminum_brushed`, … | 汎用 |

- 新規シーンの **widget** / **stage** にはロール別デフォルト材質が自動適用されます。
- ターゲット選択後、プロパティの **Material preset** で「Widget — …」「Stage — …」を選んで適用できます。
- **Widget default** / **Stage default** ボタンでロール標準材質に一発復帰できます。

### 外部メッシュの読込（パーツ別材質）

**Add → Import mesh (multi-part)...**

1. STL / OBJ / PLY / GLB / STEP を選択（STEP は下記の追加パッケージが必要）  
2. ファイル内の **パーツ一覧** が表示されます（OBJ のグループ、GLB のノードなど）  
3. インポートする行にチェックし、**Target name** と **Material preset** を指定  
4. OK で各パーツが独立した `target` になり、**パーツごとに材質を変更**できます  

インポート後はシーンアウトラインに `part_name [body]` のように表示されます。  
単一の結合メッシュとして読み込む場合は **Mesh target (single merged)...** を使います。

#### STEP ファイルの読み込み

STEP は標準インストールには含まれません。次のいずれかを導入してください。

```powershell
pip install cascadio
# またはフル構成:
pip install -e ".[all]"
```

インストール確認: `optsim doctor` の `STEP import` 行、または GUI インポート画面の `STEP backend: cascadio` 表示。

`cascadio` が無い場合は CAD から **STL/OBJ** にエクスポートして読み込んでください。

## Preview と Full render の違い

| 操作 | エンジン | 典型時間 | 用途 |
|------|----------|----------|------|
| **Preview (F5)** | fallback（簡易レイキャスタ） | 数秒 | レイアウト・照明の確認 |
| **Live preview** | fallback（低解像度） | 約1秒 | パラメータ調整中の自動更新 |
| **Render (F6)** | Mitsuba 3（失敗時 fallback） | 数十秒〜 | 物理ベースの本番評価 |

- Preview / Live は **コントラストの傾向**や**エッジの見え方**の確認向けです。BRDF・ノイズは近似です。
- **定量比較（SNR・コントラストの絶対値）**や**最終レポート**には F6（Mitsuba）を使ってください。
- Mitsuba が動かない場合は **Help → Environment check...**（または `optsim doctor`）で variant の成否を確認してください。

## 使い方

### CLI

```powershell
# サンプルシーンをレンダリング
optsim render examples/sample_scene.yaml -o out.png

# パラメータスイープ
optsim sweep examples/sample_scene.yaml --param lights.0.intensity --values 100,500,1000 -o sweep/

# 評価指標を計算
optsim analyze out.png --roi 100,100,200,200
```

### GUI

```powershell
python -m optsim.gui
```

1. **Scene** タブ: 3D ビューで配置を確認  
2. **Preview (F5)** / **Render (F6)**: 処理中は進捗ダイアログが表示され、シーン編集や再レンダは無効になります（キャンセル可）  
3. **Add → Import mesh...**: STEP が **m 単位** のとき **Uniform scale=1000** を自動設定。3D ビューは **インポートした各パーツを面表示**（簡略メッシュ、既定 50 件）。多数パーツは **先頭 50 件のみ既定選択**。**Preview (F5)** は同一配置のパーツを **1 回のレイキャストに統合** します  
4. **Analysis → Parameter sweep...**: パラメータを振って表形式でメトリクス表示。  
   「Comparison タブに追加」で各条件のサムネイルを横並び比較できます。  
5. **Help → Environment check...**: Mitsuba / fallback の動作確認

プロパティパネルで値を編集 → Live preview を ON にすると変更のたびに低解像度プレビューが更新されます。

### Python API

```python
from optsim.domain import Scene, Camera, TelecentricLens, RingLight, Target
from optsim.render import Renderer

scene = Scene(
    camera=Camera(position=(0, 0, 100), look_at=(0, 0, 0)),
    lens=TelecentricLens(magnification=0.5, working_distance=80, na=0.05),
    lights=[RingLight(position=(0, 0, 50), inner_radius=20, outer_radius=30, intensity=1000)],
    targets=[Target.from_stl("examples/widget.stl", material="brushed_aluminum")],
)

img = Renderer(spp=128).render(scene)
img.save("result.png")
```

## 配布

PyInstaller で Windows 向け実行ファイルを作成できます。

```powershell
pip install -e .[package]
pyinstaller packaging/optsim.spec
```

`dist/optsim/` に exe と必要な DLL が生成されます。

## ライセンス

MIT License
