# KEIBA NOTE V5.4.11

競馬の収支・馬券・AI予想を管理する無料Webアプリです。

## V5.4.11の方針

今回のバージョンでは、JRAの自動取得をブラウザ側の必須機能にしない設計へ変更しました。

- レース情報は `data/jra-schedule.json` からのみ読み込みます。
- GitHub Pages / iPhoneのブラウザからJRA、Jina、無料プロキシへアクセスしません。
- JRAへのアクセス制限やプロキシ障害があっても、保存済みのレース情報でアプリを使用できます。
- GitHub Actionsは「保存済みJSONを更新するための保守処理」として分離しています。
- 更新に失敗しても既存の `data/jra-schedule.json` は削除・空化・上書きされません。
- 更新処理はJRA公式の各日番組表だけを使用します。
- 取得したデータは保存前にレース数・必須項目を検証します。
- Supabase、ログイン、収支データ、AI予想、バックアップ/復元の構造は変更していません。

## レース情報の流れ

```text
JRA公式各日番組表
        ↓
GitHub Actions（定期更新・手動実行）
        ↓
データ検証
        ↓
data/jra-schedule.json
        ↓
GitHub Pages
        ↓
KEIBA NOTE
```

GitHub Actionsが失敗しても、最後に正常だったJSONをそのまま使用します。

## GitHub Actions

Workflow：`.github/workflows/update-jra-schedule.yml`

- 毎週木曜日に自動実行
- GitHub Actions画面から手動実行も可能
- 更新対象は当日から14日先まで
- 新しい正常データが取得できた場合のみJSONを更新
- 正常なデータが1日も取得できない場合は既存JSONを変更しません

## データ形式

`data/jra-schedule.json` は次の情報を保持します。

- `date`
- `course`
- `race`
- `raceName`
- `raceCondition`
- `distance`
- `surface`
- `startTime`
- `raceKey`
- `meeting`

`raceKey` は `YYYY-MM-DD-競馬場-R` 形式です。

## 注意

JRAの各日番組表は予定情報です。JRA公式ページにも記載されているとおり、出馬投票や天候などによりレース順、馬場、距離、発走時刻、開催中止・延期などが変更される場合があります。実際の馬券購入時はJRAの最新情報を確認してください。

## AI予想

OpenAI APIなどの有料APIは使用しません。ChatGPTで作成した予想を手動登録・コピペ登録できます。
