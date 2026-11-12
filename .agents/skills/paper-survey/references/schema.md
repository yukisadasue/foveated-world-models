# CSV仕様

以下は内部作業CSVの仕様。閲覧用の標準納品物は末尾のsurvey.csv。

UTF-8、ヘッダー付き、1論文1行。Python標準csv等で引用符・改行・カンマを扱い、文字列連結でCSVを作らない。配列セルはJSON配列。8項目は空でない文字列の配列。IDはホストが付けた安定IDで、タイトル変更時も変えない。以下の英語列名を固定する。

## papers.csv

`paper_id,title,authors,keywords_author,keywords_survey,first_published,version,version_date,venue,venue_status,paper_url,fulltext_url,social_background,technical_background,problem,method,results,contributions,summary,remaining_issues,read_scope,status,review_status,reader_model,retrieved_at`

authors、keywords_author、keywords_surveyと8項目はJSON配列。キーワードの出所を混ぜない。日付は判明精度に応じYYYY / YYYY-MM / YYYY-MM-DD、未確認はunknown。初回公開日と版更新日を分け、学会名に採択を推測で付与しない。状態はpartial / fulltext_unavailable / extracted。review_statusはpending / changes_requested / reviewed。

8項目の意味:
- social_background: 社会的需要・現実の制約。著者が述べていなければ明示的記載なし。
- technical_background: 先行研究の到達点と技術的障害。
- problem: この論文で実際に解く範囲。
- method: 仕組み・データ・前提・学習/実行の手順。
- results: 実証されたこと、条件、比較、評価数。理論は成立条件。
- contributions: 先行研究へ追加した手法・知識・資料。著者の新規性主張と独立確認を区別。
- summary: 問題→手段→結果を簡潔につなぐ。新情報を足さない。
- remaining_issues: 著者が述べた限界と調査者の未検証指摘を明示的に分ける。

## evidence.csv

`paper_id,field,item_index,kind,source_url,locator,note`

item_indexはリストの1始まり。kindはauthor_claim / demonstrated / interpretation / not_stated / unverified / not_applicable。locatorに節・ページ・図表・式等を記録。意味のある全項目に根拠が必要。not_stated/not_applicableは確認範囲、unverifiedは理由をnoteに書く。根拠のない欠落マーカーにはURLや位置の捏造をしない。

## registry.csv

`paper_id,title,authors,arxiv_id,doi,semantic_scholar_id,paper_url,version,status,selected,priority,priority_reason,assigned_to,assignment_model,duplicate_of`

authorsはJSON配列。selectedはtrue/false。priorityは大きいほど優先する整数。statusはcandidate / pending / assigned / extracted / reviewed / partial / fulltext_unavailable / excluded。版は別論文にしないが、更新時は旧結果を履歴保存。重複側の行はduplicate_ofを埋めて保持し、出典を失わない。IDの衝突や異なる版の抽出内容を機械的に混ぜない。

## search_log.csv

`search_id,source,query,filters,searched_at,coverage,stop_reason`

ホストが実際に行った検索を記録。取得上限や未処理ページ、日付精度も明示。

## citations.csv

`citing_id,cited_id,cited_title,cited_url,locator,priority_reason,scope_status`

cited_idは未登録なら空でもよい。引用文脈と参考文献情報からホストが登録する。scope_statusはin_scope / foundational_outside_scope / unresolved。重要度は引用件数だけで決めない。

## 保存と履歴

各調査者はworkers/<assignment_id>/へ専用出力。マスターはホストだけが編集する。変更時にはhistoryへ旧CSVをコピーする。補助プログラムのmergeは既存キーが異なれば拒否するため、手動編集は消えない。更新時はホストが差分確認して根拠と一緒に修正する。既存スキーマと異なる追加列は勝手に削除しない。

retrieved_atは本文取得日時のISO 8601。抽出完了行ではversion・version_date・fulltext_url・retrieved_atが必要。版番号のない著者資料は日付や内容ハッシュで版を識別する。assignment_modelは割り当て時の実行予定モデルを永続化し、reader_modelには実際に使用したモデルを記録する。

## survey.csv（標準納品物）

1論文1行、UTF-8 BOM付き、日本語の列名。papers.csvの全列と、各項目の番号・種別・URL・位置・注記を含む「根拠」、citations.csvの全引用情報を含む「重要な引用先」を結合する。配列はセル内の番号付き改行リストへ表示変換する。状態・版・初回公開日・確認範囲も保持するため、未確認内容が完了と見えない。検索ログと割り当て台帳は内部資料として保存する。

ホストは内部CSVの整合性を検証してからexportする。survey.csvを読むだけで内容と根拠を確認できることを納品条件とする。人手で修正された閲覧用CSVと差がある場合、まず変更を内部CSVへ反映するか差分を確認し、その後再生成する。既存出力はhistoryへ退避する。
