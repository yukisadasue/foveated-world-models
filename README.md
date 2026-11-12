# Foveated World Models

**中心・周辺視野によって、LaWAMのStage 1で学習する潜在行動表現と未来特徴予測を改善する研究です。**

静止背景が多い映像では、現在の特徴をコピーするだけでも全体の予測誤差が小さくなり、操作対象や接触部の予測失敗が隠れる可能性があります。この仮説を検証し、周辺視野で場面全体を保持しながら、中心視野で対象物・指先・接触周辺を高精細に扱う構造を研究します。

**状態：公式Stage 1の最小実行構成を追加。中心・周辺視野の提案手法と実データ実験は未実施で、有効性と新規性は未確立です。**

[Stage 1のセットアップと実行手順](docs/stage1-setup.md) — 固定した公式コード、ローカルDINOv3 ViT-B/16、画像ペアのデータ形式、学習・再開コマンド。

## 研究の問い

固定計算予算のもとで、中心・周辺視野を持つIDM・LaWMは、基準のStage 1よりも操作に重要な局所変化を正確に表現・予測できるか？

背景と動的成分の分離は「何を別々にモデル化するか」、中心・周辺視野は「どこを詳しく表現するか」という設計です。静止している目標も操作には重要なため、単純に動く場所だけを中心視野にするとは限りません。

## 対象：LaWAMのStage 1

| 構成 | 役割 |
|---|---|
| 凍結DINOv3 | 現在・未来画像を空間的な視覚特徴に変換する |
| IDM | 現在・未来特徴から、変化を説明する潜在行動 z を推定する |
| LaWM | 現在特徴と z から未来特徴を予測する |
| 補助状態予測器 | 現在の手先状態と z から未来の手先状態を予測する |

IDMとLaWMは同時に学習します。基準の学習信号は、未来DINO特徴のMSE、補助手先状態のMSE、潜在行動のKL正則化です。視覚予測の対象はRGB画素ではなくDINO特徴です。

Stage 1ではIDMが正解未来を見るため、主評価は**未来由来のzを条件とした予測能力**です。現在観測だけから未来を選ぶ能力とは区別します。Stage 2のPolicy Prior・Action Expertの改良や閉ループ制御は、今回の研究範囲に含めません。

## 検証の進め方

1. **基準の診断**：現在特徴のコピーと比較し、背景・物体・手先・接触周辺の誤差、予測変化量、zへの依存を測る。
2. **中心・周辺視野の比較**：損失重み付け、固定crop、一様な高解像度と比較する。まずLaWM側、次にIDM側と共同学習の寄与を切り分ける。
3. **表現・汎化・費用の評価**：zの運動情報、未見背景・物体・視点での局所予測、ROI選択を含む計算費用を測る。

背景への偏りや「静的な崩壊」は未検証の仮説です。基準Stage 1の補助状態損失を含めて診断し、同じ未来特徴を評価対象として比較します。

## 研究資料

| 資料 | 内容 |
|---|---|
| [研究計画](docs/research-plan.md) | 仮説、候補構造、情報の利用条件、目指す貢献 |
| [実験計画](docs/experiments.md) | 基準、比較実験、評価指標、進む・見直す判断 |
| [重点関連研究](docs/related-work.md) | LaWAM Stage 1の詳細と、情報分離・中心視野に関する先行研究 |
| [統合論文サーベイ](surveys/architecture/survey.csv) | 既存の広範な文献調査111件 |

統合サーベイは2026年11月11日以前のWAM・VLAなどを対象とする選定調査で、現在のStage 1研究の採用文献だけを集めたものではありません。追加の重点文献は関連研究ノートを参照してください。CSVのレビュー済み表示は文献抽出の確認を意味し、論文の実験結果を独立再現したものではありません。

## ファイル構成

- `docs/`：現在の研究方針・実験設計・セットアップ手順。
- `vendor/lawam/`：公式Stage 1の必要な12ファイルと取得元・ハッシュ。
- `train_stage1.py`、`vendor/dataset/`：ローカルデータ用の起動・読み込み処理。
- `configs/`：公開コード準拠の基準設定と小型の動作確認設定。
- `tests/`：データ契約と学習・保存・再開の検査。
- `surveys/architecture/survey.csv`：閲覧用の統合台帳。
- `surveys/architecture/internal/`：更新・検証に必要な書誌情報、根拠、引用、重複判定台帳、検索・レビュー記録。通常の閲覧では開く必要はありません。
- `.agents/skills/paper-survey/`：調査手順、設定、CSV操作スクリプト。

研究方針は `docs/`、既存の広範な文献調査は統合サーベイを参照してください。重点関連研究ノートに追加した文献は、統合CSVへ自動的には追加していません。

論文PDF、HTML全文、一時作業ファイル、モデル重み、データセットはGitへ含めません。

## 台帳の検証

リポジトリのルートで実行します。

```sh
python3 .agents/skills/paper-survey/scripts/survey_csv.py validate surveys/architecture/internal
python3 .agents/skills/paper-survey/scripts/survey_csv.py duplicates surveys/architecture/internal/registry.csv
```

更新時の作業ディレクトリは `surveys/architecture/internal/` です。`export` は作業ディレクトリに `survey.csv` を出力するため、既存の閲覧用CSVを作業ディレクトリへコピーして差分保護を有効にし、変更内容を確認してから出力を `surveys/architecture/survey.csv` へ移動します。閲覧用CSVを2か所に残さないでください。

調査スキルの利用方法は [SKILL.md](.agents/skills/paper-survey/SKILL.md) を参照してください。

## 実データの選定

[Traly/RoboMIND-lerobot](https://huggingface.co/datasets/Traly/RoboMIND-lerobot) の `franka_fr3_dual` を採用する。俯瞰映像 `camera_top`、左右の手先位置・姿勢、関節状態、グリッパー状態を使う。LeRobot v3.0、30fps、1,774エピソード・6タスク。俯瞰映像・状態・メタデータは合計約10.66GB。

配布された `timestamp` を時間の基準として信用する。フレーム番号の固定幅加算や `FPS × 1.2` によるペア抽出は禁止する。元の収録時刻であることは要求しない。採用した時刻から1.2秒先の最近傍を選び、末尾は1.2秒未満でも最終観測を使う。欠損が0.3秒以上なら区間を分割し、それ未満は直前値で補完する。区間の両端は全項目の実観測がそろう位置にそろえる。共通処理は `vendor/dataset/temporal_data.py` に保持している。

取得先は `/data2/yuki_sadasue/datasets/RoboMIND-lerobot/`。リビジョン `71d7062c0e60351606674a55f51066454be7296d` の対象75ファイル（10,664,394,285 bytes）の取得が完了した。俯瞰動画68本、1,774エピソード、375,807フレーム。全ファイルのサイズ、動画ヘッダーの30fps・解像度・総フレーム数、全状態の有限性、各エピソード内timestampの単調増加を検証済み。結果は取得先の `verification.json` に保存している。RoboMIND用前処理・学習ローダーを `vendor/dataset/` に実装した。前処理で全動画をデコードし、`configs/stage1_robomind.yaml` で学習に接続する。

データセット関連の実装は [`vendor/dataset/`](vendor/dataset/README.md) にまとめる。取得は `download_robomind.py`、取得後の検査は `verify_robomind.py` で再実行できる。

学習環境は `uv sync --locked` で構築する。テスト学習・本学習・再開のコマンドは [Stage 1セットアップ](docs/stage1-setup.md) を参照。テスト用の `configs/stage1_robomind_pilot.yaml` は本サイズモデルで100 stepに限定する。
