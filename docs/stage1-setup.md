# Stage 1の最小実行構成

公式LaWAMのコミット `c12168d9077edea67fe7c1b70d08b80b8e65a9c8` から、モデル・学習処理・画像前処理・バッチ化・設定の12ファイル（約210 KB）を取得した。`vendor/lawam/UPSTREAM.json` に取得元と各ファイルのSHA-256を記録している。公式コード本体は変更していない。

`train_stage1.py` と `vendor/dataset/` は本リポジトリ側の追加実装。RoboMIND `franka_fr3_dual` の俯瞰動画と状態を前処理し、timestampに基づくペアを公式学習モジュールへ渡す。旧画像ペアJSONLアダプターは削除した。

## 重みと環境

使用する重みは **DINOv3 ViT-B/16**。

```text
/data2/yuki_sadasue/models/dinov3-vitb16-pretrain-lvd1689m/
```

設定で特徴次元768、12層、patch size 16、register token 4個を検査する。旧ViT-L/16はViT-B/16の読み込み確認後に削除済み。VLM、Action Expert、学習済みLaWM重みは取得していない。起動コードはHugging Faceのオフライン動作を強制し、W&Bへの送信も無効化する。

環境はuvで構築する。Python 3.12、torch 2.11.0+cu130／torchvision 0.26.0+cu130と依存関係を `pyproject.toml`・`uv.lock` に固定した。CUDA版PyTorchは明示的なPyTorch cu130インデックスから取得する。システム環境のパッケージは継承しない。

```sh
cd /home/yuki_sadasue/foveated-world-models
export UV_CACHE_DIR=/data2/yuki_sadasue/.cache/uv
export UV_LINK_MODE=copy
uv sync --locked
uv run --locked python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'
```

`.python-version` でPython 3.12を指定している。初回の環境構築にはネットワークが必要だが、学習はローカルDINOを使ってオフラインで実行する。今回の実機はRTX 6000 Ada 48GB。`uv.lock` を更新せず再現する場合は `--locked` を付ける。旧 `requirements-stage1.txt` は依存定義の重複を避けるため廃止した。

## 基準設定

`configs/stage1_official.yaml` は公開 `dino_large_vae.yaml` のモデル・損失設定を基準とする。`large` はここではLAM側の構成名で、視覚バックボーンはViT-B/16。実行規模は1 GPU、batch 2、1,000 stepに縮小した。これは全データでの論文再現ではない。

| 項目 | この公開コード準拠設定 | 論文v2の記述 |
|---|---|---|
| 視覚バックボーン | 凍結DINOv3 ViT-B/16 | 同左 |
| IDM／LaWMの層数 | 24／12 | 24／24 |
| 未来特徴の損失 | Smooth L1（beta=0.1） | MSE |
| 潜在行動KL重み | 5e-5（コードの既定値を明示） | 1e-5 |
| ロボットの時間幅 | 1.6秒 | 1.2秒 |
| 補助状態予測 | 状態差分に対するL2 | 未来手先状態として記述 |

出典：[公開設定](https://github.com/RLinf/LaWAM/blob/c12168d9077edea67fe7c1b70d08b80b8e65a9c8/latent_action_model/config/dino_large_vae.yaml)、[論文 Appendix E](https://arxiv.org/html/2606.15768v2#A5)。論文準拠への変更は基準と分けて管理する。公式validationはVAEの推論経路を使い、訓練時のKL項を含まないため、train lossとval lossを同一の量として比較しない。

## RoboMINDのデータ処理

データセット処理は [vendor/dataset/README.md](../vendor/dataset/README.md) を参照。配布timestampを信用し、採用時刻tからt+1.2秒の最近傍を選ぶ。固定フレーム幅は使わない。末尾は1.2秒未満でも最終観測とペアにする。RoboMIND用設定は公開モデル設定を継承し、データ時間幅を1.2秒に上書きする。

## 前処理と学習・検証の分離

```sh
uv run --locked python -m vendor.dataset.prepare_robomind
uv run --locked python train_stage1.py --config configs/stage1_robomind.yaml --check-data
```

取得・前処理は完了済み。再実行時は同じ動画のデコードインデックスを再利用する。`--check-data` は学習・validationの全ペアを実際にデコードするため時間がかかる。モデルはロードしない。

trainは1,444エピソード・9,201ペア、validationは160エピソード・950ペア。testの170エピソード・1,081ペアは学習・validationに使わない。同じエピソードと俯瞰動画シャードはsplitをまたがない。起動時にtrain/validationの重複を拒否し、実行先の `split_verification.json` に件数・manifestのSHA-256を保存する。

## 本サイズモデルのテスト学習

IDM 24層／LaWM 12層、batch 2、bf16、1 GPUで100 step。DINOは凍結し、IDM・LaWM・補助状態予測器を学習する。25 stepごとにvalidationの先頭10 batch（20ペア）を検査する。これは動作・メモリ確認であり、validation全体での性能評価ではない。公開モデル設定のwarmup 10,000 stepを保持するため、この実行はwarmup中に終了する。

```sh
CUDA_VISIBLE_DEVICES=0 uv run --locked python train_stage1.py \
  --config configs/stage1_robomind_pilot.yaml \
  --output /data2/yuki_sadasue/runs/foveated-world-models/stage1-robomind-pilot-20261112
```

再試行で過去の結果を混ぜないよう、`--output` は新しいディレクトリ名に変更する。`run_summary.json` に最終step・損失・学習対象のパラメータ数・実行時間・CUDAピークメモリを記録する。実行時間にはvalidationと途中のチェックポイント保存が含まれる。CSVは `metrics/version_*/metrics.csv`、チェックポイントは `checkpoints/`。

## 本学習（ユーザー実行）

```sh
CUDA_VISIBLE_DEVICES=0 uv run --locked python train_stage1.py \
  --config configs/stage1_robomind.yaml \
  --output /data2/yuki_sadasue/runs/foveated-world-models/stage1-robomind-main
```

本学習は自動では開始しない。`stage1_robomind.yaml` で学習期間に合わせた `trainer.max_steps` と `model.warmup_steps` を設定してから実行する。現在の継承値はそれぞれ1,000／10,000で、短時間実行用のまま。1,000 stepでwarmupを終えたい場合や長期学習する場合は変更が必要。通常設定ではvalidation全950ペアを評価する。末尾の短いペアも含むため、正式な予測精度比較では時間幅別に集計する。

`--vision-model` でローカル重みパスを変更できる。再開は同じ設定・データに次を追加する。

```sh
--resume /data2/yuki_sadasue/runs/foveated-world-models/stage1-robomind-main/checkpoints/last.ckpt
```

再開時の `trainer.max_steps` は保存済みstepより大きくする。テスト学習の出力先と本学習の出力先を分ける。

## 検証

```sh
uv run --locked python -m pytest -q tests
uv run --locked python tests/smoke_robomind.py
```

後者は実データの各splitからペアをサンプルしてロードし、ローカルDINOと小型IDM・LaWMで2 stepの学習、チェックポイント保存、3 step目への再開を検査する。チェックポイントは一時ディレクトリに置いて終了時に削除する。`configs/stage1_smoke.yaml` は接続検査専用で、基準モデルの精度や学習収束を示すものではない。

以前の公開設定IDM 24層／LaWM 12層の合成1ペア検査ではforward/backward、DINOの凍結、IDM・LaWM・補助状態予測器の有限かつ非ゼロの勾配を確認した。CUDAピーク割当量は約6.0 GBだったが、optimizer状態や継続学習の必要メモリを示す値ではない。

RoboMIND接続検査（2026-11-12）：単体テスト14件と実データを使った小型構成の学習・保存・再開が成功。全動画のデコード検査とsplit別ペア数は [データセット処理](../vendor/dataset/README.md#検証済み結果2026-11-12) を参照。

## 本サイズのテスト学習結果（2026-11-12）

uvで新規構築した独立環境で、上記pilotコマンドが正常終了した。本学習は未実行。

| 項目 | 結果 |
|---|---:|
| optimizer step | 100 |
| 最終train_loss | 0.91205 |
| validation loss（25 → 50 → 75 → 100 step） | 1.04546 → 1.03104 → 0.98904 → 0.89474 |
| fit時間（検証・途中保存込み、最後のfinal保存を除く） | 179.5秒 |
| CUDAピーク割当／予約 | 12.29／12.79 GiB |

IDM 309,432,352、LaWM 228,286,720、補助状態予測器102,893,568パラメータが学習対象。DINO 85,660,416パラメータは全て凍結。全記録メトリクスが有限値で、保存した `final.ckpt` が100 stepとoptimizer状態を含んで読み出せることを確認した。テスト14件もuv環境で成功。検証20ペア・warmup中の結果であり、コピー基準に対する改善や収束を示す結果ではない。

出力先：`/data2/yuki_sadasue/runs/foveated-world-models/stage1-robomind-pilot-20261112/`

- `train.log`：実行ログ
- `resolved_config.yaml`：実際のモデル・データ・Trainer設定
- `split_verification.json`：学習／検証の分離・件数・manifestハッシュ
- `run_summary.json`：実測時間・メモリ・最終メトリクス
- `checkpoint_verification.json`：100 stepのチェックポイント読み出し結果
- `checkpoints/final.ckpt`：最終重み・optimizer状態（約7.5 GiB）
