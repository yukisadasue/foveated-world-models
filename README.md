# Foveated World Models

中心視野・周辺視野を持つ潜在世界モデルの研究ノートと論文サーベイです。LaWAMを候補基盤として、背景の予測容易性、操作対象の細部、カメラ移動、計算速度を扱います。

**状態：研究構想・評価設計。提案手法の実装、実験結果、新規性の確立はまだありません。**

## 研究の問い

固定計算予算のもとで、操作に応じて中心視野を選択する潜在世界モデルは、一様な特徴予測よりも重要な状態変化を正確かつ高速に予測できるか？

- [研究アイデアと仮説](docs/research-plan.md)
- [実験計画・比較基準・判断条件](docs/experiments.md)
- [重点関連研究とLaWAMの構造](docs/related-work.md)
- **[統合論文サーベイ：111件](surveys/architecture/survey.csv)** — 原題、URL、公開日、背景、課題、手段、結果、貢献、残課題、根拠を1ファイルに収録。

研究の中心は予測器のアーキテクチャです。強化学習の学習則・報酬設計は研究対象にしません。実機なしで、既存の実世界動画による予測評価と、シミュレーションでの閉ループ制御評価から始めます。

## 調査の範囲

既存統合台帳は2026年11月11日以前のWAM・VLA・オーケストレーションを対象とした選定調査です。新規本文調査65件と既存同一版の調査46件を含み、網羅的な系統レビューではありません。2026年初公開85件、直近1年86件、期間外の基礎・直接関連23件、初公開日未確認2件です。後続の議論で追加した重点文献は関連研究ノートに記録し、この111件へ自動的に算入していません。

学会区分は公式確認済みと未確認を区別しています。実験結果の再現は未実施です。CSVのレビュー済み表示は文献抽出のレビューを指し、論文の主張を独立検証した意味ではありません。

## ファイル構成

- `docs/`：現在の研究方針と実験設計。
- `surveys/architecture/survey.csv`：閲覧用の統合台帳。
- `surveys/architecture/internal/`：更新・検証に必要な書誌情報、根拠、引用、重複判定台帳、検索・レビュー記録。通常の閲覧では開く必要はありません。
- `.agents/skills/paper-survey/`：調査手順、設定、CSV操作スクリプト。

旧LEWM・WAMのテーマ別調査と方針変更前のアイデア集は削除しました。現在の採用文献は統合サーベイ、研究アイデアは `docs/` を参照してください。削除した資料が必要な場合はGit履歴から確認できます。

論文PDF、HTML全文、一時作業ファイル、モデル重み、データセットはGitへ含めません。

## 台帳の検証

リポジトリのルートで実行します。

```sh
python3 .agents/skills/paper-survey/scripts/survey_csv.py validate surveys/architecture/internal
python3 .agents/skills/paper-survey/scripts/survey_csv.py duplicates surveys/architecture/internal/registry.csv
```

更新時の作業ディレクトリは `surveys/architecture/internal/` です。`export` は作業ディレクトリに `survey.csv` を出力するため、既存の閲覧用CSVを作業ディレクトリへコピーして差分保護を有効にし、変更内容を確認してから出力を `surveys/architecture/survey.csv` へ移動します。閲覧用CSVを2か所に残さないでください。

調査スキルの利用方法は [SKILL.md](.agents/skills/paper-survey/SKILL.md) を参照してください。
