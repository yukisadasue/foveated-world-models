# データセット処理

本プロジェクトのRoboMIND FR3 dual用実装。公式LaWAMからの取り込みコードではない。旧画像ペアアダプターは削除済み。

| ファイル | 役割 |
|---|---|
| `download_robomind.py` | リビジョンを固定し俯瞰映像・状態・メタデータだけを取得 |
| `verify_robomind.py` | ファイルサイズ・動画ヘッダー・状態値・timestampの検証 |
| `prepare_robomind.py` | 動画の全フレーム検査、状態との時刻対応、欠損処理、有効区間とsplitの生成 |
| `temporal_data.py` | timestamp最近傍選択と短い欠損の直前値補完 |
| `robomind.py` | 時刻ペアの構築、動画デコード、公式collatorへの接続 |

## 実行

リポジトリルートから：

```sh
uv run --locked python vendor/dataset/download_robomind.py
uv run --locked python vendor/dataset/verify_robomind.py
uv run --locked python -m vendor.dataset.prepare_robomind --workers 6
uv run --locked python train_stage1.py --config configs/stage1_robomind.yaml
```

既定の取得先は `/data2/yuki_sadasue/datasets/RoboMIND-lerobot/`。前処理はその `preprocessed/` に区間ごとのNPZとtrain/validation/testのJSONLを作る。監査結果は `summary.json`、`audit.json`。動画インデックスはパス・サイズ・更新時刻が一致すると再利用する。デコードエラーでは処理を失敗させる。

## 時間と欠損

配布timestampを信用し、収録時刻であることは要求しない。フレーム番号の固定幅加算やFPSからのフレーム数計算は禁止。ローダーは採用したtに対してt+1.2秒の最近傍を順に選ぶ。同距離なら前側、末尾は短くても最終観測。ペア抽出の誤差上限は既定で設けず、12Hzや29.97Hzなど1.2秒にフレームが一致しない場合も最近傍を選ぶ。必要な場合だけ `tolerance_seconds` を秒単位で設定できる。前処理の動画・状態同期許容20msとは別の設定。

前処理はエピソードの動画開始時刻＋状態timestampを動画PTSと対応付ける（許容20ms）。対応しない動画時刻も時間列に含め、欠落した状態行を検出する。状態は左右のxyz・姿勢・グリッパー、画像は非破損かつほぼ真っ黒でないことを確認する。姿勢・位置は腕ごとにまとめて有効判定し、異なる時刻の成分を混ぜない。

欠損期間が0.3秒以上、または時刻列自体に0.3秒以上の空白があれば区間を分割する。短い内部欠損は成分ごと（姿勢・位置は腕ごと）に直前値で補完する。区間両端は全項目の実観測がそろう時点まで切り詰める。元の有効マスクと補完元からの経過秒を保存する。配布時点での補間・重複は、値とtimestampだけでは完全には検出できない。

## 状態と画像

左右それぞれxyz[m]＋姿勢rot6d[回転行列の先頭2列]＋グリッパー値[配布値0..1]、合計20次元。配布メタデータのroll/pitch/yawとしてRz(yaw)Ry(pitch)Rx(roll)を使用する。姿勢の±π境界で補助差分が跳ばないようrot6dに変換する。各腕の元座標系を保持し、左右が共通world座標であるとは仮定しない。校正精度やEuler規約の原収録コードとの照合は別途必要。

`observation.states.*` を使い、`actions.*` は使わない。ロボットembodiment IDは1。20次元を超えるモデル側領域は公式collatorでpaddingし、20未満ならエラー。グリッパーの0/1の開閉向きは変換せず保存する。

俯瞰画像は手先が左右端にあるため中心cropをせず、縦横比を保持して256×256に黒帯で埋める。その後の学習時augmentationは公式実装の設定に従う。

## 分割と評価

元の収録IDは変換版にないため、俯瞰動画シャードをgroupとし、各groupの最多タスクで層化してSHA256順に並べ、おおむね80/10/10でtrain/validation/testへ分割する。3group以上あるタスク層は評価各splitに最低1groupを割り当て、3未満はtrainのみとする。同一エピソードと同一動画シャードのsplit越境を拒否する。ただし別シャードにまたがる同一収録を識別できる保証はない。タスクごとの分布は学習前に監査する。

validation/testは補完された端点を除く。短い末尾ペアも保持し、`dt`、`is_tail`、元の有効マスク、補完経過秒をバッチに含める。正式評価では通常ペアと末尾ペアを分けて集計すること。現在の公式Trainerのval_lossは両者をまとめた接続検査用で、独立したStage 1ベンチマーク評価器はまだない。

## 検証済み結果（2026-11-12）

俯瞰動画68本・375,807フレームを全デコードし、今回の検査基準では映像・状態の欠損なし、補完0件。全splitに6タスクを含む。

| split | エピソード | ペア | うち短い末尾 |
|---|---:|---:|---:|
| train | 1444 | 9201 | 1407 |
| validation | 160 | 950 | 155 |
| test | 170 | 1081 | 165 |

単体テスト14件成功。各splitから8ペアずつの実動画ロード、実DINO＋小型IDM/LaWMの2 step学習、保存・3 step目への再開に成功。これは接続検査であり、本構成の学習収束・予測精度を示すものではない。取得先 `preprocessed/loader_verification.json` に結果を保存。
