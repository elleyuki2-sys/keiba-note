# KEIBA NOTE V5.4.3

V5.2.1をベースに、収支入力とスマホUIを改善した版です。

## 今回の変更
- 収支記録に「馬番」入力欄を追加。例：`8` / `5-8` / `1-3-7`
- 1レースで「＋ 馬券を追加」して複数馬券を一括登録可能
- 既存の収支データは従来どおり1馬券=1レコードで保持し、分析・集計ロジックを壊さない設計
- iPhone Safariの入力フォーカスによる自動拡大を抑制
- AI予想の詳細・統計・履歴を初期状態では非表示。必要な時だけ「詳細を表示」
- 画面左下/スマホ右下の「☰ メニュー」から各セクションへジャンプ
- Supabase `keiba_records` に `horses` 列を追加

## Supabase
V5.4.2では `supabase.sql` に既存テーブル向けの `horses` 列追加SQLが含まれています。
既存のV5.2環境でもこのSQLを1回実行してください。

## AI予想
OpenAI APIは使用しません。ChatGPTで作成した予想を手動登録・コピペ登録できます。


## V5.4.2 競馬場・レース自動選択（無料ベース）
- 日付を選ぶと、JRA公式の各日番組表を元に開催中の競馬場だけを自動表示。
- 競馬場を選ぶと、レース番号・レース名/条件・距離・芝/ダ・発走時刻を自動表示。
- 収支データに race_name / race_condition / distance / surface / start_time / race_key / meeting を保存。
- JRA公式ページの内容を読み取るため、GitHub Pagesからの取得には無料・APIキー不要の `r.jina.ai` テキストプロキシを利用。JRA公式ページへのリンクも表示。
- プロキシ障害時は自動取得できないため、JRA公式番組を開いて確認できるフェイルセーフを用意。
- Supabase利用時は `supabase.sql` をもう一度実行してV5.4.2の列を追加する。既存データは保持される。

※JRAの各日番組表は予定情報であり、出馬投票・天候などによりレース順、馬場、距離、発走時刻、開催中止等が変更される場合があります。実際の投票記録ではJRAの最新情報も確認してください。


## V5.4.3 競馬場・レース情報の高速化
- ブラウザからJRAを毎回プロキシ経由で読む方式をやめ、GitHub Pages内の `data/jra-schedule.json` を最優先で読み込む方式に変更。通常はほぼ即時表示。
- GitHub Actions (`.github/workflows/update-jra-schedule.yml`) が毎日JRA公式の各日番組表を取得し、過去7日～未来30日のスケジュールJSONを更新。手動実行も可能。
- ローカルJSONにまだ存在しない日付だけ、無料オンライン取得を短時間だけ試行。複数プロキシを並列化し、長時間待たない設計。
- 2026-09-12 / 2026-09-13 の初期データを同梱。
- Supabaseの収支データ構造は変更なし。追加SQLは不要。

### GitHub Actionsについて
GitHubへV5.4.3をアップロードした後、Actionsタブの `Update JRA schedule` から `Run workflow` を1回実行すると、その時点の番組データをすぐ更新できます。以後は毎日自動更新されます。

※JRAの各日番組表は予定情報です。最新の出馬表でレース順、馬場、距離、発走時刻等が変更される場合があります。


## V5.4.7 diagnostic note
- Jina Reader HTTP content is now logged in a bounded excerpt when the parser finds 0 races.
- This release is for identifying the actual Jina response format before finalizing the parser.
- Existing `data/jra-schedule.json` is still protected from overwrite when 0 races are fetched.
