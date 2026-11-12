# CSVコマンド

Python 3標準ライブラリのみ。ネットワーク接続もモデル起動も行わない。以下の`<skill-dir>`を実際のスキルディレクトリへ置換する。ホストが単独でマスターを更新する。

```sh
python3 <skill-dir>/scripts/survey_csv.py init surveys/topic
python3 <skill-dir>/scripts/survey_csv.py query surveys/topic/registry.csv --contains 'keyword' --columns paper_id,title,status --limit 20
python3 <skill-dir>/scripts/survey_csv.py query surveys/topic/registry.csv --where status=pending
python3 <skill-dir>/scripts/survey_csv.py duplicates surveys/topic/registry.csv
python3 <skill-dir>/scripts/survey_csv.py mark-duplicate surveys/topic/registry.csv --keep p001 --drop p002
python3 <skill-dir>/scripts/survey_csv.py plan surveys/topic/registry.csv --available-readers 3
python3 <skill-dir>/scripts/survey_csv.py validate surveys/topic/workers/assignment
python3 <skill-dir>/scripts/survey_csv.py merge surveys/topic/papers.csv surveys/topic/workers/assignment/papers.csv
python3 <skill-dir>/scripts/survey_csv.py merge surveys/topic/evidence.csv surveys/topic/workers/assignment/evidence.csv --key paper_id,field,item_index
python3 <skill-dir>/scripts/survey_csv.py validate surveys/topic
python3 <skill-dir>/scripts/survey_csv.py export surveys/topic
```

queryは本文を読む代わりに小さな台帳を照会。duplicatesは候補を報告するだけで削除しない。arXiv版番号・DOI接頭辞を正規化する。タイトル類似は必ずホスト判断。mark-duplicateは登録を消さずリンクを残す。

ホストが外部検索で見つけた情報は標準csvライブラリで追記し、更新前にhistoryへ保存する。引用先も同じ流れで登録。手作業の文字列連結はしない。既存の選定や手動編集を上書きしない。

planは割り当てを台帳に保存する変更操作。selected=true、未割り当て、candidate/pendingだけを対象とし、優先度順。対象数は--targetで上書き、モデルは--modelで今回だけ変更可能。環境の空き枠を--available-readersで渡す。出力JSONを割り当て記録として保存し、ホストが各waveを起動する。再実行は割り当て済みを飛ばすため、同じ調査の再開では既存assigned行を確認して未完了の割り当てを再利用する。新規バッチを追加して件数を超過しない。

mergeは完全一致の既存行を再利用し、同じキーで異なる内容は書き込み前に拒否する。更新はホストが差分を確認し旧結果をhistoryへ保存してから行う。papers/evidence両方を更新した後validateする。途中中断時はホストが両方の整合性を確認するまで完了としない。

検証は列・リスト・日付・状態・根拠の対応のみ。内容の真偽、根拠を実際に読んだか、採択の事実はホストレビューが必要。論文取得と一時ファイル削除はホスト/調査エージェントが行い、このスクリプトはユーザーの本文ファイルを削除しない。

planはassignments/<日時>.jsonにもモデル・wave・対象件数を保存する。再開時はregistryのassigned_toと照合し、対応するassigned行がない未確定マニフェストからエージェントを起動しない。台帳が割り当ての正本。validateはworkerではpapers/evidence、マスターでは存在する他のCSVも検査する。

exportはネットワークを使わず、検証済みのpapers/evidence/citationsをsurvey.csvへ結合する。入力CSVは変更しない。同一内容なら何もしない。出力と差がある場合は上書きを拒否するため、ホストが人手編集と入力差分を確認・反映した後だけ `export surveys/topic --replace-reviewed` を使う。置換前の出力はhistoryへ保存する。最終回答では原則この統合CSVを案内する。
